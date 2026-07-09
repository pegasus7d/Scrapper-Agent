"""CSV serialization for the export endpoints (PHASE2.md step 8).

Kept separate from routes.py so the route handlers stay thin — this is the
only place that knows about CSV's column order and quoting.
"""

import csv
import io

from backend.db.models import InterviewQuestion, Job

_JOB_COLUMNS = (
    "title",
    "company",
    "location",
    "salary",
    "requirements",
    "posting_url",
    "apply_url",
    "source",
    "extraction_tier",
    "scraped_at",
    "starred",
)

_QUESTION_COLUMNS = (
    "company",
    "role",
    "question",
    "round",
    "source_url",
    "source",
    "extraction_tier",
    "scraped_at",
)


def jobs_to_csv(jobs: list[Job]) -> str:
    """Render jobs as CSV text, one row per job, requirements semicolon-joined."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(_JOB_COLUMNS)
    for job in jobs:
        writer.writerow(
            [
                job.title,
                job.company,
                job.location,
                job.salary,
                "; ".join(job.requirements),
                job.posting_url,
                job.apply_url,
                job.source,
                job.extraction_tier,
                job.scraped_at.isoformat(),
                job.starred,
            ]
        )
    return buffer.getvalue()


def questions_to_csv(questions: list[InterviewQuestion]) -> str:
    """Render questions as CSV text, one row per question."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(_QUESTION_COLUMNS)
    for question in questions:
        writer.writerow(
            [
                question.company,
                question.role,
                question.question,
                question.round,
                question.source_url,
                question.source,
                question.extraction_tier,
                question.scraped_at.isoformat(),
            ]
        )
    return buffer.getvalue()
