"""SQLAlchemy ORM models for the three tables (DESIGN.md §2)."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend import config


class Base(DeclarativeBase):
    pass


# Application pipeline tracking (PHASE8.md step 2) — a real status
# progression, separate from the pre-existing `starred` bookmark (which
# stays a "flag this, decide later" flag; a starred-but-untouched job and a
# job someone has actually applied to are real, distinct states worth
# keeping distinguishable). One column, not a history table: matches every
# other status-like field already in this schema (`Run.status`,
# `Run.kind`) rather than introducing a new pattern for one field.
JOB_STATUSES = ("none", "applied", "interviewing", "offer", "rejected")


class Run(Base):
    """One scrape run — the observability record the UI polls."""

    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str]  # "jobs" | "questions"
    source: Mapped[str]
    # Which local model this run's extraction used (PHASE6.md step 3) —
    # never the global config.LOCAL_MODEL implicitly; every run records its
    # own choice, defaulting to it only when the caller doesn't pick one.
    model: Mapped[str] = mapped_column(default=config.LOCAL_MODEL)
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
    starred: Mapped[bool] = mapped_column(default=False)  # PHASE2.md step 8
    status: Mapped[str] = mapped_column(default="none")  # one of JOB_STATUSES
    status_changed_at: Mapped[datetime | None] = mapped_column(default=None)


class InterviewQuestion(Base):
    """One stored interview question."""

    __tablename__ = "interview_questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Null for generic, non-company-attributed question banks (PHASE3.md step 4).
    company: Mapped[str | None]
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


class Company(Base):
    """One discovered company (PHASE7.md step 5) — unresolved until slug
    resolution (step 6) finds a real ATS match; resolved rows become
    dynamic scrape sources (step 7) instead of a hand-curated list."""

    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    slug: Mapped[str | None] = mapped_column(default=None)
    ats_provider: Mapped[str | None] = mapped_column(default=None)  # "greenhouse" | "lever"
    # YC batch (e.g. "Summer 2013") — only meaningful for YC-discovered
    # companies (PHASE8.md step 5); null for any other discovery source.
    batch: Mapped[str | None] = mapped_column(default=None)
    # Which discovery source found this company (PHASE8.md steps 6, 9;
    # PHASE9.md steps 9-10): "yc" | "largest_us_companies" | "a16z" |
    # "sequoia" | "foundersfund" | "bvp" | "russell1000" | "accel".
    # Defaults to "yc" — every company discovered before this column
    # existed came from that source.
    source: Mapped[str] = mapped_column(default="yc")
    discovered_at: Mapped[datetime]
    last_checked_at: Mapped[datetime | None] = mapped_column(default=None)
    # Auto-apply blocklist (PHASE10.md step 3) — a real, per-company opt
    # out, checked before any application attempt starts.
    auto_apply_blocked: Mapped[bool] = mapped_column(default=False)


# Auto-apply (PHASE10.md steps 3-4). Application is the per-attempt
# observability record, mirroring Run's own role for scrape runs.
# ApplicationEvent is the append-only, typed audit trail — OpenHands'
# propose -> execute -> observe Event pattern (this phase's own prior-art
# research), not free-text logging.
APPLICATION_STATUSES = ("pending", "awaiting_confirmation", "submitted", "rejected", "failed")


class Application(Base):
    """One real application attempt."""

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), default=None)
    status: Mapped[str] = mapped_column(default="pending")  # one of APPLICATION_STATUSES
    # "low" never pauses; "high" pauses under SUBMIT_CONFIRMATION_POLICY=
    # "risky" (config.py) — classification fails safe to "high" on any
    # ambiguity, never silently "low" (mirrors OpenHands' fail-safe-to-HIGH
    # SecurityRisk design).
    risk_level: Mapped[str] = mapped_column(default="low")  # "low" | "high"
    started_at: Mapped[datetime]
    finished_at: Mapped[datetime | None] = mapped_column(default=None)
    error: Mapped[str | None] = mapped_column(default=None)
    # The full per-field plan the planner (PHASE11.md step 5) produced --
    # one dict per detected field ({field_name, label, input_type, answer,
    # source}), persisted so a human can review exactly what would be
    # submitted before confirming. Same JSON-column precedent Run.errors
    # already set for a real, variable-length list of structured records.
    planned_fields: Mapped[list[dict[str, str | None]]] = mapped_column(JSON, default=list)


class ApplicationEvent(Base):
    """One real action and its outcome, append-only — never overwritten
    or deleted. `parent_event_id` links a retry/follow-up action back to
    the one it responds to, the same real per-application replay shape
    OpenHands' own event tree uses."""

    __tablename__ = "application_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"))
    parent_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("application_events.id"), default=None
    )
    action: Mapped[str]  # e.g. "detect_fields", "fill_field:full_name", "submit"
    success: Mapped[bool]
    detail: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime]


class AutoApplySettings(Base):
    """A real, single-row (id=1) settings table — the kill switch needs to
    be toggleable state, not a config.py constant that would require a
    restart to flip."""

    __tablename__ = "autoapply_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    kill_switch_enabled: Mapped[bool] = mapped_column(default=False)


class ApplicantProfile(Base):
    """A real, single-row (id=1) structured profile (PHASE10.md step 5) —
    the form-filler answer-tool system (step 7) reads from this, never
    invents values on the user's behalf. Every field starts unset (None);
    only the user filling in the frontend form gives it real content."""

    __tablename__ = "applicant_profile"

    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str | None] = mapped_column(default=None)
    current_salary: Mapped[str | None] = mapped_column(default=None)
    expected_salary: Mapped[str | None] = mapped_column(default=None)
    work_authorization: Mapped[str | None] = mapped_column(default=None)
    relocation: Mapped[bool | None] = mapped_column(default=None)
    start_date_availability: Mapped[str | None] = mapped_column(default=None)
    # The converted resume Markdown (PHASE11.md step 1) — the answer-tool
    # system's open-ended fallback grounding, persisted once per upload
    # instead of re-uploaded per application attempt. The PDF bytes
    # themselves live at config.RESUME_STORAGE_PATH, a real file on disk,
    # not a second DB column — same "binary belongs on the filesystem"
    # precedent BACKUP_DIR already set.
    resume_markdown: Mapped[str | None] = mapped_column(default=None)


class FieldDetectionCache(Base):
    """A cached field map per (ats_provider, company) pair (PHASE12.md step
    2) — Greenhouse/Lever forms are configured at a company's ATS account
    level, so every posting from the same company on the same ATS shares
    one real form shape in practice. Never trusted blindly: every cached
    selector is re-verified against the live page before use
    (autoapply/field_cache.py), falling through to full live detection —
    which then overwrites this row — on any mismatch, since a company can
    add or remove a custom question at any time."""

    __tablename__ = "field_detection_cache"
    __table_args__ = (UniqueConstraint("company_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ats_provider: Mapped[str]
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    # One dict per DetectedField (name/tag/input_type/label/
    # confirmed_by_ax_tree/selector/options) — same JSON-column precedent
    # Application.planned_fields already set.
    field_map: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    cached_at: Mapped[datetime]


class Schedule(Base):
    """A recurring scrape: run this kind/source every N hours (PHASE2.md step 6)."""

    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    # "jobs" | "questions" | "companies" (PHASE8.md step 7 — a companies
    # schedule dispatches to a discovery task, never a Run row).
    kind: Mapped[str]
    source: Mapped[str]
    every_hours: Mapped[int]
    enabled: Mapped[bool] = mapped_column(default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(default=None)
