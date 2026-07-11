"""Structured applicant profile endpoints (PHASE10.md step 5) — split from
routes.py to stay under CLAUDE.md's 300-line file cap.
"""

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from backend import config
from backend.api.deps import SessionDep
from backend.api.dto import (
    ApplicantProfileIn,
    ApplicantProfileOut,
    MatchScoreList,
    MatchScoreOut,
)
from backend.autoapply import matching
from backend.autoapply.profile import get_profile, save_profile
from backend.db.models import ApplicantProfile, Job

router = APIRouter()


def _to_out(row: ApplicantProfile) -> ApplicantProfileOut:
    return ApplicantProfileOut(
        phone=row.phone,
        current_salary=row.current_salary,
        expected_salary=row.expected_salary,
        work_authorization=row.work_authorization,
        relocation=row.relocation,
        start_date_availability=row.start_date_availability,
        has_resume=row.resume_markdown is not None,
    )


@router.get("/profile")
def read_profile(session: SessionDep) -> ApplicantProfileOut:
    """The current applicant profile — all fields unset until the user saves some."""
    return _to_out(get_profile(session))


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
    return _to_out(row)


@router.get("/profile/match-scores")
def profile_match_scores(session: SessionDep) -> MatchScoreList:
    """Real match-score distribution over every job with a stored
    embedding (PHASE11.md step 4) — lets the user see, on their own real
    data, what MATCH_SCORE_THRESHOLD's default would gate out before
    trusting it blindly."""
    profile_row = get_profile(session)
    if profile_row.resume_markdown is None:
        raise HTTPException(422, "no resume uploaded yet")

    scored = matching.score_all_jobs(session, profile_row.resume_markdown)
    job_ids = [job_id for job_id, _ in scored]
    jobs_by_id = {job.id: job for job in session.scalars(select(Job).where(Job.id.in_(job_ids)))}
    items = [
        MatchScoreOut(
            job_id=job_id,
            title=jobs_by_id[job_id].title,
            company=jobs_by_id[job_id].company,
            score=score,
        )
        for job_id, score in scored
        if job_id in jobs_by_id
    ]
    return MatchScoreList(items=items, threshold=config.MATCH_SCORE_THRESHOLD)
