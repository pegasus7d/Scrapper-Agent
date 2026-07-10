"""Tests for company discovery — no real network (CLAUDE.md); Transport is faked."""

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy.orm import Session

from backend.db import repo
from backend.scraper import discovery as discovery_module
from backend.scraper.discovery import (
    DiscoveredCompany,
    build_a16z_fetcher,
    build_bvp_fetcher,
    build_foundersfund_fetcher,
    build_largest_us_companies_fetcher,
    build_sequoia_fetcher,
    build_yc_fetcher,
    discover_a16z_companies,
    discover_and_save_companies,
    discover_bvp_companies,
    discover_foundersfund_companies,
    discover_largest_us_companies,
    discover_sequoia_companies,
    discover_yc_companies,
)
from backend.scraper.fetcher import PageFetcher
from backend.scraper.transport import HttpxTransport, ScraplingTransport, TransportResponse

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


# Mirrors the real Wikipedia wikitable shape confirmed by direct inspection
# (PHASE8.md step 6): three table.wikitable elements on the page, the first
# is the revenue-ranked one; each data row's second <td> holds the company
# name inside a child <a> link — a plain .text read on the <td> itself
# returns empty on the real markup (confirmed directly), so the link's own
# text is what's actually parsed.
_WIKI_HTML = """
<html><body>
<table class="wikitable">
<tr><th>Rank</th><th>Name</th><th>Revenue</th></tr>
<tr><td>1</td><td><a href="/wiki/Walmart" title="Walmart">Walmart</a></td><td>680,985</td></tr>
<tr><td>2</td><td><a href="/wiki/Amazon" title="Amazon">Amazon</a></td><td>637,959</td></tr>
<tr><td>3</td><td>No link company</td><td>100,000</td></tr>
</table>
<table class="wikitable">
<tr><th>Rank</th><th>Name</th><th>Employees</th></tr>
<tr><td>1</td><td><a href="/wiki/Walmart">Walmart</a></td><td>2,100,000</td></tr>
</table>
</body></html>
"""


def test_discover_largest_us_companies_uses_the_first_wikitable() -> None:
    names = discover_largest_us_companies(make_fetcher(_WIKI_HTML))
    assert names == ["Walmart", "Amazon"]


def test_discover_largest_us_companies_skips_rows_without_a_link() -> None:
    names = discover_largest_us_companies(make_fetcher(_WIKI_HTML))
    assert "No link company" not in names


def test_discover_largest_us_companies_raises_when_no_wikitable_found() -> None:
    with pytest.raises(ValueError, match="no wikitable"):
        discover_largest_us_companies(make_fetcher("<html><body>nothing here</body></html>"))


def test_build_largest_us_companies_fetcher_uses_plain_httpx() -> None:
    fetcher = build_largest_us_companies_fetcher()
    assert isinstance(fetcher._transport, HttpxTransport)  # type: ignore[attr-defined]


# Mirrors the real a16z markup shape confirmed by direct inspection
# (PHASE8.md step 9): the full portfolio ships inline as a JS global,
# `window.a16z_portfolio_companies = [...]`, in a <script> tag — each
# element a JSON object whose "title" field (not "name") holds the real
# company name.
_A16Z_HTML = """
<html><body>
<script>window.a16z_portfolio_companies = [
{"id": "1", "title": "SpaceX", "web": "https://spacex.com"},
{"id": "2", "title": "[untitled]", "web": "https://untitled.stream"},
{"id": "3", "title": "SpaceX", "web": "https://spacex.com"},
{"id": "4", "title": ""}
];</script>
</body></html>
"""


def test_discover_a16z_companies_returns_deduplicated_names() -> None:
    names = discover_a16z_companies(make_fetcher(_A16Z_HTML))
    assert names == ["SpaceX", "[untitled]"]


def test_discover_a16z_companies_raises_when_array_not_found() -> None:
    with pytest.raises(ValueError, match="a16z_portfolio_companies"):
        discover_a16z_companies(make_fetcher("<html><body>nothing here</body></html>"))


def test_build_a16z_fetcher_uses_plain_httpx() -> None:
    fetcher = build_a16z_fetcher()
    assert isinstance(fetcher._transport, HttpxTransport)  # type: ignore[attr-defined]


# Mirrors the real Sequoia markup shape confirmed by direct inspection
# (PHASE8.md step 9): a <table id="company_listing"> whose data rows use
# <th scope="row"> for the company name as a direct text node (no nested
# .text-returns-empty quirk this time, confirmed directly) — the header
# row uses scope="col", naturally excluded by the selector.
_SEQUOIA_HTML = """
<html><body>
<table id="company_listing">
<thead><tr><th scope="col">Company Name</th></tr></thead>
<tbody>
<tr><th scope="row">Cisco</th></tr>
<tr><th scope="row">HubSpot</th></tr>
<tr><th scope="row">Cisco</th></tr>
</tbody>
</table>
</body></html>
"""


def test_discover_sequoia_companies_returns_deduplicated_names() -> None:
    names = discover_sequoia_companies(make_fetcher(_SEQUOIA_HTML))
    assert names == ["Cisco", "HubSpot"]


def test_build_sequoia_fetcher_uses_tab_and_load_more_clicks() -> None:
    fetcher = build_sequoia_fetcher()
    transport = fetcher._transport  # type: ignore[attr-defined]
    assert isinstance(transport, ScraplingTransport)
    assert transport._tab_selector  # type: ignore[attr-defined]
    assert transport._load_more_selector  # type: ignore[attr-defined]


# Mirrors the real Founders Fund markup shape confirmed by direct
# inspection (PHASE8.md step 9): plain server-rendered HTML, no
# scroll/click/pagination — each company's name lives as a direct text
# node inside h2.tile-heading span.
_FOUNDERSFUND_HTML = """
<html><body>
<div class="portfolio-tile">
  <h2 class="h3 tile-heading inline-block m0"><span>Stripe</span></h2>
</div>
<div class="portfolio-tile">
  <h2 class="h3 tile-heading inline-block m0"><span>Anduril</span></h2>
</div>
<div class="portfolio-tile">
  <h2 class="h3 tile-heading inline-block m0"><span>Stripe</span></h2>
</div>
</body></html>
"""


def test_discover_foundersfund_companies_returns_deduplicated_names() -> None:
    names = discover_foundersfund_companies(make_fetcher(_FOUNDERSFUND_HTML))
    assert names == ["Stripe", "Anduril"]


def test_build_foundersfund_fetcher_uses_plain_httpx_with_crawl_delay() -> None:
    fetcher = build_foundersfund_fetcher()
    assert isinstance(fetcher._transport, HttpxTransport)  # type: ignore[attr-defined]
    assert fetcher._delay_s == 10.0  # type: ignore[attr-defined]


# Mirrors the real BVP markup shape confirmed by direct inspection
# (PHASE8.md step 9): plain server-rendered HTML, no scroll/click/
# pagination — each company's name lives as a direct text node inside
# h3.name a.name.
_BVP_HTML = """
<html><body>
<article class="box investment"><div class="company">
  <h3 class="h-module-h3 name">
    <a href="/companies/abridge" class="name click-to-open">Abridge</a></h3>
</div></article>
<article class="box investment"><div class="company">
  <h3 class="h-module-h3 name"><a href="/companies/2u" class="name click-to-open">2U</a></h3>
</div></article>
<article class="box investment"><div class="company">
  <h3 class="h-module-h3 name">
    <a href="/companies/abridge" class="name click-to-open">Abridge</a></h3>
</div></article>
</body></html>
"""


def test_discover_bvp_companies_returns_deduplicated_names() -> None:
    names = discover_bvp_companies(make_fetcher(_BVP_HTML))
    assert names == ["Abridge", "2U"]


def test_build_bvp_fetcher_uses_plain_httpx() -> None:
    fetcher = build_bvp_fetcher()
    assert isinstance(fetcher._transport, HttpxTransport)  # type: ignore[attr-defined]


# Real per-source parsing (the fixtures above) stays fully explicit
# (PHASE9.md step 4 — collapsing those would blur real differences like
# YC's batch extraction or Sequoia's click-pagination fetcher config), but
# "no companies on an empty page" is genuinely identical logic across every
# source without a raise-on-missing-marker behavior (a16z's
# `raises_when_array_not_found` is the one real exception, kept separate).
@pytest.mark.parametrize(
    "discover_fn",
    [discover_sequoia_companies, discover_foundersfund_companies, discover_bvp_companies],
)
def test_discover_returns_empty_for_no_matches(
    discover_fn: Callable[[PageFetcher], list[str]],
) -> None:
    names = discover_fn(make_fetcher("<html><body>no companies here</body></html>"))
    assert names == []


@pytest.fixture
def session() -> Session:
    engine = repo.make_engine("sqlite:///:memory:")
    return Session(engine)


def test_discover_and_save_companies_yc_saves_name_and_batch(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        discovery_module,
        "discover_yc_companies",
        lambda fetcher: [DiscoveredCompany(name="DoorDash", batch="Summer 2013")],
    )
    saved = discover_and_save_companies(session, "yc")
    assert saved == 1
    items, _ = repo.list_companies(session)
    assert items[0].name == "DoorDash"
    assert items[0].source == "yc"
    assert items[0].batch == "Summer 2013"


# Real per-source dispatch (registry wiring, PHASE9.md step 1) collapses
# to identical logic for every source without a batch concept — genuinely
# safe to parametrize, unlike the parsing tests above, since this only
# exercises discover_and_save_companies' own save/attribute-source path,
# never a source's real markup.
@pytest.mark.parametrize(
    ("source", "patch_attr", "fake_name"),
    [
        ("largest_us_companies", "discover_largest_us_companies", "Walmart"),
        ("a16z", "discover_a16z_companies", "SpaceX"),
        ("sequoia", "discover_sequoia_companies", "Cisco"),
        ("foundersfund", "discover_foundersfund_companies", "Anduril"),
        ("bvp", "discover_bvp_companies", "Abridge"),
    ],
)
def test_discover_and_save_companies_no_batch_sources(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    source: str,
    patch_attr: str,
    fake_name: str,
) -> None:
    monkeypatch.setattr(discovery_module, patch_attr, lambda fetcher: [fake_name])
    saved = discover_and_save_companies(session, source)
    assert saved == 1
    items, _ = repo.list_companies(session)
    assert items[0].name == fake_name
    assert items[0].source == source
    assert items[0].batch is None


def test_discover_and_save_companies_is_idempotent(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        discovery_module,
        "discover_yc_companies",
        lambda fetcher: [DiscoveredCompany(name="DoorDash", batch=None)],
    )
    discover_and_save_companies(session, "yc")
    second = discover_and_save_companies(session, "yc")
    assert second == 0
