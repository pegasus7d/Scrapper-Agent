"""Company discovery (PHASE7.md step 5): find real company names to become
dynamic scrape sources later (step 7), rather than a hand-curated list — the
user's own explicit direction ("we should be able to scrape companies then
use them as sources").

Routed through `PageFetcher` (not a bare `DynamicFetcher` call) so the same
robots.txt/retry/honest-UA policy every other fetch gets applies here too —
the caller supplies a `ScraplingTransport`-backed fetcher, since the YC
listing page needs real JS rendering (confirmed empirically, PHASE7.md step
5's "Done" note). `ycombinator.com/robots.txt` allows the bare listing page
(`config.YC_COMPANIES_URL`); only query-string-filtered views are
disallowed.

Full coverage (PHASE8.md step 5): the initial page load only renders 40
company cards — confirmed real that scrolling surfaces more (120 after 5
scroll+wait cycles, via `ScraplingTransport(scroll_count=...)`'s real
`page_action` capability, not a fixed page limit this site enforces).
`a[href^="/companies/"]` finds each company's link (its href holds the real
YC slug), a child `span[class*="coName"]` (partial-class match — the exact
hashed class name is build-specific/fragile) holds the clean company name,
and the first `a[href*="?batch="]` pill inside the same card holds the real
YC batch (e.g. "Summer 2013") — extracted from the query param, not the
pill's visible text, since a plain `.text` read returns empty on this
particular nested structure (confirmed directly; the href is reliable).

A second discovery source (PHASE8.md step 6): Wikipedia's own real
revenue-ranked companies table (`config.LARGEST_US_COMPANIES_URL`) — plain
server-rendered HTML, `HttpxTransport` (default), no browser needed unlike
YC. Confirmed real before writing this: the page has three `table.wikitable`
elements (revenue/employees/profits rankings); the first is the
revenue-ranked one this function wants — a real, if slightly fragile,
positional assumption, same trade-off as YC's hashed-class-name matching.
Each row's second `<td>`'s child `<a>` link holds the real company name —
same `.text`-on-a-parent-returns-empty quirk as YC's batch pill (confirmed
directly against all 100 real rows), so the link's own text is read
instead of the cell's.

A third discovery source (PHASE8.md step 9): a16z's portfolio page
(`config.A16Z_PORTFOLIO_URL`). No `robots.txt` at all (404) — same
"no restrictions" interpretation as everywhere else in this project. Unlike
YC, no scrolling/JS-rendering is needed: the *entire* real portfolio (849
companies, confirmed directly) ships inline as a JS global,
`window.a16z_portfolio_companies = [...]`, in a `<script>` tag on the plain
server-rendered page — a real, if site-specific, shortcut discovered by
fetching the page and grepping for markers before assuming a YC-style
scroll-driven approach was needed. Each array element is a JSON object with
a `title` field holding the real company name (not `name` — confirmed by
inspection).

A fourth discovery source (PHASE8.md step 9): Sequoia Capital's portfolio
page (`config.SEQUOIA_COMPANIES_URL`). Real `robots.txt` confirmed wide
open. A genuinely different real shape from the other three: the full,
accessible company table (`table#company_listing`) lives inside a
Bootstrap tab-pane hidden by default (`#all-tab` reveals it) and is itself
paginated behind a real "Load More" button, not a scroll — confirmed
directly (52 companies, A-C only, before any interaction; 412, A-Z, after
`ScraplingTransport`'s new `load_more_selector` clicks it repeatedly until
the button is removed from the DOM, the real termination signal once the
last page has loaded). Each data row's `th[scope="row"]` holds the company
name as a direct text node — no nested-element `.text`-returns-empty quirk
this time (confirmed directly), unlike YC's batch pill or Wikipedia's link.
"""

import json
import logging
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from scrapling import Selector
from sqlalchemy.orm import Session

from backend import config
from backend.db import repo
from backend.scraper.fetcher import PageFetcher
from backend.scraper.transport import HttpxTransport, ScraplingTransport

logger = logging.getLogger(__name__)

_COMPANY_LINK_SELECTOR = 'a[href^="/companies/"]'
_COMPANY_NAME_SELECTOR = 'span[class*="coName"]'
_BATCH_LINK_SELECTOR = 'a[href*="?batch="]'
_SCROLL_COUNT = 5  # confirmed real: 40 -> 120 companies after 5 scroll+wait cycles

_WIKITABLE_SELECTOR = "table.wikitable"

_A16Z_PORTFOLIO_PATTERN = re.compile(
    r"window\.a16z_portfolio_companies\s*=\s*(\[.*?\]);", re.DOTALL
)

_SEQUOIA_TABLE_SELECTOR = "table#company_listing th[scope='row']"
_SEQUOIA_TAB_SELECTOR = "#all-tab"
_SEQUOIA_LOAD_MORE_SELECTOR = ".facetwp-load-more"

# The real, valid values for POST /companies/discover's source param and
# Schedule.source when Schedule.kind == "companies" (PHASE8.md step 7) —
# shared here rather than duplicated in routes_companies.py/routes.py.
DISCOVERY_SOURCES = ("yc", "largest_us_companies", "a16z", "sequoia")


@dataclass
class DiscoveredCompany:
    name: str
    batch: str | None


def build_yc_fetcher() -> PageFetcher:
    """Wire a PageFetcher for the YC listing page — the real call site's
    fetcher, injected into discover_yc_companies the same way
    build_resume_extractor() is injected into derive_search_positions()
    (dependency injection discipline: tests substitute a fake fetcher,
    never this one). scroll_count drives real full-coverage scrolling
    (PHASE8.md step 5), not just the first page's 40 cards."""
    return PageFetcher(transport=ScraplingTransport(scroll_count=_SCROLL_COUNT))


def _extract_batch(link: Selector) -> str | None:
    batch_link = link.css_first(_BATCH_LINK_SELECTOR)
    if not isinstance(batch_link, Selector):
        return None
    href = batch_link.attrib.get("href")
    if not href:
        return None
    values = parse_qs(urlparse(href).query).get("batch")
    return values[0] if values else None


def discover_yc_companies(fetcher: PageFetcher) -> list[DiscoveredCompany]:
    """Fetch the YC company directory (scrolled for full coverage) and
    return real, deduplicated companies with their batch."""
    page = fetcher.fetch(config.YC_COMPANIES_URL)
    selector = Selector(content=page.raw)
    companies: list[DiscoveredCompany] = []
    seen: set[str] = set()
    for link in selector.css(_COMPANY_LINK_SELECTOR):
        # .css() is typed to also allow TextHandler/list results (returned
        # only for ::text-style pseudo-selectors, which this query never
        # uses) — narrow explicitly rather than assume the union away.
        if not isinstance(link, Selector):
            continue
        name_element = link.css_first(_COMPANY_NAME_SELECTOR)
        if not isinstance(name_element, Selector) or not name_element.text:
            continue
        name = name_element.text.strip()
        if name and name not in seen:
            seen.add(name)
            companies.append(DiscoveredCompany(name=name, batch=_extract_batch(link)))
    logger.info("yc discovery: %d company names found", len(companies))
    return companies


def build_largest_us_companies_fetcher() -> PageFetcher:
    """Wire a PageFetcher for the Wikipedia revenue-ranked table — plain
    HttpxTransport (the page is server-rendered, no JS needed unlike YC)."""
    return PageFetcher(transport=HttpxTransport())


def discover_largest_us_companies(fetcher: PageFetcher) -> list[str]:
    """Fetch Wikipedia's largest-US-companies-by-revenue table and return
    real, deduplicated company names — no batch concept for this source."""
    page = fetcher.fetch(config.LARGEST_US_COMPANIES_URL)
    selector = Selector(content=page.raw)
    table = selector.css_first(_WIKITABLE_SELECTOR)
    if not isinstance(table, Selector):
        raise ValueError("no wikitable found on the largest-US-companies page")
    names: list[str] = []
    seen: set[str] = set()
    for row in table.css("tr"):
        if not isinstance(row, Selector):
            continue
        cells = [c for c in row.css("td") if isinstance(c, Selector)]
        if len(cells) < 2:
            continue  # the header row has <th>, not <td> — naturally skipped
        name_link = cells[1].css_first("a")
        if not isinstance(name_link, Selector) or not name_link.text:
            continue
        name = name_link.text.strip()
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    logger.info("largest-US-companies discovery: %d company names found", len(names))
    return names


def build_a16z_fetcher() -> PageFetcher:
    """Wire a PageFetcher for the a16z portfolio page — plain HttpxTransport,
    same as Wikipedia: the full list ships inline in the server-rendered
    HTML, no browser needed."""
    return PageFetcher(transport=HttpxTransport())


def discover_a16z_companies(fetcher: PageFetcher) -> list[str]:
    """Fetch the a16z portfolio page and return real, deduplicated company
    names — no batch concept for this source."""
    page = fetcher.fetch(config.A16Z_PORTFOLIO_URL)
    match = _A16Z_PORTFOLIO_PATTERN.search(page.raw)
    if not match:
        raise ValueError("a16z_portfolio_companies JS array not found on the portfolio page")
    companies = json.loads(match.group(1))
    names: list[str] = []
    seen: set[str] = set()
    for company in companies:
        title = company.get("title")
        if not isinstance(title, str):
            continue
        name = title.strip()
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    logger.info("a16z discovery: %d company names found", len(names))
    return names


def build_sequoia_fetcher() -> PageFetcher:
    """Wire a PageFetcher for the Sequoia portfolio page — real JS rendering
    plus a click sequence (tab open, then repeated "Load More" clicks) to
    reach the full, real company table, confirmed empirically (PHASE8.md
    step 9)."""
    return PageFetcher(
        transport=ScraplingTransport(
            tab_selector=_SEQUOIA_TAB_SELECTOR,
            load_more_selector=_SEQUOIA_LOAD_MORE_SELECTOR,
        )
    )


def discover_sequoia_companies(fetcher: PageFetcher) -> list[str]:
    """Fetch the Sequoia portfolio page (tab opened, fully paginated) and
    return real, deduplicated company names — no batch concept for this
    source."""
    page = fetcher.fetch(config.SEQUOIA_COMPANIES_URL)
    selector = Selector(content=page.raw)
    names: list[str] = []
    seen: set[str] = set()
    for cell in selector.css(_SEQUOIA_TABLE_SELECTOR):
        if not isinstance(cell, Selector) or not cell.text:
            continue
        name = cell.text.strip()
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    logger.info("sequoia discovery: %d company names found", len(names))
    return names


def discover_and_save_companies(session: Session, source: str) -> int:
    """Run one discovery pass for `source` and save any new companies —
    shared by the API route (`POST /companies/discover`) and the scheduled
    Huey task (PHASE8.md step 7) so the two don't duplicate the per-source
    dispatch. Trusts `source` is already one of DISCOVERY_SOURCES —
    validated once at the call site (the API route's 422, or schedule
    creation's own validation), not re-checked here."""
    if source == "yc":
        yc_companies = discover_yc_companies(build_yc_fetcher())
        return sum(
            1
            for c in yc_companies
            if repo.save_company(session, c.name, source="yc", batch=c.batch)
        )
    if source == "a16z":
        a16z_names = discover_a16z_companies(build_a16z_fetcher())
        return sum(1 for name in a16z_names if repo.save_company(session, name, source="a16z"))
    if source == "sequoia":
        sequoia_names = discover_sequoia_companies(build_sequoia_fetcher())
        return sum(
            1 for name in sequoia_names if repo.save_company(session, name, source="sequoia")
        )
    names = discover_largest_us_companies(build_largest_us_companies_fetcher())
    return sum(
        1 for name in names if repo.save_company(session, name, source="largest_us_companies")
    )
