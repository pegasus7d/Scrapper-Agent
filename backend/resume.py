"""Resume PDF -> Markdown -> derived search positions (PHASE7.md steps 2-3).

Kept separate from the scraper/extraction modules: parsing an uploaded
resume is a different domain from scraping public job postings, sharing
only the same FastAPI app and Pydantic-schema discipline. Position
derivation deliberately reuses the extraction cascade (Extractor,
OllamaClient, FrontierClient) rather than a parallel LLM-calling path —
same retry/validate/optionally-escalate discipline job/question extraction
already gets, not a second bespoke mechanism for one more schema.
"""

from pathlib import Path

import pymupdf
import pymupdf4llm

from backend import config
from backend.llm.client import FrontierClient, LLMClient, OllamaClient
from backend.schemas import ResumePosition
from backend.scraper.extractor import Extractor


class ResumeParseError(Exception):
    """Raised when the uploaded bytes aren't a real, parseable PDF."""


def pdf_to_markdown(pdf_bytes: bytes) -> str:
    """Convert a resume PDF's raw bytes to Markdown."""
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")  # type: ignore[no-untyped-call]
    except pymupdf.FileDataError as error:
        raise ResumeParseError(f"not a valid PDF: {error}") from error
    return pymupdf4llm.to_markdown(doc)  # type: ignore[no-any-return]


def save_resume_pdf(pdf_bytes: bytes, path: str = config.RESUME_STORAGE_PATH) -> None:
    """Persist the real, validated PDF bytes to disk (PHASE11.md step 1) —
    the executor attaches this exact file to a real application form
    rather than requiring a re-upload per attempt. Called only after
    pdf_to_markdown() has already confirmed the bytes parse as a real PDF."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(pdf_bytes)


def build_resume_extractor(model: str = config.LOCAL_MODEL) -> Extractor[ResumePosition]:
    """Wire the same two-tier cascade pipeline.build_extractor() does, just
    parameterized for ResumePosition instead of the job/question union —
    Extractor is generic per-instance, so a differently-typed one is needed
    rather than reusing that job/question-typed builder."""
    api_key = config.anthropic_api_key()
    local: LLMClient = OllamaClient(model)
    frontier: LLMClient | None = FrontierClient(api_key) if api_key is not None else None
    return Extractor[ResumePosition](local, frontier=frontier)


def derive_search_positions(markdown: str, extractor: Extractor[ResumePosition]) -> list[str]:
    """Ask which job titles this resume genuinely supports searching for.

    `extractor` is injected (build_resume_extractor() at the real call
    site, a fake in tests) — same dependency-injection discipline
    pipeline.py's execute_run(extractor=...) already uses, rather than
    building it internally where a test can't substitute it.
    """
    result = extractor.extract(markdown, ResumePosition)
    return [item.title for item in result.items]
