"""Hacker News sources: "Who is hiring?" jobs + interview-question search.

Both go through the free Algolia API — no login, no anti-bot friction — and
return structured JSON: a whole thread (jobs) or a page of comment hits
(questions), each comment keeping its id as the chunk's permalink
(DESIGN.md §3).
"""

import json
import logging
from typing import Any, Literal
from urllib.parse import urlparse

from backend.scraper.fetcher import Page
from backend.scraper.sources._base import MIN_CHUNK_CHARS, Chunk, clean_html

logger = logging.getLogger(__name__)

_ALGOLIA_SEARCH_URL = (
    "https://hn.algolia.com/api/v1/search_by_date?tags=story,author_whoishiring&hitsPerPage=10"
)
_ALGOLIA_SEARCH_PATH = "/api/v1/search_by_date"
_ALGOLIA_ITEM_URL = "https://hn.algolia.com/api/v1/items/{id}"
_HN_PERMALINK = "https://news.ycombinator.com/item?id={id}"
_WHO_IS_HIRING_PREFIX = "Ask HN: Who is hiring?"

_INTERVIEW_SEARCH_URL = (
    "https://hn.algolia.com/api/v1/search_by_date"
    "?query=%22interview%20questions%22&tags=comment&hitsPerPage=50"
)


class HNJobs:
    """HN "Who is hiring?" thread → one Chunk per top-level comment."""

    kind: Literal["jobs", "questions"] = "jobs"

    def seed_urls(self) -> list[str]:
        return [_ALGOLIA_SEARCH_URL]

    def next_links(self, page: Page) -> list[str]:
        # A thread page is complete in itself — no pagination via Algolia.
        return [_latest_hiring_thread_url(page.raw)] if _is_search_page(page.url) else []

    def split_items(self, page: Page) -> list[Chunk]:
        # The search page only points at the thread.
        return [] if _is_search_page(page.url) else _thread_chunks(page.raw)


class HNInterviews:
    """HN comments matching "interview questions" → one Chunk per hit."""

    kind: Literal["jobs", "questions"] = "questions"

    def seed_urls(self) -> list[str]:
        return [_INTERVIEW_SEARCH_URL]

    def next_links(self, page: Page) -> list[str]:
        return []  # one search page of recent comments is the whole scrape

    def split_items(self, page: Page) -> list[Chunk]:
        return _comment_hit_chunks(page.raw)


def _is_search_page(url: str) -> bool:
    """Match by path: the pipeline normalizes URLs, so query encoding may differ."""
    return urlparse(url).path == _ALGOLIA_SEARCH_PATH


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
        cleaned = clean_html(text)
        if len(cleaned) < MIN_CHUNK_CHARS:
            skipped += 1
            continue
        chunks.append(Chunk(text=cleaned, url=_HN_PERMALINK.format(id=comment["id"])))
    logger.info("thread %s: %d chunks, %d skipped", thread.get("id"), len(chunks), skipped)
    return chunks


def _comment_hit_chunks(raw: str) -> list[Chunk]:
    """Turn an Algolia comment-search payload into one chunk per comment hit."""
    payload = json.loads(raw)
    hits = payload.get("hits") if isinstance(payload, dict) else None
    if not isinstance(hits, list):
        raise ValueError("not an Algolia comment-search payload")
    chunks: list[Chunk] = []
    skipped = 0
    for hit in hits:
        comment: dict[str, Any] = hit
        text = clean_html(str(comment.get("comment_text") or ""))
        if len(text) < MIN_CHUNK_CHARS:
            skipped += 1
            continue
        chunks.append(Chunk(text=text, url=_HN_PERMALINK.format(id=comment["objectID"])))
    logger.info("comment search: %d chunks, %d skipped", len(chunks), skipped)
    return chunks
