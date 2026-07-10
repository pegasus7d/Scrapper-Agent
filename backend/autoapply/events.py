"""Application lifecycle + append-only audit event log (PHASE10.md step 4).

Mirrors `backend/db/repo/_writes.py`'s Run lifecycle
(`create_run`/`finish_run`) — `Application` is the per-attempt
observability record, the same real role `Run` plays for scrape runs.
`ApplicationEvent` rows are never updated or deleted once written: each
call to `record_event` appends a new row, giving a genuine per-application
replay (propose -> execute -> observe, OpenHands' own Event pattern, this
phase's own prior-art research) rather than a final-outcome summary.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Application, ApplicationEvent

logger = logging.getLogger(__name__)


def start_application(
    session: Session, *, company_id: int, job_id: int | None = None, risk_level: str = "low"
) -> Application:
    """Insert and return a new application in "pending" state."""
    application = Application(
        company_id=company_id,
        job_id=job_id,
        risk_level=risk_level,
        status="pending",
        started_at=datetime.now(UTC),
    )
    session.add(application)
    session.commit()
    return application


def finish_application(
    session: Session, application: Application, *, status: str, error: str | None = None
) -> None:
    """Mark the application finished with the given terminal status."""
    application.status = status
    application.error = error
    application.finished_at = datetime.now(UTC)
    session.commit()
    logger.info("application %s finished: %s", application.id, status)


def record_event(
    session: Session,
    application: Application,
    *,
    action: str,
    success: bool,
    detail: str | None = None,
    parent_event_id: int | None = None,
) -> ApplicationEvent:
    """Append one event to the application's audit trail — never updates or
    deletes a prior event, only ever inserts a new one."""
    event = ApplicationEvent(
        application_id=application.id,
        parent_event_id=parent_event_id,
        action=action,
        success=success,
        detail=detail,
        created_at=datetime.now(UTC),
    )
    session.add(event)
    session.commit()
    if not success:
        logger.warning("application %s event %r failed: %s", application.id, action, detail)
    return event


def list_events(session: Session, application: Application) -> list[ApplicationEvent]:
    """Every event for one application, oldest first — the real replay order."""
    query = select(ApplicationEvent).where(ApplicationEvent.application_id == application.id)
    return list(session.scalars(query.order_by(ApplicationEvent.created_at)).all())
