"""Tests for the application-attempt endpoints (PHASE11.md step 6) —
TestClient over an in-memory DB; the real Huey tasks are faked (same
pattern test_api.py already uses for scrape runs) so these tests verify
the API's own wiring, not planner/executor internals (covered in their
own test files)."""

from datetime import UTC, datetime

import pytest
import sqlite_vec
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend import config
from backend.api import routes_applications
from backend.api.main import create_app
from backend.autoapply import events
from backend.autoapply.profile import save_profile, save_resume_markdown
from backend.db import migrate, repo, vectors
from backend.db.models import Company, Job
from backend.schemas import JobExtract


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
def plan_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, int, int, bool]]:
    calls: list[tuple[int, int, int, bool]] = []
    monkeypatch.setattr(
        routes_applications,
        "plan_application_page_task",
        lambda application_id, job_id, company_id, is_first: calls.append(
            (application_id, job_id, company_id, is_first)
        ),
    )
    return calls


@pytest.fixture
def execute_calls(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    calls: list[int] = []
    monkeypatch.setattr(
        routes_applications,
        "execute_application_task",
        lambda application_id: calls.append(application_id),
    )
    return calls


@pytest.fixture
def client(
    engine: Engine,
    plan_calls: list,
    execute_calls: list,  # noqa: ARG001 - fixtures for side effects
) -> TestClient:
    return TestClient(create_app(engine, start_consumer=False))


def _vec(nonzero_dims: list[float]) -> bytes:
    padded = nonzero_dims + [0.0] * (config.EMBED_DIM - len(nonzero_dims))
    return sqlite_vec.serialize_float32(padded)


def _make_ready_company_and_job(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> tuple[int, int]:
    """A company/job pair that passes every real pre-flight gate."""
    monkeypatch.setattr("backend.autoapply.matching.embed_text", lambda text: _vec([1.0, 0.0]))
    with Session(engine) as session:
        company = Company(name="Acme", ats_provider="lever", discovered_at=datetime.now(UTC))
        session.add(company)
        session.commit()

        save_profile(
            session,
            phone="555-0100",
            current_salary=None,
            expected_salary=None,
            work_authorization=None,
            relocation=None,
            start_date_availability=None,
        )
        save_resume_markdown(session, "Experienced backend engineer skilled in Python.")

        run = repo.create_run(session, kind="jobs", source="hn")
        extract = JobExtract(
            title="Backend Engineer",
            company="Acme",
            location=None,
            salary=None,
            requirements=["Python"],
            apply_url=None,
        )
        repo.save_job(
            session,
            extract,
            posting_url="https://x.com/acme-job",
            source="hn",
            tier="local",
            run=run,
            embed=lambda _: _vec([1.0, 0.0]),
        )
        from sqlalchemy import select

        job_id = session.scalar(select(Job.id).where(Job.posting_url == "https://x.com/acme-job"))
        assert job_id is not None
        company_id = company.id
    return company_id, job_id


def test_start_application_404s_when_job_missing(client: TestClient) -> None:
    response = client.post("/api/applications", json={"job_id": 999})
    assert response.status_code == 404


def test_start_application_409s_when_another_attempt_active(
    client: TestClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    company_id, job_id = _make_ready_company_and_job(engine, monkeypatch)
    with Session(engine) as session:
        events.start_application(session, company_id=company_id)  # a real "pending" row

    response = client.post("/api/applications", json={"job_id": job_id})
    assert response.status_code == 409


def test_start_application_422s_on_a_preflight_failure(
    client: TestClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    with Session(engine) as session:
        run = repo.create_run(session, kind="jobs", source="hn")
        extract = JobExtract(
            title="Backend Engineer",
            company="Unresolved Co",
            location=None,
            salary=None,
            requirements=["Python"],
            apply_url=None,
        )
        repo.save_job(
            session,
            extract,
            posting_url="https://x.com/unresolved",
            source="hn",
            tier="local",
            run=run,
        )
        from sqlalchemy import select

        job_id = session.scalar(select(Job.id).where(Job.posting_url == "https://x.com/unresolved"))

    response = client.post("/api/applications", json={"job_id": job_id})
    assert response.status_code == 422


def test_start_application_enqueues_planning_and_returns_201(
    client: TestClient, engine: Engine, monkeypatch: pytest.MonkeyPatch, plan_calls: list
) -> None:
    company_id, job_id = _make_ready_company_and_job(engine, monkeypatch)
    response = client.post("/api/applications", json={"job_id": job_id})
    assert response.status_code == 201
    application_id = response.json()["application_id"]
    assert plan_calls == [(application_id, job_id, company_id, True)]


def test_list_applications_returns_items_and_total(
    client: TestClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    company_id, job_id = _make_ready_company_and_job(engine, monkeypatch)
    with Session(engine) as session:
        events.start_application(session, company_id=company_id, job_id=job_id)

    response = client.get("/api/applications")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "pending"


def test_get_application_returns_row_and_events(
    client: TestClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    company_id, job_id = _make_ready_company_and_job(engine, monkeypatch)
    with Session(engine) as session:
        application = events.start_application(session, company_id=company_id, job_id=job_id)
        events.record_event(session, application, action="detect_fields", success=True)
        application_id = application.id

    response = client.get(f"/api/applications/{application_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["application"]["id"] == application_id
    assert [e["action"] for e in body["events"]] == ["detect_fields"]


def test_get_application_404s_when_missing(client: TestClient) -> None:
    assert client.get("/api/applications/999").status_code == 404


def test_reject_application_marks_rejected(
    client: TestClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    company_id, job_id = _make_ready_company_and_job(engine, monkeypatch)
    with Session(engine) as session:
        application = events.start_application(session, company_id=company_id, job_id=job_id)
        events.mark_awaiting_confirmation(
            session, application, risk_level="high", planned_fields=[]
        )
        application_id = application.id

    response = client.post(f"/api/applications/{application_id}/reject")
    assert response.status_code == 200
    assert response.json() == {"rejected": True}

    detail = client.get(f"/api/applications/{application_id}").json()
    assert detail["application"]["status"] == "rejected"
    assert any(e["action"] == "reject" for e in detail["events"])


def test_reject_application_422s_when_not_awaiting_confirmation(
    client: TestClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    company_id, job_id = _make_ready_company_and_job(engine, monkeypatch)
    with Session(engine) as session:
        application = events.start_application(session, company_id=company_id, job_id=job_id)
        application_id = application.id

    response = client.post(f"/api/applications/{application_id}/reject")
    assert response.status_code == 422


def test_confirm_application_records_event_and_enqueues_executor(
    client: TestClient, engine: Engine, monkeypatch: pytest.MonkeyPatch, execute_calls: list
) -> None:
    company_id, job_id = _make_ready_company_and_job(engine, monkeypatch)
    with Session(engine) as session:
        application = events.start_application(session, company_id=company_id, job_id=job_id)
        events.mark_awaiting_confirmation(
            session, application, risk_level="high", planned_fields=[]
        )
        application_id = application.id

    response = client.post(f"/api/applications/{application_id}/confirm")
    assert response.status_code == 200
    assert response.json() == {"confirmed": True}
    assert execute_calls == [application_id]

    detail = client.get(f"/api/applications/{application_id}").json()
    assert any(e["action"] == "confirm" for e in detail["events"])


def test_kill_switch_get_and_set(client: TestClient) -> None:
    assert client.get("/api/autoapply/kill-switch").json() == {"enabled": False}
    response = client.post("/api/autoapply/kill-switch", json={"enabled": True})
    assert response.json() == {"enabled": True}
    assert client.get("/api/autoapply/kill-switch").json() == {"enabled": True}


def test_company_auto_apply_block_toggle(
    client: TestClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    company_id, _job_id = _make_ready_company_and_job(engine, monkeypatch)
    response = client.post(f"/api/companies/{company_id}/auto-apply-block", json={"blocked": True})
    assert response.status_code == 200
    assert response.json() == {"blocked": True}


def test_company_auto_apply_block_404s_when_missing(client: TestClient) -> None:
    response = client.post("/api/companies/999/auto-apply-block", json={"blocked": True})
    assert response.status_code == 404
