"""Real SQLite backup mechanism (PHASE9.md step 5) — hirable.db held real,
growing personal data (1920+ discovered companies, months of scraped
jobs/questions, resume-derived data) with zero recovery story until now.

Uses `sqlite3.Connection.backup()`, not a raw file copy — the real,
documented-safe way to back up a live SQLite database (a plain
`shutil.copy2` mid-write could produce a genuinely corrupt file if a write
lands during the copy; a raw copy is fine for the backup *target*, an
already-closed static file, but never for the live source).
"""

import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from backend import config

logger = logging.getLogger(__name__)

_BACKUP_GLOB = "hirable-*.db"


def create_backup() -> Path:
    """Copy hirable.db to a real, timestamped file in BACKUP_DIR, then
    prune backups beyond BACKUP_RETENTION_COUNT."""
    backup_dir = Path(config.BACKUP_DIR)
    backup_dir.mkdir(exist_ok=True)
    # Microsecond precision, not just seconds — two backups within the same
    # second (never happens at the real once-daily cadence, but a real,
    # latent bug caught by this file's own test suite) would otherwise
    # collide on the same filename and silently overwrite each other.
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    dest = backup_dir / f"hirable-{timestamp}.db"

    source_conn = sqlite3.connect(config.DATABASE_FILE)
    try:
        dest_conn = sqlite3.connect(dest)
        try:
            source_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        source_conn.close()

    logger.info("database backup created: %s", dest)
    _prune_old_backups(backup_dir)
    return dest


def _prune_old_backups(backup_dir: Path) -> None:
    # Timestamped filenames sort lexicographically the same as chronologically.
    backups = sorted(backup_dir.glob(_BACKUP_GLOB), reverse=True)
    for stale in backups[config.BACKUP_RETENTION_COUNT :]:
        stale.unlink()
        logger.info("pruned old backup: %s", stale)
