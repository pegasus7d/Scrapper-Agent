"""The confirmed-application executor (PHASE11.md step 7) — the only
module in this project that can cause a real application submission.
Refuses to run unless the application is genuinely `awaiting_confirmation`
with a recorded confirmation event and the kill switch is off. Re-detects
the live form and fails safe on any drift from the reviewed plan, rather
than filling a form that changed since a human looked at it.

**Gate discipline**: this module's own tests and smoke test run only
against the local test-form server (PHASE10.md step 1) — never against a
real, live ATS. The first real submission is the user's own confirmation
in the UI, against a plan they reviewed; that action is never exercised
by this project's own build/test loop.
"""

import logging

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, sync_playwright
from sqlalchemy.orm import Session

from backend import config
from backend.autoapply import events, safety
from backend.autoapply.filler import DetectedField, detect_fields
from backend.autoapply.filler_actions import fill_field, submit, upload_file
from backend.autoapply.filler_types import ActionResult
from backend.autoapply.providers import (
    PagePreparationFailed,
    UnknownProvider,
    prepare_application_page,
)
from backend.db.models import Application, Company, Job

logger = logging.getLogger(__name__)

_CONFIRMATION_SELECTOR = "#confirmation"


class NotAwaitingConfirmation(Exception):
    """Raised when the application isn't in a confirmable state."""


class NotConfirmed(Exception):
    """Raised when no confirmation event has been recorded for this application."""


def _is_confirmed(session: Session, application: Application) -> bool:
    return any(event.action == "confirm" for event in events.list_events(session, application))


def _plan_matches_live_fields(
    planned_fields: list[dict[str, str | None]], live_names: set[str]
) -> bool:
    """The real, structural drift check: the exact set of field names must
    match. A live form with a field added/removed/renamed since the plan
    was reviewed is a real, different form — never filled blind."""
    planned_names = {str(field["field_name"]) for field in planned_fields}
    return planned_names == live_names


def _planned_answer(planned_fields: list[dict[str, str | None]], field_name: str) -> str | None:
    for planned in planned_fields:
        if planned["field_name"] == field_name:
            return planned["answer"]
    return None


def execute_submission(session: Session, application: Application) -> None:
    """Fill and submit exactly the plan a human already reviewed and
    confirmed. Every real failure — drift, a fill error, a submit error,
    no real confirmation-page state afterward — marks the application
    "failed" with the reason recorded, never left hanging."""
    if application.status != "awaiting_confirmation":
        raise NotAwaitingConfirmation(f"application {application.id} is {application.status!r}")
    if not _is_confirmed(session, application):
        raise NotConfirmed(f"application {application.id} has no recorded confirmation event")
    if safety.kill_switch_enabled(session):
        raise safety.KillSwitchActive("kill switch is on")

    company = session.get(Company, application.company_id)
    job = session.get(Job, application.job_id) if application.job_id is not None else None
    if company is None or job is None or company.ats_provider is None:
        events.finish_application(
            session, application, status="failed", error="missing company/job/provider"
        )
        return

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            try:
                _execute_on_page(session, application, page, company.ats_provider, job.posting_url)
            finally:
                page.close()
        finally:
            browser.close()


def _execute_on_page(
    session: Session, application: Application, page: Page, ats_provider: str, posting_url: str
) -> None:
    try:
        prepare_application_page(page, ats_provider, posting_url)
        fields = detect_fields(page)
    except (PlaywrightError, UnknownProvider, PagePreparationFailed) as error:
        events.finish_application(session, application, status="failed", error=str(error))
        return

    live_names = {field.name for field in fields}
    if not _plan_matches_live_fields(application.planned_fields, live_names):
        events.finish_application(
            session, application, status="failed", error="live form drifted from the reviewed plan"
        )
        return

    for field in fields:
        result = _fill_one_field(page, field, application.planned_fields)
        if result is None:
            continue  # nothing planned for this field -- left blank, same as detect_and_fill
        events.record_event(
            session,
            application,
            action=f"fill_field:{field.name}",
            success=result.success,
            detail=result.error,
        )
        if not result.success:
            events.finish_application(
                session,
                application,
                status="failed",
                error=f"failed to fill {field.name}: {result.error}",
            )
            return

    submit_result = submit(page)
    events.record_event(
        session,
        application,
        action="submit",
        success=submit_result.success,
        detail=submit_result.error,
    )
    if not submit_result.success:
        events.finish_application(session, application, status="failed", error=submit_result.error)
        return

    # Real confirmation-page verification -- currently tuned to the local
    # test form's own #confirmation markup (PHASE10.md step 1); a real
    # ATS's confirmation-page shape is unknown until the submission gate
    # is separately crossed and this gets generalized against real data.
    try:
        page.wait_for_selector(_CONFIRMATION_SELECTOR, timeout=5000)
    except PlaywrightError:
        events.finish_application(
            session,
            application,
            status="failed",
            error="no confirmation element found after submit",
        )
        return

    events.finish_application(session, application, status="submitted")


def _fill_one_field(
    page: Page, field: DetectedField, planned_fields: list[dict[str, str | None]]
) -> ActionResult | None:
    answer = _planned_answer(planned_fields, field.name)
    if answer is None:
        return None
    if field.input_type == "file":
        return upload_file(page, field, config.RESUME_STORAGE_PATH)
    return fill_field(page, field, answer)
