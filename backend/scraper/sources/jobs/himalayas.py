"""Himalayas jobs: public JSON API, no login, no anti-bot friction
(PHASE5.md step 5). `robots.txt` is `Allow: /` for `User-agent: *`.
"""

import json
import logging
from typing import Literal

from backend import config
from backend.scraper.fetcher import Page
from backend.scraper.sources._base import MIN_CHUNK_CHARS, Chunk, clean_html, collapse_whitespace

logger = logging.getLogger(__name__)

_PAGE_SIZE = 20
_API_URL = f"https://himalayas.app/jobs/api?limit={_PAGE_SIZE}&offset=0"
_NEXT_URL = "https://himalayas.app/jobs/api?limit={limit}&offset={offset}"


class Himalayas:
    """Himalayas' public API → one Chunk per listing, url = the listing's own page."""

    kind: Literal["jobs", "questions"] = "jobs"
    transport: Literal["httpx", "scrapling"] = "httpx"
    delay_s: float = config.REQUEST_DELAY_S

    def seed_urls(self) -> list[str]:
        return [_API_URL]

    def next_links(self, page: Page) -> list[str]:
        # No `links.next` field like Arbeitnow — the next page has to be
        # computed from the response's own offset/limit/totalCount.
        payload = json.loads(page.raw)
        offset = payload.get("offset", 0)
        limit = payload.get("limit", _PAGE_SIZE)
        total = payload.get("totalCount", 0)
        next_offset = offset + limit
        if next_offset >= total:
            return []
        return [_NEXT_URL.format(limit=limit, offset=next_offset)]

    def split_items(self, page: Page) -> list[Chunk]:
        return _himalayas_chunks(page.raw)


def _himalayas_chunks(raw: str) -> list[Chunk]:
    """Turn a Himalayas API page into one chunk per listing."""
    payload = json.loads(raw)
    listings = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(listings, list):
        raise ValueError("not a Himalayas API payload")
    chunks: list[Chunk] = []
    skipped = 0
    for listing in listings:
        if not isinstance(listing, dict) or not listing.get("applicationLink"):
            skipped += 1
            continue
        locations = listing.get("locationRestrictions") or []
        summary = (
            f"{listing.get('title', '')} at {listing.get('companyName', '')}. "
            f"Location: {', '.join(locations) or 'Remote'}. "
            f"Salary: {_salary_text(listing)}. "
            f"{clean_html(str(listing.get('description', '')))}"
        )
        text = collapse_whitespace(summary)
        if len(text) < MIN_CHUNK_CHARS:
            skipped += 1
            continue
        chunks.append(Chunk(text=text, url=str(listing["applicationLink"])))
    logger.info("himalayas: %d chunks, %d skipped", len(chunks), skipped)
    return chunks


def _salary_text(listing: dict[str, object]) -> str:
    lo, hi = listing.get("minSalary"), listing.get("maxSalary")
    if lo is None and hi is None:
        return "not specified"
    return f"{lo or 0}-{hi or 0} {listing.get('currency', '')}/{listing.get('salaryPeriod', '')}"
