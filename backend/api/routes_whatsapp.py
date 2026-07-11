"""WhatsApp job-link intake endpoints (PHASE13.md steps 10-11) — split
from routes.py per CLAUDE.md's 300-line cap, same pattern as
routes_companies.py. Real credentials (PHASE13.md step 9) are a hard stop
only the user can clear; this router is fully wired and testable without
them — `config.whatsapp_verify_token()` simply returns None until then,
which the verification handshake already fails closed on.
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

from backend import config
from backend.api.deps import SessionDep
from backend.scraper.fetcher import PageFetcher
from backend.scraper.pipeline import build_extractor
from backend.whatsapp.intake import extract_urls, intake_job_link
from backend.whatsapp.webhook import extract_message_texts, verify_challenge

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/whatsapp/webhook", response_class=PlainTextResponse)
def verify_webhook(
    hub_mode: str | None = Query(None, alias="hub.mode"),
    hub_verify_token: str | None = Query(None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(None, alias="hub.challenge"),
) -> str:
    """Meta's real one-time verification handshake when the webhook URL is
    first registered — echoes `hub.challenge` back only on a real match."""
    challenge = verify_challenge(
        hub_mode, hub_verify_token, hub_challenge, config.whatsapp_verify_token()
    )
    if challenge is None:
        raise HTTPException(403, "webhook verification failed")
    return challenge


@router.post("/whatsapp/webhook")
def receive_webhook(payload: dict[str, Any], session: SessionDep) -> dict[str, int]:
    """Real inbound message payloads — extracts every shared URL and tries
    to save each as a job. Never raises on a bad link (fetch/extraction
    failures are recorded on their own Run row and skipped, per
    `intake_job_link`); a malformed payload from a source other than Meta
    itself would be the one real reason to reject early, but Meta's own
    retry-with-backoff behavior means a 200 here is the correct response
    even when zero real links were found in this event."""
    urls = [url for text in extract_message_texts(payload) for url in extract_urls(text)]
    if not urls:
        return {"received": 0, "saved": 0}

    fetcher = PageFetcher()
    extractor = build_extractor()
    saved = sum(1 for url in urls if intake_job_link(session, url, fetcher, extractor))
    return {"received": len(urls), "saved": saved}
