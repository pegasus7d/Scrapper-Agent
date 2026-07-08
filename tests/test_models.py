"""Tests for the ORM models: table creation and uniqueness constraints."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.models import Base, InterviewQuestion, Job, Run


@pytest.fixture
def engine() -> Engine:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def make_run() -> Run:
    return Run(kind="jobs", source="hn", status="running", started_at=datetime.now(UTC))


def make_job(run_id: int, posting_url: str = "https://news.ycombinator.com/item?id=1") -> Job:
    return Job(
        title="Backend Engineer",
        company="Acme",
        location=None,
        salary=None,
        requirements=["Python"],
        posting_url=posting_url,
        apply_url=None,
        source="hn",
        extraction_tier="local",
        scraped_at=datetime.now(UTC),
        run_id=run_id,
    )


def make_question(run_id: int, question_hash: str = "abc123") -> InterviewQuestion:
    return InterviewQuestion(
        company="Acme",
        role=None,
        question="Design a URL shortener.",
        round=None,
        source_url="https://reddit.com/r/cscareerquestions/1",
        question_hash=question_hash,
        source="reddit",
        extraction_tier="local",
        scraped_at=datetime.now(UTC),
        run_id=run_id,
    )


def test_all_tables_create_and_accept_rows(engine: Engine) -> None:
    with Session(engine) as session:
        run = make_run()
        session.add(run)
        session.flush()
        session.add(make_job(run.id))
        session.add(make_question(run.id))
        session.commit()
        assert run.id is not None
        assert run.errors == []
        assert run.cancel_requested is False


def test_duplicate_posting_url_rejected(engine: Engine) -> None:
    with Session(engine) as session:
        run = make_run()
        session.add(run)
        session.flush()
        session.add(make_job(run.id, posting_url="https://example.com/j/1"))
        session.commit()
        session.add(make_job(run.id, posting_url="https://example.com/j/1"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_duplicate_question_hash_rejected(engine: Engine) -> None:
    with Session(engine) as session:
        run = make_run()
        session.add(run)
        session.flush()
        session.add(make_question(run.id, question_hash="samehash"))
        session.commit()
        session.add(make_question(run.id, question_hash="samehash"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_same_source_url_allowed_for_different_questions(engine: Engine) -> None:
    with Session(engine) as session:
        run = make_run()
        session.add(run)
        session.flush()
        session.add(make_question(run.id, question_hash="hash1"))
        session.add(make_question(run.id, question_hash="hash2"))
        session.commit()
