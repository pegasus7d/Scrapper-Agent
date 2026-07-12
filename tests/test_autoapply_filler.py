"""Tests for the Playwright-driven form fill-and-submit spike (PHASE10.md
step 1). A real, live HTTP server (uvicorn in a background thread) serving
the real `test_form_server` app, driven by a real headless-Chromium
browser — Playwright needs a genuine socket, not an ASGI TestClient, so
this suite is deliberately real end-to-end, not mocked."""

import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import Browser, Page, sync_playwright

from backend.autoapply import filler, test_form_server

_PORT = 8923
_URL = f"http://127.0.0.1:{_PORT}"


@pytest.fixture(scope="module")
def live_form_server() -> Iterator[None]:
    config = uvicorn.Config(test_form_server.app, host="127.0.0.1", port=_PORT, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.1)
    else:
        raise RuntimeError("test form server did not start in time")
    yield
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture
def page(browser: Browser, live_form_server: None) -> Iterator[Page]:
    p = browser.new_page()
    yield p
    p.close()


@pytest.fixture
def resume_file(tmp_path: Path, resume_pdf_bytes: bytes) -> Path:
    path = tmp_path / "resume-backend.pdf"
    path.write_bytes(resume_pdf_bytes)
    return path


def test_detect_fields_finds_real_fields_with_ax_confirmed_labels(page: Page) -> None:
    page.goto(_URL)
    fields = filler.detect_fields(page)
    by_name = {f.name: f for f in fields}
    assert set(by_name) == {
        "full_name",
        "email",
        "phone",
        "role",
        "resume",
        "cover_note",
        "relocate",
        "remote_ok",
    }
    assert by_name["full_name"].label == "Full name"
    assert by_name["full_name"].confirmed_by_ax_tree is True
    assert by_name["email"].input_type == "email"
    assert by_name["role"].tag == "select"
    assert by_name["resume"].input_type == "file"
    assert by_name["cover_note"].tag == "textarea"
    assert by_name["remote_ok"].input_type == "checkbox"


def test_detect_fields_collapses_a_radio_group_into_one_field_with_options(page: Page) -> None:
    page.goto(_URL)
    fields = filler.detect_fields(page)
    relocate = next(f for f in fields if f.name == "relocate")
    assert relocate.input_type == "radio"
    assert relocate.options == ["Yes", "No"]


def test_detect_fields_works_on_a_page_with_no_form_element(page: Page) -> None:
    """Real bug found live (PHASE13.md step 4): a real Ashby application
    page has no <form> at all, which made the old `page.locator("form")`
    snapshot hang for the full 30s timeout. `test_form_server`'s
    ashby-like route reproduces that exact shape (its field is inserted
    by a delayed script, the same real client-rendering behavior step
    5 found separately — waited for here since this test is about the
    no-<form> fix specifically, not that timing fix)."""
    page.goto(f"{_URL}/ashby-like/1/application")
    page.wait_for_selector('[name="_systemfield_name"]')
    fields = filler.detect_fields(page)
    assert len(fields) == 1
    assert fields[0].name == "_systemfield_name"
    assert fields[0].label == "Legal Name"


def test_fill_and_submit_real_happy_path(page: Page, resume_file: Path) -> None:
    text_values = {
        "full_name": "Ada Lovelace",
        "email": "ada@example.com",
        "phone": "555-0100",
        "role": "backend",
        "cover_note": "Real test submission.",
        "relocate": "Yes",  # matches the radio option's real resolved label
        "remote_ok": "true",
    }
    result = filler.fill_and_submit(page, _URL, text_values, {"resume": str(resume_file)})
    assert result.success is True
    assert "confirmed" in result.reason

    # Real confirmation page content, not just a 200 — echoed back by the
    # server, read back out of the real rendered page.
    assert page.locator("#received-full_name").inner_text() == "Ada Lovelace"
    assert page.locator("#received-email").inner_text() == "ada@example.com"
    assert page.locator("#received-phone").inner_text() == "555-0100"
    assert page.locator("#received-role").inner_text() == "backend"
    assert page.locator("#received-cover_note").inner_text() == "Real test submission."
    assert page.locator("#received-relocate").inner_text() == "yes"  # the real HTML value=
    assert page.locator("#received-remote_ok").inner_text() == "True"
    assert page.locator("#received-resume_filename").inner_text() == "resume-backend.pdf"
    assert int(page.locator("#received-resume_size_bytes").inner_text()) > 0


def test_fill_field_selects_a_radio_option_by_its_real_label(page: Page) -> None:
    page.goto(_URL)
    fields = filler.detect_fields(page)
    relocate = next(f for f in fields if f.name == "relocate")
    result = filler.fill_field(page, relocate, "No")
    assert result.success is True
    assert page.locator('[name="relocate"][value="no"]').is_checked()
    assert not page.locator('[name="relocate"][value="yes"]').is_checked()


def test_fill_field_reports_failure_for_an_unmatched_radio_option(page: Page) -> None:
    page.goto(_URL)
    fields = filler.detect_fields(page)
    relocate = next(f for f in fields if f.name == "relocate")
    result = filler.fill_field(page, relocate, "Maybe")
    assert result.success is False
    assert "no radio option matching" in (result.error or "")


def test_fill_field_sets_a_checkbox_from_a_truthy_or_falsy_value(page: Page) -> None:
    page.goto(_URL)
    fields = filler.detect_fields(page)
    remote_ok = next(f for f in fields if f.name == "remote_ok")

    assert filler.fill_field(page, remote_ok, "true").success is True
    assert page.locator('[name="remote_ok"]').is_checked()

    assert filler.fill_field(page, remote_ok, "false").success is True
    assert not page.locator('[name="remote_ok"]').is_checked()


def test_fill_and_submit_is_not_flaky_across_repeated_runs(
    browser: Browser, live_form_server: None, resume_file: Path
) -> None:
    """Re-runs the real happy path a few times (PHASE10.md step 1's own
    smoke-test requirement) against fresh pages each time."""
    for _ in range(3):
        p = browser.new_page()
        try:
            result = filler.fill_and_submit(
                p,
                _URL,
                {
                    "full_name": "Grace Hopper",
                    "email": "grace@example.com",
                    "role": "fullstack",
                },
                {"resume": str(resume_file)},
            )
            assert result.success is True
        finally:
            p.close()


def test_fill_and_submit_reports_failure_for_an_unreachable_url(page: Page) -> None:
    result = filler.fill_and_submit(page, "http://127.0.0.1:1", {"full_name": "X"}, {})
    assert result.success is False
    assert "failed to load form" in result.reason


def test_fill_and_submit_detects_a_confirmation_via_a_real_url_redirect(page: Page) -> None:
    """PHASE14.md step 3 -- proves the heuristic generalizes past the
    original `id="confirmation"` fixture: Greenhouse/Lever's real shape
    is a redirect to a distinct URL with no special id or phrase at
    all (researched via their own docs, not assumed)."""
    result = filler.fill_and_submit(page, f"{_URL}/redirect-form", {"full_name": "X"}, {})
    assert result.success is True
    assert "confirmed" in result.reason
    assert page.url == f"{_URL}/redirect-thanks"
    assert page.locator("#confirmation").count() == 0


def test_fill_and_submit_detects_a_confirmation_via_a_real_phrase_no_navigation(
    page: Page,
) -> None:
    """Ashby's real shape -- a client-rendered SPA with no URL change at
    all, just a real confirmation phrase swapped into the DOM."""
    result = filler.fill_and_submit(page, f"{_URL}/phrase-form", {"full_name": "X"}, {})
    assert result.success is True
    assert "confirmed" in result.reason
    assert page.url == f"{_URL}/phrase-form"
    assert page.locator("#confirmation").count() == 0
    assert "thank you for applying" in page.locator("body").inner_text().lower()


def test_fill_and_submit_reports_failure_when_no_confirmation_signal_ever_appears(
    page: Page,
) -> None:
    """Negative path: a submit that changes nothing (no URL change, no
    phrase, submit button still present) must not be reported as a
    success just because no exception was raised."""
    result = filler.fill_and_submit(page, f"{_URL}/stuck-form", {"full_name": "X"}, {})
    assert result.success is False
    assert "no confirmation signal" in result.reason


def test_detect_and_fill_fills_but_never_submits(page: Page, resume_file: Path) -> None:
    """PHASE10.md step 8's real constraint made structural: detect_and_fill
    fills real fields but has no code path that can click submit — the
    page must still show the unsubmitted form afterward, not the
    confirmation page fill_and_submit reaches."""
    text_values = {
        "full_name": "Ada Lovelace",
        "email": "ada@example.com",
        "phone": "555-0100",
        "role": "backend",
        "cover_note": "Real test fill, never submitted.",
    }
    result = filler.detect_and_fill(page, _URL, text_values, {"resume": str(resume_file)})

    assert set(result.filled) == {"full_name", "email", "phone", "role", "cover_note", "resume"}
    assert result.failed == []
    # The real page state: still the unsubmitted form, values genuinely
    # present in the real DOM — not the confirmation page.
    assert page.locator("#confirmation").count() == 0
    assert page.locator('[name="full_name"]').input_value() == "Ada Lovelace"
    assert page.locator('[name="email"]').input_value() == "ada@example.com"
