"""Tests for company discovery — no real network (CLAUDE.md); Transport is faked."""

from typing import Any

from backend.scraper.discovery import discover_yc_companies
from backend.scraper.fetcher import PageFetcher
from backend.scraper.transport import TransportResponse

# Mirrors the real YC markup shape confirmed by direct inspection
# (PHASE7.md step 5): an <a href="/companies/{slug}"> wrapping a child
# span whose class merely contains "coName" (the real hashed class name
# is build-specific).
_YC_HTML = """
<html><body>
<div class="companies-list">
  <a href="/companies/doordash"><span class="_coName_18olp_472">DoorDash</span></a>
  <a href="/companies/airbnb"><span class="_coName_18olp_472">Airbnb</span></a>
  <a href="/companies/doordash"><span class="_coName_18olp_472">DoorDash</span></a>
  <a href="/companies/coinbase"><div>not a name span</div></a>
</div>
<a href="/other/page">Not a company link</a>
</body></html>
"""


class FakeTransport:
    def __init__(self, text: str) -> None:
        self._text = text

    def get(self, url: str, *, timeout: int, headers: dict[str, str]) -> TransportResponse:
        return TransportResponse(status=200, body=self._text, text="")


def make_fetcher(html: str) -> PageFetcher:
    fetcher = PageFetcher(transport=FakeTransport(html))
    fetcher._allowed_by_robots = lambda url: True  # type: ignore[method-assign]
    return fetcher


def test_discover_yc_companies_returns_deduplicated_names() -> None:
    names = discover_yc_companies(make_fetcher(_YC_HTML))
    assert names == ["DoorDash", "Airbnb"]


def test_discover_yc_companies_skips_links_without_a_name() -> None:
    names = discover_yc_companies(make_fetcher(_YC_HTML))
    assert "Coinbase" not in names


def test_discover_yc_companies_returns_empty_for_no_matches() -> None:
    names = discover_yc_companies(make_fetcher("<html><body>no companies here</body></html>"))
    assert names == []


def test_discover_yc_companies_fetches_the_configured_url() -> None:
    calls: list[Any] = []
    fetcher = make_fetcher(_YC_HTML)
    original_fetch = fetcher.fetch

    def recording_fetch(url: str) -> Any:
        calls.append(url)
        return original_fetch(url)

    fetcher.fetch = recording_fetch  # type: ignore[method-assign]
    discover_yc_companies(fetcher)
    assert calls == ["https://www.ycombinator.com/companies"]
