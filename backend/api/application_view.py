"""Shared Application -> ApplicationOut conversion (PHASE14.md step 4) —
used by both routes_applications.py and stream.py so the live SSE stream
and the one-shot GET return byte-identical payloads for the same
application, never two independently-maintained shapes.
"""

from sqlalchemy.orm import Session

from backend.api.dto_applications import ApplicationOut
from backend.db.models import Application, Company, Job


def to_application_out(session: Session, application: Application) -> ApplicationOut:
    """Built explicitly rather than via model_validate: company_name/
    job_title aren't real columns on Application, they're joined in here
    so the UI never has to make a second round-trip per row just to show
    a real company name instead of a bare id."""
    company = session.get(Company, application.company_id)
    job = session.get(Job, application.job_id) if application.job_id is not None else None
    return ApplicationOut(
        id=application.id,
        company_id=application.company_id,
        company_name=company.name if company is not None else "unknown",
        job_id=application.job_id,
        job_title=job.title if job is not None else None,
        status=application.status,
        risk_level=application.risk_level,
        started_at=application.started_at,
        finished_at=application.finished_at,
        error=application.error,
        planned_fields=application.planned_fields,
    )
