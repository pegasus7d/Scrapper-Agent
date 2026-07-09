"""Transport: the actual HTTP request execution, chosen per-source
(PHASE4.md step 2). `PageFetcher` keeps every bit of its robots.txt /
retry-backoff / honest-UA policy unchanged no matter which transport
executes the request underneath it.

Confirmed before writing this: no source's `split_items` reads
`Page.markdown` — every source so far is a plain JSON/XML/text API, so
`HttpxTransport` is the default. `ScraplingTransport` stays a real, tested
alternative for the moment a source genuinely needs HTML-cleaning or a
stealth fetch.
"""

from dataclasses import dataclass
from typing import Protocol

import httpx
from curl_cffi.curl import CurlError
from scrapling.fetchers import Fetcher as ScraplingFetcher


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
    """Scrapling's stealth fetch — opt-in for a source that needs HTML
    cleaning or JS rendering."""

    def get(self, url: str, *, timeout: int, headers: dict[str, str]) -> TransportResponse:
        try:
            response = ScraplingFetcher.get(url, timeout=timeout, headers=headers)
        except (CurlError, OSError) as error:
            raise TransportError(str(error)) from error
        text = response.get_all_text(ignore_tags=("script", "style"))
        return TransportResponse(status=response.status, body=response.body, text=text)
