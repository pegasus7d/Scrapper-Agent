"""Tests for the company discovery endpoints (PHASE7.md step 5) — TestClient
over an in-memory DB; no real scraping happens (discovery is mocked)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool

from backend.api import routes_companies
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


def test_list_companies_starts_empty(client: TestClient) -> None:
    response = client.get("/api/companies")
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0}


def test_discover_companies_saves_real_names(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        routes_companies, "discover_yc_companies", lambda fetcher: ["DoorDash", "Airbnb"]
    )
    response = client.post("/api/companies/discover")
    assert response.status_code == 200
    assert response.json() == {"discovered": 2, "total": 2}

    listed = client.get("/api/companies")
    names = {item["name"] for item in listed.json()["items"]}
    assert names == {"DoorDash", "Airbnb"}


def test_discover_companies_is_idempotent(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(routes_companies, "discover_yc_companies", lambda fetcher: ["DoorDash"])
    client.post("/api/companies/discover")
    second = client.post("/api/companies/discover")
    assert second.json() == {"discovered": 0, "total": 1}
