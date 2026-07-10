"""Streaming CSV/JSON serialization for the export endpoints (PHASE2.md step
8; real streaming added PHASE9.md step 8). Kept separate from routes.py so
the route handlers stay thin — this is the only place that knows about
CSV's column order/quoting and the JSON array framing.

`GET /jobs/export`/`/questions/export` used to pull every matching row into
memory at once (`repo.export_jobs` returning a full list) before building
one giant CSV/JSON string. Both now stay bounded to roughly one row at a
time: each `stream_*` function below opens its own short-lived session from
the engine and keeps it open only as long as it's actually being
iterated — mirrors `stream.py`'s existing session-per-generator pattern for
`GET /runs/stream`, the only other place in this app that already solved
"a session must outlive a generator-driven `StreamingResponse`," since
FastAPI's request-scoped `SessionDep` closes as soon as the route handler
function *returns*, which happens immediately after constructing a
`StreamingResponse` — well before its body is actually sent.
"""

import csv
import json
from collections.abc import Iterable, Iterator

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from backend.api.dto import JobOut, QuestionOut
from backend.db import repo
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


class _EchoWriter:
    """A pseudo-file whose write() just returns what it's given — csv.writer
    needs a file-like object, but this turns each writerow() call into one
    real CSV line yielded on its own, instead of accumulating into a
    shared in-memory buffer."""

    def write(self, row: str) -> str:
        return row


def _job_row(job: Job) -> list[object]:
    return [
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


def _question_row(question: InterviewQuestion) -> list[object]:
    return [
        question.company,
        question.role,
        question.question,
        question.round,
        question.source_url,
        question.source,
        question.extraction_tier,
        question.scraped_at.isoformat(),
    ]


def jobs_to_csv_lines(jobs: Iterable[Job]) -> Iterator[str]:
    """Pure CSV serialization, no DB — testable directly against plain ORM
    instances (test_export.py), same discipline the original jobs_to_csv
    had before PHASE9.md step 8 made the DB-touching path lazy/streaming."""
    writer = csv.writer(_EchoWriter())
    yield writer.writerow(_JOB_COLUMNS)
    for job in jobs:
        yield writer.writerow(_job_row(job))


def questions_to_csv_lines(questions: Iterable[InterviewQuestion]) -> Iterator[str]:
    """Pure CSV serialization, no DB — same reasoning as jobs_to_csv_lines."""
    writer = csv.writer(_EchoWriter())
    yield writer.writerow(_QUESTION_COLUMNS)
    for question in questions:
        yield writer.writerow(_question_row(question))


def stream_jobs_csv(
    engine: Engine,
    *,
    company: str | None,
    source: str | None,
    q: str | None,
    starred: bool | None,
    status: str | None,
) -> Iterator[str]:
    with Session(engine) as session:
        jobs = repo.export_jobs(
            session, company=company, source=source, q=q, starred=starred, status=status
        )
        yield from jobs_to_csv_lines(jobs)


def stream_jobs_json(
    engine: Engine,
    *,
    company: str | None,
    source: str | None,
    q: str | None,
    starred: bool | None,
    status: str | None,
) -> Iterator[str]:
    with Session(engine) as session:
        jobs = repo.export_jobs(
            session, company=company, source=source, q=q, starred=starred, status=status
        )
        yield "["
        first = True
        for job in jobs:
            item = JobOut.model_validate(job).model_dump(mode="json")
            yield ("" if first else ",") + json.dumps(item)
            first = False
        yield "]"


def stream_questions_csv(
    engine: Engine, *, company: str | None, round_: str | None, q: str | None
) -> Iterator[str]:
    with Session(engine) as session:
        questions = repo.export_questions(session, company=company, round_=round_, q=q)
        yield from questions_to_csv_lines(questions)


def stream_questions_json(
    engine: Engine, *, company: str | None, round_: str | None, q: str | None
) -> Iterator[str]:
    with Session(engine) as session:
        questions = repo.export_questions(session, company=company, round_=round_, q=q)
        yield "["
        first = True
        for question in questions:
            item = QuestionOut.model_validate(question).model_dump(mode="json")
            yield ("" if first else ",") + json.dumps(item)
            first = False
        yield "]"
