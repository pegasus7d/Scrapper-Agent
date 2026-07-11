"""Tests for the field-detection cache (PHASE12.md step 2). The DB
read/write half is pure (in-memory SQLite, no Playwright); the
`fields_resolve_on_page` half needs a real Page, reusing test_autoapply_
filler.py's exact real-local-server-plus-real-browser pattern — Playwright
needs a genuine socket, not a mock."""

import threading
import time
from collections.abc import Iterator

import pytest
import uvicorn
from playwright.sync_api import Browser, Page, sync_playwright
from sqlalchemy.orm import Session

from backend.autoapply import field_cache, test_form_server
from backend.autoapply.filler_types import DetectedField
from backend.db import repo

_PORT = 8926
_URL = f"http://127.0.0.1:{_PORT}"


@pytest.fixture
def session() -> Session:
    engine = repo.make_engine("sqlite:///:memory:")
    return Session(engine)


def _field(name: str = "full_name", selector: str = '[name="full_name"]') -> DetectedField:
    return DetectedField(
        name=name,
        tag="input",
        input_type="text",
        label="Full name",
        confirmed_by_ax_tree=True,
        selector=selector,
    )


def test_get_cached_fields_returns_none_when_no_row(session: Session) -> None:
    assert field_cache.get_cached_fields(session, "lever", company_id=1) is None


def test_save_then_get_round_trips(session: Session) -> None:
    field_cache.save_cached_fields(session, "lever", company_id=1, fields=[_field()])
    cached = field_cache.get_cached_fields(session, "lever", company_id=1)
    assert cached == [_field()]


def test_get_cached_fields_scoped_to_ats_provider(session: Session) -> None:
    field_cache.save_cached_fields(session, "lever", company_id=1, fields=[_field()])
    assert field_cache.get_cached_fields(session, "greenhouse", company_id=1) is None


def test_save_cached_fields_overwrites_the_existing_row_for_the_same_company(
    session: Session,
) -> None:
    field_cache.save_cached_fields(session, "lever", company_id=1, fields=[_field()])
    field_cache.save_cached_fields(
        session, "lever", company_id=1, fields=[_field(name="email", selector='[name="email"]')]
    )
    cached = field_cache.get_cached_fields(session, "lever", company_id=1)
    assert cached is not None
    assert [f.name for f in cached] == ["email"]


def test_save_cached_fields_keeps_separate_rows_per_company(session: Session) -> None:
    field_cache.save_cached_fields(session, "lever", company_id=1, fields=[_field()])
    field_cache.save_cached_fields(
        session, "lever", company_id=2, fields=[_field(name="email", selector='[name="email"]')]
    )
    assert [f.name for f in field_cache.get_cached_fields(session, "lever", 1) or []] == [
        "full_name"
    ]
    assert [f.name for f in field_cache.get_cached_fields(session, "lever", 2) or []] == ["email"]


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
    p.goto(_URL)
    yield p
    p.close()


def test_fields_resolve_on_page_true_when_every_selector_matches(page: Page) -> None:
    fields = [_field(), _field(name="email", selector='[name="email"]')]
    assert field_cache.fields_resolve_on_page(page, fields) is True


def test_fields_resolve_on_page_false_when_a_selector_is_missing(page: Page) -> None:
    fields = [_field(), _field(name="ssn", selector='[name="ssn"]')]
    assert field_cache.fields_resolve_on_page(page, fields) is False
