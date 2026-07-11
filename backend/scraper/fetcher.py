"""Polite page fetching: robots.txt, honest UA, bounded retries.

Policy per DESIGN.md §3: respect robots.txt (cached per domain), identify with
the project User-Agent, retry once on timeout/5xx, back off longer on 429, and
raise FetchError for everything else — the pipeline records it and moves on.
The actual request execution is delegated to a `Transport` (`transport.py`,
PHASE4.md step 2), so this policy layer never changes when the transport does.
"""

import logging
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

from backend import config
from backend.scraper.transport import HttpxTransport, Transport, TransportError, TransportResponse

logger = logging.getLogger(__name__)

_RATE_LIMIT_BACKOFF_FACTOR = 4


@dataclass
class Page:
    url: str
    markdown: str  # cleaned page text, for HTML sources
    raw: str  # undecorated body, for JSON API sources


class FetchError(Exception):
    """A page could not be fetched politely and successfully."""


class RobotsDisallowed(FetchError):
    """robots.txt disallows this URL — a FetchError subtype so existing
    `except FetchError` callers (pipeline.py) are unaffected, while callers
    that need to tell "blocked" apart from "unreachable" (health.py,
    PHASE12.md step 1) can catch this specifically instead of parsing the
    error message."""


class PageFetcher:
    """Fetches pages as cleaned text, one robots.txt check per domain."""

    def __init__(
        self,
        transport: Transport | None = None,
        user_agent: str = config.USER_AGENT,
        delay_s: float = config.REQUEST_DELAY_S,
        retries: int = config.FETCH_RETRIES,
        timeout_s: int = config.FETCH_TIMEOUT_S,
    ) -> None:
        self._transport = transport if transport is not None else HttpxTransport()
        self._user_agent = user_agent
        self._delay_s = delay_s
        self._retries = retries
        self._timeout_s = timeout_s
        self._robots: dict[str, RobotFileParser] = {}

    def fetch(self, url: str) -> Page:
        """Fetch one URL as cleaned page text; raises FetchError on any failure."""
        if not self._allowed_by_robots(url):
            raise RobotsDisallowed(f"disallowed by robots.txt: {url}")
        response = self._get_with_retry(url)
        body = response.body
        raw = body.decode("utf-8", "replace") if isinstance(body, bytes) else body
        return Page(url=url, markdown=response.text, raw=raw)

    def _get_with_retry(self, url: str) -> TransportResponse:
        attempts = self._retries + 1
        last_error = ""
        for attempt in range(attempts):
            remaining = attempts - attempt - 1
            try:
                response = self._transport.get(
                    url,
                    timeout=self._timeout_s,
                    headers={"User-Agent": self._user_agent},
                )
            except TransportError as error:
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
            parser.parse(self._fetch_robots_lines(domain))
            self._robots[domain] = parser
        return parser.can_fetch(self._user_agent, url)

    def _fetch_robots_lines(self, domain: str) -> list[str]:
        """Fetch robots.txt with our own honest UA, not RobotFileParser.read()'s
        internal urlopen call — that sends urllib's generic default UA, which
        some sites (e.g. WeWorkRemotely) 403 outright, silently producing a
        false "disallow everything" even though the real robots.txt is open.
        """
        request = Request(f"https://{domain}/robots.txt", headers={"User-Agent": self._user_agent})
        try:
            with urlopen(request, timeout=self._timeout_s) as response:
                body: bytes = response.read()
                return body.decode("utf-8", "replace").splitlines()
        except HTTPError as error:
            if error.code == 404:
                return ["User-agent: *", "Allow: /"]  # no robots.txt = no restrictions
            if error.code in (401, 403):
                # An explicit denial to our own honest, identified UA — respect it.
                logger.warning("robots.txt forbidden for %s: %s", domain, error)
                return ["User-agent: *", "Disallow: /"]
            logger.warning("robots.txt error for %s: %s — treating as unrestricted", domain, error)
            return ["User-agent: *", "Allow: /"]
        except URLError as error:
            # Unreachable robots.txt is treated as "no restrictions", the same
            # interpretation browsers and crawlers use.
            logger.warning("robots.txt unreachable for %s: %s", domain, error)
            return ["User-agent: *", "Allow: /"]
