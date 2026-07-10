"""Wikipedia "large company list" discovery sources — split out of
discovery.py once that file hit the 300-line hard cap (CLAUDE.md) with
Russell 1000 added alongside YC and the registry/orchestration code,
mirroring the earlier discovery_vc.py split for VC portfolio sources.

The first source (PHASE8.md step 6): Wikipedia's own real revenue-ranked
companies table (`config.LARGEST_US_COMPANIES_URL`) — plain server-rendered
HTML, `HttpxTransport` (default), no browser needed. Confirmed real before
writing this: the page has three `table.wikitable` elements (revenue/
employees/profits rankings); the first is the revenue-ranked one this
function wants — a real, if slightly fragile, positional assumption. Each
row's second `<td>`'s child `<a>` link holds the real company name — a
plain `.text`-on-a-parent-returns-empty quirk (confirmed directly against
all 100 real rows), so the link's own text is read instead of the cell's.

A second source (PHASE9.md step 9): Russell 1000 constituents
(`config.RUSSELL_1000_URL`) — added after the source above turned out to
only cover the top ~100 companies by revenue, missing companies like
Netflix entirely. Checked multiple real candidates before picking this one
(Fortune's own list is paywalled; a market-cap list and S&P 500 were both
checked too) — Russell 1000 is real, complete (1002 companies confirmed),
and includes Netflix. Same `en.wikipedia.org/robots.txt` policy already
verified. Unlike the source above's fragile "first wikitable" positional
guess, the real constituent table has a stable `id="constituents"` — used
directly, not a position. Same `.text`-on-a-parent-returns-empty quirk.
"""

import logging

from scrapling import Selector

from backend import config
from backend.scraper.fetcher import PageFetcher
from backend.scraper.transport import HttpxTransport

logger = logging.getLogger(__name__)

_WIKITABLE_SELECTOR = "table.wikitable"
_RUSSELL_1000_TABLE_SELECTOR = "table#constituents"


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


def build_russell_1000_fetcher() -> PageFetcher:
    """Wire a PageFetcher for the Russell 1000 constituents page — plain
    HttpxTransport, same as the other Wikipedia sources: server-rendered,
    no JS needed (confirmed directly)."""
    return PageFetcher(transport=HttpxTransport())


def discover_russell_1000_companies(fetcher: PageFetcher) -> list[str]:
    """Fetch the Russell 1000 constituents table and return real,
    deduplicated company names — no batch concept for this source."""
    page = fetcher.fetch(config.RUSSELL_1000_URL)
    selector = Selector(content=page.raw)
    table = selector.css_first(_RUSSELL_1000_TABLE_SELECTOR)
    if not isinstance(table, Selector):
        raise ValueError("no constituents table found on the Russell 1000 page")
    names: list[str] = []
    seen: set[str] = set()
    for row in table.css("tr"):
        if not isinstance(row, Selector):
            continue
        cells = [c for c in row.css("td") if isinstance(c, Selector)]
        if not cells:
            continue  # the header row has <th>, not <td> — naturally skipped
        name_link = cells[0].css_first("a")
        if not isinstance(name_link, Selector) or not name_link.text:
            continue
        name = name_link.text.strip()
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    logger.info("russell1000 discovery: %d company names found", len(names))
    return names
