"""Source registry: formalized as a plugin architecture (DESIGN.md §10 step 1).

Each platform is a `Source` — pure adapter logic (seed URLs, page→chunk
splitting, link discovery), no HTTP calls of its own; fetching always goes
through `fetcher.py`. Adding a platform means writing one new file and
registering an instance below; `pipeline.py`'s calls
(`sources.seed_urls(...)`, `sources.split_items(...)`, `sources.Chunk`) never
change — this module is re-exported flat exactly like `db/repo/__init__.py`.
"""

from typing import Literal, Protocol

from backend.scraper.fetcher import Page
from backend.scraper.sources._base import Chunk
from backend.scraper.sources.arbeitnow import Arbeitnow
from backend.scraper.sources.hn import HNInterviews, HNJobs
from backend.scraper.sources.remoteok import RemoteOK
from backend.scraper.sources.weworkremotely import WeWorkRemotely


class Source(Protocol):
    """One platform's adapter. `kind` drives the JOB_SOURCES/QUESTION_SOURCES
    split below — a new source only needs to declare it once."""

    kind: Literal["jobs", "questions"]

    def seed_urls(self) -> list[str]: ...
    def next_links(self, page: Page) -> list[str]: ...
    def split_items(self, page: Page) -> list[Chunk]: ...


SOURCES: dict[str, Source] = {
    "hn": HNJobs(),
    "remoteok": RemoteOK(),
    "weworkremotely": WeWorkRemotely(),
    "arbeitnow": Arbeitnow(),
    "hn-interviews": HNInterviews(),
}

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


__all__ = [
    "Chunk",
    "JOB_SOURCES",
    "QUESTION_SOURCES",
    "SOURCES",
    "Source",
    "next_links",
    "seed_urls",
    "split_items",
]
