"""Source registry: formalized as a plugin architecture (PHASE3.md step 1),
split by domain as of PHASE4.md step 1.

Each platform is a `Source` — pure adapter logic (seed URLs, page→chunk
splitting, link discovery), no HTTP calls of its own; fetching always goes
through `fetcher.py`. A platform lives under `jobs/` or `questions/`, never
both, and is registered in that domain's own small `SOURCES` dict; this
module merges the two into one flat `SOURCES` so `pipeline.py`'s calls
(`sources.seed_urls(...)`, `sources.split_items(...)`, `sources.Chunk`) never
change — same re-export-flat pattern as `db/repo/__init__.py`.
"""

from typing import Literal

from backend.scraper.fetcher import Page
from backend.scraper.sources import jobs, questions
from backend.scraper.sources._base import Chunk, Source

SOURCES: dict[str, Source] = {**jobs.SOURCES, **questions.SOURCES}

JOB_SOURCES = tuple(name for name, source in SOURCES.items() if source.kind == "jobs")
QUESTION_SOURCES = tuple(name for name, source in SOURCES.items() if source.kind == "questions")


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


__all__ = [
    "Chunk",
    "JOB_SOURCES",
    "QUESTION_SOURCES",
    "SOURCES",
    "Source",
    "delay_for",
    "next_links",
    "seed_urls",
    "split_items",
    "transport_for",
]
