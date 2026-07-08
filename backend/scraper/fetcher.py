"""Polite page fetching via Scrapling: robots.txt, honest UA, bounded retries.

Policy per DESIGN.md §3: respect robots.txt (cached per domain), identify with
the project User-Agent, retry once on timeout/5xx, back off longer on 429, and
raise FetchError for everything else — the pipeline records it and moves on.
"""

import logging
import time
from dataclasses import dataclass
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from curl_cffi.curl import CurlError
from scrapling.engines.toolbelt.custom import Response
from scrapling.fetchers import Fetcher as ScraplingFetcher

from backend import config

logger = logging.getLogger(__name__)

_RATE_LIMIT_BACKOFF_FACTOR = 4


@dataclass
class Page:
    url: str
    markdown: str  # cleaned page text, for HTML sources
    raw: str  # undecorated body, for JSON API sources


class FetchError(Exception):
    """A page could not be fetched politely and successfully."""


class PageFetcher:
    """Fetches pages as cleaned text, one robots.txt check per domain."""

    def __init__(
        self,
        user_agent: str = config.USER_AGENT,
        delay_s: float = config.REQUEST_DELAY_S,
        retries: int = config.FETCH_RETRIES,
        timeout_s: int = config.FETCH_TIMEOUT_S,
    ) -> None:
        self._user_agent = user_agent
        self._delay_s = delay_s
        self._retries = retries
        self._timeout_s = timeout_s
        self._robots: dict[str, RobotFileParser] = {}

    def fetch(self, url: str) -> Page:
        """Fetch one URL as cleaned page text; raises FetchError on any failure."""
        if not self._allowed_by_robots(url):
            raise FetchError(f"disallowed by robots.txt: {url}")
        response = self._get_with_retry(url)
        markdown = response.get_all_text(ignore_tags=("script", "style"))
        body = response.body
        raw = body.decode("utf-8", "replace") if isinstance(body, bytes) else body
        return Page(url=url, markdown=markdown, raw=raw)

    def _get_with_retry(self, url: str) -> Response:
        attempts = self._retries + 1
        last_error = ""
        for attempt in range(attempts):
            remaining = attempts - attempt - 1
            try:
                response = ScraplingFetcher.get(
                    url,
                    timeout=self._timeout_s,
                    headers={"User-Agent": self._user_agent},
                )
            except (CurlError, OSError) as error:
                last_error = str(error)
                logger.warning("fetch failed (%s), %d retries left: %s", error, remaining, url)
                self._backoff(remaining, self._delay_s)
                continue
            if response.status == 200:
                return response
            if response.status == 429:
                last_error = "HTTP 429"
                logger.warning("rate limited, %d retries left: %s", remaining, url)
                self._backoff(remaining, _RATE_LIMIT_BACKOFF_FACTOR * self._delay_s)
                continue
            if 500 <= response.status < 600:
                last_error = f"HTTP {response.status}"
                logger.warning("%s, %d retries left: %s", last_error, remaining, url)
                self._backoff(remaining, self._delay_s)
                continue
            raise FetchError(f"HTTP {response.status}: {url}")
        raise FetchError(f"{last_error}: {url}")

    def _backoff(self, remaining: int, seconds: float) -> None:
        if remaining > 0:
            time.sleep(seconds)

    def _allowed_by_robots(self, url: str) -> bool:
        domain = urlparse(url).netloc
        parser = self._robots.get(domain)
        if parser is None:
            parser = RobotFileParser(f"https://{domain}/robots.txt")
            try:
                parser.read()
            except OSError as error:
                # Unreachable robots.txt is treated as "no restrictions", the
                # same interpretation browsers and crawlers use.
                logger.warning("robots.txt unreadable for %s: %s", domain, error)
                parser.parse(["User-agent: *", "Allow: /"])
            self._robots[domain] = parser
        return parser.can_fetch(self._user_agent, url)
