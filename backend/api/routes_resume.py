"""Resume upload/derived-position endpoints (PHASE7.md steps 2-3) — split
from routes.py to stay under CLAUDE.md's 300-line file cap.
"""

from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from backend import config
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
async def upload_resume(request: Request, file: Annotated[UploadFile, File()]) -> ResumeMarkdown:
    """Convert an uploaded resume PDF to Markdown (PHASE7.md step 2).

    Real size/type guard (PHASE9.md step 7) — an oversized or wrong-type
    file used to be fully read into memory (`await file.read()`) before any
    validation ran. Content-Length is checked first, a fast rejection with
    no read at all for the common case a browser/curl client sends it; the
    real byte count is checked again after reading as a fallback for the
    rare case a client omits it (e.g. chunked transfer encoding)."""
    content_length = request.headers.get("content-length")
    if content_length is not None and int(content_length) > config.RESUME_MAX_BYTES:
        raise HTTPException(413, f"resume file too large (max {config.RESUME_MAX_BYTES} bytes)")
    if file.content_type != config.RESUME_CONTENT_TYPE:
        raise HTTPException(422, f"unsupported file type: {file.content_type}")
    pdf_bytes = await file.read()
    if len(pdf_bytes) > config.RESUME_MAX_BYTES:
        raise HTTPException(413, f"resume file too large (max {config.RESUME_MAX_BYTES} bytes)")
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
