"""Request/response models for the API (DESIGN.md §4) — kept out of routes.py
so route handlers stay thin. Every response goes through one of these; list
endpoints return {items, total}.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HealthOut(BaseModel):
    database: bool
    huey_consumer: bool


class RunRequest(BaseModel):
    kind: Literal["jobs", "questions"]
    source: str
    # Which locally-installed model to extract with (PHASE6.md step 3) —
    # None means "use the app default", never a hardcoded model the caller
    # can't see; the route validates this against GET /api/models.
    model: str | None = None


class RunBatchRequest(BaseModel):
    kind: Literal["jobs", "questions"]
    sources: list[str] = Field(min_length=1)
    model: str | None = None


class RunCreated(BaseModel):
    run_id: int


class BatchQueued(BaseModel):
    queued: list[str]


class Cancelled(BaseModel):
    cancelled: bool


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    source: str
    model: str
    status: str
    cancel_requested: bool
    started_at: datetime
    finished_at: datetime | None
    pages_fetched: int
    items_saved: int
    items_duplicate: int
    escalations: int
    errors: list[dict[str, str]]


class ModelOut(BaseModel):
    name: str
    size_bytes: int


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    company: str
    location: str | None
    salary: str | None
    requirements: list[str]
    posting_url: str
    apply_url: str | None
    source: str
    extraction_tier: str
    scraped_at: datetime
    starred: bool
    status: str
    status_changed_at: datetime | None


class StarRequest(BaseModel):
    starred: bool


class StatusRequest(BaseModel):
    status: str


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company: str | None
    role: str | None
    question: str
    round: str | None
    source_url: str
    source: str
    extraction_tier: str
    scraped_at: datetime


class RunList(BaseModel):
    items: list[RunOut]
    total: int


class JobList(BaseModel):
    items: list[JobOut]
    total: int


class QuestionList(BaseModel):
    items: list[QuestionOut]
    total: int


class StatsOut(BaseModel):
    jobs: int
    questions: int
    companies: int
    discovered_companies: int
    escalation_rate: float


class ScheduleRequest(BaseModel):
    kind: Literal["jobs", "questions", "companies"]
    source: str
    every_hours: int = Field(ge=1, le=24 * 7)


class ToggleRequest(BaseModel):
    enabled: bool


class ScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    source: str
    every_hours: int
    enabled: bool
    last_run_at: datetime | None


class ApplicantProfileOut(BaseModel):
    # A single field, not separate first/last (PHASE14.md step 2): real
    # names don't always split into exactly two parts. answers.py's
    # get_first_name/get_last_name tools split this naively at answer
    # time for a form that wants separate fields.
    full_name: str | None
    email: str | None
    linkedin_url: str | None
    location: str | None
    phone: str | None
    current_salary: str | None
    expected_salary: str | None
    work_authorization: str | None
    relocation: bool | None
    start_date_availability: str | None
    # Whether a resume has ever been uploaded (PHASE11.md step 1) — never
    # the Markdown itself, which can be large and is only needed by the
    # planner, not by a profile-completeness check in the UI.
    has_resume: bool


class ApplicantProfileIn(BaseModel):
    full_name: str | None = None
    email: str | None = None
    linkedin_url: str | None = None
    location: str | None = None
    phone: str | None = None
    current_salary: str | None = None
    expected_salary: str | None = None
    work_authorization: str | None = None
    relocation: bool | None = None
    start_date_availability: str | None = None


class MatchScoreOut(BaseModel):
    job_id: int
    title: str
    company: str
    score: float


class MatchScoreList(BaseModel):
    items: list[MatchScoreOut]
    threshold: float


class ResumeMarkdown(BaseModel):
    markdown: str


class ResumePositionsOut(BaseModel):
    positions: list[str]


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str | None
    ats_provider: str | None
    batch: str | None
    source: str
    discovered_at: datetime
    last_checked_at: datetime | None


class CompanyList(BaseModel):
    items: list[CompanyOut]
    total: int


class DiscoverySourceOut(BaseModel):
    name: str
    label: str


class SourceHealthOut(BaseModel):
    name: str
    kind: Literal["jobs", "questions", "discovery"]
    status: Literal["ok", "blocked", "unreachable"]
    detail: str | None


class DiscoveryResult(BaseModel):
    discovered: int  # newly-inserted companies this run
    total: int  # all companies now on file


class ResolutionResult(BaseModel):
    checked: int  # unresolved companies probed this run
    resolved: int  # of those, how many got a real ATS match


# Application/kill-switch/company-block DTOs live in dto_applications.py
# (PHASE14.md step 4 prep) — this file was over CLAUDE.md's 300-line cap.
