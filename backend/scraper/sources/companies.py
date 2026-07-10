"""Company-driven job sources (PHASE7.md step 7): unlike every other Source,
these aren't declared as a fixed `SOURCES` dict entry — they're built at
scrape time from a resolved `Company` row's own slug/provider
(`register_company_source`, `sources/__init__.py`), keeping the registry
dynamic and driven by the companies table (steps 5/6) instead of a
hand-maintained entry per company — the user's own explicit direction.

Real response shapes confirmed before writing this (PHASE7.md step 7):
Greenhouse's `?content=true` job list content field is HTML, but
double-HTML-escaped inside the JSON string itself (`&lt;div&gt;` as literal
text, not a real `<div>` tag) — `html.unescape()` must run before
`clean_html()`'s own tag-stripping, or the tags are never found. Lever's
postings already ship a clean plain-text field (`descriptionPlain`), no HTML
handling needed at all. Both APIs return every posting on one page —
confirmed real (Airbnb: 209 jobs, one response) — `next_links()` is always
`[]`.
"""

import html
import json
import logging
from typing import Literal

from backend import config
from backend.scraper.fetcher import Page
from backend.scraper.sources._base import MIN_CHUNK_CHARS, Chunk, clean_html, collapse_whitespace

logger = logging.getLogger(__name__)


class GreenhouseCompanySource:
    """One resolved company's Greenhouse job board."""

    kind: Literal["jobs", "questions"] = "jobs"
    transport: Literal["httpx", "scrapling"] = "httpx"
    delay_s: float = config.REQUEST_DELAY_S

    def __init__(self, slug: str, company_name: str) -> None:
        self._slug = slug
        self._company_name = company_name

    def seed_urls(self) -> list[str]:
        return [f"https://boards-api.greenhouse.io/v1/boards/{self._slug}/jobs?content=true"]

    def next_links(self, page: Page) -> list[str]:
        return []  # confirmed real: one response holds every posting

    def split_items(self, page: Page) -> list[Chunk]:
        return _greenhouse_chunks(page.raw, self._company_name)


class LeverCompanySource:
    """One resolved company's Lever job board."""

    kind: Literal["jobs", "questions"] = "jobs"
    transport: Literal["httpx", "scrapling"] = "httpx"
    delay_s: float = config.REQUEST_DELAY_S

    def __init__(self, slug: str, company_name: str) -> None:
        self._slug = slug
        self._company_name = company_name

    def seed_urls(self) -> list[str]:
        return [f"https://api.lever.co/v0/postings/{self._slug}?mode=json"]

    def next_links(self, page: Page) -> list[str]:
        return []

    def split_items(self, page: Page) -> list[Chunk]:
        return _lever_chunks(page.raw, self._company_name)


def _greenhouse_chunks(raw: str, company_name: str) -> list[Chunk]:
    payload = json.loads(raw)
    jobs = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(jobs, list):
        raise ValueError("not a Greenhouse boards API payload")
    chunks: list[Chunk] = []
    skipped = 0
    for job in jobs:
        if not isinstance(job, dict) or not job.get("absolute_url"):
            skipped += 1
            continue
        location = job.get("location")
        location_name = location.get("name", "") if isinstance(location, dict) else ""
        # Double-HTML-escaped — unescape before stripping tags, or clean_html()
        # never finds a literal "<" to match (see module docstring).
        content = clean_html(html.unescape(str(job.get("content", ""))))
        summary = f"{job.get('title', '')} at {company_name}. Location: {location_name}. {content}"
        text = collapse_whitespace(summary)
        if len(text) < MIN_CHUNK_CHARS:
            skipped += 1
            continue
        chunks.append(Chunk(text=text, url=str(job["absolute_url"])))
    logger.info("greenhouse/%s: %d chunks, %d skipped", company_name, len(chunks), skipped)
    return chunks


def _lever_chunks(raw: str, company_name: str) -> list[Chunk]:
    postings = json.loads(raw)
    if not isinstance(postings, list):
        raise ValueError("not a Lever postings API payload")
    chunks: list[Chunk] = []
    skipped = 0
    for posting in postings:
        if not isinstance(posting, dict) or not posting.get("hostedUrl"):
            skipped += 1
            continue
        categories = posting.get("categories")
        location = categories.get("location", "") if isinstance(categories, dict) else ""
        description = collapse_whitespace(str(posting.get("descriptionPlain", "")))
        title = posting.get("text", "")
        summary = f"{title} at {company_name}. Location: {location}. {description}"
        text = collapse_whitespace(summary)
        if len(text) < MIN_CHUNK_CHARS:
            skipped += 1
            continue
        chunks.append(Chunk(text=text, url=str(posting["hostedUrl"])))
    logger.info("lever/%s: %d chunks, %d skipped", company_name, len(chunks), skipped)
    return chunks
