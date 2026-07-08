"""Tests for the persistence layer: dedupe, normalization, run lifecycle."""

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
