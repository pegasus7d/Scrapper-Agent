"""WhatsApp Business Platform webhook parsing (PHASE13.md step 10) — the
compliant path checked before scoping this phase: the official Cloud API
only delivers messages sent to a number the user provisions and verifies
through Meta Business, never a channel/group read directly. Fully
unit-testable with scripted payloads; no real Meta account is needed to
build or test this module.
"""

from typing import Any


def verify_challenge(
    mode: str | None, token: str | None, challenge: str | None, configured_token: str | None
) -> str | None:
    """Meta's real GET verification handshake: echo `challenge` back only
    when every condition matches, otherwise None (fails closed — a
    misconfigured or absent verify token must never pass)."""
    if configured_token is None:
        return None
    if mode != "subscribe" or token != configured_token or challenge is None:
        return None
    return challenge


def extract_message_texts(payload: dict[str, Any]) -> list[str]:
    """Real inbound text-message bodies from a Cloud API webhook payload,
    ignoring every other real event shape it also delivers (message
    status updates, template quality changes, etc.) — this app only ever
    wants to read message text, never send or track delivery status."""
    texts: list[str] = []
    for entry in payload.get("entry", []):
        if not isinstance(entry, dict):
            continue
        for change in entry.get("changes", []):
            if not isinstance(change, dict):
                continue
            value = change.get("value")
            if not isinstance(value, dict):
                continue
            for message in value.get("messages", []):
                if not isinstance(message, dict):
                    continue
                text = message.get("text", {})
                body = text.get("body") if isinstance(text, dict) else None
                if isinstance(body, str) and body:
                    texts.append(body)
    return texts
