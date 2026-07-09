"""SQLAlchemy ORM models for the three tables (DESIGN.md §2)."""

from datetime import datetime

from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Run(Base):
    """One scrape run — the observability record the UI polls."""

    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str]  # "jobs" | "questions"
    source: Mapped[str]
    status: Mapped[str]  # "running" | "completed" | "failed" | "cancelled"
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    started_at: Mapped[datetime]
    finished_at: Mapped[datetime | None] = mapped_column(default=None)
    pages_fetched: Mapped[int] = mapped_column(default=0)
    items_saved: Mapped[int] = mapped_column(default=0)
    items_duplicate: Mapped[int] = mapped_column(default=0)
    escalations: Mapped[int] = mapped_column(default=0)
    errors: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)


class Job(Base):
    """One stored job posting."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    company: Mapped[str]
    location: Mapped[str | None]
    salary: Mapped[str | None]
    requirements: Mapped[list[str]] = mapped_column(JSON)
    # The item's own permalink, never the listing-page URL (DESIGN.md §2).
    posting_url: Mapped[str] = mapped_column(unique=True)
    apply_url: Mapped[str | None]
    source: Mapped[str]
    extraction_tier: Mapped[str]  # "local" | "frontier"
    scraped_at: Mapped[datetime]
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"))


class InterviewQuestion(Base):
    """One stored interview question."""

    __tablename__ = "interview_questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    company: Mapped[str]
    role: Mapped[str | None]
    question: Mapped[str]
    round: Mapped[str | None]
    # Not unique: one thread page can yield many questions.
    source_url: Mapped[str] = mapped_column(index=True)
    # sha256 of normalized company+question — the dedupe key (DESIGN.md §2).
    question_hash: Mapped[str] = mapped_column(unique=True)
    source: Mapped[str]
    extraction_tier: Mapped[str]  # "local" | "frontier"
    scraped_at: Mapped[datetime]
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"))


class Schedule(Base):
    """A recurring scrape: run this kind/source every N hours (DESIGN.md §9 step 6)."""

    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str]  # "jobs" | "questions"
    source: Mapped[str]
    every_hours: Mapped[int]
    enabled: Mapped[bool] = mapped_column(default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(default=None)
