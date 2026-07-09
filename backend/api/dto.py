"""Request/response models for the API (DESIGN.md §4) — kept out of routes.py
so route handlers stay thin. Every response goes through one of these; list
endpoints return {items, total}.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RunRequest(BaseModel):
    kind: Literal["jobs", "questions"]
    source: str


class RunBatchRequest(BaseModel):
    kind: Literal["jobs", "questions"]
    sources: list[str] = Field(min_length=1)


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
    status: str
    cancel_requested: bool
    started_at: datetime
    finished_at: datetime | None
    pages_fetched: int
    items_saved: int
    items_duplicate: int
    escalations: int
    errors: list[dict[str, str]]


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


class StarRequest(BaseModel):
    starred: bool


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
    escalation_rate: float


class ScheduleRequest(BaseModel):
    kind: Literal["jobs", "questions"]
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
