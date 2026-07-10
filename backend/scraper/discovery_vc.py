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

Bessemer Venture Partners' companies page (`config.BVP_COMPANIES_URL`).
Real `robots.txt` confirmed: a real disallow list, but none of it touches
this path. The simplest of the four shapes: plain server-rendered HTML,
517 real companies in one page load, no scroll/click/pagination/delay
needed (confirmed directly — no markers found, no crawl-delay requested).
Each name lives inside `h3.name a.name` as a direct text node.

A fifth VC source (PHASE9.md step 10): Accel's companies page
(`config.ACCEL_PORTFOLIO_URL`). Real `robots.txt` confirmed wide open
(only `/admin/`/`/api/` disallowed). A genuinely different real shape from
the other four: plain `httpx` returns a truly empty body (a heavy
client-rendered app, confirmed directly — not a UA-blocking issue, checked
with a real browser UA first) — real JS rendering is required, same as YC.
No company-name text node at all; the real, reliable signal is each
portfolio card's link `aria-label`, shaped `"View {Name} company
details"` — parsed by stripping the fixed prefix/suffix, not a CSS text
selector. 194 real companies confirmed on the page's initial render, no
scroll attempted yet — same "ship partial real coverage now, expand later"
precedent YC itself set (its own first 40-card commit, full scroll
coverage added in a later phase step).
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

_BVP_NAME_SELECTOR = "h3.name a.name"

_ACCEL_LINK_SELECTOR = 'a[aria-label$=" company details"]'
_ACCEL_LABEL_PREFIX = "View "
_ACCEL_LABEL_SUFFIX = " company details"


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


def build_bvp_fetcher() -> PageFetcher:
    """Wire a PageFetcher for the BVP companies page — plain HttpxTransport
    (no JS needed, confirmed)."""
    return PageFetcher(transport=HttpxTransport())


def discover_bvp_companies(fetcher: PageFetcher) -> list[str]:
    """Fetch the BVP companies page and return real, deduplicated company
    names — no batch concept for this source."""
    page = fetcher.fetch(config.BVP_COMPANIES_URL)
    selector = Selector(content=page.raw)
    names: list[str] = []
    seen: set[str] = set()
    for link in selector.css(_BVP_NAME_SELECTOR):
        if not isinstance(link, Selector) or not link.text:
            continue
        name = link.text.strip()
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    logger.info("bvp discovery: %d company names found", len(names))
    return names


def build_accel_fetcher() -> PageFetcher:
    """Wire a PageFetcher for the Accel companies page — real JS rendering
    required (confirmed directly: plain httpx returns a genuinely empty
    body), unlike every other VC source in this module except Sequoia."""
    return PageFetcher(transport=ScraplingTransport())


def discover_accel_companies(fetcher: PageFetcher) -> list[str]:
    """Fetch the Accel companies page and return real, deduplicated company
    names — no batch concept for this source. Real gap acknowledged, not
    hidden: this is the initial render only, no scroll/pagination
    interaction attempted yet, so it may not be Accel's full portfolio
    (confirmed real precedent for shipping partial coverage now: YC's own
    first version did the same before a later phase step added scroll)."""
    page = fetcher.fetch(config.ACCEL_PORTFOLIO_URL)
    selector = Selector(content=page.raw)
    names: list[str] = []
    seen: set[str] = set()
    for link in selector.css(_ACCEL_LINK_SELECTOR):
        if not isinstance(link, Selector):
            continue
        label = link.attrib.get("aria-label")
        if not label or not label.startswith(_ACCEL_LABEL_PREFIX):
            continue
        name = label[len(_ACCEL_LABEL_PREFIX) : -len(_ACCEL_LABEL_SUFFIX)].strip()
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    logger.info("accel discovery: %d company names found", len(names))
    return names
