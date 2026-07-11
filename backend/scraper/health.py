"""Source health checks (PHASE12.md step 1): a cheap liveness probe across
every registered job/question/discovery source, distinct from a real
scrape — one low-timeout, no-retry fetch of a source's own seed URL, no
LLM call, no full page extraction. Nothing today distinguishes "a
scheduled run returned zero rows because nothing matched" from "the
source's site changed shape and every fetch is now failing"; this module
exists to answer that question directly, on demand.
"""

from dataclasses import dataclass
from typing import Literal

from backend.scraper import discovery, sources
from backend.scraper.fetcher import FetchError, PageFetcher, RobotsDisallowed

# Deliberately shorter/stricter than the real scrape fetcher's defaults
# (config.FETCH_RETRIES/FETCH_TIMEOUT_S) — a health check that retries and
# backs off like a real scrape defeats its own purpose of being cheap.
_HEALTH_CHECK_TIMEOUT_S = 5
_HEALTH_CHECK_RETRIES = 0

HealthStatus = Literal["ok", "blocked", "unreachable"]
SourceCategory = Literal["jobs", "questions", "discovery"]


@dataclass
class SourceHealth:
    name: str
    kind: SourceCategory
    status: HealthStatus
    detail: str | None  # error message on blocked/unreachable, None on ok


def _probe(name: str, kind: SourceCategory, url: str) -> SourceHealth:
    fetcher = PageFetcher(retries=_HEALTH_CHECK_RETRIES, timeout_s=_HEALTH_CHECK_TIMEOUT_S)
    try:
        fetcher.fetch(url)
    except RobotsDisallowed as error:
        return SourceHealth(name=name, kind=kind, status="blocked", detail=str(error))
    except FetchError as error:
        return SourceHealth(name=name, kind=kind, status="unreachable", detail=str(error))
    return SourceHealth(name=name, kind=kind, status="ok", detail=None)


def check_all_sources() -> list[SourceHealth]:
    """Probe every registered job/question source (sources.SOURCES) and
    discovery source (discovery.discovery_seed_urls), in registry order.
    Dynamically-registered per-company sources (sources.SOURCES keys
    prefixed "company:") are excluded — there can be thousands of them,
    and they're not fixed infrastructure to monitor the health of."""
    results = []
    for name, source in sources.SOURCES.items():
        if name.startswith("company:"):
            continue
        results.append(_probe(name, source.kind, source.seed_urls()[0]))
    for name, seed_url in discovery.discovery_seed_urls():
        results.append(_probe(name, "discovery", seed_url))
    return results
