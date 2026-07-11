"""Structured applicant profile persistence (PHASE10.md step 5) — the real
inputs a form-filler answer-tool (step 7) will read from. Nothing here
invents a real phone number, salary, or work-authorization status; it only
ever stores exactly what the user enters via the frontend form, defaulting
to unset (None) until they do.
"""

from sqlalchemy.orm import Session

from backend.db.models import ApplicantProfile

_PROFILE_ROW_ID = 1


def get_profile(session: Session) -> ApplicantProfile:
    """The single applicant-profile row, creating an all-unset one on first read."""
    row = session.get(ApplicantProfile, _PROFILE_ROW_ID)
    if row is None:
        row = ApplicantProfile(id=_PROFILE_ROW_ID)
        session.add(row)
        session.commit()
    return row


def save_profile(
    session: Session,
    *,
    phone: str | None,
    current_salary: str | None,
    expected_salary: str | None,
    work_authorization: str | None,
    relocation: bool | None,
    start_date_availability: str | None,
) -> ApplicantProfile:
    """Overwrite the profile with exactly the given values."""
    row = get_profile(session)
    row.phone = phone
    row.current_salary = current_salary
    row.expected_salary = expected_salary
    row.work_authorization = work_authorization
    row.relocation = relocation
    row.start_date_availability = start_date_availability
    session.commit()
    return row


def save_resume_markdown(session: Session, markdown: str) -> ApplicantProfile:
    """Update only the resume Markdown (PHASE11.md step 1) — a resume
    re-upload must not clobber salary/phone/etc. the way a full
    save_profile() call would; every other field is left untouched."""
    row = get_profile(session)
    row.resume_markdown = markdown
    session.commit()
    return row
