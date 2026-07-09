"""RemoteOK jobs: public JSON API, no login, no anti-bot friction (PHASE2.md step 7).

Already-structured fields still go through the same LLM extraction path as
every other source — proves a second job source needs no pipeline changes.
"""

import json
import logging
from typing import Literal

from backend.scraper.fetcher import Page
from backend.scraper.sources._base import MIN_CHUNK_CHARS, Chunk, clean_html, collapse_whitespace

logger = logging.getLogger(__name__)

_REMOTEOK_API_URL = "https://remoteok.com/api"


class RemoteOK:
    """RemoteOK's public API → one Chunk per listing, url = RemoteOK's own page."""

    kind: Literal["jobs", "questions"] = "jobs"

    def seed_urls(self) -> list[str]:
        return [_REMOTEOK_API_URL]

    def next_links(self, page: Page) -> list[str]:
        return []  # one API call returns every current listing, no pagination

    def split_items(self, page: Page) -> list[Chunk]:
        return _remoteok_chunks(page.raw)


def _remoteok_chunks(raw: str) -> list[Chunk]:
    """Turn a RemoteOK API payload into one chunk per listing.

    The first element is always a legal/attribution notice, not a job — it has
    no "id" field, which is how we tell it apart. `url` is RemoteOK's own
    listing page (not `apply_url`), satisfying their API's link-back term.
    """
    listings = json.loads(raw)
    if not isinstance(listings, list):
        raise ValueError("not a RemoteOK API payload")
    chunks: list[Chunk] = []
    skipped = 0
    for listing in listings:
        if not isinstance(listing, dict) or "id" not in listing:
            continue  # the legal notice, or anything else unrecognized
        summary = (
            f"{listing.get('position', '')} at {listing.get('company', '')}. "
            f"Location: {listing.get('location', '')}. "
            f"Salary range: {listing.get('salary_min', 0)}-{listing.get('salary_max', 0)}. "
            f"{clean_html(str(listing.get('description', '')))}"
        )
        text = collapse_whitespace(summary)
        if len(text) < MIN_CHUNK_CHARS or not listing.get("url"):
            skipped += 1
            continue
        chunks.append(Chunk(text=text, url=str(listing["url"])))
    logger.info("remoteok: %d chunks, %d skipped", len(chunks), skipped)
    return chunks
