"""Tests for the LLM extraction contracts (DESIGN.md §7)."""

import pytest
from pydantic import ValidationError

from backend.schemas import JobExtract, QuestionExtract

VALID_JOB = {
    "title": "Senior Backend Engineer",
    "company": "Acme",
    "location": "Remote (EU)",
    "salary": "$150k-$180k",
    "requirements": ["Python", "PostgreSQL"],
    "apply_url": "https://acme.example/apply",
}

VALID_QUESTION = {
    "company": "Acme",
    "role": "SWE II",
    "question": "Design a rate limiter for a public API.",
    "round": "onsite",
}


def test_valid_job_payload_passes() -> None:
    job = JobExtract.model_validate(VALID_JOB)
    assert job.title == "Senior Backend Engineer"
    assert job.requirements == ["Python", "PostgreSQL"]


def test_job_optional_fields_accept_none() -> None:
    payload = {**VALID_JOB, "location": None, "salary": None, "apply_url": None}
    job = JobExtract.model_validate(payload)
    assert job.location is None


def test_job_missing_required_field_fails() -> None:
    payload = dict(VALID_JOB)
    del payload["company"]
    with pytest.raises(ValidationError):
        JobExtract.model_validate(payload)


def test_job_wrong_type_fails() -> None:
    with pytest.raises(ValidationError):
        JobExtract.model_validate({**VALID_JOB, "requirements": "Python"})


def test_job_empty_title_fails() -> None:
    with pytest.raises(ValidationError):
        JobExtract.model_validate({**VALID_JOB, "title": "   "})


def test_valid_question_payload_passes() -> None:
    question = QuestionExtract.model_validate(VALID_QUESTION)
    assert question.round == "onsite"


def test_question_optional_fields_accept_none() -> None:
    payload = {**VALID_QUESTION, "role": None, "round": None}
    question = QuestionExtract.model_validate(payload)
    assert question.role is None


def test_question_company_accepts_none() -> None:
    # Generic, non-company-attributed question banks (DESIGN.md §10 step 4).
    question = QuestionExtract.model_validate({**VALID_QUESTION, "company": None})
    assert question.company is None


def test_question_missing_required_field_fails() -> None:
    payload = dict(VALID_QUESTION)
    del payload["question"]
    with pytest.raises(ValidationError):
        QuestionExtract.model_validate(payload)


def test_question_empty_question_fails() -> None:
    with pytest.raises(ValidationError):
        QuestionExtract.model_validate({**VALID_QUESTION, "question": ""})
