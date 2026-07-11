"""Tests for the match-score gating pipeline (PHASE10.md step 6) — no
network, no LLM (CLAUDE.md): embed_text is monkeypatched, never really
calls Ollama.
"""

import pytest
import sqlite_vec
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend import config
from backend.autoapply import matching
from backend.db import repo
from backend.db.models import Job, Run
from backend.schemas import JobExtract


def _vec(nonzero_dims: list[float]) -> bytes:
    """A real EMBED_DIM-length vector with the given leading values, zero-padded."""
    padded = nonzero_dims + [0.0] * (config.EMBED_DIM - len(nonzero_dims))
    return sqlite_vec.serialize_float32(padded)


@pytest.fixture
def session() -> Session:
    return Session(repo.make_engine("sqlite:///:memory:"))


@pytest.fixture
def run(session: Session) -> Run:
    return repo.create_run(session, kind="jobs", source="hn")


def _save_job(
    session: Session, run: Run, *, embedding: bytes | None, posting_url: str = "https://x.com/1"
) -> int:
    """Insert one real job (embedded if given a vector) and return its id."""
    job = JobExtract(
        title="Backend Engineer",
        company="Acme",
        location=None,
        salary=None,
        requirements=["Python"],
        apply_url=None,
    )
    embed = (lambda _: embedding) if embedding is not None else None
    repo.save_job(
        session, job, posting_url=posting_url, source="hn", tier="local", run=run, embed=embed
    )
    job_id = session.scalar(select(Job.id).where(Job.posting_url == posting_url))
    assert job_id is not None
    return job_id


def test_compute_match_score_is_near_1_for_identical_vectors(
    session: Session, run: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    vector = _vec([1.0, 0.5])
    job_id = _save_job(session, run, embedding=vector)

    monkeypatch.setattr(matching, "embed_text", lambda text: vector)
    score = matching.compute_match_score(session, job_id=job_id, resume_text="anything")
    assert score == pytest.approx(1.0, abs=1e-4)


def test_compute_match_score_is_near_0_for_orthogonal_vectors(
    session: Session, run: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_id = _save_job(session, run, embedding=_vec([1.0, 0.0]))

    monkeypatch.setattr(matching, "embed_text", lambda text: _vec([0.0, 1.0]))
    score = matching.compute_match_score(session, job_id=job_id, resume_text="anything")
    assert score == pytest.approx(0.0, abs=1e-4)


def test_compute_match_score_raises_when_job_has_no_stored_embedding(
    session: Session, run: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_id = _save_job(session, run, embedding=None)

    monkeypatch.setattr(matching, "embed_text", lambda text: _vec([1.0]))
    with pytest.raises(matching.NoStoredEmbedding):
        matching.compute_match_score(session, job_id=job_id, resume_text="anything")


def test_gate_passes_when_score_meets_the_threshold(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        matching, "compute_match_score", lambda session, *, job_id, resume_text: 0.8
    )
    monkeypatch.setattr(config, "MATCH_SCORE_THRESHOLD", 0.5)
    context = matching.gate(session, job_id=1, resume_text="anything")
    assert context.passed is True
    assert context.score == 0.8
    assert context.job_id == 1


def test_gate_fails_when_score_is_below_the_threshold(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        matching, "compute_match_score", lambda session, *, job_id, resume_text: 0.2
    )
    monkeypatch.setattr(config, "MATCH_SCORE_THRESHOLD", 0.5)
    context = matching.gate(session, job_id=1, resume_text="anything")
    assert context.passed is False


def test_score_all_jobs_scores_every_embedded_job_highest_first(
    session: Session, run: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    close_job = _save_job(
        session, run, embedding=_vec([1.0, 0.0]), posting_url="https://x.com/close"
    )
    far_job = _save_job(session, run, embedding=_vec([0.0, 1.0]), posting_url="https://x.com/far")

    monkeypatch.setattr(matching, "embed_text", lambda text: _vec([1.0, 0.0]))
    scored = matching.score_all_jobs(session, "anything")

    by_id = dict(scored)
    assert by_id[close_job] == pytest.approx(1.0, abs=1e-4)
    assert by_id[far_job] == pytest.approx(0.0, abs=1e-4)
    assert [job_id for job_id, _ in scored] == [close_job, far_job]  # highest first


def test_score_all_jobs_skips_jobs_with_no_stored_embedding(
    session: Session, run: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    _save_job(session, run, embedding=None, posting_url="https://x.com/unembedded")
    monkeypatch.setattr(matching, "embed_text", lambda text: _vec([1.0, 0.0]))
    assert matching.score_all_jobs(session, "anything") == []
