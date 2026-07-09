"""Tests for resume PDF -> Markdown conversion (PHASE7.md step 2) — no
network, no LLM (CLAUDE.md): pymupdf/pymupdf4llm are pure local parsing.
"""

import pymupdf
import pytest

from backend.resume import ResumeParseError, pdf_to_markdown


def _minimal_pdf_bytes(text: str) -> bytes:
    """Build a real, minimal PDF in memory — no bundled binary fixture file."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    return doc.tobytes()  # type: ignore[no-any-return]


def test_pdf_to_markdown_extracts_real_text() -> None:
    pdf_bytes = _minimal_pdf_bytes("Backend Engineer with Python experience.")
    markdown = pdf_to_markdown(pdf_bytes)
    assert "Backend Engineer" in markdown


def test_pdf_to_markdown_rejects_non_pdf_bytes() -> None:
    with pytest.raises(ResumeParseError):
        pdf_to_markdown(b"not a real pdf at all, just garbage bytes")
