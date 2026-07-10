"""Tests for the persistence layer: dedupe, normalization, run lifecycle."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from backend import config
from backend.db import repo, vectors
from backend.db.models import Base, Run
from backend.schemas import JobExtract, QuestionExtract

JOB = JobExtract(
    title="Backend Engineer",
    company="Acme",
    location="Remote",
    salary=None,
    requirements=["Python"],
    apply_url=None,
)

QUESTION = QuestionExtract(
    company="Acme",
    role="SWE",
    question="Design a URL shortener.",
    round="onsite",
)


@pytest.fixture
def session() -> Session:
    engine = repo.make_engine("sqlite:///:memory:")
    return Session(engine)


@pytest.fixture
def run(session: Session) -> Run:
    return repo.create_run(session, kind="jobs", source="hn")


def test_make_engine_stamps_a_pre_alembic_db_without_losing_data(tmp_path: Path) -> None:
    # A real pre-Alembic database (PHASE7.md step 1) — full current ORM
    # schema plus the vec0/FTS5 tables, built by the old ad-hoc mechanism
    # (phase 6 steps 3/7/8), but no alembic_version table. This is exactly
    # the real project's own hirable.db's shape the moment this code lands.
    # make_engine() must stamp it at head, not re-run CREATE TABLE against
    # tables that already exist (which would error) or lose real data.
    db_path = tmp_path / "old.db"
    old_engine = create_engine(f"sqlite:///{db_path}")
    vectors.register_vec_extension(old_engine)
    Base.metadata.create_all(old_engine)
    with old_engine.connect() as conn:
        conn.exec_driver_sql("CREATE VIRTUAL TABLE job_embeddings USING vec0(embedding float[768])")
        conn.exec_driver_sql(
            "CREATE VIRTUAL TABLE question_embeddings USING vec0(embedding float[768])"
        )
        conn.exec_driver_sql(
            "CREATE VIRTUAL TABLE job_search_fts "
            "USING fts5(title, company, location, salary, requirements)"
        )
        conn.exec_driver_sql(
            "CREATE VIRTUAL TABLE question_search_fts USING fts5(question, company, role)"
        )
        conn.exec_driver_sql(
            "INSERT INTO runs (id, kind, source, model, status, cancel_requested, "
            "started_at, pages_fetched, items_saved, items_duplicate, escalations, errors) "
            "VALUES (1, 'jobs', 'hn', 'qwen2.5:7b-instruct', 'completed', 0, "
            "'2026-01-01 00:00:00', 1, 1, 0, 0, '[]')"
        )
        conn.commit()
    old_engine.dispose()

    engine = repo.make_engine(f"sqlite:///{db_path}")
    with Session(engine) as session:
        preserved = session.get(Run, 1)
        assert preserved is not None
        assert preserved.model == "qwen2.5:7b-instruct"  # real pre-existing data, untouched

        version = session.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert version is not None  # stamped, not left untracked

        new_run = repo.create_run(session, kind="jobs", source="hn")
        assert new_run.model == config.LOCAL_MODEL


def test_normalize_url_strips_tracking_params_only() -> None:
    url = "https://x.com/j/1?utm_source=a&ref=b&gclid=c&page=2#frag"
    assert repo.normalize_url(url) == "https://x.com/j/1?page=2#frag"


def test_normalize_url_keeps_fragment() -> None:
    # The GitHub question-bank source's per-question identity is a URL
    # fragment (#L{line}) — it must survive normalization (PHASE3.md step 4).
    url = "https://github.com/h5bp/repo/blob/main/questions.md#L7"
    assert repo.normalize_url(url) == url


def test_normalize_url_keeps_clean_urls_unchanged() -> None:
    assert repo.normalize_url("https://x.com/j/1?id=5") == "https://x.com/j/1?id=5"


def test_save_job_saves_and_counts(session: Session, run: Run) -> None:
    assert repo.save_job(
        session, JOB, posting_url="https://x.com/j/1", source="hn", tier="local", run=run
    )
    assert run.items_saved == 1
    assert run.items_duplicate == 0


def test_duplicate_posting_url_skipped_and_counted(session: Session, run: Run) -> None:
    repo.save_job(session, JOB, posting_url="https://x.com/j/1", source="hn", tier="local", run=run)
    # Same job reached via a tracking link must still count as a duplicate.
    saved = repo.save_job(
        session,
        JOB,
        posting_url="https://x.com/j/1?utm_source=feed",
        source="hn",
        tier="local",
        run=run,
    )
    assert saved is False
    assert run.items_saved == 1
    assert run.items_duplicate == 1


def test_save_question_saves_and_counts(session: Session, run: Run) -> None:
    assert repo.save_question(
        session, QUESTION, source_url="https://r.com/t/1", source="reddit", tier="local", run=run
    )
    assert run.items_saved == 1


def test_duplicate_question_case_whitespace_variant_skipped(session: Session, run: Run) -> None:
    repo.save_question(
        session, QUESTION, source_url="https://r.com/t/1", source="reddit", tier="local", run=run
    )
    variant = QuestionExtract(
        company="ACME",
        role=None,
        question="  design a   URL shortener.  ",
        round=None,
    )
    saved = repo.save_question(
        session, variant, source_url="https://r.com/t/2", source="reddit", tier="local", run=run
    )
    assert saved is False
    assert run.items_duplicate == 1


def test_question_hash_normalizes_null_company_to_empty_string() -> None:
    assert repo.question_hash(None, "Design a cache.") == repo.question_hash("", "Design a cache.")


def test_save_question_with_null_company_saves_and_dedupes(session: Session, run: Run) -> None:
    generic = QuestionExtract(company=None, role=None, question="Explain closures.", round=None)
    assert repo.save_question(
        session, generic, source_url="https://gh.com/q/1", source="github", tier="local", run=run
    )
    saved = repo.save_question(
        session, generic, source_url="https://gh.com/q/2", source="github", tier="local", run=run
    )
    assert saved is False  # same companyless question, different source_url — still a duplicate
    assert run.items_duplicate == 1


def _fake_blob() -> bytes:
    # Real-shaped BLOB (config.EMBED_DIM float32s) — content doesn't matter,
    # only that it lands in the vec0 table's rowid-keyed row.
    return b"\x00" * (4 * config.EMBED_DIM)


def test_save_job_with_embed_stores_vector_same_transaction(session: Session, run: Run) -> None:
    calls: list[str] = []

    def fake_embed(embed_text: str) -> bytes:
        calls.append(embed_text)
        return _fake_blob()

    repo.save_job(
        session,
        JOB,
        posting_url="https://x.com/j/1",
        source="hn",
        tier="local",
        run=run,
        embed=fake_embed,
    )
    assert len(calls) == 1
    assert JOB.title in calls[0]
    assert JOB.company in calls[0]
    row = session.execute(text("SELECT rowid FROM job_embeddings")).fetchone()
    assert row is not None


def test_save_job_without_embed_stores_no_vector(session: Session, run: Run) -> None:
    repo.save_job(session, JOB, posting_url="https://x.com/j/1", source="hn", tier="local", run=run)
    row = session.execute(text("SELECT rowid FROM job_embeddings")).fetchone()
    assert row is None


def test_save_question_with_embed_stores_vector_same_transaction(
    session: Session, run: Run
) -> None:
    calls: list[str] = []

    def fake_embed(embed_text: str) -> bytes:
        calls.append(embed_text)
        return _fake_blob()

    repo.save_question(
        session,
        QUESTION,
        source_url="https://r.com/t/1",
        source="reddit",
        tier="local",
        run=run,
        embed=fake_embed,
    )
    assert calls == [QUESTION.question]
    row = session.execute(text("SELECT rowid FROM question_embeddings")).fetchone()
    assert row is not None


def test_save_question_without_embed_stores_no_vector(session: Session, run: Run) -> None:
    repo.save_question(
        session, QUESTION, source_url="https://r.com/t/1", source="reddit", tier="local", run=run
    )
    row = session.execute(text("SELECT rowid FROM question_embeddings")).fetchone()
    assert row is None


def test_run_lifecycle(session: Session) -> None:
    run = repo.create_run(session, kind="jobs", source="hn")
    assert run.status == "running"
    assert run.finished_at is None
    repo.finish_run(session, run)
    assert run.status == "completed"
    assert run.finished_at is not None


def test_record_error_caps_at_limit(session: Session, run: Run) -> None:
    for i in range(repo.MAX_RUN_ERRORS + 10):
        repo.record_error(session, run, url=f"https://x.com/{i}", error="boom")
    assert len(run.errors) == repo.MAX_RUN_ERRORS


def test_request_cancel_and_check(session: Session, run: Run) -> None:
    assert repo.cancel_requested(session, run) is False
    assert repo.request_cancel(session, run.id) is True
    assert repo.cancel_requested(session, run) is True


def test_request_cancel_missing_run_returns_false(session: Session) -> None:
    assert repo.request_cancel(session, run_id=999) is False


def test_active_run_exists(session: Session, run: Run) -> None:
    assert repo.active_run_exists(session) is True
    repo.finish_run(session, run)
    assert repo.active_run_exists(session) is False


def test_recover_stale_runs_marks_only_running_rows(session: Session) -> None:
    stale = repo.create_run(session, kind="jobs", source="hn")
    done = repo.create_run(session, kind="jobs", source="hn")
    repo.finish_run(session, done)
    assert repo.recover_stale_runs(session) == 1
    assert stale.status == "failed"
    assert stale.errors[-1]["error"] == "interrupted by restart"
    assert done.status == "completed"


def save_jobs(session: Session, run: Run, *titles: str, tier: str = "local") -> None:
    for n, title in enumerate(titles):
        extract = JOB.model_copy(update={"title": title, "company": f"Company {n}"})
        url = f"https://x.com/j/{title}"
        repo.save_job(session, extract, posting_url=url, source="hn", tier=tier, run=run)


def test_list_runs_newest_first_with_total(session: Session) -> None:
    first = repo.create_run(session, kind="jobs", source="hn")
    second = repo.create_run(session, kind="jobs", source="hn")
    runs, total = repo.list_runs(session, limit=1, offset=0)
    assert total == 2
    assert [r.id for r in runs] == [second.id]
    assert repo.get_run(session, first.id) is first
    assert repo.get_run(session, 999) is None


def test_list_jobs_paginates_newest_first(session: Session, run: Run) -> None:
    save_jobs(session, run, "A", "B", "C")
    jobs, total = repo.list_jobs(session, limit=2, offset=1)
    assert total == 3
    assert [job.title for job in jobs] == ["B", "A"]


def test_list_jobs_filters_by_company_source_and_title(session: Session, run: Run) -> None:
    save_jobs(session, run, "Backend Engineer", "Data Scientist")
    by_company, total = repo.list_jobs(session, company="company 0", limit=20, offset=0)
    assert (total, by_company[0].title) == (1, "Backend Engineer")
    by_title, total = repo.list_jobs(session, q="scientist", limit=20, offset=0)
    assert (total, by_title[0].title) == (1, "Data Scientist")
    assert repo.list_jobs(session, source="reddit", limit=20, offset=0) == ([], 0)


def test_list_questions_filters_by_company_round_and_text(session: Session, run: Run) -> None:
    repo.save_question(
        session, QUESTION, source_url="https://r.com/t/1", source="reddit", tier="local", run=run
    )
    by_round, total = repo.list_questions(session, round_="onsite", limit=20, offset=0)
    assert (total, by_round[0].company) == (1, "Acme")
    by_text, total = repo.list_questions(session, q="shortener", limit=20, offset=0)
    assert total == 1 and by_text[0].question == QUESTION.question
    assert repo.list_questions(session, company="other", limit=20, offset=0) == ([], 0)


def test_set_job_starred_toggles_and_reports_missing(session: Session, run: Run) -> None:
    save_jobs(session, run, "Backend Engineer")
    job_id = repo.list_jobs(session, limit=1, offset=0)[0][0].id
    starred = repo.set_job_starred(session, job_id, True)
    assert starred is not None and starred.starred is True
    assert repo.set_job_starred(session, 999, True) is None


def test_list_jobs_filters_by_starred(session: Session, run: Run) -> None:
    save_jobs(session, run, "A", "B")
    jobs, _ = repo.list_jobs(session, limit=20, offset=0)
    repo.set_job_starred(session, jobs[0].id, True)
    starred_only, total = repo.list_jobs(session, starred=True, limit=20, offset=0)
    assert total == 1 and starred_only[0].id == jobs[0].id
    unstarred_only, total = repo.list_jobs(session, starred=False, limit=20, offset=0)
    assert total == 1 and unstarred_only[0].id == jobs[1].id


def test_export_jobs_returns_all_matches_unpaginated(session: Session, run: Run) -> None:
    save_jobs(session, run, "A", "B", "C")
    assert len(repo.export_jobs(session)) == 3
    assert len(repo.export_jobs(session, company="company 0")) == 1


def test_new_jobs_default_to_status_none(session: Session, run: Run) -> None:
    save_jobs(session, run, "A")
    job = repo.list_jobs(session, limit=1, offset=0)[0][0]
    assert job.status == "none"
    assert job.status_changed_at is None


def test_set_job_status_records_the_transition_and_reports_missing(
    session: Session, run: Run
) -> None:
    save_jobs(session, run, "A")
    job_id = repo.list_jobs(session, limit=1, offset=0)[0][0].id
    updated = repo.set_job_status(session, job_id, "applied")
    assert updated is not None
    assert updated.status == "applied"
    assert updated.status_changed_at is not None
    assert repo.set_job_status(session, 999, "applied") is None


def test_list_jobs_filters_by_status(session: Session, run: Run) -> None:
    save_jobs(session, run, "A", "B")
    jobs, _ = repo.list_jobs(session, limit=20, offset=0)
    repo.set_job_status(session, jobs[0].id, "applied")
    applied_only, total = repo.list_jobs(session, status="applied", limit=20, offset=0)
    assert total == 1 and applied_only[0].id == jobs[0].id
    none_only, total = repo.list_jobs(session, status="none", limit=20, offset=0)
    assert total == 1 and none_only[0].id == jobs[1].id


def test_export_questions_returns_all_matches_unpaginated(session: Session, run: Run) -> None:
    repo.save_question(
        session, QUESTION, source_url="https://r.com/t/1", source="reddit", tier="local", run=run
    )
    assert len(repo.export_questions(session)) == 1
    assert len(repo.export_questions(session, round_="onsite")) == 1
    assert len(repo.export_questions(session, round_="phone")) == 0


def test_compute_stats_counts_and_escalation_rate(session: Session, run: Run) -> None:
    save_jobs(session, run, "A", "B", "C")
    repo.save_job(
        session,
        JOB.model_copy(update={"company": "Company 0"}),  # duplicate company, frontier tier
        posting_url="https://x.com/j/frontier",
        source="hn",
        tier="frontier",
        run=run,
    )
    repo.save_question(
        session, QUESTION, source_url="https://r.com/t/1", source="reddit", tier="local", run=run
    )
    generic = QuestionExtract(company=None, role=None, question="Explain closures.", round=None)
    repo.save_question(
        session, generic, source_url="https://gh.com/q/1", source="github", tier="local", run=run
    )
    stats = repo.compute_stats(session)
    assert (stats.jobs, stats.questions) == (4, 2)
    # Company 0/1/2 + Acme; the duplicate not double-counted, null company not counted.
    assert stats.companies == 4
    assert stats.escalation_rate == pytest.approx(1 / 6)  # 1 frontier item of 6


def test_compute_stats_discovered_companies_is_a_real_separate_count(
    session: Session, run: Run
) -> None:
    # Real, deliberate distinction (PHASE8.md step 3): scraped-job company
    # names vs. rows in the companies discovery table (PHASE7.md step 5) —
    # a company can be discovered with zero jobs scraped from it yet.
    save_jobs(session, run, "A")
    repo.save_company(session, "Deel")
    repo.save_company(session, "Airbnb")
    stats = repo.compute_stats(session)
    assert stats.companies == 1
    assert stats.discovered_companies == 2


def test_compute_stats_empty_db_is_all_zeros(session: Session) -> None:
    assert repo.compute_stats(session) == repo.Stats(
        jobs=0, questions=0, companies=0, discovered_companies=0, escalation_rate=0.0
    )


def test_item_url_exists_matches_jobs_across_tracking_params(session: Session, run: Run) -> None:
    assert repo.item_url_exists(session, "jobs", "https://x.com/j/1") is False
    repo.save_job(session, JOB, posting_url="https://x.com/j/1", source="hn", tier="local", run=run)
    assert repo.item_url_exists(session, "jobs", "https://x.com/j/1") is True
    # The same permalink reached via a tracking link is still known.
    assert repo.item_url_exists(session, "jobs", "https://x.com/j/1?utm_source=feed") is True


def test_item_url_exists_matches_questions_by_source_url(session: Session, run: Run) -> None:
    assert repo.item_url_exists(session, "questions", "https://r.com/t/1") is False
    repo.save_question(
        session, QUESTION, source_url="https://r.com/t/1", source="reddit", tier="local", run=run
    )
    assert repo.item_url_exists(session, "questions", "https://r.com/t/1") is True
    assert repo.item_url_exists(session, "jobs", "https://r.com/t/1") is False  # kind-scoped


def test_create_and_list_schedules(session: Session) -> None:
    repo.create_schedule(session, kind="jobs", source="hn", every_hours=6)
    repo.create_schedule(session, kind="questions", source="hn-interviews", every_hours=24)
    schedules = repo.list_schedules(session)
    assert [(s.kind, s.source, s.every_hours, s.enabled) for s in schedules] == [
        ("jobs", "hn", 6, True),
        ("questions", "hn-interviews", 24, True),
    ]
    assert schedules[0].last_run_at is None


def test_set_schedule_enabled_toggles_and_reports_missing(session: Session) -> None:
    schedule = repo.create_schedule(session, kind="jobs", source="hn", every_hours=6)
    updated = repo.set_schedule_enabled(session, schedule.id, False)
    assert updated is not None and updated.enabled is False
    assert repo.list_schedules(session)[0].enabled is False
    assert repo.set_schedule_enabled(session, 999, True) is None


def test_due_schedules_never_run_is_due_immediately(session: Session) -> None:
    repo.create_schedule(session, kind="jobs", source="hn", every_hours=6)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert len(repo.due_schedules(session, now)) == 1


def test_due_schedules_respects_interval_and_enabled_flag(session: Session) -> None:
    schedule = repo.create_schedule(session, kind="jobs", source="hn", every_hours=6)
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    repo.mark_schedule_run(session, schedule, now)
    assert repo.due_schedules(session, now + timedelta(hours=3)) == []
    assert repo.due_schedules(session, now + timedelta(hours=6)) == [schedule]

    repo.set_schedule_enabled(session, schedule.id, False)
    assert repo.due_schedules(session, now + timedelta(hours=100)) == []
