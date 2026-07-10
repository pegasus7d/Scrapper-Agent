"""Source registry: formalized as a plugin architecture (PHASE3.md step 1),
split by domain as of PHASE4.md step 1.

Each platform is a `Source` — pure adapter logic (seed URLs, page→chunk
splitting, link discovery), no HTTP calls of its own; fetching always goes
through `fetcher.py`. A platform lives under `jobs/` or `questions/`, never
both, and is registered in that domain's own small `SOURCES` dict; this
module merges the two into one flat `SOURCES` so `pipeline.py`'s calls
(`sources.seed_urls(...)`, `sources.split_items(...)`, `sources.Chunk`) never
change — same re-export-flat pattern as `db/repo/__init__.py`.

Resolved companies (PHASE7.md step 7) are the one exception: `SOURCES` is a
plain mutable dict, so `register_company_source` adds a company's Source to
it at scrape time, keyed `company:{slug}` — driven by the `companies` table
(steps 5/6), never a fixed per-company dict entry hand-written here.
"""

from collections.abc import Callable
from typing import Literal

from backend.db.models import Company
from backend.scraper.fetcher import Page
from backend.scraper.sources import jobs, questions
from backend.scraper.sources._base import Chunk, Source
from backend.scraper.sources.companies import GreenhouseCompanySource, LeverCompanySource

SOURCES: dict[str, Source] = {**jobs.SOURCES, **questions.SOURCES}

JOB_SOURCES = tuple(name for name, source in SOURCES.items() if source.kind == "jobs")
QUESTION_SOURCES = tuple(name for name, source in SOURCES.items() if source.kind == "questions")

_COMPANY_SOURCE_BUILDERS: dict[str, Callable[[str, str], Source]] = {
    "greenhouse": GreenhouseCompanySource,
    "lever": LeverCompanySource,
}


def _get(source: str) -> Source:
    try:
        return SOURCES[source]
    except KeyError:
        raise ValueError(f"unknown source: {source}") from None


def seed_urls(source: str) -> list[str]:
    """Return the starting URLs for a source."""
    return _get(source).seed_urls()


def next_links(page: Page, source: str) -> list[str]:
    """Return further URLs discovered on a page (already-seen ones are fine)."""
    return _get(source).next_links(page)


def split_items(page: Page, source: str) -> list[Chunk]:
    """Split a page into per-item chunks, each with its own permalink."""
    return _get(source).split_items(page)


def transport_for(source: str) -> Literal["httpx", "scrapling"]:
    """Which Transport a source's PageFetcher should use (PHASE4.md step 2)."""
    return _get(source).transport


def delay_for(source: str) -> float:
    """This source's own politeness delay between page fetches (PHASE4.md step 3)."""
    return _get(source).delay_s


def company_source_key(company: Company) -> str:
    """The dynamic SOURCES key a resolved company scrapes under."""
    return f"company:{company.slug}"


def register_company_source(company: Company) -> str:
    """Build a resolved company's Source and register it into SOURCES
    (PHASE7.md step 7), returning the key to scrape it with. Re-registering
    is cheap and safe — every scrape call does it fresh, so there's no
    stale-registry problem after a process restart (SOURCES is in-memory
    only; the Company row itself is the durable record)."""
    if company.slug is None or company.ats_provider is None:
        raise ValueError(f"company {company.name!r} has not been resolved to an ATS yet")
    builder = _COMPANY_SOURCE_BUILDERS.get(company.ats_provider)
    if builder is None:
        raise ValueError(f"unknown ATS provider: {company.ats_provider}")
    key = company_source_key(company)
    SOURCES[key] = builder(company.slug, company.name)
    return key


__all__ = [
    "Chunk",
    "JOB_SOURCES",
    "QUESTION_SOURCES",
    "SOURCES",
    "Source",
    "company_source_key",
    "delay_for",
    "next_links",
    "register_company_source",
    "seed_urls",
    "split_items",
    "transport_for",
]
