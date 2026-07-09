"""Tests for the extraction prompt templates."""

import pytest

from backend.schemas import JobExtract, QuestionExtract
from backend.scraper.prompts import extraction_prompt, retry_prompt


def test_job_prompt_contains_label_schema_and_text() -> None:
    prompt = extraction_prompt(JobExtract, "We are hiring a backend engineer.")
    assert "job posting" in prompt
    assert "title" in prompt and "company" in prompt
    assert "We are hiring a backend engineer." in prompt


def test_question_prompt_uses_question_label() -> None:
    prompt = extraction_prompt(QuestionExtract, "They asked me to invert a tree.")
    assert "interview question" in prompt
    assert "question" in prompt


def test_question_prompt_includes_relevance_criteria() -> None:
    prompt = extraction_prompt(QuestionExtract, "They asked me to invert a tree.")
    assert "specific company or employer is named" in prompt
    assert "stated concretely" in prompt


def test_job_prompt_has_no_extra_criteria_noise() -> None:
    prompt = extraction_prompt(JobExtract, "We are hiring a backend engineer.")
    assert "specific company or employer is named" not in prompt


def test_question_prompt_allows_generic_companyless_questions() -> None:
    # PHASE3.md step 4: curated GitHub question banks name no company.
    prompt = extraction_prompt(QuestionExtract, "They asked me to invert a tree.")
    assert "generic reference source" in prompt
    assert "set `company` to null" in prompt


def test_unknown_schema_raises() -> None:
    class Unknown(JobExtract):
        pass

    with pytest.raises(ValueError, match="no prompt label"):
        extraction_prompt(Unknown, "text")


def test_retry_prompt_includes_previous_and_error() -> None:
    prompt = retry_prompt("original prompt", "field 'title' is required")
    assert "original prompt" in prompt
    assert "field 'title' is required" in prompt
