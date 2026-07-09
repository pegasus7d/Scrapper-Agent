"""Hacker News interview questions: comments matching "interview questions".

Goes through the free Algolia API (DESIGN.md §3) — same underlying API as
`jobs/hn.py`, split into a separate file because the two serve different
domains, not because the fetch mechanism differs.
"""

import json
import logging
from typing import Any, Literal

from backend import config
from backend.scraper.fetcher import Page
from backend.scraper.sources._base import MIN_CHUNK_CHARS, Chunk, clean_html

logger = logging.getLogger(__name__)

_HN_PERMALINK = "https://news.ycombinator.com/item?id={id}"
_INTERVIEW_SEARCH_URL = (
    "https://hn.algolia.com/api/v1/search_by_date"
    "?query=%22interview%20questions%22&tags=comment&hitsPerPage=50"
)


class HNInterviews:
    """HN comments matching "interview questions" → one Chunk per hit."""

    kind: Literal["jobs", "questions"] = "questions"
    transport: Literal["httpx", "scrapling"] = "httpx"
    delay_s: float = config.REQUEST_DELAY_S

    def seed_urls(self) -> list[str]:
        return [_INTERVIEW_SEARCH_URL]

    def next_links(self, page: Page) -> list[str]:
        return []  # one search page of recent comments is the whole scrape

    def split_items(self, page: Page) -> list[Chunk]:
        return _comment_hit_chunks(page.raw)


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
