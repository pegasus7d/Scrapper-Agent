"""Tests for the API — TestClient over an in-memory DB; no scraping happens."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.api import routes
from backend.api.main import create_app
from backend.db import repo
from backend.db.models import Base, Run
from backend.schemas import JobExtract, QuestionExtract


@pytest.fixture
def engine() -> Engine:
    # StaticPool shares the one in-memory connection across the TestClient's
    # worker threads; a plain :memory: engine would give each thread its own DB.
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def client(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    def fake_run_scrape_task(run_id: int) -> None:
        with Session(engine) as session:
            run = session.get(Run, run_id)
            assert run is not None
            repo.finish_run(session, run)

    # Execution is the pipeline's job (tested in test_pipeline); here we only
    # verify the wiring: enqueuing the task runs it and finishes the run.
    monkeypatch.setattr(routes, "run_scrape_task", fake_run_scrape_task)
    return TestClient(create_app(engine, start_consumer=False))


def seed_items(engine: Engine) -> None:
    with Session(engine) as session:
        run = repo.create_run(session, kind="jobs", source="hn")
        for n in (1, 2, 3):
            job = JobExtract(
                title=f"Engineer {n}",
                company=f"Company {n}",
                location=None,
                salary=None,
                requirements=["Python"],
                apply_url=None,
            )
            repo.save_job(
                session, job, posting_url=f"https://x.com/{n}", source="hn", tier="local", run=run
            )
        question = QuestionExtract(
            company="Acme", role=None, question="Reverse a linked list.", round="phone"
        )
        repo.save_question(
            session, question, source_url="https://r.com/1", source="reddit", tier="local", run=run
        )
        repo.finish_run(session, run)


def test_start_run_returns_id_and_executes(client: TestClient) -> None:
    response = client.post("/api/runs", json={"kind": "jobs", "source": "hn"})
    assert response.status_code == 201
    run_id = response.json()["run_id"]
    run = client.get(f"/api/runs/{run_id}").json()
    assert run["status"] == "completed"  # the (faked) background task ran


def test_start_run_while_active_returns_409(client: TestClient, engine: Engine) -> None:
    with Session(engine) as session:
        repo.create_run(session, kind="jobs", source="hn")
    response = client.post("/api/runs", json={"kind": "jobs", "source": "hn"})
    assert response.status_code == 409


def test_start_run_rejects_unknown_kind_and_source(client: TestClient) -> None:
    assert client.post("/api/runs", json={"kind": "resumes", "source": "hn"}).status_code == 422
    assert client.post("/api/runs", json={"kind": "jobs", "source": "x"}).status_code == 422


def test_cancel_sets_flag_and_404s_when_not_running(client: TestClient, engine: Engine) -> None:
    with Session(engine) as session:
        run = repo.create_run(session, kind="jobs", source="hn")
        run_id = run.id
    assert client.post(f"/api/runs/{run_id}/cancel").json() == {"cancelled": True}
    with Session(engine) as session:
        assert session.get(Run, run_id) is not None
        assert repo.cancel_requested(session, session.get(Run, run_id)) is True  # type: ignore[arg-type]
    assert client.post("/api/runs/999/cancel").status_code == 404


def test_list_runs_newest_first(client: TestClient, engine: Engine) -> None:
    with Session(engine) as session:
        repo.finish_run(session, repo.create_run(session, kind="jobs", source="hn"))
        repo.finish_run(session, repo.create_run(session, kind="jobs", source="hn"))
    body = client.get("/api/runs").json()
    assert body["total"] == 2
    assert [run["id"] for run in body["items"]] == [2, 1]


def test_get_run_missing_returns_404(client: TestClient) -> None:
    assert client.get("/api/runs/999").status_code == 404


def test_list_jobs_with_filter_and_pagination(client: TestClient, engine: Engine) -> None:
    seed_items(engine)
    body = client.get("/api/jobs", params={"limit": 2, "offset": 1}).json()
    assert body["total"] == 3
    assert [job["title"] for job in body["items"]] == ["Engineer 2", "Engineer 1"]
    filtered = client.get("/api/jobs", params={"company": "company 3"}).json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["posting_url"] == "https://x.com/3"


def test_list_jobs_limit_above_100_rejected(client: TestClient) -> None:
    assert client.get("/api/jobs", params={"limit": 101}).status_code == 422


def test_star_job_toggles_and_404s_when_missing(client: TestClient, engine: Engine) -> None:
    seed_items(engine)
    job_id = client.get("/api/jobs").json()["items"][0]["id"]
    starred = client.post(f"/api/jobs/{job_id}/star", json={"starred": True})
    assert starred.status_code == 200
    assert starred.json()["starred"] is True
    assert client.get("/api/jobs", params={"starred": True}).json()["total"] == 1
    assert client.post("/api/jobs/999/star", json={"starred": True}).status_code == 404


def test_export_jobs_json_and_csv(client: TestClient, engine: Engine) -> None:
    seed_items(engine)
    as_json = client.get("/api/jobs/export").json()
    assert len(as_json) == 3
    assert {job["title"] for job in as_json} == {"Engineer 1", "Engineer 2", "Engineer 3"}

    as_csv = client.get("/api/jobs/export", params={"format": "csv"})
    assert as_csv.headers["content-type"].startswith("text/csv")
    lines = as_csv.text.strip().splitlines()
    assert lines[0].startswith("title,company")
    assert len(lines) == 4  # header + 3 jobs


def test_export_questions_json_and_csv(client: TestClient, engine: Engine) -> None:
    seed_items(engine)
    as_json = client.get("/api/questions/export").json()
    assert len(as_json) == 1
    assert as_json[0]["question"] == "Reverse a linked list."

    as_csv = client.get("/api/questions/export", params={"format": "csv", "round": "phone"})
    assert len(as_csv.text.strip().splitlines()) == 2  # header + 1 question
    header_only = client.get("/api/questions/export", params={"format": "csv", "round": "onsite"})
    assert len(header_only.text.strip().splitlines()) == 1


def test_list_questions_with_filters(client: TestClient, engine: Engine) -> None:
    seed_items(engine)
    body = client.get("/api/questions", params={"round": "phone"}).json()
    assert body["total"] == 1
    assert body["items"][0]["question"] == "Reverse a linked list."
    assert client.get("/api/questions", params={"round": "onsite"}).json()["total"] == 0


def test_stats_totals(client: TestClient, engine: Engine) -> None:
    seed_items(engine)
    assert client.get("/api/stats").json() == {
        "jobs": 3,
        "questions": 1,
        "companies": 4,
        "escalation_rate": 0.0,
    }


def test_create_and_list_schedules(client: TestClient) -> None:
    created = client.post("/api/schedules", json={"kind": "jobs", "source": "hn", "every_hours": 6})
    assert created.status_code == 201
    assert created.json()["enabled"] is True
    assert created.json()["last_run_at"] is None

    body = client.get("/api/schedules").json()
    assert len(body) == 1
    assert body[0]["source"] == "hn"


def test_create_schedule_rejects_unknown_source(client: TestClient) -> None:
    response = client.post(
        "/api/schedules", json={"kind": "jobs", "source": "bogus", "every_hours": 6}
    )
    assert response.status_code == 422


def test_create_schedule_rejects_out_of_range_interval(client: TestClient) -> None:
    response = client.post(
        "/api/schedules", json={"kind": "jobs", "source": "hn", "every_hours": 0}
    )
    assert response.status_code == 422


def test_toggle_schedule_flips_enabled_and_404s_when_missing(client: TestClient) -> None:
    created = client.post(
        "/api/schedules", json={"kind": "jobs", "source": "hn", "every_hours": 6}
    ).json()
    toggled = client.post(f"/api/schedules/{created['id']}/toggle", json={"enabled": False})
    assert toggled.status_code == 200
    assert toggled.json()["enabled"] is False
    assert client.post("/api/schedules/999/toggle", json={"enabled": True}).status_code == 404


def test_startup_recovers_stale_runs(engine: Engine) -> None:
    with Session(engine) as session:
        repo.create_run(session, kind="jobs", source="hn")
    create_app(engine, start_consumer=False)
    with Session(engine) as session:
        run = session.get(Run, 1)
        assert run is not None
        assert run.status == "failed"
