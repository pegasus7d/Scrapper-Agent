"""Tests for the company discovery/resolution/scrape endpoints (PHASE7.md
steps 5-7) — TestClient over an in-memory DB; no real network happens
(mocked)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.api import routes_companies
from backend.api.main import create_app
from backend.db import migrate, repo, vectors
from backend.db.models import Run
from backend.scraper import discovery as discovery_module
from backend.scraper.discovery import DiscoveredCompany
from backend.scraper.resolve import ResolutionSummary


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
def client(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    def fake_run_scrape_task(run_id: int) -> None:
        with Session(engine) as session:
            run = session.get(Run, run_id)
            assert run is not None
            repo.finish_run(session, run)

    # Execution is pipeline.py's own job (tested in test_pipeline); here we
    # only verify the wiring, same fake used in test_api.py's client fixture.
    monkeypatch.setattr(routes_companies, "run_scrape_task", fake_run_scrape_task)
    return TestClient(create_app(engine, start_consumer=False))


def test_list_companies_starts_empty(client: TestClient) -> None:
    response = client.get("/api/companies")
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0}


def test_discover_companies_saves_real_names_and_batch(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        discovery_module,
        "discover_yc_companies",
        lambda fetcher: [
            DiscoveredCompany(name="DoorDash", batch="Summer 2013"),
            DiscoveredCompany(name="Airbnb", batch=None),
        ],
    )
    response = client.post("/api/companies/discover")
    assert response.status_code == 200
    assert response.json() == {"discovered": 2, "total": 2}

    listed = client.get("/api/companies").json()["items"]
    by_name = {item["name"]: item for item in listed}
    assert by_name.keys() == {"DoorDash", "Airbnb"}
    assert by_name["DoorDash"]["batch"] == "Summer 2013"
    assert by_name["Airbnb"]["batch"] is None


def test_discover_companies_is_idempotent(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        discovery_module,
        "discover_yc_companies",
        lambda fetcher: [DiscoveredCompany(name="DoorDash", batch=None)],
    )
    client.post("/api/companies/discover")
    second = client.post("/api/companies/discover")
    assert second.json() == {"discovered": 0, "total": 1}


def test_discover_companies_largest_us_companies_source(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        discovery_module, "discover_largest_us_companies", lambda fetcher: ["Walmart", "Amazon"]
    )
    response = client.post("/api/companies/discover", params={"source": "largest_us_companies"})
    assert response.status_code == 200
    assert response.json() == {"discovered": 2, "total": 2}

    listed = client.get("/api/companies").json()["items"]
    by_name = {item["name"]: item for item in listed}
    assert by_name["Walmart"]["source"] == "largest_us_companies"
    assert by_name["Walmart"]["batch"] is None


def test_discover_companies_rejects_an_unknown_source(client: TestClient) -> None:
    response = client.post("/api/companies/discover", params={"source": "bogus"})
    assert response.status_code == 422


def test_list_companies_filters_by_source(client: TestClient, engine: Engine) -> None:
    with Session(engine) as session:
        repo.save_company(session, "DoorDash", source="yc")
        repo.save_company(session, "Walmart", source="largest_us_companies")

    response = client.get("/api/companies", params={"source": "largest_us_companies"})
    names = {item["name"] for item in response.json()["items"]}
    assert names == {"Walmart"}


def test_resolve_companies_returns_the_real_summary(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, engine: Engine
) -> None:
    with Session(engine) as session:
        repo.save_company(session, "Airbnb")
        repo.save_company(session, "Deel")

    monkeypatch.setattr(
        routes_companies,
        "resolve_unresolved_companies",
        lambda session: ResolutionSummary(checked=2, resolved=1),
    )
    response = client.post("/api/companies/resolve")
    assert response.status_code == 200
    assert response.json() == {"checked": 2, "resolved": 1}


def test_scrape_company_returns_404_for_an_unknown_id(client: TestClient) -> None:
    assert client.post("/api/companies/999/scrape").status_code == 404


def test_scrape_company_returns_422_for_an_unresolved_company(
    client: TestClient, engine: Engine
) -> None:
    with Session(engine) as session:
        repo.save_company(session, "Deel")
        items, _ = repo.list_companies(session)
        company_id = items[0].id

    response = client.post(f"/api/companies/{company_id}/scrape")
    assert response.status_code == 422


def test_scrape_company_enqueues_a_real_run_for_a_resolved_company(
    client: TestClient, engine: Engine
) -> None:
    with Session(engine) as session:
        repo.save_company(session, "Airbnb")
        items, _ = repo.list_companies(session)
        company = items[0]
        repo.mark_company_checked(session, company, slug="airbnb", ats_provider="greenhouse")
        company_id = company.id

    response = client.post(f"/api/companies/{company_id}/scrape")
    assert response.status_code == 201
    run_id = response.json()["run_id"]

    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.source == "company:airbnb"
        assert run.kind == "jobs"


def test_scrape_company_rejects_a_second_run_while_one_is_active(
    client: TestClient, engine: Engine
) -> None:
    with Session(engine) as session:
        repo.save_company(session, "Airbnb")
        items, _ = repo.list_companies(session)
        company = items[0]
        repo.mark_company_checked(session, company, slug="airbnb", ats_provider="greenhouse")
        company_id = company.id
        repo.create_run(session, "jobs", "hn")  # left "running" — no finish_run call

    response = client.post(f"/api/companies/{company_id}/scrape")
    assert response.status_code == 409
