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

Two more discovery sources — Wikipedia's revenue-ranked table (PHASE8.md
step 6) and Russell 1000 constituents (PHASE9.md step 9) — live in
`discovery_lists.py`, not here: this file was already at the 300-line hard
cap once Russell 1000 landed alongside YC and the registry/orchestration
code. Four further sources — a16z, Sequoia, Founders Fund, and Bessemer
(PHASE8.md step 9, VC portfolio pages) — live in `discovery_vc.py` for the
same reason. Neither sibling module needs to know about the other beyond
the shared `DiscoveredCompany`/`discover_and_save_companies` dispatch below.

Registry, not an `if/elif` chain (PHASE9.md step 1): mirrors
`sources/__init__.py`'s existing `SOURCES: dict[str, Source]` pattern for
job/question sources, which this module never adopted when it grew from
one source to six across PHASE7-8 — real, observed cost documented in
PHASE9.md ("Why this matters"). Each source's real `discover_X_companies`
function keeps its own real return type (`list[DiscoveredCompany]` for YC,
`list[str]` for everything else — no batch concept there) exactly as it
already was; a small per-source adapter normalizes the return shape into
`list[DiscoveredCompany]` only at registry-construction time, so no
existing parsing logic or function signature changes, just how they're
wired together.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from scrapling import Selector
from sqlalchemy.orm import Session

from backend import config
from backend.db import repo
from backend.scraper.discovery_lists import (
    build_largest_us_companies_fetcher,
    build_russell_1000_fetcher,
    discover_largest_us_companies,
    discover_russell_1000_companies,
)
from backend.scraper.discovery_vc import (
    build_a16z_fetcher,
    build_bvp_fetcher,
    build_foundersfund_fetcher,
    build_sequoia_fetcher,
    discover_a16z_companies,
    discover_bvp_companies,
    discover_foundersfund_companies,
    discover_sequoia_companies,
)
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


def _no_batch(names: list[str]) -> list[DiscoveredCompany]:
    """Adapter for every source without a batch concept — normalizes a
    plain `list[str]` into the registry's uniform `list[DiscoveredCompany]`
    shape without changing the real discover_X_companies function itself."""
    return [DiscoveredCompany(name=name, batch=None) for name in names]


def _discover_yc(fetcher: PageFetcher) -> list[DiscoveredCompany]:
    """A thin wrapper, not a direct reference to discover_yc_companies in
    the registry below — a real bug, caught by this file's own test suite:
    a direct reference captures the function object at registry-
    construction time, which silently bypasses `monkeypatch.setattr`
    (patches the module attribute, not an already-bound dict value) and
    made a real network call to ycombinator.com during a test run that was
    supposed to be fully faked. Every entry in the registry goes through a
    same-shaped call-time name lookup instead, this one included."""
    return discover_yc_companies(fetcher)


def _discover_largest_us_companies(fetcher: PageFetcher) -> list[DiscoveredCompany]:
    return _no_batch(discover_largest_us_companies(fetcher))


def _discover_a16z(fetcher: PageFetcher) -> list[DiscoveredCompany]:
    return _no_batch(discover_a16z_companies(fetcher))


def _discover_sequoia(fetcher: PageFetcher) -> list[DiscoveredCompany]:
    return _no_batch(discover_sequoia_companies(fetcher))


def _discover_foundersfund(fetcher: PageFetcher) -> list[DiscoveredCompany]:
    return _no_batch(discover_foundersfund_companies(fetcher))


def _discover_bvp(fetcher: PageFetcher) -> list[DiscoveredCompany]:
    return _no_batch(discover_bvp_companies(fetcher))


def _discover_russell_1000(fetcher: PageFetcher) -> list[DiscoveredCompany]:
    return _no_batch(discover_russell_1000_companies(fetcher))


@dataclass
class DiscoverySource:
    build_fetcher: Callable[[], PageFetcher]
    discover: Callable[[PageFetcher], list[DiscoveredCompany]]
    # Human-readable display label (PHASE9.md step 2) — the backend's own
    # concern now, not a hand-mirrored dict in the frontend that can drift
    # out of sync with real, observed cost (a source shipped once without
    # its frontend label, caught only while writing FEATURES.md).
    label: str


# The real registry (PHASE9.md step 1) — adding a source means adding one
# entry here, not a new `if` branch in discover_and_save_companies below.
# Order matches the original DISCOVERY_SOURCES tuple so nothing that reads
# "first source" (e.g. the frontend's default selection) changes behavior.
_REGISTRY: dict[str, DiscoverySource] = {
    "yc": DiscoverySource(build_yc_fetcher, _discover_yc, label="YC"),
    "largest_us_companies": DiscoverySource(
        build_largest_us_companies_fetcher,
        _discover_largest_us_companies,
        label="Largest US companies",
    ),
    "a16z": DiscoverySource(build_a16z_fetcher, _discover_a16z, label="a16z"),
    "sequoia": DiscoverySource(build_sequoia_fetcher, _discover_sequoia, label="Sequoia"),
    "foundersfund": DiscoverySource(
        build_foundersfund_fetcher, _discover_foundersfund, label="Founders Fund"
    ),
    "bvp": DiscoverySource(build_bvp_fetcher, _discover_bvp, label="BVP"),
    "russell1000": DiscoverySource(
        build_russell_1000_fetcher, _discover_russell_1000, label="Russell 1000"
    ),
}

# The real, valid values for POST /companies/discover's source param and
# Schedule.source when Schedule.kind == "companies" (PHASE8.md step 7) —
# derived from the registry above, not hand-maintained (PHASE9.md step 1).
DISCOVERY_SOURCES = tuple(_REGISTRY.keys())


def discovery_source_labels() -> list[tuple[str, str]]:
    """Real (name, label) pairs for every discovery source, in registry
    order — the single source of truth GET /companies/sources (PHASE9.md
    step 2) serves, so the frontend never hand-mirrors this list again."""
    return [(name, entry.label) for name, entry in _REGISTRY.items()]


def discover_and_save_companies(session: Session, source: str) -> int:
    """Run one discovery pass for `source` and save any new companies —
    shared by the API route (`POST /companies/discover`) and the scheduled
    Huey task (PHASE8.md step 7) so the two don't duplicate the per-source
    dispatch. Trusts `source` is already one of DISCOVERY_SOURCES —
    validated once at the call site (the API route's 422, or schedule
    creation's own validation), not re-checked here."""
    entry = _REGISTRY[source]
    companies = entry.discover(entry.build_fetcher())
    return sum(
        1 for c in companies if repo.save_company(session, c.name, source=source, batch=c.batch)
    )
