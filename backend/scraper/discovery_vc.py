"""VC portfolio pages as company discovery sources (PHASE8.md step 9) —
split out of `discovery.py` once that file hit the 300-line hard cap
(CLAUDE.md) with YC and Wikipedia already in it. Each VC gets its own real,
verified page shape (WORKFLOW.md rule 2: check before naming a source, not
after) — no two of these four share a parsing approach, confirmed by
building each one against the real live page before writing its parser.

a16z's portfolio page (`config.A16Z_PORTFOLIO_URL`). No `robots.txt` at all
(404) — same "no restrictions" interpretation as everywhere else in this
project. Unlike YC, no scrolling/JS-rendering is needed: the *entire* real
portfolio (849 companies, confirmed directly) ships inline as a JS global,
`window.a16z_portfolio_companies = [...]`, in a `<script>` tag on the plain
server-rendered page — a real, if site-specific, shortcut discovered by
fetching the page and grepping for markers before assuming a YC-style
scroll-driven approach was needed. Each array element is a JSON object with
a `title` field holding the real company name (not `name` — confirmed by
inspection).

Sequoia Capital's portfolio page (`config.SEQUOIA_COMPANIES_URL`). Real
`robots.txt` confirmed wide open. A genuinely different real shape from
a16z: the full, accessible company table (`table#company_listing`) lives
inside a Bootstrap tab-pane hidden by default (`#all-tab` reveals it) and is
itself paginated behind a real "Load More" button, not a scroll — confirmed
directly (52 companies, A-C only, before any interaction; 412, A-Z, after
`ScraplingTransport`'s `load_more_selector` clicks it repeatedly until the
button is removed from the DOM, the real termination signal once the last
page has loaded). Each data row's `th[scope="row"]` holds the company name
as a direct text node — no nested-element `.text`-returns-empty quirk this
time (confirmed directly), unlike YC's batch pill or Wikipedia's link.

Founders Fund's portfolio page (`config.FOUNDERSFUND_PORTFOLIO_URL`). Real
`robots.txt` confirmed wide open, but requests a 10s crawl-delay — honored
via `PageFetcher`'s own `delay_s` override (the same mechanism Arbeitnow
already uses), not a new concept. The simplest of the three shapes here: no
scroll, no click, no pagination markers found anywhere on the page
(confirmed by grepping for "load more"/"infinite"/"pagination") — the
entire real portfolio (62 companies) is plain server-rendered HTML in one
page load. Each company's name lives as a direct text node inside
`h2.tile-heading span` — confirmed directly, no quirk this time either.
"""

import json
import logging
import re

from scrapling import Selector

from backend import config
from backend.scraper.fetcher import PageFetcher
from backend.scraper.transport import HttpxTransport, ScraplingTransport

logger = logging.getLogger(__name__)

_A16Z_PORTFOLIO_PATTERN = re.compile(
    r"window\.a16z_portfolio_companies\s*=\s*(\[.*?\]);", re.DOTALL
)

_SEQUOIA_TABLE_SELECTOR = "table#company_listing th[scope='row']"
_SEQUOIA_TAB_SELECTOR = "#all-tab"
_SEQUOIA_LOAD_MORE_SELECTOR = ".facetwp-load-more"

_FOUNDERSFUND_NAME_SELECTOR = "h2.tile-heading span"


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


def build_foundersfund_fetcher() -> PageFetcher:
    """Wire a PageFetcher for the Founders Fund portfolio page — plain
    HttpxTransport (no JS needed, confirmed) with a 10s delay_s honoring
    the site's real requested Crawl-delay."""
    return PageFetcher(transport=HttpxTransport(), delay_s=config.FOUNDERSFUND_DELAY_S)


def discover_foundersfund_companies(fetcher: PageFetcher) -> list[str]:
    """Fetch the Founders Fund portfolio page and return real, deduplicated
    company names — no batch concept for this source."""
    page = fetcher.fetch(config.FOUNDERSFUND_PORTFOLIO_URL)
    selector = Selector(content=page.raw)
    names: list[str] = []
    seen: set[str] = set()
    for span in selector.css(_FOUNDERSFUND_NAME_SELECTOR):
        if not isinstance(span, Selector) or not span.text:
            continue
        name = span.text.strip()
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    logger.info("foundersfund discovery: %d company names found", len(names))
    return names
