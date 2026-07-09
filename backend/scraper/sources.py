"""Source-specific knowledge: seed URLs, page→chunk splitting, link discovery.

Only Hacker News "Who is hiring?" is implemented for now (MVP); Reddit lands in
build-order step 6. HN goes through the free Algolia API because it returns the
whole thread as structured JSON — every comment keeps its id, which becomes the
chunk's permalink (DESIGN.md §3). Malformed payloads raise ValueError; the
pipeline records that against the URL and continues.
"""

import html
import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from backend.scraper.fetcher import Page

logger = logging.getLogger(__name__)

HN = "hn"
JOB_SOURCES = (HN,)
QUESTION_SOURCES: tuple[str, ...] = ()  # Reddit lands in step 6

# Skip one-liners ("email me!") that cannot possibly hold a job posting.
MIN_CHUNK_CHARS = 80

_ALGOLIA_SEARCH_URL = (
    "https://hn.algolia.com/api/v1/search_by_date?tags=story,author_whoishiring&hitsPerPage=10"
)
_ALGOLIA_ITEM_URL = "https://hn.algolia.com/api/v1/items/{id}"
_HN_PERMALINK = "https://news.ycombinator.com/item?id={id}"
_WHO_IS_HIRING_PREFIX = "Ask HN: Who is hiring?"

_TAGS = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")


@dataclass
class Chunk:
    text: str  # one item's cleaned text
    url: str  # that item's permalink — becomes posting_url / source_url


def seed_urls(source: str) -> list[str]:
    """Return the starting URLs for a source."""
    if source == HN:
        return [_ALGOLIA_SEARCH_URL]
    raise ValueError(f"unknown source: {source}")


def next_links(page: Page, source: str) -> list[str]:
    """Return further URLs discovered on a page (already-seen ones are fine)."""
    if source != HN:
        raise ValueError(f"unknown source: {source}")
    if page.url == _ALGOLIA_SEARCH_URL:
        return [_latest_hiring_thread_url(page.raw)]
    return []  # a thread page is complete in itself — no pagination via Algolia


def split_items(page: Page, source: str) -> list[Chunk]:
    """Split a page into per-item chunks, each with its own permalink."""
    if source != HN:
        raise ValueError(f"unknown source: {source}")
    if page.url == _ALGOLIA_SEARCH_URL:
        return []  # the search page only points at the thread
    return _thread_chunks(page.raw)


def _latest_hiring_thread_url(raw: str) -> str:
    """Pick the newest "Who is hiring?" story from an Algolia search response."""
    hits = json.loads(raw).get("hits", [])
    for hit in hits:  # search_by_date returns newest first
        if str(hit.get("title", "")).startswith(_WHO_IS_HIRING_PREFIX):
            return _ALGOLIA_ITEM_URL.format(id=hit["objectID"])
    raise ValueError("no 'Who is hiring?' thread in Algolia search response")


def _thread_chunks(raw: str) -> list[Chunk]:
    """Turn an Algolia item payload into one chunk per top-level comment."""
    thread: dict[str, Any] = json.loads(raw)
    chunks: list[Chunk] = []
    skipped = 0
    for comment in thread.get("children", []):
        text = comment.get("text")
        if not text:  # deleted/dead comments come through as null
            skipped += 1
            continue
        cleaned = _clean_html(text)
        if len(cleaned) < MIN_CHUNK_CHARS:
            skipped += 1
            continue
        chunks.append(Chunk(text=cleaned, url=_HN_PERMALINK.format(id=comment["id"])))
    logger.info("thread %s: %d chunks, %d skipped", thread.get("id"), len(chunks), skipped)
    return chunks


def _clean_html(text: str) -> str:
    """Strip tags and entities from HN comment HTML, collapsing whitespace."""
    return _WHITESPACE.sub(" ", html.unescape(_TAGS.sub(" ", text))).strip()
