"""Resume PDF -> Markdown conversion (PHASE7.md step 2).

Kept separate from the scraper/extraction modules: parsing an uploaded
resume is a different domain from scraping public job postings, sharing
only the same FastAPI app and Pydantic-schema discipline.
"""

import pymupdf
import pymupdf4llm


class ResumeParseError(Exception):
    """Raised when the uploaded bytes aren't a real, parseable PDF."""


def pdf_to_markdown(pdf_bytes: bytes) -> str:
    """Convert a resume PDF's raw bytes to Markdown."""
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")  # type: ignore[no-untyped-call]
    except pymupdf.FileDataError as error:
        raise ResumeParseError(f"not a valid PDF: {error}") from error
    return pymupdf4llm.to_markdown(doc)  # type: ignore[no-any-return]
