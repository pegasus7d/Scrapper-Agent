"""Hybrid search: sqlite-vec similarity + FTS5 keyword, merged with
reciprocal rank fusion (PHASE6.md step 8).

Kept out of _queries.py: this is raw SQL against vec0/FTS5 virtual tables,
not ORM queries — same separation vectors.py/fts.py already use for the
write path.
"""

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.db.models import InterviewQuestion, Job

RRF_K = 60  # standard reciprocal-rank-fusion constant


def _fts_query(q: str) -> str:
    """Free text -> a safe, OR-of-terms FTS5 MATCH query — never pass raw
    user input straight into FTS5's own query syntax."""
    tokens = q.split()
    return " OR ".join(f'"{token}"' for token in tokens) if tokens else '""'


def _rrf_merge(*ranked_id_lists: list[int]) -> list[int]:
    """Combine ranked id lists into one, scored by sum(1 / (RRF_K + rank))
    across every list an id appears in — standard hybrid-search fusion."""
    scores: dict[int, float] = {}
    for ids in ranked_id_lists:
        for rank, item_id in enumerate(ids):
            scores[item_id] = scores.get(item_id, 0.0) + 1 / (RRF_K + rank + 1)
    return sorted(scores, key=lambda i: scores[i], reverse=True)


def search_jobs(session: Session, q: str, embedding: bytes, limit: int) -> list[Job]:
    fts_ids = [
        row[0]
        for row in session.execute(
            text(
                "SELECT rowid FROM job_search_fts WHERE job_search_fts MATCH :q "
                "ORDER BY rank LIMIT :limit"
            ),
            {"q": _fts_query(q), "limit": limit},
        )
    ]
    vec_ids = [
        row[0]
        for row in session.execute(
            text(
                "SELECT rowid FROM job_embeddings WHERE embedding MATCH :embedding "
                "AND k = :limit ORDER BY distance"
            ),
            {"embedding": embedding, "limit": limit},
        )
    ]
    ranked_ids = _rrf_merge(fts_ids, vec_ids)[:limit]
    if not ranked_ids:
        return []
    by_id = {job.id: job for job in session.scalars(select(Job).where(Job.id.in_(ranked_ids)))}
    return [by_id[i] for i in ranked_ids if i in by_id]


def search_questions(
    session: Session, q: str, embedding: bytes, limit: int
) -> list[InterviewQuestion]:
    fts_ids = [
        row[0]
        for row in session.execute(
            text(
                "SELECT rowid FROM question_search_fts WHERE question_search_fts MATCH :q "
                "ORDER BY rank LIMIT :limit"
            ),
            {"q": _fts_query(q), "limit": limit},
        )
    ]
    vec_ids = [
        row[0]
        for row in session.execute(
            text(
                "SELECT rowid FROM question_embeddings WHERE embedding MATCH :embedding "
                "AND k = :limit ORDER BY distance"
            ),
            {"embedding": embedding, "limit": limit},
        )
    ]
    ranked_ids = _rrf_merge(fts_ids, vec_ids)[:limit]
    if not ranked_ids:
        return []
    by_id = {
        item.id: item
        for item in session.scalars(
            select(InterviewQuestion).where(InterviewQuestion.id.in_(ranked_ids))
        )
    }
    return [by_id[i] for i in ranked_ids if i in by_id]
