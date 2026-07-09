"""RemoteJobs.org jobs: public JSON API, no login, no anti-bot friction
(PHASE5.md step 6). `robots.txt` is `Allow: /` for `User-agent: *`.
"""

import json
import logging
from typing import Literal

from backend import config
from backend.scraper.fetcher import Page
from backend.scraper.sources._base import MIN_CHUNK_CHARS, Chunk, clean_html, collapse_whitespace

logger = logging.getLogger(__name__)

_PAGE_SIZE = 20
_API_URL = f"https://remotejobs.org/api/v1/jobs?category=programming&limit={_PAGE_SIZE}&offset=0"
_NEXT_URL = "https://remotejobs.org/api/v1/jobs?category=programming&limit={limit}&offset={offset}"


class RemoteJobsOrg:
    """RemoteJobs.org's public API → one Chunk per listing, url = the listing's own page."""

    kind: Literal["jobs", "questions"] = "jobs"
    transport: Literal["httpx", "scrapling"] = "httpx"
    delay_s: float = config.REQUEST_DELAY_S

    def seed_urls(self) -> list[str]:
        return [_API_URL]

    def next_links(self, page: Page) -> list[str]:
        pagination = json.loads(page.raw).get("pagination", {})
        if not pagination.get("has_more"):
            return []
        offset = pagination.get("offset", 0)
        limit = pagination.get("limit", _PAGE_SIZE)
        return [_NEXT_URL.format(limit=limit, offset=offset + limit)]

    def split_items(self, page: Page) -> list[Chunk]:
        return _remotejobs_chunks(page.raw)


def _remotejobs_chunks(raw: str) -> list[Chunk]:
    """Turn a RemoteJobs.org API page into one chunk per listing."""
    payload = json.loads(raw)
    listings = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(listings, list):
        raise ValueError("not a RemoteJobs.org API payload")
    chunks: list[Chunk] = []
    skipped = 0
    for listing in listings:
        if not isinstance(listing, dict) or not listing.get("url"):
            skipped += 1
            continue
        company = listing.get("company") or {}
        summary = (
            f"{listing.get('title', '')} at {company.get('name', '')}. "
            f"Location: {listing.get('location', '')}. "
            f"Type: {listing.get('type', '')}. "
            f"{clean_html(str(listing.get('description', '')))}"
        )
        text = collapse_whitespace(summary)
        if len(text) < MIN_CHUNK_CHARS:
            skipped += 1
            continue
        chunks.append(Chunk(text=text, url=str(listing["url"])))
    logger.info("remotejobs: %d chunks, %d skipped", len(chunks), skipped)
    return chunks
