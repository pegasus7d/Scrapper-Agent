"""Tests for the API — TestClient over an in-memory DB; no scraping happens."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend import config
from backend.api import routes, routes_runs
from backend.api.main import create_app
from backend.db import migrate, repo, vectors
from backend.db.models import Run
from backend.llm.client import LocalModel
from backend.schemas import JobExtract, QuestionExtract


@pytest.fixture
def engine() -> Engine:
    # StaticPool shares the one in-memory connection across the TestClient's
    # worker threads; a plain :memory: engine would give each thread its own DB.
    # Mirrors repo.make_engine()'s setup (can't call it directly here: it
    # always calls plain create_engine(), which wouldn't get StaticPool).
    database_url = "sqlite://"
    engine = create_engine(
        database_url, connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    vectors.register_vec_extension(engine)
    migrate.run_migrations(engine, database_url)
    return engine


@pytest.fixture
def batch_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, list[str], str]]:
    calls: list[tuple[str, list[str], str]] = []
    monkeypatch.setattr(
        routes_runs,
        "enqueue_batch",
        lambda kind, sources, model: calls.append((kind, sources, model)),
    )
    return calls


@pytest.fixture
def client(
    engine: Engine, monkeypatch: pytest.MonkeyPatch, batch_calls: list[tuple[str, list[str], str]]
) -> TestClient:
    def fake_run_scrape_task(run_id: int) -> None:
        with Session(engine) as session:
            run = session.get(Run, run_id)
            assert run is not None
            repo.finish_run(session, run)

    # Execution is the pipeline's job (tested in test_pipeline); here we only
    # verify the wiring: enqueuing the task runs it and finishes the run.
    # enqueue_batch is faked the same way — batch_calls records what it
    # would have queued, tested separately (Huey pipeline wiring is
    # tested in test_tasks).
    monkeypatch.setattr(routes_runs, "run_scrape_task", fake_run_scrape_task)
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


def test_start_run_batch_queues_the_pipeline(
    client: TestClient, batch_calls: list[tuple[str, list[str], str]]
) -> None:
    response = client.post(
        "/api/runs/batch",
        json={"kind": "jobs", "source": "x"},  # wrong shape, sanity check below
    )
    assert response.status_code == 422  # source instead of sources

    response = client.post("/api/runs/batch", json={"kind": "jobs", "sources": ["hn", "remoteok"]})
    assert response.status_code == 202
    assert response.json() == {"queued": ["hn", "remoteok"]}
    assert batch_calls == [("jobs", ["hn", "remoteok"], config.LOCAL_MODEL)]


def test_start_run_batch_while_active_returns_409(
    client: TestClient, engine: Engine, batch_calls: list[tuple[str, list[str], str]]
) -> None:
    with Session(engine) as session:
        repo.create_run(session, kind="jobs", source="hn")
    response = client.post("/api/runs/batch", json={"kind": "jobs", "sources": ["hn"]})
    assert response.status_code == 409
    assert batch_calls == []


def test_start_run_batch_rejects_unknown_source(
    client: TestClient, batch_calls: list[tuple[str, list[str], str]]
) -> None:
    response = client.post("/api/runs/batch", json={"kind": "jobs", "sources": ["hn", "linkedin"]})
    assert response.status_code == 422
    assert batch_calls == []


def test_start_run_batch_rejects_empty_sources(client: TestClient) -> None:
    response = client.post("/api/runs/batch", json={"kind": "jobs", "sources": []})
    assert response.status_code == 422


def _fake_local_models(monkeypatch: pytest.MonkeyPatch) -> None:
    # Patches both modules: routes.py's GET /models calls list_local_models
    # directly, routes_runs.py's _resolve_model calls it independently
    # (PHASE9.md step 3 split them into separate files).
    models = [
        LocalModel(name="qwen2.5:7b-instruct", size_bytes=4_683_087_332),
        LocalModel(name="phi4-mini:3.8b", size_bytes=2_400_000_000),
    ]
    monkeypatch.setattr(routes, "list_local_models", lambda: models)
    monkeypatch.setattr(routes_runs, "list_local_models", lambda: models)


def test_health_reports_database_ok_and_no_consumer_in_tests(client: TestClient) -> None:
    """Every test client runs with start_consumer=False (main.py) — a real,
    verifiable distinction from the live app, not a hardcoded field."""
    body = client.get("/api/health").json()
    assert body == {"database": True, "huey_consumer": False}


def test_health_reports_database_down_for_a_genuinely_broken_engine(engine: Engine) -> None:
    """A real broken engine (an unreachable path), not a mock — proves the
    check actually queries the database rather than always returning True.
    Swapped in *after* create_app() succeeds (using the real, working
    `engine` fixture) since create_app() itself already touches the
    database during startup (recover_stale_runs) — a broken engine passed
    directly in would fail app construction, not reach GET /health at all."""
    app = create_app(engine, start_consumer=False)
    app.state.engine = create_engine("sqlite:////nonexistent_dir_xyz/broken.db")
    broken_client = TestClient(app)
    body = broken_client.get("/api/health").json()
    assert body["database"] is False


def test_list_models_returns_installed_only(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_local_models(monkeypatch)
    body = client.get("/api/models").json()
    assert body == [
        {"name": "qwen2.5:7b-instruct", "size_bytes": 4_683_087_332},
        {"name": "phi4-mini:3.8b", "size_bytes": 2_400_000_000},
    ]


def test_start_run_with_installed_model_uses_it(
    client: TestClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_local_models(monkeypatch)
    response = client.post(
        "/api/runs", json={"kind": "jobs", "source": "hn", "model": "phi4-mini:3.8b"}
    )
    assert response.status_code == 201
    run_id = response.json()["run_id"]
    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.model == "phi4-mini:3.8b"


def test_start_run_with_uninstalled_model_rejected(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_local_models(monkeypatch)
    response = client.post(
        "/api/runs", json={"kind": "jobs", "source": "hn", "model": "not-installed:1b"}
    )
    assert response.status_code == 422


def test_start_run_without_model_uses_default(client: TestClient, engine: Engine) -> None:
    response = client.post("/api/runs", json={"kind": "jobs", "source": "hn"})
    assert response.status_code == 201
    run_id = response.json()["run_id"]
    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.model == config.LOCAL_MODEL


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


def test_new_job_status_defaults_to_none(client: TestClient, engine: Engine) -> None:
    seed_items(engine)
    job = client.get("/api/jobs").json()["items"][0]
    assert job["status"] == "none"
    assert job["status_changed_at"] is None


def test_status_job_updates_and_404s_when_missing(client: TestClient, engine: Engine) -> None:
    seed_items(engine)
    job_id = client.get("/api/jobs").json()["items"][0]["id"]
    updated = client.post(f"/api/jobs/{job_id}/status", json={"status": "applied"})
    assert updated.status_code == 200
    assert updated.json()["status"] == "applied"
    assert updated.json()["status_changed_at"] is not None
    assert client.get("/api/jobs", params={"status": "applied"}).json()["total"] == 1
    assert client.post("/api/jobs/999/status", json={"status": "applied"}).status_code == 404


def test_status_job_rejects_an_unknown_status(client: TestClient, engine: Engine) -> None:
    seed_items(engine)
    job_id = client.get("/api/jobs").json()["items"][0]["id"]
    response = client.post(f"/api/jobs/{job_id}/status", json={"status": "ghosted"})
    assert response.status_code == 422


def test_job_interview_questions_matches_by_company(client: TestClient, engine: Engine) -> None:
    with Session(engine) as session:
        run = repo.create_run(session, kind="jobs", source="hn")
        job = JobExtract(
            title="Backend Engineer",
            company="Acme",
            location=None,
            salary=None,
            requirements=["Python"],
            apply_url=None,
        )
        repo.save_job(
            session, job, posting_url="https://x.com/acme", source="hn", tier="local", run=run
        )
        acme_question = QuestionExtract(
            company="Acme", role=None, question="Reverse a linked list.", round="phone"
        )
        repo.save_question(
            session,
            acme_question,
            source_url="https://r.com/1",
            source="reddit",
            tier="local",
            run=run,
        )
        other_question = QuestionExtract(
            company="Other Co", role=None, question="Design a URL shortener.", round="onsite"
        )
        repo.save_question(
            session,
            other_question,
            source_url="https://r.com/2",
            source="reddit",
            tier="local",
            run=run,
        )
        repo.finish_run(session, run)

    jobs = client.get("/api/jobs", params={"q": "Backend Engineer"}).json()["items"]
    job_id = jobs[0]["id"]

    response = client.get(f"/api/jobs/{job_id}/interview-questions")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["question"] == "Reverse a linked list."


def test_job_interview_questions_404s_when_job_missing(client: TestClient) -> None:
    assert client.get("/api/jobs/999/interview-questions").status_code == 404


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
        "discovered_companies": 0,
        "escalation_rate": 0.0,
    }


def _fake_embed_text(monkeypatch: pytest.MonkeyPatch) -> None:
    # search.py takes a pre-computed embedding and never calls Ollama
    # itself (tested for real in test_search.py) — only the route handler
    # calls embed_text, so that's the one thing to fake here.
    monkeypatch.setattr(routes, "embed_text", lambda q: b"\x00" * (4 * config.EMBED_DIM))  # noqa: ARG005


def test_search_jobs_matches_by_keyword(
    client: TestClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_items(engine)
    _fake_embed_text(monkeypatch)
    # "Engineer" alone would OR-match all three seeded jobs (FTS5 tokenizes
    # on whitespace) — "2" alone is the token unique to job 2.
    body = client.get("/api/search", params={"q": "2", "kind": "jobs"}).json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Engineer 2"


def test_search_questions_matches_by_keyword(
    client: TestClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_items(engine)
    _fake_embed_text(monkeypatch)
    body = client.get("/api/search", params={"q": "linked list", "kind": "questions"}).json()
    assert body["total"] == 1
    assert body["items"][0]["question"] == "Reverse a linked list."


def test_search_rejects_empty_query(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_embed_text(monkeypatch)
    assert client.get("/api/search", params={"q": "  ", "kind": "jobs"}).status_code == 422


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


def test_create_companies_schedule_accepts_a_real_discovery_source(client: TestClient) -> None:
    response = client.post(
        "/api/schedules", json={"kind": "companies", "source": "yc", "every_hours": 24}
    )
    assert response.status_code == 201
    assert response.json()["kind"] == "companies"


def test_create_companies_schedule_rejects_an_unknown_source(client: TestClient) -> None:
    response = client.post(
        "/api/schedules", json={"kind": "companies", "source": "bogus", "every_hours": 24}
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
