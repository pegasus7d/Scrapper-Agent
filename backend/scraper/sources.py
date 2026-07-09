"""Source-specific knowledge: seed URLs, page→chunk splitting, link discovery.

Jobs come from Hacker News "Who is hiring?" via the free Algolia API — it
returns the whole thread as structured JSON, and every comment keeps its id,
which becomes the chunk's permalink (DESIGN.md §3) — plus RemoteOK's public
JSON API, which is already structured but still goes through the same
Chunk -> LLM extraction path as everything else, proving a second job source
needs no pipeline changes. Interview questions come from the HN Algolia API:
comments matching "interview questions", one comment = one chunk. (Reddit was
the planned source, but its robots.txt now disallows all crawling — see
DESIGN.md §3.) Malformed payloads raise ValueError; the pipeline records that
against the URL and continues.
"""

import html
import json
import logging
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from backend.scraper.fetcher import Page

logger = logging.getLogger(__name__)

HN = "hn"
REMOTEOK = "remoteok"
HN_INTERVIEWS = "hn-interviews"
JOB_SOURCES = (HN, REMOTEOK)
QUESTION_SOURCES = (HN_INTERVIEWS,)

# Skip one-liners ("email me!") that cannot possibly hold a job posting.
MIN_CHUNK_CHARS = 80

_INTERVIEW_SEARCH_URL = (
    "https://hn.algolia.com/api/v1/search_by_date"
    "?query=%22interview%20questions%22&tags=comment&hitsPerPage=50"
)

_REMOTEOK_API_URL = "https://remoteok.com/api"

_ALGOLIA_SEARCH_URL = (
    "https://hn.algolia.com/api/v1/search_by_date?tags=story,author_whoishiring&hitsPerPage=10"
)
_ALGOLIA_SEARCH_PATH = "/api/v1/search_by_date"
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
    if source == REMOTEOK:
        return [_REMOTEOK_API_URL]
    if source == HN_INTERVIEWS:
        return [_INTERVIEW_SEARCH_URL]
    raise ValueError(f"unknown source: {source}")


def next_links(page: Page, source: str) -> list[str]:
    """Return further URLs discovered on a page (already-seen ones are fine)."""
    if source == HN:
        # A thread page is complete in itself — no pagination via Algolia.
        return [_latest_hiring_thread_url(page.raw)] if _is_search_page(page.url) else []
    if source == REMOTEOK:
        return []  # one API call returns every current listing, no pagination
    if source == HN_INTERVIEWS:
        return []  # one search page of recent comments is the whole scrape
    raise ValueError(f"unknown source: {source}")


def split_items(page: Page, source: str) -> list[Chunk]:
    """Split a page into per-item chunks, each with its own permalink."""
    if source == HN:
        # The search page only points at the thread.
        return [] if _is_search_page(page.url) else _thread_chunks(page.raw)
    if source == REMOTEOK:
        return _remoteok_chunks(page.raw)
    if source == HN_INTERVIEWS:
        return _comment_hit_chunks(page.raw)
    raise ValueError(f"unknown source: {source}")


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
        cleaned = _clean_html(text)
        if len(cleaned) < MIN_CHUNK_CHARS:
            skipped += 1
            continue
        chunks.append(Chunk(text=cleaned, url=_HN_PERMALINK.format(id=comment["id"])))
    logger.info("thread %s: %d chunks, %d skipped", thread.get("id"), len(chunks), skipped)
    return chunks


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
            f"{_clean_html(str(listing.get('description', '')))}"
        )
        text = _WHITESPACE.sub(" ", summary).strip()
        if len(text) < MIN_CHUNK_CHARS or not listing.get("url"):
            skipped += 1
            continue
        chunks.append(Chunk(text=text, url=str(listing["url"])))
    logger.info("remoteok: %d chunks, %d skipped", len(chunks), skipped)
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
        text = _clean_html(str(comment.get("comment_text") or ""))
        if len(text) < MIN_CHUNK_CHARS:
            skipped += 1
            continue
        chunks.append(Chunk(text=text, url=_HN_PERMALINK.format(id=comment["objectID"])))
    logger.info("comment search: %d chunks, %d skipped", len(chunks), skipped)
    return chunks


def _clean_html(text: str) -> str:
    """Strip tags and entities from comment HTML, collapsing whitespace."""
    return _WHITESPACE.sub(" ", html.unescape(_TAGS.sub(" ", text))).strip()
