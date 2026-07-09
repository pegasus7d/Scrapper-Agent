"""sqlite-vec wiring: extension loading and embedding inserts (PHASE6.md
step 7). Table creation lives in the Alembic migrations (PHASE7.md step 1)
instead, since it's schema history now, not a repeated setup call.

Kept out of repo/_writes.py: vec0 virtual tables aren't ORM-mapped models
(SQLAlchemy has no vec0 concept), so this is raw SQL by necessity —
reviewable on its own rather than mixed into the ORM-based saves.
"""

from sqlalchemy import Engine, event, text
from sqlalchemy.orm import Session


def register_vec_extension(engine: Engine) -> None:
    """Load sqlite-vec on every new DBAPI connection this engine opens.

    Verified real: the dbapi_connection SQLAlchemy's "connect" event passes
    is the raw sqlite3.Connection, compatible with sqlite_vec.load()'s
    enable_load_extension() pattern — SQLAlchemy has no extension-loading
    support of its own, this is the documented workaround.
    """

    @event.listens_for(engine, "connect")
    def _load(dbapi_connection: object, connection_record: object) -> None:
        import sqlite_vec

        dbapi_connection.enable_load_extension(True)  # type: ignore[attr-defined]
        sqlite_vec.load(dbapi_connection)
        dbapi_connection.enable_load_extension(False)  # type: ignore[attr-defined]


def save_job_embedding(session: Session, job_id: int, embedding: bytes) -> None:
    session.execute(
        text("INSERT INTO job_embeddings(rowid, embedding) VALUES (:id, :embedding)"),
        {"id": job_id, "embedding": embedding},
    )


def save_question_embedding(session: Session, question_id: int, embedding: bytes) -> None:
    session.execute(
        text("INSERT INTO question_embeddings(rowid, embedding) VALUES (:id, :embedding)"),
        {"id": question_id, "embedding": embedding},
    )
