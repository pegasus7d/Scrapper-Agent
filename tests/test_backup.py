"""Tests for the real SQLite backup mechanism (PHASE9.md step 5) — real
files on a real tmp_path, no mocking sqlite3 itself (a mock would prove
nothing about whether a real, openable backup file actually gets created)."""

import sqlite3
from pathlib import Path

import pytest

from backend import config
from backend.db import backup


@pytest.fixture
def real_source_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A real SQLite file with real rows — not the actual hirable.db, so
    the test suite never touches real project data, but genuinely openable
    and queryable, same as the real one."""
    db_path = tmp_path / "hirable.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE companies (id INTEGER PRIMARY KEY, name TEXT)")
    conn.executemany(
        "INSERT INTO companies (name) VALUES (?)", [("Acme",), ("Widgets Inc",), ("Foo Corp",)]
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(config, "DATABASE_FILE", str(db_path))
    monkeypatch.setattr(config, "BACKUP_DIR", str(tmp_path / "backups"))
    return db_path


def test_create_backup_creates_a_real_openable_sqlite_file(real_source_db: Path) -> None:
    dest = backup.create_backup()
    assert dest.exists()
    conn = sqlite3.connect(dest)
    rows = conn.execute("SELECT name FROM companies ORDER BY id").fetchall()
    conn.close()
    assert rows == [("Acme",), ("Widgets Inc",), ("Foo Corp",)]


def test_create_backup_names_files_with_a_real_timestamp(real_source_db: Path) -> None:
    dest = backup.create_backup()
    assert dest.name.startswith("hirable-")
    assert dest.name.endswith(".db")


def test_create_backup_prunes_beyond_retention_count(
    real_source_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "BACKUP_RETENTION_COUNT", 2)
    for _ in range(4):
        backup.create_backup()
    remaining = sorted(Path(config.BACKUP_DIR).glob("hirable-*.db"))
    assert len(remaining) == 2


def test_create_backup_keeps_the_newest_files_when_pruning(
    real_source_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "BACKUP_RETENTION_COUNT", 1)
    first = backup.create_backup()
    second = backup.create_backup()
    remaining = list(Path(config.BACKUP_DIR).glob("hirable-*.db"))
    assert remaining == [second]
    assert not first.exists()
