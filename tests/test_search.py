"""Tests for hybrid search: sqlite-vec + FTS5 + RRF (PHASE6.md step 8) —
no network, no LLM (CLAUDE.md): search.py takes a pre-computed embedding,
never calls Ollama itself.
"""

import pytest
import sqlite_vec
from sqlalchemy.orm import Session

from backend import config
from backend.db import repo, search
from backend.db.models import Run
from backend.schemas import JobExtract, QuestionExtract


def _vec(value: float) -> bytes:
    return sqlite_vec.serialize_float32([value] * config.EMBED_DIM)


@pytest.fixture
def session() -> Session:
    return Session(repo.make_engine("sqlite:///:memory:"))


@pytest.fixture
def run(session: Session) -> Run:
    return repo.create_run(session, kind="jobs", source="hn")


def test_search_jobs_ranks_the_dual_match_first(session: Session, run: Run) -> None:
    python_job = JobExtract(
        title="Remote Python Backend Engineer",
        company="Acme",
        location=None,
        salary=None,
        requirements=["Python", "Django"],
        apply_url=None,
    )
    frontend_job = JobExtract(
        title="Frontend React Developer",
        company="Beta",
        location=None,
        salary=None,
        requirements=["React", "TypeScript"],
        apply_url=None,
    )
    repo.save_job(
        session,
        python_job,
        posting_url="https://x.com/1",
        source="hn",
        tier="local",
        run=run,
        embed=lambda _: _vec(1.0),
    )
    repo.save_job(
        session,
        frontend_job,
        posting_url="https://x.com/2",
        source="hn",
        tier="local",
        run=run,
        embed=lambda _: _vec(9.0),
    )

    # Query embedding matches python_job's vector exactly (distance 0) and
    # the keyword "python" only appears in python_job's FTS row — it should
    # win both signals and rank first; frontend_job still appears (weaker,
    # vector-only match) but behind it.
    results = search.search_jobs(session, "python", _vec(1.0), limit=10)

    assert [j.title for j in results][0] == "Remote Python Backend Engineer"
    assert {j.title for j in results} == {python_job.title, frontend_job.title}


def test_search_jobs_no_matches_returns_empty(session: Session, run: Run) -> None:
    job = JobExtract(
        title="Backend Engineer",
        company="Acme",
        location=None,
        salary=None,
        requirements=["Go"],
        apply_url=None,
    )
    repo.save_job(session, job, posting_url="https://x.com/1", source="hn", tier="local", run=run)
    # No embedding saved (embed=None) and no keyword overlap — nothing to find.
    assert search.search_jobs(session, "kubernetes", _vec(5.0), limit=10) == []


def test_search_questions_ranks_the_dual_match_first(session: Session, run: Run) -> None:
    closures_q = QuestionExtract(
        company=None, role=None, question="Explain closures in JavaScript.", round=None
    )
    other_q = QuestionExtract(
        company=None, role=None, question="Design a URL shortener.", round=None
    )
    repo.save_question(
        session,
        closures_q,
        source_url="https://x.com/q1",
        source="github",
        tier="local",
        run=run,
        embed=lambda _: _vec(1.0),
    )
    repo.save_question(
        session,
        other_q,
        source_url="https://x.com/q2",
        source="github",
        tier="local",
        run=run,
        embed=lambda _: _vec(9.0),
    )

    results = search.search_questions(session, "closures", _vec(1.0), limit=10)

    assert results[0].question == closures_q.question
