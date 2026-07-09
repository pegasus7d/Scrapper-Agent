"""Tests for the persistence layer: dedupe, normalization, run lifecycle."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from backend.db import repo
from backend.db.models import Run
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


def test_normalize_url_strips_tracking_params_and_fragment() -> None:
    url = "https://x.com/j/1?utm_source=a&ref=b&gclid=c&page=2#frag"
    assert repo.normalize_url(url) == "https://x.com/j/1?page=2"


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
    stats = repo.compute_stats(session)
    assert (stats.jobs, stats.questions) == (4, 1)
    assert stats.companies == 4  # Company 0/1/2 + Acme; the duplicate not double-counted
    assert stats.escalation_rate == pytest.approx(0.2)  # 1 frontier item of 5


def test_compute_stats_empty_db_is_all_zeros(session: Session) -> None:
    assert repo.compute_stats(session) == repo.Stats(
        jobs=0, questions=0, companies=0, escalation_rate=0.0
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
