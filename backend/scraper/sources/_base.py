"""Shared types and utilities for every source (PHASE3.md step 1).

Kept separate from `__init__.py` so platform modules — including the
`jobs/`/`questions/` domain registries (PHASE4.md step 1) — can import
`Source`, `Chunk`, and these helpers without a circular import back through
the top-level registry.
"""

import html
import re
from dataclasses import dataclass
from typing import Literal, Protocol

from backend.scraper.fetcher import Page

# Skip one-liners ("email me!") that cannot possibly hold a job posting.
MIN_CHUNK_CHARS = 80

_TAGS = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")


@dataclass
class Chunk:
    text: str  # one item's cleaned text
    url: str  # that item's permalink — becomes posting_url / source_url


class Source(Protocol):
    """One platform's adapter. `kind` places it in JOB_SOURCES/QUESTION_SOURCES
    (`sources/__init__.py`) — a new source only needs to declare it once.
    `transport` (PHASE4.md step 2) picks this source's `Transport`, defaulting
    to `"httpx"` since no current source needs Scrapling's HTML-cleaning or
    stealth fetch."""

    kind: Literal["jobs", "questions"]
    transport: Literal["httpx", "scrapling"]

    def seed_urls(self) -> list[str]: ...
    def next_links(self, page: Page) -> list[str]: ...
    def split_items(self, page: Page) -> list[Chunk]: ...


def clean_html(text: str) -> str:
    """Strip tags and entities from HTML, collapsing whitespace."""
    return _WHITESPACE.sub(" ", html.unescape(_TAGS.sub(" ", text))).strip()


def collapse_whitespace(text: str) -> str:
    """Collapse whitespace runs in already-plain text (no tags to strip)."""
    return _WHITESPACE.sub(" ", text).strip()
