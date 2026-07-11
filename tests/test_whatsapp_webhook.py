"""Tests for WhatsApp webhook parsing (PHASE13.md step 10) — pure
functions, no network, no real Meta account (CLAUDE.md)."""

from backend.whatsapp.webhook import extract_message_texts, verify_challenge


def test_verify_challenge_echoes_back_on_a_real_match() -> None:
    assert verify_challenge("subscribe", "secret", "12345", "secret") == "12345"


def test_verify_challenge_fails_closed_when_no_token_configured_yet() -> None:
    # Real state before the user completes PHASE13.md step 9's setup.
    assert verify_challenge("subscribe", "anything", "12345", None) is None


def test_verify_challenge_rejects_a_wrong_token() -> None:
    assert verify_challenge("subscribe", "wrong", "12345", "secret") is None


def test_verify_challenge_rejects_a_non_subscribe_mode() -> None:
    assert verify_challenge("unsubscribe", "secret", "12345", "secret") is None


def test_verify_challenge_rejects_a_missing_challenge() -> None:
    assert verify_challenge("subscribe", "secret", None, "secret") is None


def _payload_with_texts(*bodies: str) -> dict:
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [{"text": {"body": body}} for body in bodies],
                        },
                        "field": "messages",
                    }
                ]
            }
        ]
    }


def test_extract_message_texts_reads_real_message_bodies() -> None:
    payload = _payload_with_texts("check this out: https://example.com/job/1", "hello")
    assert extract_message_texts(payload) == [
        "check this out: https://example.com/job/1",
        "hello",
    ]


def test_extract_message_texts_ignores_non_message_event_shapes() -> None:
    # A real status-update event (delivered/read) — no "messages" key at all.
    payload = {
        "entry": [
            {"changes": [{"value": {"statuses": [{"status": "delivered"}]}, "field": "messages"}]}
        ]
    }
    assert extract_message_texts(payload) == []


def test_extract_message_texts_handles_an_empty_payload() -> None:
    assert extract_message_texts({}) == []


def test_extract_message_texts_skips_malformed_entries_without_crashing() -> None:
    payload = {"entry": [{"changes": [{"value": "not a dict"}]}, "not a dict either"]}
    assert extract_message_texts(payload) == []
