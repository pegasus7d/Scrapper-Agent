"""FTS5 keyword-search tables and inserts (PHASE6.md step 8) — the keyword
half of hybrid search, paired with vectors.py's similarity half.
"""

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session


def create_fts_tables(engine: Engine) -> None:
    """One FTS5 table per item kind, keyed by the item's own row id."""
    with engine.connect() as conn:
        conn.execute(
            text(
                "CREATE VIRTUAL TABLE IF NOT EXISTS job_search_fts "
                "USING fts5(title, company, location, salary, requirements)"
            )
        )
        conn.execute(
            text(
                "CREATE VIRTUAL TABLE IF NOT EXISTS question_search_fts "
                "USING fts5(question, company, role)"
            )
        )
        conn.commit()


def index_job(
    session: Session,
    job_id: int,
    *,
    title: str,
    company: str,
    location: str | None,
    salary: str | None,
    requirements: list[str],
) -> None:
    session.execute(
        text(
            "INSERT INTO job_search_fts(rowid, title, company, location, salary, requirements) "
            "VALUES (:id, :title, :company, :location, :salary, :requirements)"
        ),
        {
            "id": job_id,
            "title": title,
            "company": company,
            "location": location or "",
            "salary": salary or "",
            "requirements": " ".join(requirements),
        },
    )


def index_question(
    session: Session, question_id: int, *, question: str, company: str | None, role: str | None
) -> None:
    session.execute(
        text(
            "INSERT INTO question_search_fts(rowid, question, company, role) "
            "VALUES (:id, :question, :company, :role)"
        ),
        {"id": question_id, "question": question, "company": company or "", "role": role or ""},
    )
