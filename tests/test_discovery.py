"""Tests for company discovery — no real network (CLAUDE.md); Transport is faked."""

from typing import Any

from backend.scraper.discovery import build_yc_fetcher, discover_yc_companies
from backend.scraper.fetcher import PageFetcher
from backend.scraper.transport import ScraplingTransport, TransportResponse

# Mirrors the real YC markup shape confirmed by direct inspection
# (PHASE7.md step 5, batch pill confirmed PHASE8.md step 5): an
# <a href="/companies/{slug}"> wrapping a child span whose class merely
# contains "coName" (the real hashed class name is build-specific), plus a
# real batch pill link whose href carries the batch as a query param (its
# visible .text is empty on the real markup — confirmed directly — so the
# href is what's actually parsed).
_YC_HTML = """
<html><body>
<div class="companies-list">
  <a href="/companies/doordash">
    <span class="_coName_18olp_472">DoorDash</span>
    <div class="_pillWrapper_18olp_33">
      <a href="/companies?batch=Summer%202013" class="_tagLink_18olp_1042">
        <span class="pill">Summer 2013</span>
      </a>
    </div>
  </a>
  <a href="/companies/airbnb">
    <span class="_coName_18olp_472">Airbnb</span>
  </a>
  <a href="/companies/doordash">
    <span class="_coName_18olp_472">DoorDash</span>
    <div class="_pillWrapper_18olp_33">
      <a href="/companies?batch=Summer%202013"><span class="pill">Summer 2013</span></a>
    </div>
  </a>
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


def test_discover_yc_companies_returns_deduplicated_names_and_batch() -> None:
    companies = discover_yc_companies(make_fetcher(_YC_HTML))
    assert [(c.name, c.batch) for c in companies] == [
        ("DoorDash", "Summer 2013"),
        ("Airbnb", None),
    ]


def test_discover_yc_companies_skips_links_without_a_name() -> None:
    companies = discover_yc_companies(make_fetcher(_YC_HTML))
    assert "Coinbase" not in [c.name for c in companies]


def test_discover_yc_companies_returns_empty_for_no_matches() -> None:
    companies = discover_yc_companies(make_fetcher("<html><body>no companies here</body></html>"))
    assert companies == []


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


def test_build_yc_fetcher_scrolls_for_real_full_coverage() -> None:
    fetcher = build_yc_fetcher()
    transport = fetcher._transport  # type: ignore[attr-defined]
    assert isinstance(transport, ScraplingTransport)
    assert transport._scroll_count > 0  # type: ignore[attr-defined]
