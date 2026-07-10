"""Match-score gating pipeline (PHASE10.md step 6) — a real gate step
(score -> threshold -> proceed/skip) against the resume's derived search
positions, not an implicit if-statement buried in the filler.

Reuses this project's own embedding infrastructure (`embed_text`, the
`job_embeddings` vec0 table `backend/db/search.py` already ranks against)
rather than a new similarity mechanism: cosine similarity between a fresh
embedding of the resume text and a specific job's already-stored embedding.
"""

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend import config
from backend.llm.embeddings import embed_text


class NoStoredEmbedding(Exception):
    """Raised when the given job has no stored embedding to compare against."""


@dataclass
class MatchContext:
    """One shared, namespaced context object per application attempt
    (Dify's per-workflow-run context pattern, not Dify itself) — carries
    the match score and gate decision together, instead of scattering
    values across separate function returns as steps 7-8 add more to the
    same attempt."""

    job_id: int
    resume_text: str
    score: float
    passed: bool


def compute_match_score(session: Session, *, job_id: int, resume_text: str) -> float:
    """Cosine similarity (1 - cosine distance) between a fresh embedding of
    resume_text and the job's already-stored embedding. Raises
    NoStoredEmbedding when the job was saved without one (embed=None at
    scrape time)."""
    resume_embedding = embed_text(resume_text)
    row = session.execute(
        text(
            "SELECT vec_distance_cosine(embedding, :resume_embedding) "
            "FROM job_embeddings WHERE rowid = :job_id"
        ),
        {"resume_embedding": resume_embedding, "job_id": job_id},
    ).first()
    if row is None:
        raise NoStoredEmbedding(f"job {job_id} has no stored embedding")
    return 1.0 - float(row[0])


def gate(session: Session, *, job_id: int, resume_text: str) -> MatchContext:
    """Compute the match score and apply MATCH_SCORE_THRESHOLD — the real
    proceed/skip decision, not an implicit if-statement inline in the
    caller."""
    score = compute_match_score(session, job_id=job_id, resume_text=resume_text)
    return MatchContext(
        job_id=job_id,
        resume_text=resume_text,
        score=score,
        passed=score >= config.MATCH_SCORE_THRESHOLD,
    )
