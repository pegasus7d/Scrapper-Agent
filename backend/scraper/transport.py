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

import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import httpx
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page
from scrapling.fetchers import DynamicFetcher

_SCROLL_WAIT_MS = 800
_LOAD_MORE_WAIT_MS = 1500
_CONSECUTIVE_ERROR_LIMIT = 3


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

    `tab_selector`/`load_more_selector` (PHASE8.md step 9): a different real
    shape, confirmed for `sequoiacap.com/our-companies` — the full,
    accessible company table lives inside a Bootstrap tab-pane that isn't
    shown by default (`tab_selector` clicks it open once) and is itself
    paginated behind a "Load More" button, not a scroll (`load_more_selector`
    clicks it repeatedly). Confirmed real: 52 companies (A-C only) before any
    clicking, 412 (A-Z) after clicking "Load More" until it stops responding
    — the button is removed from the DOM once the last page loads, so a
    click timeout there is the real, expected termination condition, not a
    failure to swallow silently elsewhere.
    """

    def __init__(
        self,
        scroll_count: int = 0,
        tab_selector: str | None = None,
        load_more_selector: str | None = None,
        load_more_max_clicks: int = 20,
    ) -> None:
        self._scroll_count = scroll_count
        self._tab_selector = tab_selector
        self._load_more_selector = load_more_selector
        self._load_more_max_clicks = load_more_max_clicks

    def _scroll(self, page: Page) -> Page:
        for _ in range(self._scroll_count):
            page.mouse.wheel(0, 3000)
            page.wait_for_timeout(_SCROLL_WAIT_MS)
        return page

    def _click_load_more(self, page: Page) -> Page:
        """Confirmed real and necessary against sequoiacap.com (PHASE8.md
        step 9): each click triggers a FacetWP AJAX re-render that replaces
        the whole results table, so the *next* button must be re-queried
        fresh each iteration (a stale ElementHandle from a prior iteration
        raises a generic Playwright Error, not a clean timeout) — a single
        click failure is a transient race with that in-flight AJAX call,
        not proof the button is gone for good, so up to
        `_CONSECUTIVE_ERROR_LIMIT` consecutive failures are tolerated and
        retried before giving up. `button is None` (the real end-of-results
        signal — the button is removed from the DOM once the last page has
        loaded) still stops immediately.
        """
        if self._tab_selector:
            tab = page.query_selector(self._tab_selector)
            if tab:
                tab.click()
                # Best-effort settle; the click loop below still re-checks for real.
                with contextlib.suppress(PlaywrightError):
                    page.wait_for_selector(
                        f"{self._load_more_selector}, table tbody tr", timeout=10_000
                    )
        consecutive_errors = 0
        for _ in range(self._load_more_max_clicks):
            button = page.query_selector(self._load_more_selector)  # type: ignore[arg-type]
            if not button:
                break
            try:
                button.click(timeout=8000)
                consecutive_errors = 0
            except PlaywrightError:
                consecutive_errors += 1
                if consecutive_errors >= _CONSECUTIVE_ERROR_LIMIT:
                    break
                page.wait_for_timeout(_LOAD_MORE_WAIT_MS)
                continue
            page.wait_for_timeout(_LOAD_MORE_WAIT_MS)
        return page

    def _page_action(self) -> Callable[[Page], Page] | None:
        if self._load_more_selector:
            return self._click_load_more
        if self._scroll_count:
            return self._scroll
        return None

    def get(self, url: str, *, timeout: int, headers: dict[str, str]) -> TransportResponse:
        try:
            response = DynamicFetcher.fetch(
                url,
                timeout=timeout * 1000,  # DynamicFetcher's timeout is milliseconds, not seconds
                extra_headers=headers,
                network_idle=True,
                page_action=self._page_action(),
            )
        except PlaywrightError as error:
            raise TransportError(str(error)) from error
        text = response.get_all_text(ignore_tags=("script", "style"))
        return TransportResponse(status=response.status, body=response.body, text=text)
