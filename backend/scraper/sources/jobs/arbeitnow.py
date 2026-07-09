"""Arbeitnow jobs: public JSON API, no login, no anti-bot friction (PHASE3.md step 3).

`robots.txt` has no disallow rules at all. Already-structured fields still go
through the same LLM extraction path as every other source (RemoteOK's
reasoning, PHASE2.md step 7). The API paginates via `links.next` — one
`next_links()` call per page, bounded by `MAX_PAGES_PER_RUN` like every source.
"""

import json
import logging
from typing import Literal

from backend import config
from backend.scraper.fetcher import Page
from backend.scraper.sources._base import MIN_CHUNK_CHARS, Chunk, clean_html, collapse_whitespace

logger = logging.getLogger(__name__)

_API_URL = "https://www.arbeitnow.com/api/job-board-api"


class Arbeitnow:
    """Arbeitnow's public API → one Chunk per listing, url = the listing's own page."""

    kind: Literal["jobs", "questions"] = "jobs"
    transport: Literal["httpx", "scrapling"] = "httpx"
    # Arbeitnow's own API terms say "please do not abuse" — double the
    # global politeness delay between paginated pages.
    delay_s: float = config.REQUEST_DELAY_S * 2

    def seed_urls(self) -> list[str]:
        return [_API_URL]

    def next_links(self, page: Page) -> list[str]:
        next_url = json.loads(page.raw).get("links", {}).get("next")
        return [next_url] if next_url else []

    def split_items(self, page: Page) -> list[Chunk]:
        return _arbeitnow_chunks(page.raw)


def _arbeitnow_chunks(raw: str) -> list[Chunk]:
    """Turn an Arbeitnow API page into one chunk per listing."""
    payload = json.loads(raw)
    listings = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(listings, list):
        raise ValueError("not an Arbeitnow API payload")
    chunks: list[Chunk] = []
    skipped = 0
    for listing in listings:
        if not isinstance(listing, dict) or not listing.get("url"):
            skipped += 1
            continue
        summary = (
            f"{listing.get('title', '')} at {listing.get('company_name', '')}. "
            f"Location: {listing.get('location', '')}. "
            f"Remote: {listing.get('remote', False)}. "
            f"Job type: {', '.join(listing.get('job_types', []))}. "
            f"{clean_html(str(listing.get('description', '')))}"
        )
        text = collapse_whitespace(summary)
        if len(text) < MIN_CHUNK_CHARS:
            skipped += 1
            continue
        chunks.append(Chunk(text=text, url=str(listing["url"])))
    logger.info("arbeitnow: %d chunks, %d skipped", len(chunks), skipped)
    return chunks
