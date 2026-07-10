"""Structured applicant profile endpoints (PHASE10.md step 5) — split from
routes.py to stay under CLAUDE.md's 300-line file cap.
"""

from fastapi import APIRouter

from backend.api.deps import SessionDep
from backend.api.dto import ApplicantProfileIn, ApplicantProfileOut
from backend.autoapply.profile import get_profile, save_profile

router = APIRouter()


@router.get("/profile")
def read_profile(session: SessionDep) -> ApplicantProfileOut:
    """The current applicant profile — all fields unset until the user saves some."""
    return ApplicantProfileOut.model_validate(get_profile(session))


@router.post("/profile")
def update_profile(body: ApplicantProfileIn, session: SessionDep) -> ApplicantProfileOut:
    """Overwrite the profile with exactly the given values — never invents any."""
    row = save_profile(
        session,
        phone=body.phone,
        current_salary=body.current_salary,
        expected_salary=body.expected_salary,
        work_authorization=body.work_authorization,
        relocation=body.relocation,
        start_date_availability=body.start_date_availability,
    )
    return ApplicantProfileOut.model_validate(row)
