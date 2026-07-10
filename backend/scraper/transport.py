"""Transport: the actual HTTP request execution, chosen per-source
(PHASE4.md step 2). `PageFetcher` keeps every bit of its robots.txt /
retry-backoff / honest-UA policy unchanged no matter which transport
executes the request underneath it.

Confirmed before writing this: no source's `split_items` reads
`Page.markdown` — every source so far is a plain JSON/XML/text API, so
`HttpxTransport` is the default. `ScraplingTransport` stays a real, tested
alternative for the moment a source genuinely needs HTML-cleaning or a
stealth fetch.

`ScraplingTransport` originally wrapped Scrapling's plain `Fetcher`, which
never actually rendered JavaScript despite the class's own docstring
claiming "JS rendering" as its purpose — nothing had exercised that claim
until PHASE7.md step 5 needed a genuinely JS-rendered page
(`ycombinator.com/companies`, empty without real rendering) and it came
back essentially blank. Fixed by switching to `DynamicFetcher` (Camoufox,
a real browser — `camoufox fetch` must be run once locally), which
actually renders. This is the first genuine browser-binary dependency
this project has needed; every other source still defaults to `httpx`.
"""

from dataclasses import dataclass
from typing import Protocol

import httpx
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page
from scrapling.fetchers import DynamicFetcher

_SCROLL_WAIT_MS = 800


@dataclass
class TransportResponse:
    status: int
    body: bytes | str
    text: str  # cleaned page text where the transport can produce one, else ""


class TransportError(Exception):
    """A transport-level failure (timeout, connection error) — distinct from
    an HTTP status, which the caller interprets itself (200/429/5xx/other)."""


class Transport(Protocol):
    def get(self, url: str, *, timeout: int, headers: dict[str, str]) -> TransportResponse: ...


class HttpxTransport:
    """Plain HTTP GET — the default transport for every current source."""

    def get(self, url: str, *, timeout: int, headers: dict[str, str]) -> TransportResponse:
        try:
            response = httpx.get(url, timeout=timeout, headers=headers)
        except httpx.HTTPError as error:
            raise TransportError(str(error)) from error
        return TransportResponse(status=response.status_code, body=response.content, text="")


class ScraplingTransport:
    """Scrapling's real JS-rendering fetch (Camoufox via `DynamicFetcher`) —
    opt-in for a source that needs a genuinely rendered DOM, not just a
    stealthier plain HTTP request.

    `scroll_count` (PHASE8.md step 5): some JS-rendered pages only render
    the first page of results until scrolled — confirmed real for
    `ycombinator.com/companies` (40 companies statically, 120 after 5
    scroll+wait cycles). 0 (default) does no scrolling, unchanged behavior
    for every other current caller; a source that needs more sets it
    explicitly rather than this transport scrolling everywhere by default.
    """

    def __init__(self, scroll_count: int = 0) -> None:
        self._scroll_count = scroll_count

    def _scroll(self, page: Page) -> Page:
        for _ in range(self._scroll_count):
            page.mouse.wheel(0, 3000)
            page.wait_for_timeout(_SCROLL_WAIT_MS)
        return page

    def get(self, url: str, *, timeout: int, headers: dict[str, str]) -> TransportResponse:
        try:
            response = DynamicFetcher.fetch(
                url,
                timeout=timeout * 1000,  # DynamicFetcher's timeout is milliseconds, not seconds
                extra_headers=headers,
                network_idle=True,
                page_action=self._scroll if self._scroll_count else None,
            )
        except PlaywrightError as error:
            raise TransportError(str(error)) from error
        text = response.get_all_text(ignore_tags=("script", "style"))
        return TransportResponse(status=response.status, body=response.body, text=text)
