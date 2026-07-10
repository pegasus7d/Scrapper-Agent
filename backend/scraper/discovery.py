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
"""

import logging
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from scrapling import Selector

from backend import config
from backend.scraper.fetcher import PageFetcher
from backend.scraper.transport import ScraplingTransport

logger = logging.getLogger(__name__)

_COMPANY_LINK_SELECTOR = 'a[href^="/companies/"]'
_COMPANY_NAME_SELECTOR = 'span[class*="coName"]'
_BATCH_LINK_SELECTOR = 'a[href*="?batch="]'
_SCROLL_COUNT = 5  # confirmed real: 40 -> 120 companies after 5 scroll+wait cycles


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
