"""Application/kill-switch/company-block request/response models — split
out of dto.py (PHASE14.md step 4 prep) to stay under CLAUDE.md's
300-line file cap. Only `routes_applications.py` consumes these.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ApplicationRequest(BaseModel):
    job_id: int


class ApplicationCreated(BaseModel):
    application_id: int


class ApplicationEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    action: str
    success: bool
    detail: str | None
    parent_event_id: int | None
    created_at: datetime


class ApplicationOut(BaseModel):
    id: int
    company_id: int
    company_name: str
    job_id: int | None
    job_title: str | None
    status: str
    risk_level: str
    started_at: datetime
    finished_at: datetime | None
    error: str | None
    planned_fields: list[dict[str, str | None]]


class ApplicationList(BaseModel):
    items: list[ApplicationOut]
    total: int


class ApplicationDetail(BaseModel):
    application: ApplicationOut
    events: list[ApplicationEventOut]


class Rejected(BaseModel):
    rejected: bool


class Confirmed(BaseModel):
    confirmed: bool


class KillSwitchOut(BaseModel):
    enabled: bool


class KillSwitchRequest(BaseModel):
    enabled: bool


class CompanyBlockRequest(BaseModel):
    blocked: bool


class CompanyBlockOut(BaseModel):
    blocked: bool
