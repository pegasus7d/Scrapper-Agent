"""The application-attempt planner (PHASE11.md step 5) — composes every
safety control built in PHASE10.md into one dry, review-only pass: real
field detection, one answer per field, risk classification, and a fully
persisted plan. Ends at "awaiting_confirmation" — this module is
structurally incapable of filling or submitting anything on a real page;
it only ever calls `detect_fields`, never `fill_field`/`upload_file`/
`submit`. The first real submission happens only when a human confirms
the persisted plan (step 7's executor), never here.
"""

import logging
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend import config
from backend.autoapply import events, safety
from backend.autoapply.answers import Answer, build_answer_extractor
from backend.autoapply.answers import answer_field as answer_one_field
from backend.autoapply.filler import DetectedField, detect_fields
from backend.autoapply.matching import gate as match_gate
from backend.autoapply.profile import get_profile
from backend.autoapply.providers import (
    PagePreparationFailed,
    UnknownProvider,
    prepare_application_page,
)
from backend.db.models import ApplicantProfile, Application, Company, Job

logger = logging.getLogger(__name__)


class NoResolvedProvider(Exception):
    """Raised when the job's company has no resolved ats_provider."""


class CompanyBlocked(Exception):
    """Raised when the company is on the auto-apply blocklist."""


class DuplicateApplication(Exception):
    """Raised when an Application already exists for this exact company/job pair."""


class NoResumeUploaded(Exception):
    """Raised when no resume has been uploaded — the planner needs real
    resume text to gate on match score and answer open-ended questions."""


class MatchScoreTooLow(Exception):
    """Raised when the job's real match score is below MATCH_SCORE_THRESHOLD."""


def _resolve_company(session: Session, job: Job) -> Company:
    company = session.scalar(select(Company).where(Company.name == job.company))
    if company is None or company.ats_provider is None:
        raise NoResolvedProvider(f"{job.company!r} has no resolved ats_provider")
    return company


def _question_text(field: DetectedField) -> str:
    # Grouped radios (PHASE11.md step 3) have no group-level label of
    # their own, only per-option labels — falls back to the field's real
    # name= as the closest available question text, a real, honest
    # limitation rather than a fabricated question.
    return field.label or field.name


def _job_posting_text(job: Job) -> str:
    # Same real "text_for_embedding" convention repo/_writes.py's
    # save_job already uses — one consistent job-text format, not a
    # second, differently-shaped one invented here.
    return f"{job.title} at {job.company}. " + " ".join(job.requirements)


def _overall_confidence(answered: list[Answer]) -> float | None:
    """A real, simple confidence proxy: any open-ended LLM guess makes the
    whole plan uncertain (None, fails safe to high risk); a genuinely
    unanswered field is a different, less risky situation — we know we
    don't have data for it, we didn't guess."""
    if any(answer.source == "llm" for answer in answered):
        return None
    return 1.0


def check_preflight(session: Session, job: Job) -> tuple[Company, ApplicantProfile, bool]:
    """Every fast, pure-DB pre-flight gate — no browser involved. Raises a
    real, typed exception for the first gate that fails. Returns
    (company, profile_row, is_first_application_to_company) once every
    gate passes, so a caller (the API route) can surface a real 422
    immediately, before any Application row exists or any Huey task
    enqueues real, slow browser work."""
    if safety.kill_switch_enabled(session):
        raise safety.KillSwitchActive("kill switch is on")

    company = _resolve_company(session, job)
    if safety.is_company_blocked(company):
        raise CompanyBlocked(f"{company.name} is blocked from auto-apply")
    if safety.has_existing_application(session, company_id=company.id, job_id=job.id):
        raise DuplicateApplication(f"an application already exists for job {job.id}")

    safety.check_daily_cap(session)
    safety.check_pacing(session)

    profile_row = get_profile(session)
    if profile_row.resume_markdown is None:
        raise NoResumeUploaded("no resume uploaded yet")

    match_context = match_gate(session, job_id=job.id, resume_text=profile_row.resume_markdown)
    if not match_context.passed:
        raise MatchScoreTooLow(
            f"job {job.id} scored {match_context.score:.2f}, "
            f"below the {config.MATCH_SCORE_THRESHOLD:.2f} threshold"
        )

    # Computed before start_application creates this attempt's own row --
    # afterward, "any application exists for this company" would always
    # be true, including for this brand-new first attempt.
    is_first_application = not safety.has_existing_application(
        session, company_id=company.id, job_id=None
    )
    return company, profile_row, is_first_application


def plan_application(session: Session, job: Job) -> Application:
    """The full, synchronous plan: every pre-flight gate, then the real
    (slow) browser work, in one call — used directly by tests and by any
    caller that doesn't need the API's fast-fail/async-task split.
    `run_page_planning` is what `backend.autoapply.tasks`' Huey task calls
    instead, once the API route has already run `check_preflight` and
    created the Application row itself."""
    company, profile_row, is_first_application = check_preflight(session, job)
    application = events.start_application(session, company_id=company.id, job_id=job.id)
    run_page_planning(session, application, job, company, profile_row, is_first_application)
    return application


def _detect_real_fields(company: Company, job: Job) -> list[DetectedField] | None:
    """Real, read-only browser work: open the page, detect fields, close
    the browser. Returns None (never raises past this point) on any real
    navigation/detection failure — the caller records that as a failed
    application, not a plan-time exception."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            try:
                # _resolve_company already guarantees this is not None.
                assert company.ats_provider is not None
                prepare_application_page(page, company.ats_provider, job.posting_url)
                return detect_fields(page)
            except (PlaywrightError, UnknownProvider, PagePreparationFailed) as error:
                logger.warning("plan_application: page preparation failed: %s", error)
                return None
            finally:
                page.close()
        finally:
            browser.close()


def run_page_planning(
    session: Session,
    application: Application,
    job: Job,
    company: Company,
    profile_row: ApplicantProfile,
    is_first_application: bool,
) -> None:
    """The real, slow browser work: detect fields, answer each one,
    classify risk, persist the plan. Called directly by plan_application
    for the synchronous, all-in-one path, and by
    backend.autoapply.tasks' Huey task for the API's async path."""
    fields = _detect_real_fields(company, job)
    if not fields:
        events.finish_application(
            session, application, status="failed", error="no fillable fields detected"
        )
        return

    extractor = build_answer_extractor()
    job_posting_text = _job_posting_text(job)
    answered: list[Answer] = []
    planned_fields: list[dict[str, Any]] = []

    for field in fields:
        answer = answer_one_field(
            session,
            application,
            extractor,
            profile_row,
            question=_question_text(field),
            resume_markdown=profile_row.resume_markdown or "",
            job_posting_text=job_posting_text,
        )
        answered.append(answer)
        planned_fields.append(
            {
                "field_name": field.name,
                "label": field.label,
                "input_type": field.input_type,
                "answer": answer.text,
                "source": answer.source,
            }
        )

    risk = safety.classify_risk(
        is_first_application_to_company=is_first_application,
        llm_confidence=_overall_confidence(answered),
    )
    events.mark_awaiting_confirmation(
        session, application, risk_level=risk, planned_fields=planned_fields
    )
