"""Alembic-driven schema migrations (PHASE7.md step 1).

Replaces the old create_all() + ad-hoc ALTER TABLE pattern (phase 6 step 3),
which had no single record of which migrations had actually been applied to
a given database — every future schema change would have needed its own
copy-pasted detect-and-patch function.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, inspect

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_MIGRATIONS_DIR = _PROJECT_ROOT / "migrations"


def _alembic_config(database_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    # Alembic's documented programmatic-use pattern: env.py reads this back
    # via config.attributes, taking priority over app_config.DATABASE_URL —
    # critical for tests, which pass their own sqlite:///:memory:/tmp-file
    # URLs to make_engine(), not the real app default.
    cfg.attributes["configure_url"] = database_url
    return cfg


def _has_applied_version(connection: Connection, tables: set[str]) -> bool:
    """True only when `alembic_version` exists *and* actually has a row.

    Confirmed for real this distinction matters: `alembic revision
    --autogenerate` creates an empty `alembic_version` table as a side
    effect of reading the current version to link a new revision's
    down_revision — it doesn't insert a row. A table-existence check alone
    would misread that empty table as "already tracked" and try to
    `upgrade` a database whose tables already exist, erroring on `CREATE
    TABLE runs` (caught by this step's own real smoke test, against a real
    copy of this project's own dev database).
    """
    if "alembic_version" not in tables:
        return False
    row = connection.exec_driver_sql("SELECT version_num FROM alembic_version").fetchone()
    return row is not None


def run_migrations(engine: Engine, database_url: str) -> None:
    """Bring the database to the latest schema.

    A brand new database gets every migration run for real, creating every
    table from nothing. A database that already has application tables but
    no applied `alembic_version` row is one of this project's own
    pre-Alembic databases (its schema already matches head — just applied
    via the old ad-hoc mechanism, never tracked) — stamp it at head instead
    of re-running `CREATE TABLE` against tables that already exist.

    Runs on one connection opened from the caller's own `engine`, passed to
    Alembic via `config.attributes["connection"]` (see migrations/env.py) —
    required for sqlite:///:memory: URLs specifically: a fresh Engine
    opened here would migrate a separate, throwaway in-memory database
    (confirmed for real — see env.py's docstring), leaving the caller's own
    engine connected to an empty, unmigrated one.

    Confirmed for real: when Alembic is handed an external connection this
    way, it does not commit on our behalf (it assumes the caller owns the
    transaction, per Alembic's own "sharing a connection" cookbook pattern)
    — without the explicit commit() below, both the DDL and the
    alembic_version row silently roll back the moment this connection closes.
    """
    cfg = _alembic_config(database_url)
    with engine.connect() as connection:
        cfg.attributes["connection"] = connection
        tables = set(inspect(connection).get_table_names())
        if not _has_applied_version(connection, tables) and "runs" in tables:
            command.stamp(cfg, "head")
        else:
            command.upgrade(cfg, "head")
        connection.commit()
