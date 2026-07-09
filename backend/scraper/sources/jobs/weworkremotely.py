"""WeWorkRemotely jobs: public RSS feed, no login, no anti-bot friction
(PHASE3.md step 2). robots.txt is `Allow: /` for `User-agent: *`, only
account/admin paths disallowed.
"""

import logging
import xml.etree.ElementTree as ET
from typing import Literal

from backend import config
from backend.scraper.fetcher import Page
from backend.scraper.sources._base import MIN_CHUNK_CHARS, Chunk, clean_html

logger = logging.getLogger(__name__)

_RSS_URL = "https://weworkremotely.com/categories/remote-programming-jobs.rss"


class WeWorkRemotely:
    """WWR's public RSS feed → one Chunk per `<item>`, url = the job's own page."""

    kind: Literal["jobs", "questions"] = "jobs"
    transport: Literal["httpx", "scrapling"] = "httpx"
    delay_s: float = config.REQUEST_DELAY_S

    def seed_urls(self) -> list[str]:
        return [_RSS_URL]

    def next_links(self, page: Page) -> list[str]:
        return []  # one feed fetch returns every current listing, no pagination

    def split_items(self, page: Page) -> list[Chunk]:
        return _rss_chunks(page.raw)


def _rss_chunks(raw: str) -> list[Chunk]:
    """Turn an RSS feed into one chunk per `<item>`."""
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as error:
        raise ValueError(f"not a valid RSS feed: {error}") from error
    chunks: list[Chunk] = []
    skipped = 0
    for item in root.iterfind(".//item"):
        title = _text(item, "title")
        link = _text(item, "link")
        category = _text(item, "category")
        description = clean_html(_text(item, "description"))
        text = f"{title}. Category: {category}. {description}".strip()
        if len(text) < MIN_CHUNK_CHARS or not link:
            skipped += 1
            continue
        chunks.append(Chunk(text=text, url=link))
    logger.info("weworkremotely: %d chunks, %d skipped", len(chunks), skipped)
    return chunks


def _text(item: ET.Element, tag: str) -> str:
    element = item.find(tag)
    return element.text.strip() if element is not None and element.text else ""
