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
from scrapling.fetchers import DynamicFetcher


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
    stealthier plain HTTP request."""

    def get(self, url: str, *, timeout: int, headers: dict[str, str]) -> TransportResponse:
        try:
            response = DynamicFetcher.fetch(
                url,
                timeout=timeout * 1000,  # DynamicFetcher's timeout is milliseconds, not seconds
                extra_headers=headers,
                network_idle=True,
            )
        except PlaywrightError as error:
            raise TransportError(str(error)) from error
        text = response.get_all_text(ignore_tags=("script", "style"))
        return TransportResponse(status=response.status, body=response.body, text=text)
