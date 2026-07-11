"""Shared pytest fixtures across the test suite."""

from pathlib import Path

import pytest

_RESUME_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "resume-backend.pdf"


@pytest.fixture
def resume_pdf_bytes() -> bytes:
    """A real, fixed synthetic resume PDF (a "Backend Engineer" persona,
    not real personal data) — used consistently across every test and
    smoke test that needs real resume bytes, instead of generating a new
    throwaway PDF each time."""
    return _RESUME_FIXTURE_PATH.read_bytes()
