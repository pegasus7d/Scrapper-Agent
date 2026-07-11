"""Tests for GET /sources/health (PHASE12.md step 1) — TestClient over an
in-memory DB; no real network happens (health.check_all_sources is faked
at the boundary this route calls through)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool

from backend.api import routes_sources
from backend.api.main import create_app
from backend.db import migrate, vectors
from backend.scraper.health import SourceHealth


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


def test_sources_health_returns_every_probe_result(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_results = [
        SourceHealth(name="hn-jobs", kind="jobs", status="ok", detail=None),
        SourceHealth(
            name="wwr", kind="jobs", status="blocked", detail="disallowed by robots.txt: x"
        ),
        SourceHealth(name="yc", kind="discovery", status="unreachable", detail="HTTP 500"),
    ]
    monkeypatch.setattr(routes_sources, "check_all_sources", lambda: fake_results)

    response = client.get("/api/sources/health")

    assert response.status_code == 200
    assert response.json() == [
        {"name": "hn-jobs", "kind": "jobs", "status": "ok", "detail": None},
        {
            "name": "wwr",
            "kind": "jobs",
            "status": "blocked",
            "detail": "disallowed by robots.txt: x",
        },
        {"name": "yc", "kind": "discovery", "status": "unreachable", "detail": "HTTP 500"},
    ]


def test_sources_health_empty_registry_returns_empty_list(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(routes_sources, "check_all_sources", lambda: [])
    response = client.get("/api/sources/health")
    assert response.status_code == 200
    assert response.json() == []
