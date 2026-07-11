"""Tests for resume PDF -> Markdown -> derived positions (PHASE7.md steps
2-3) — no network, no LLM (CLAUDE.md): pymupdf/pymupdf4llm are pure local
parsing, and derive_search_positions takes an injected fake Extractor.
"""

import json
from pathlib import Path

import pytest

from backend import resume as resume_module
from backend.llm.client import FrontierClient
from backend.resume import (
    ResumeParseError,
    build_resume_extractor,
    derive_search_positions,
    pdf_to_markdown,
    save_resume_pdf,
)
from backend.schemas import ResumePosition
from backend.scraper.extractor import Extractor


def test_pdf_to_markdown_extracts_real_text(resume_pdf_bytes: bytes) -> None:
    markdown = pdf_to_markdown(resume_pdf_bytes)
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


def test_save_resume_pdf_writes_the_real_bytes(tmp_path: Path, resume_pdf_bytes: bytes) -> None:
    destination = tmp_path / "resume.pdf"
    save_resume_pdf(resume_pdf_bytes, str(destination))
    assert destination.read_bytes() == resume_pdf_bytes


def test_save_resume_pdf_creates_missing_parent_directories(tmp_path: Path) -> None:
    destination = tmp_path / "nested" / "dir" / "resume.pdf"
    save_resume_pdf(b"real pdf bytes", str(destination))
    assert destination.read_bytes() == b"real pdf bytes"


def test_save_resume_pdf_overwrites_a_prior_upload(tmp_path: Path) -> None:
    destination = tmp_path / "resume.pdf"
    save_resume_pdf(b"first upload", str(destination))
    save_resume_pdf(b"second upload", str(destination))
    assert destination.read_bytes() == b"second upload"
