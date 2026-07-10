"""Tests for CSV export serialization — plain ORM instances, no DB needed.

jobs_to_csv_lines/questions_to_csv_lines are the pure, streaming-friendly
core (PHASE9.md step 8) — each call yields one real CSV line rather than
building one big string, but "".join(...) reconstructs the same full text
these tests already asserted against before that change.
"""

from datetime import UTC, datetime

from backend.api.export import jobs_to_csv_lines, questions_to_csv_lines
from backend.db.models import InterviewQuestion, Job

SCRAPED_AT = datetime(2026, 1, 1, tzinfo=UTC)


def make_job(**overrides: object) -> Job:
    defaults: dict[str, object] = {
        "title": "Backend Engineer",
        "company": "Acme",
        "location": "Remote",
        "salary": "$150k",
        "requirements": ["Python", "SQL"],
        "posting_url": "https://x.com/1",
        "apply_url": "https://x.com/1/apply",
        "source": "hn",
        "extraction_tier": "local",
        "scraped_at": SCRAPED_AT,
        "starred": False,
    }
    return Job(**{**defaults, **overrides})


def make_question(**overrides: object) -> InterviewQuestion:
    defaults: dict[str, object] = {
        "company": "Acme",
        "role": "SWE",
        "question": "Design a URL shortener.",
        "round": "onsite",
        "source_url": "https://r.com/1",
        "source": "hn-interviews",
        "extraction_tier": "local",
        "scraped_at": SCRAPED_AT,
    }
    return InterviewQuestion(**{**defaults, **overrides})


def test_jobs_to_csv_has_header_and_one_row_per_job() -> None:
    csv_text = "".join(jobs_to_csv_lines([make_job(), make_job(title="Data Scientist")]))
    lines = csv_text.strip().splitlines()
    assert lines[0].startswith("title,company,location")
    assert len(lines) == 3
    assert "Backend Engineer" in lines[1]
    assert "Data Scientist" in lines[2]


def test_jobs_to_csv_joins_requirements_with_semicolons() -> None:
    csv_text = "".join(jobs_to_csv_lines([make_job(requirements=["Python", "SQL", "Docker"])]))
    assert "Python; SQL; Docker" in csv_text


def test_jobs_to_csv_empty_list_is_header_only() -> None:
    lines = "".join(jobs_to_csv_lines([])).strip().splitlines()
    assert len(lines) == 1


def test_questions_to_csv_has_header_and_one_row_per_question() -> None:
    csv_text = "".join(questions_to_csv_lines([make_question(), make_question(company="Beta")]))
    lines = csv_text.strip().splitlines()
    assert lines[0].startswith("company,role,question")
    assert len(lines) == 3
    assert "Design a URL shortener." in lines[1]


def test_questions_to_csv_empty_list_is_header_only() -> None:
    lines = "".join(questions_to_csv_lines([])).strip().splitlines()
    assert len(lines) == 1
