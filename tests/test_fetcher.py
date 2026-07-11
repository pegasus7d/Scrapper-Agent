"""Tests for the fetcher — no real network (CLAUDE.md); Transport is faked."""

from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

from backend.scraper import fetcher as fetcher_module
from backend.scraper.fetcher import FetchError, Page, PageFetcher, RobotsDisallowed
from backend.scraper.transport import TransportError, TransportResponse


class FakeTransport:
    """Returns/raises scripted outcomes per call, in order; records every call."""

    def __init__(self, outcomes: list[Any]) -> None:
        self._outcomes = outcomes
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, *, timeout: int, headers: dict[str, str]) -> TransportResponse:
        self.calls.append({"url": url, "timeout": timeout, "headers": headers})
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def ok_response(text: str = "page text", raw: bytes = b"<html>raw</html>") -> TransportResponse:
    return TransportResponse(status=200, body=raw, text=text)


def status_response(status: int) -> TransportResponse:
    return TransportResponse(status=status, body=b"", text="")


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    recorded: list[float] = []
    monkeypatch.setattr(fetcher_module.time, "sleep", recorded.append)
    return recorded


def make_fetcher(
    monkeypatch: pytest.MonkeyPatch, outcomes: list[Any]
) -> tuple[PageFetcher, FakeTransport]:
    transport = FakeTransport(outcomes)
    instance = PageFetcher(transport=transport, delay_s=0.5, retries=1)
    monkeypatch.setattr(instance, "_allowed_by_robots", lambda url: True)
    return instance, transport


def test_fetch_returns_page_with_text(sleeps: list[float], monkeypatch: pytest.MonkeyPatch) -> None:
    instance, transport = make_fetcher(monkeypatch, [ok_response("hello world", raw=b'{"a": 1}')])
    page = instance.fetch("https://x.com/a")
    assert page == Page(url="https://x.com/a", markdown="hello world", raw='{"a": 1}')
    assert transport.calls[0]["headers"]["User-Agent"]  # honest UA sent
    assert sleeps == []


def test_timeout_then_retry_succeeds(sleeps: list[float], monkeypatch: pytest.MonkeyPatch) -> None:
    instance, _ = make_fetcher(monkeypatch, [TransportError("timeout"), ok_response()])
    assert instance.fetch("https://x.com/a").markdown == "page text"
    assert sleeps == [0.5]


def test_timeout_twice_raises_fetch_error(
    sleeps: list[float], monkeypatch: pytest.MonkeyPatch
) -> None:
    instance, _ = make_fetcher(monkeypatch, [TransportError("timeout"), TransportError("timeout")])
    with pytest.raises(FetchError, match="timeout"):
        instance.fetch("https://x.com/a")


def test_5xx_then_success_retries(sleeps: list[float], monkeypatch: pytest.MonkeyPatch) -> None:
    instance, _ = make_fetcher(monkeypatch, [status_response(503), ok_response()])
    assert instance.fetch("https://x.com/a").markdown == "page text"
    assert sleeps == [0.5]


def test_429_backs_off_longer(sleeps: list[float], monkeypatch: pytest.MonkeyPatch) -> None:
    instance, _ = make_fetcher(monkeypatch, [status_response(429), ok_response()])
    assert instance.fetch("https://x.com/a").markdown == "page text"
    assert sleeps == [2.0]  # 4 x delay_s


def test_other_non_200_fails_immediately(
    sleeps: list[float], monkeypatch: pytest.MonkeyPatch
) -> None:
    instance, transport = make_fetcher(monkeypatch, [status_response(404)])
    with pytest.raises(FetchError, match="HTTP 404"):
        instance.fetch("https://x.com/a")
    assert len(transport.calls) == 1
    assert sleeps == []


def test_robots_disallowed_never_fetches(
    sleeps: list[float], monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = FakeTransport([])
    instance = PageFetcher(transport=transport)
    monkeypatch.setattr(instance, "_allowed_by_robots", lambda url: False)
    with pytest.raises(FetchError, match="robots.txt"):
        instance.fetch("https://x.com/private")
    assert transport.calls == []


def test_robots_disallowed_raises_the_specific_subtype(
    sleeps: list[float], monkeypatch: pytest.MonkeyPatch
) -> None:
    """RobotsDisallowed (PHASE12.md step 1) must stay a FetchError subtype
    so pipeline.py's existing `except FetchError` is unaffected, while
    health.py can catch it specifically to tell "blocked" apart from
    "unreachable" without parsing the error message."""
    instance = PageFetcher(transport=FakeTransport([]))
    monkeypatch.setattr(instance, "_allowed_by_robots", lambda url: False)
    with pytest.raises(RobotsDisallowed):
        instance.fetch("https://x.com/private")


class _FakeRobotsResponse:
    """Minimal urlopen()-compatible context manager over robots.txt text."""

    def __init__(self, text: str) -> None:
        self._text = text

    def __enter__(self) -> "_FakeRobotsResponse":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def read(self) -> bytes:
        return self._text.encode()


def script_robots(monkeypatch: pytest.MonkeyPatch, outcomes: list[Any]) -> list[Request]:
    """Make urlopen() return/raise queued outcomes; records the Request objects
    so tests can assert on the User-Agent header actually sent."""
    calls: list[Request] = []

    def fake_urlopen(request: Request, timeout: float) -> _FakeRobotsResponse:
        calls.append(request)
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return _FakeRobotsResponse(outcome)

    monkeypatch.setattr(fetcher_module, "urlopen", fake_urlopen)
    return calls


def test_robots_fetched_with_our_own_honest_user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    # RobotFileParser.read() sends urllib's generic default UA internally,
    # which some sites (e.g. WeWorkRemotely) 403 outright — we fetch it
    # ourselves instead, with the same UA every other request uses.
    instance = PageFetcher(user_agent="test-agent/1.0")
    calls = script_robots(monkeypatch, ["User-agent: *\nAllow: /"])
    assert instance._allowed_by_robots("https://x.com/a") is True
    assert calls[0].get_header("User-agent") == "test-agent/1.0"


def test_robots_404_treated_as_allow_all(monkeypatch: pytest.MonkeyPatch) -> None:
    instance = PageFetcher()
    script_robots(
        monkeypatch, [HTTPError("https://x.com/robots.txt", 404, "not found", None, None)]
    )
    assert instance._allowed_by_robots("https://x.com/anything") is True


def test_robots_403_treated_as_disallow_all(monkeypatch: pytest.MonkeyPatch) -> None:
    # Forbidden even to our own honest, identified UA — respect it.
    instance = PageFetcher()
    script_robots(
        monkeypatch, [HTTPError("https://x.com/robots.txt", 403, "forbidden", None, None)]
    )
    assert instance._allowed_by_robots("https://x.com/anything") is False


def test_robots_401_treated_as_allow_all(monkeypatch: pytest.MonkeyPatch) -> None:
    # Real case (PHASE13.md step 3): api.ashbyhq.com/robots.txt itself
    # returns 401 because the whole subdomain requires auth by default,
    # not because it's rejecting crawlers -- a 401 says nothing about
    # whether some other path is meant to be public, unlike a 403.
    instance = PageFetcher()
    script_robots(
        monkeypatch, [HTTPError("https://x.com/robots.txt", 401, "unauthorized", None, None)]
    )
    assert instance._allowed_by_robots("https://x.com/anything") is True


def test_robots_unreachable_treated_as_allow_all(monkeypatch: pytest.MonkeyPatch) -> None:
    instance = PageFetcher()
    script_robots(monkeypatch, [URLError("connection refused")])
    assert instance._allowed_by_robots("https://x.com/anything") is True


def test_robots_parser_cached_per_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    instance = PageFetcher()
    calls = script_robots(monkeypatch, ["User-agent: *\nAllow: /", "User-agent: *\nAllow: /"])
    assert instance._allowed_by_robots("https://x.com/a")
    assert instance._allowed_by_robots("https://x.com/b")
    assert instance._allowed_by_robots("https://y.com/c")
    assert len(calls) == 2  # one robots.txt fetch per domain
