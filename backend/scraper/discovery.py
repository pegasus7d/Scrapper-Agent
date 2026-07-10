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

The listing page renders 40 real company cards on initial load with no
scroll needed for a first version — confirmed by direct inspection:
`a[href^="/companies/"]` finds each company's link (its href holds the real
YC slug), and a child `span[class*="coName"]` (partial-class match — the
exact hashed class name is build-specific/fragile) holds the clean company
name.
"""

import logging

from scrapling import Selector

from backend import config
from backend.scraper.fetcher import PageFetcher

logger = logging.getLogger(__name__)

_COMPANY_LINK_SELECTOR = 'a[href^="/companies/"]'
_COMPANY_NAME_SELECTOR = 'span[class*="coName"]'


def discover_yc_companies(fetcher: PageFetcher) -> list[str]:
    """Fetch the YC company directory and return real, deduplicated company names."""
    page = fetcher.fetch(config.YC_COMPANIES_URL)
    selector = Selector(content=page.raw)
    names: list[str] = []
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
            names.append(name)
    logger.info("yc discovery: %d company names found", len(names))
    return names
