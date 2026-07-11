"""Tests for provider-specific page preparation (PHASE11.md step 2) — a
real, live HTTP server (uvicorn in a background thread) serving the real
test_form_server app's Greenhouse-like/Lever-like simulated routes, driven
by a real headless-Chromium browser. Real live Greenhouse/Lever pages
themselves are never touched by the permanent test suite (PHASE10.md
step 8's own precedent) — only a one-time smoke test does that.
"""

import threading
import time
from collections.abc import Iterator

import pytest
import uvicorn
from playwright.sync_api import Browser, Page, sync_playwright

from backend.autoapply import providers, test_form_server

_PORT = 8924
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


def test_lever_navigates_to_the_real_apply_url(page: Page) -> None:
    providers.prepare_application_page(page, "lever", f"{_URL}/lever-like/123")
    assert page.url == f"{_URL}/lever-like/123/apply"
    assert page.locator('[name="name"]').count() == 1


def test_greenhouse_clicks_apply_and_reveals_the_real_form(page: Page) -> None:
    providers.prepare_application_page(page, "greenhouse", f"{_URL}/greenhouse-like")
    assert page.url == f"{_URL}/greenhouse-like"
    assert page.locator('[name="first_name"]').is_visible()


def test_unknown_provider_raises_without_navigating(page: Page) -> None:
    with pytest.raises(providers.UnknownProvider):
        providers.prepare_application_page(page, "workday", f"{_URL}/greenhouse-like")
    assert page.url == "about:blank"  # never navigated anywhere


def test_greenhouse_without_a_real_apply_button_raises(page: Page) -> None:
    page.goto(f"{_URL}/lever-like/123")  # a real page with no Apply button at all
    with pytest.raises(providers.PagePreparationFailed):
        providers._click_greenhouse_apply(page)


def test_ashby_navigates_to_the_real_application_url(page: Page) -> None:
    providers.prepare_application_page(page, "ashby", f"{_URL}/ashby-like/123")
    assert page.url == f"{_URL}/ashby-like/123/application"
    assert page.locator('[name="_systemfield_name"]').count() == 1
    assert page.locator("form").count() == 0  # the real quirk this simulates
