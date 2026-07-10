"""Tests for the Transport implementations — no real network (CLAUDE.md)."""

from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from playwright.sync_api import Error as PlaywrightError

from backend.scraper import transport as transport_module
from backend.scraper.transport import HttpxTransport, ScraplingTransport, TransportError


def test_httpx_transport_returns_response(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url: str, *, timeout: int, headers: dict[str, str]) -> httpx.Response:
        return httpx.Response(200, content=b'{"a": 1}')

    monkeypatch.setattr(transport_module.httpx, "get", fake_get)
    response = HttpxTransport().get("https://x.com/a", timeout=10, headers={"User-Agent": "x"})
    assert response.status == 200
    assert response.body == b'{"a": 1}'
    assert response.text == ""  # no cleaning — no current source reads Page.markdown


def test_httpx_transport_wraps_network_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url: str, *, timeout: int, headers: dict[str, str]) -> httpx.Response:
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(transport_module.httpx, "get", fake_get)
    with pytest.raises(TransportError, match="refused"):
        HttpxTransport().get("https://x.com/a", timeout=10, headers={})


def test_scrapling_transport_returns_response(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_response = SimpleNamespace(
        status=200, body=b"<html>hi</html>", get_all_text=lambda **kwargs: "hi"
    )
    monkeypatch.setattr(
        transport_module.DynamicFetcher,
        "fetch",
        staticmethod(lambda url, **kwargs: fake_response),
    )
    response = ScraplingTransport().get("https://x.com/a", timeout=10, headers={})
    assert response.status == 200
    assert response.body == b"<html>hi</html>"
    assert response.text == "hi"


def test_scrapling_transport_passes_timeout_in_milliseconds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    def fake_fetch(url: str, **kwargs: Any) -> Any:
        seen.update(kwargs)
        return SimpleNamespace(status=200, body=b"", get_all_text=lambda **kw: "")

    monkeypatch.setattr(transport_module.DynamicFetcher, "fetch", staticmethod(fake_fetch))
    ScraplingTransport().get("https://x.com/a", timeout=10, headers={})
    assert seen["timeout"] == 10_000


def test_scrapling_transport_wraps_playwright_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_fetch(url: str, **kwargs: Any) -> Any:
        raise PlaywrightError("timeout")

    monkeypatch.setattr(transport_module.DynamicFetcher, "fetch", staticmethod(fake_fetch))
    with pytest.raises(TransportError, match="timeout"):
        ScraplingTransport().get("https://x.com/a", timeout=10, headers={})


def test_scrapling_transport_defaults_to_no_scroll_action(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_fetch(url: str, **kwargs: Any) -> Any:
        seen.update(kwargs)
        return SimpleNamespace(status=200, body=b"", get_all_text=lambda **kw: "")

    monkeypatch.setattr(transport_module.DynamicFetcher, "fetch", staticmethod(fake_fetch))
    ScraplingTransport().get("https://x.com/a", timeout=10, headers={})
    assert seen["page_action"] is None


def test_scrapling_transport_scroll_action_scrolls_the_real_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    def fake_fetch(url: str, **kwargs: Any) -> Any:
        seen.update(kwargs)
        return SimpleNamespace(status=200, body=b"", get_all_text=lambda **kw: "")

    monkeypatch.setattr(transport_module.DynamicFetcher, "fetch", staticmethod(fake_fetch))
    ScraplingTransport(scroll_count=3).get("https://x.com/a", timeout=10, headers={})

    wheel_calls = []
    fake_page = SimpleNamespace(
        mouse=SimpleNamespace(wheel=lambda x, y: wheel_calls.append((x, y))),
        wait_for_timeout=lambda ms: None,
    )
    seen["page_action"](fake_page)
    assert len(wheel_calls) == 3
