"""Tests for the fetcher — no real network (CLAUDE.md); scrapling is faked."""

from types import SimpleNamespace
from typing import Any

import pytest
from curl_cffi.curl import CurlError

from backend.scraper import fetcher as fetcher_module
from backend.scraper.fetcher import FetchError, Page, PageFetcher


def ok_response(text: str = "page text", raw: bytes = b"<html>raw</html>") -> SimpleNamespace:
    return SimpleNamespace(status=200, get_all_text=lambda **kwargs: text, body=raw)


def status_response(status: int) -> SimpleNamespace:
    return SimpleNamespace(status=status, get_all_text=lambda **kwargs: "", body=b"")


@pytest.fixture
def fetcher(monkeypatch: pytest.MonkeyPatch) -> PageFetcher:
    instance = PageFetcher(delay_s=0.5, retries=1)
    monkeypatch.setattr(instance, "_allowed_by_robots", lambda url: True)
    return instance


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    recorded: list[float] = []
    monkeypatch.setattr(fetcher_module.time, "sleep", recorded.append)
    return recorded


def script_get(monkeypatch: pytest.MonkeyPatch, outcomes: list[Any]) -> list[dict[str, Any]]:
    """Make ScraplingFetcher.get return/raise the queued outcomes in order."""
    calls: list[dict[str, Any]] = []

    def fake_get(url: str, **kwargs: Any) -> Any:
        calls.append({"url": url, **kwargs})
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(fetcher_module.ScraplingFetcher, "get", staticmethod(fake_get))
    return calls


def test_fetch_returns_page_with_text(
    fetcher: PageFetcher, sleeps: list[float], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = script_get(monkeypatch, [ok_response("hello world", raw=b'{"a": 1}')])
    page = fetcher.fetch("https://x.com/a")
    assert page == Page(url="https://x.com/a", markdown="hello world", raw='{"a": 1}')
    assert calls[0]["headers"]["User-Agent"]  # honest UA sent
    assert sleeps == []


def test_timeout_then_retry_succeeds(
    fetcher: PageFetcher, sleeps: list[float], monkeypatch: pytest.MonkeyPatch
) -> None:
    script_get(monkeypatch, [CurlError("timeout"), ok_response()])
    assert fetcher.fetch("https://x.com/a").markdown == "page text"
    assert sleeps == [0.5]


def test_timeout_twice_raises_fetch_error(
    fetcher: PageFetcher, sleeps: list[float], monkeypatch: pytest.MonkeyPatch
) -> None:
    script_get(monkeypatch, [CurlError("timeout"), CurlError("timeout")])
    with pytest.raises(FetchError, match="timeout"):
        fetcher.fetch("https://x.com/a")


def test_5xx_then_success_retries(
    fetcher: PageFetcher, sleeps: list[float], monkeypatch: pytest.MonkeyPatch
) -> None:
    script_get(monkeypatch, [status_response(503), ok_response()])
    assert fetcher.fetch("https://x.com/a").markdown == "page text"
    assert sleeps == [0.5]


def test_429_backs_off_longer(
    fetcher: PageFetcher, sleeps: list[float], monkeypatch: pytest.MonkeyPatch
) -> None:
    script_get(monkeypatch, [status_response(429), ok_response()])
    assert fetcher.fetch("https://x.com/a").markdown == "page text"
    assert sleeps == [2.0]  # 4 x delay_s


def test_other_non_200_fails_immediately(
    fetcher: PageFetcher, sleeps: list[float], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = script_get(monkeypatch, [status_response(404)])
    with pytest.raises(FetchError, match="HTTP 404"):
        fetcher.fetch("https://x.com/a")
    assert len(calls) == 1
    assert sleeps == []


def test_robots_disallowed_never_fetches(
    sleeps: list[float], monkeypatch: pytest.MonkeyPatch
) -> None:
    instance = PageFetcher()
    monkeypatch.setattr(instance, "_allowed_by_robots", lambda url: False)
    calls = script_get(monkeypatch, [])
    with pytest.raises(FetchError, match="robots.txt"):
        instance.fetch("https://x.com/private")
    assert calls == []


def test_robots_parser_cached_per_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    instance = PageFetcher()
    reads: list[str] = []

    def fake_read(self: Any) -> None:
        reads.append(self.url)

    monkeypatch.setattr(fetcher_module.RobotFileParser, "read", fake_read)
    monkeypatch.setattr(fetcher_module.RobotFileParser, "can_fetch", lambda self, agent, url: True)
    assert instance._allowed_by_robots("https://x.com/a")
    assert instance._allowed_by_robots("https://x.com/b")
    assert instance._allowed_by_robots("https://y.com/c")
    assert len(reads) == 2  # one robots.txt read per domain
