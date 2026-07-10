"""Resume upload/derived-position endpoints (PHASE7.md steps 2-3) — split
from routes.py to stay under CLAUDE.md's 300-line file cap.
"""

from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile

from backend.api.dto import ResumeMarkdown, ResumePositionsOut
from backend.resume import (
    ResumeParseError,
    build_resume_extractor,
    derive_search_positions,
    pdf_to_markdown,
)
from backend.scraper.extractor import ExtractionFailed

router = APIRouter()


@router.post("/resume")
async def upload_resume(file: Annotated[UploadFile, File()]) -> ResumeMarkdown:
    """Convert an uploaded resume PDF to Markdown (PHASE7.md step 2)."""
    pdf_bytes = await file.read()
    try:
        markdown = pdf_to_markdown(pdf_bytes)
    except ResumeParseError as error:
        raise HTTPException(422, str(error)) from error
    return ResumeMarkdown(markdown=markdown)


@router.post("/resume/positions")
def resume_positions(body: ResumeMarkdown) -> ResumePositionsOut:
    """Derive job-search positions from resume Markdown (PHASE7.md step 3),
    reusing the same extraction cascade job/question extraction uses."""
    try:
        positions = derive_search_positions(body.markdown, build_resume_extractor())
    except ExtractionFailed as error:
        raise HTTPException(502, f"couldn't derive positions: {error}") from error
    return ResumePositionsOut(positions=positions)
