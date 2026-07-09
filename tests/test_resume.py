"""Tests for resume PDF -> Markdown -> derived positions (PHASE7.md steps
2-3) — no network, no LLM (CLAUDE.md): pymupdf/pymupdf4llm are pure local
parsing, and derive_search_positions takes an injected fake Extractor.
"""

import json

import pymupdf
import pytest

from backend import resume as resume_module
from backend.llm.client import FrontierClient
from backend.resume import (
    ResumeParseError,
    build_resume_extractor,
    derive_search_positions,
    pdf_to_markdown,
)
from backend.schemas import ResumePosition
from backend.scraper.extractor import Extractor


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


class _ScriptedClient:
    """Fake LLMClient returning one queued response — same pattern
    test_extractor.py uses for the shared Extractor cascade."""

    def __init__(self, response: str) -> None:
        self._response = response

    def complete(self, prompt: str, *, schema: dict | None = None) -> str:
        return self._response


def test_derive_search_positions_returns_real_titles() -> None:
    response = json.dumps({"items": [{"title": "Backend Engineer"}, {"title": "Python Developer"}]})
    extractor: Extractor[ResumePosition] = Extractor(_ScriptedClient(response), frontier=None)
    positions = derive_search_positions("some resume markdown", extractor)
    assert positions == ["Backend Engineer", "Python Developer"]


def test_derive_search_positions_empty_when_nothing_supported() -> None:
    extractor: Extractor[ResumePosition] = Extractor(
        _ScriptedClient(json.dumps({"items": []})), frontier=None
    )
    assert derive_search_positions("irrelevant text", extractor) == []


def test_build_resume_extractor_without_api_key_disables_escalation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(resume_module.config, "anthropic_api_key", lambda: None)
    assert build_resume_extractor()._frontier is None


def test_build_resume_extractor_with_api_key_enables_frontier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(resume_module.config, "anthropic_api_key", lambda: "sk-test")
    assert isinstance(build_resume_extractor()._frontier, FrontierClient)
