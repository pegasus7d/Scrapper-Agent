"""Tests for the structured applicant profile endpoints (PHASE10.md step 5)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.api.main import create_app
from backend.autoapply import profile as profile_repo
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


def test_get_profile_returns_all_unset_before_any_save(client: TestClient) -> None:
    response = client.get("/api/profile")
    assert response.status_code == 200
    assert response.json() == {
        "phone": None,
        "current_salary": None,
        "expected_salary": None,
        "work_authorization": None,
        "relocation": None,
        "start_date_availability": None,
        "has_resume": False,
    }


def test_post_profile_saves_and_returns_the_given_values(client: TestClient) -> None:
    body = {
        "phone": "555-0100",
        "current_salary": "$120,000",
        "expected_salary": "$140,000",
        "work_authorization": "US Citizen",
        "relocation": True,
        "start_date_availability": "2 weeks notice",
    }
    response = client.post("/api/profile", json=body)
    assert response.status_code == 200
    assert response.json() == {**body, "has_resume": False}


def test_get_profile_reflects_a_prior_save(client: TestClient) -> None:
    client.post("/api/profile", json={"phone": "555-0100"})
    response = client.get("/api/profile")
    assert response.json()["phone"] == "555-0100"


def test_post_profile_with_no_fields_clears_everything(client: TestClient) -> None:
    client.post("/api/profile", json={"phone": "555-0100"})
    response = client.post("/api/profile", json={})
    assert response.json()["phone"] is None


def test_has_resume_reflects_a_saved_resume_without_a_full_profile_save(
    client: TestClient, engine: Engine
) -> None:
    """A resume upload (PHASE11.md step 1) only ever touches
    resume_markdown -- proven here via the repo function directly, since
    the actual upload endpoint needs a real PDF (covered in
    test_api_resume.py)."""
    with Session(engine) as session:
        profile_repo.save_resume_markdown(session, "# Resume\nBackend engineer.")

    response = client.get("/api/profile")
    assert response.json()["has_resume"] is True
    assert response.json()["phone"] is None  # untouched by the resume save
