"""Source-specific knowledge: seed URLs, page→chunk splitting, link discovery.

Jobs come from Hacker News "Who is hiring?" via the free Algolia API — it
returns the whole thread as structured JSON, and every comment keeps its id,
which becomes the chunk's permalink (DESIGN.md §3). Interview questions come
from Reddit's public .json listing endpoints: one post = one chunk, with the
post's permalink as the chunk URL. Malformed payloads raise ValueError; the
pipeline records that against the URL and continues.
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
REDDIT = "reddit"
JOB_SOURCES = (HN,)
QUESTION_SOURCES = (REDDIT,)

# Skip one-liners ("email me!") that cannot possibly hold a job posting.
MIN_CHUNK_CHARS = 80

_REDDIT_SUBS = ("cscareerquestions", "leetcode")
_REDDIT_LISTING_URL = "https://www.reddit.com/r/{sub}/top.json?t=week&limit=25"
_REDDIT_PERMALINK = "https://www.reddit.com{permalink}"

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
    if source == REDDIT:
        return [_REDDIT_LISTING_URL.format(sub=sub) for sub in _REDDIT_SUBS]
    raise ValueError(f"unknown source: {source}")


def next_links(page: Page, source: str) -> list[str]:
    """Return further URLs discovered on a page (already-seen ones are fine)."""
    if source == HN:
        # A thread page is complete in itself — no pagination via Algolia.
        return [_latest_hiring_thread_url(page.raw)] if _is_search_page(page.url) else []
    if source == REDDIT:
        return []  # the seed listings are all we scrape — posts, not comment threads
    raise ValueError(f"unknown source: {source}")


def split_items(page: Page, source: str) -> list[Chunk]:
    """Split a page into per-item chunks, each with its own permalink."""
    if source == HN:
        # The search page only points at the thread.
        return [] if _is_search_page(page.url) else _thread_chunks(page.raw)
    if source == REDDIT:
        return _reddit_chunks(page.raw)
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


def _reddit_chunks(raw: str) -> list[Chunk]:
    """Turn a Reddit .json listing into one chunk per substantive post."""
    listing = json.loads(raw)
    children = listing.get("data", {}).get("children") if isinstance(listing, dict) else None
    if not isinstance(children, list):
        raise ValueError("not a Reddit listing payload")
    chunks: list[Chunk] = []
    skipped = 0
    for child in children:
        post: dict[str, Any] = child.get("data", {})
        text = _clean_html(f"{post.get('title', '')} {post.get('selftext', '')}")
        if post.get("stickied") or len(text) < MIN_CHUNK_CHARS:
            skipped += 1  # mod announcements and link-only posts hold no questions
            continue
        chunks.append(Chunk(text=text, url=_REDDIT_PERMALINK.format(permalink=post["permalink"])))
    logger.info("reddit listing: %d chunks, %d skipped", len(chunks), skipped)
    return chunks


def _clean_html(text: str) -> str:
    """Strip tags and entities from comment HTML, collapsing whitespace."""
    return _WHITESPACE.sub(" ", html.unescape(_TAGS.sub(" ", text))).strip()
