"""Application-attempt endpoints (PHASE11.md step 6) — split from
routes.py to stay under CLAUDE.md's 300-line file cap, mirroring the
existing routes_companies.py/routes_resume.py splits.

The route does the fast, synchronous work (pre-flight gates, row
creation) and enqueues a Huey task for the slow, real browser work — same
split `backend.scraper.tasks` already uses for scrape runs.
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import Engine, func, select

from backend.api.application_view import to_application_out
from backend.api.deps import LimitParam, OffsetParam, SessionDep
from backend.api.dto_applications import (
    ApplicationCreated,
    ApplicationDetail,
    ApplicationEventOut,
    ApplicationList,
    ApplicationRequest,
    CompanyBlockOut,
    CompanyBlockRequest,
    Confirmed,
    KillSwitchOut,
    KillSwitchRequest,
    Rejected,
)
from backend.api.stream import application_updates
from backend.autoapply import events, planner, safety
from backend.autoapply.tasks import execute_application_task, plan_application_page_task
from backend.db.models import Application, Company, Job

router = APIRouter()


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
    return ApplicationList(items=[to_application_out(session, row) for row in rows], total=total)


@router.get("/applications/{application_id}/stream")
def stream_application(application_id: int, request: Request) -> StreamingResponse:
    """SSE: a frame each time this application's detail payload changes
    (PHASE14.md step 4), same shape as GET /applications/{id} —
    registered before /applications/{application_id} so "stream" is
    never captured as an application_id path parameter (same ordering
    routes_runs.py already uses for GET /runs/stream)."""
    engine: Engine = request.app.state.engine
    return StreamingResponse(
        application_updates(engine, request, application_id), media_type="text/event-stream"
    )


@router.get("/applications/{application_id}")
def get_application(application_id: int, session: SessionDep) -> ApplicationDetail:
    application = session.get(Application, application_id)
    if application is None:
        raise HTTPException(404, "application not found")
    log = events.list_events(session, application)
    return ApplicationDetail(
        application=to_application_out(session, application),
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
