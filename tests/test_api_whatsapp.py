"""Tests for the WhatsApp webhook endpoints (PHASE13.md steps 10-11) —
TestClient over an in-memory DB; no real network or Meta account (the
route's own PageFetcher/extractor construction is monkeypatched at the
call site, same pattern test_api_sources.py already uses)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool

from backend import config
from backend.api import routes_whatsapp
from backend.api.main import create_app
from backend.db import migrate, vectors


@pytest.fixture
def engine() -> Engine:
    database_url = "sqlite://"
    engine = create_engine(
        database_url, connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    vectors.register_vec_extension(engine)
    migrate.run_migrations(engine, database_url)
    return engine


@pytest.fixture
def client(engine: Engine) -> TestClient:
    return TestClient(create_app(engine, start_consumer=False))


def test_verify_webhook_echoes_challenge_on_a_real_match(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "whatsapp_verify_token", lambda: "secret")
    response = client.get(
        "/api/whatsapp/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": "secret", "hub.challenge": "12345"},
    )
    assert response.status_code == 200
    assert response.text == "12345"


def test_verify_webhook_rejects_before_setup_is_done(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # config.whatsapp_verify_token() is genuinely None until the user
    # completes PHASE13.md step 9 — asserted explicitly rather than
    # relying on the ambient environment happening to have it unset.
    monkeypatch.setattr(config, "whatsapp_verify_token", lambda: None)
    response = client.get(
        "/api/whatsapp/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": "anything", "hub.challenge": "12345"},
    )
    assert response.status_code == 403


def test_receive_webhook_with_no_urls_is_a_real_no_op(client: TestClient) -> None:
    response = client.post("/api/whatsapp/webhook", json={"entry": []})
    assert response.status_code == 200
    assert response.json() == {"received": 0, "saved": 0}


def test_receive_webhook_extracts_urls_and_calls_intake_per_url(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(routes_whatsapp, "PageFetcher", lambda: object())
    monkeypatch.setattr(routes_whatsapp, "build_extractor", lambda: object())
    monkeypatch.setattr(
        routes_whatsapp,
        "intake_job_link",
        lambda session, url, fetcher, extractor: calls.append(url) or True,
    )

    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [{"text": {"body": "job here: https://example.com/job/1"}}]
                        }
                    }
                ]
            }
        ]
    }
    response = client.post("/api/whatsapp/webhook", json=payload)

    assert response.status_code == 200
    assert response.json() == {"received": 1, "saved": 1}
    assert calls == ["https://example.com/job/1"]
