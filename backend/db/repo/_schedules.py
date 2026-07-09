"""Schedule CRUD and the due-check the background scheduler polls (DESIGN.md §9 step 6)."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Schedule


def create_schedule(session: Session, kind: str, source: str, every_hours: int) -> Schedule:
    """Insert and return a new enabled schedule."""
    schedule = Schedule(kind=kind, source=source, every_hours=every_hours)
    session.add(schedule)
    session.commit()
    return schedule


def list_schedules(session: Session) -> list[Schedule]:
    """Return every schedule, oldest first."""
    return list(session.scalars(select(Schedule).order_by(Schedule.id)).all())


def set_schedule_enabled(session: Session, schedule_id: int, enabled: bool) -> Schedule | None:
    """Flip a schedule's enabled flag; returns None when it doesn't exist."""
    schedule = session.get(Schedule, schedule_id)
    if schedule is None:
        return None
    schedule.enabled = enabled
    session.commit()
    return schedule


def due_schedules(session: Session, now: datetime) -> list[Schedule]:
    """Enabled schedules that have never run, or whose interval has elapsed."""
    # SQLite round-trips DateTime columns as naive (same convention as
    # started_at/finished_at elsewhere) — drop tzinfo from `now` to compare.
    naive_now = now.replace(tzinfo=None)
    enabled = session.scalars(select(Schedule).where(Schedule.enabled)).all()
    return [
        schedule
        for schedule in enabled
        if schedule.last_run_at is None
        or naive_now - schedule.last_run_at >= timedelta(hours=schedule.every_hours)
    ]


def mark_schedule_run(session: Session, schedule: Schedule, now: datetime) -> None:
    """Record that a schedule just triggered a run, resetting its interval clock."""
    schedule.last_run_at = now
    session.commit()
