"""Application-attempt endpoints (PHASE11.md step 6) — split from
routes.py to stay under CLAUDE.md's 300-line file cap, mirroring the
existing routes_companies.py/routes_resume.py splits.

The route does the fast, synchronous work (pre-flight gates, row
creation) and enqueues a Huey task for the slow, real browser work — same
split `backend.scraper.tasks` already uses for scrape runs.
"""

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.api.deps import LimitParam, OffsetParam, SessionDep
from backend.api.dto import (
    ApplicationCreated,
    ApplicationDetail,
    ApplicationEventOut,
    ApplicationList,
    ApplicationOut,
    ApplicationRequest,
    CompanyBlockOut,
    CompanyBlockRequest,
    Confirmed,
    KillSwitchOut,
    KillSwitchRequest,
    Rejected,
)
from backend.autoapply import events, planner, safety
from backend.autoapply.tasks import execute_application_task, plan_application_page_task
from backend.db.models import Application, Company, Job

router = APIRouter()


def _to_out(session: Session, application: Application) -> ApplicationOut:
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


@router.post("/applications", status_code=201)
def start_application(body: ApplicationRequest, session: SessionDep) -> ApplicationCreated:
    job = session.get(Job, body.job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    if safety.active_application_exists(session):
        raise HTTPException(409, "an application attempt is already active")

    try:
        company, _profile_row, is_first_application = planner.check_preflight(session, job)
    except (
        safety.KillSwitchActive,
        safety.ApplicationCapReached,
        safety.PacingViolation,
        planner.NoResolvedProvider,
        planner.CompanyBlocked,
        planner.DuplicateApplication,
        planner.NoResumeUploaded,
        planner.MatchScoreTooLow,
    ) as error:
        raise HTTPException(422, str(error)) from error

    application = events.start_application(session, company_id=company.id, job_id=job.id)
    plan_application_page_task(application.id, job.id, company.id, is_first_application)
    return ApplicationCreated(application_id=application.id)


@router.get("/applications")
def list_applications(
    session: SessionDep, limit: LimitParam = 20, offset: OffsetParam = 0
) -> ApplicationList:
    query = select(Application).order_by(Application.id.desc())
    total = session.scalar(select(func.count()).select_from(Application)) or 0
    rows = session.scalars(query.limit(limit).offset(offset)).all()
    return ApplicationList(items=[_to_out(session, row) for row in rows], total=total)


@router.get("/applications/{application_id}")
def get_application(application_id: int, session: SessionDep) -> ApplicationDetail:
    application = session.get(Application, application_id)
    if application is None:
        raise HTTPException(404, "application not found")
    log = events.list_events(session, application)
    return ApplicationDetail(
        application=_to_out(session, application),
        events=[ApplicationEventOut.model_validate(event) for event in log],
    )


@router.post("/applications/{application_id}/reject")
def reject_application(application_id: int, session: SessionDep) -> Rejected:
    application = session.get(Application, application_id)
    if application is None:
        raise HTTPException(404, "application not found")
    if application.status != "awaiting_confirmation":
        raise HTTPException(
            422, f"application is {application.status!r}, not awaiting_confirmation"
        )
    events.record_event(session, application, action="reject", success=True)
    events.finish_application(session, application, status="rejected")
    return Rejected(rejected=True)


@router.post("/applications/{application_id}/confirm")
def confirm_application(application_id: int, session: SessionDep) -> Confirmed:
    """Records the real confirmation event, then enqueues the executor —
    execute_submission itself still refuses to run without exactly this
    event recorded, so this endpoint is not the only thing guarding a
    real submission."""
    application = session.get(Application, application_id)
    if application is None:
        raise HTTPException(404, "application not found")
    if application.status != "awaiting_confirmation":
        raise HTTPException(
            422, f"application is {application.status!r}, not awaiting_confirmation"
        )
    events.record_event(session, application, action="confirm", success=True)
    execute_application_task(application_id)
    return Confirmed(confirmed=True)


@router.get("/autoapply/kill-switch")
def read_kill_switch(session: SessionDep) -> KillSwitchOut:
    return KillSwitchOut(enabled=safety.kill_switch_enabled(session))


@router.post("/autoapply/kill-switch")
def set_kill_switch(body: KillSwitchRequest, session: SessionDep) -> KillSwitchOut:
    safety.set_kill_switch(session, body.enabled)
    return KillSwitchOut(enabled=body.enabled)


@router.post("/companies/{company_id}/auto-apply-block")
def set_company_auto_apply_block(
    company_id: int, body: CompanyBlockRequest, session: SessionDep
) -> CompanyBlockOut:
    company = session.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "company not found")
    company.auto_apply_blocked = body.blocked
    session.commit()
    return CompanyBlockOut(blocked=company.auto_apply_blocked)
