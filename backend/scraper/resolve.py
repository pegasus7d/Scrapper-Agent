"""ATS slug resolution (PHASE7.md step 6): for each undiscovered-provider
company, guess a slug from its name and probe both Greenhouse and Lever's
public job-board APIs — a 404 means "not on this platform," a skip, not a
failure. Confirmed empirically against real discovered companies: guessed
slugs hit well under 100% ("Deel"/"Heap"/"Codecademy"/"DoorDash" 404 on
both, while "Airbnb"/"Checkr"/"Brex"/"Coinbase"/"Figma"/"Stripe" 200 on
Greenhouse) — the phase doc's own expectation, not a bug to chase.

The slug guess strips everything but lowercase alphanumerics — no spaces,
no hyphens. Confirmed real: "The Athletic" resolves as "theathletic" on
Lever, not "the-athletic", which 404s on both platforms.

Both APIs are plain JSON with robots.txt confirmed open for these exact
paths (`boards-api.greenhouse.io/robots.txt` only disallows `/embed/`;
`api.lever.co/robots.txt` allows everything). Probed directly via
`HttpxTransport` rather than `PageFetcher`: this is an existence check that
needs the real per-call HTTP status (200 vs. 404), not PageFetcher's
retry/backoff policy built for full page-content fetches, which collapses
every non-2xx/429/5xx status into one FetchError.
"""

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from backend import config
from backend.db import repo
from backend.scraper.transport import HttpxTransport, TransportError

logger = logging.getLogger(__name__)


@dataclass
class ResolutionSummary:
    checked: int
    resolved: int


_SLUG_STRIP = re.compile(r"[^a-z0-9]")

_ATS_URLS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
    "lever": "https://api.lever.co/v0/postings/{slug}",
}


def guess_slug(name: str) -> str:
    """Normalize a company name into its most likely ATS slug."""
    return _SLUG_STRIP.sub("", name.lower())


def resolve_company(name: str, transport: HttpxTransport | None = None) -> tuple[str, str] | None:
    """Probe Greenhouse then Lever for a company's real job board.

    Returns (slug, provider) on a real hit, None when neither platform has
    this company under the guessed slug — the normal, majority case, not an
    error.
    """
    transport = transport if transport is not None else HttpxTransport()
    slug = guess_slug(name)
    for provider, url_template in _ATS_URLS.items():
        url = url_template.format(slug=slug)
        try:
            response = transport.get(
                url, timeout=config.FETCH_TIMEOUT_S, headers={"User-Agent": config.USER_AGENT}
            )
        except TransportError as error:
            logger.warning("slug probe failed for %s on %s: %s", name, provider, error)
            continue
        if response.status == 200:
            return slug, provider
    return None


def resolve_unresolved_companies(session: Session) -> ResolutionSummary:
    """Probe every company with no known ATS provider yet. Every probed
    company gets last_checked_at set regardless of outcome — a real,
    timestamped record of the attempt, not just the successful ones."""
    unresolved = repo.unresolved_companies(session)
    resolved = 0
    for company in unresolved:
        match = resolve_company(company.name)
        checked_at = datetime.now(UTC)
        if match is None:
            repo.mark_company_checked(session, company, checked_at=checked_at)
            continue
        slug, provider = match
        repo.mark_company_checked(
            session, company, slug=slug, ats_provider=provider, checked_at=checked_at
        )
        resolved += 1
    return ResolutionSummary(checked=len(unresolved), resolved=resolved)
