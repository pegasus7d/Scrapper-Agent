"""Form-filler answer-tool system (PHASE10.md step 7) — structured-profile
lookups as plain, type-hinted, docstringed Python functions; the LLM
cascade sees a schema built FROM those functions' names/docstrings (Open
WebUI's tool-description pattern), not a hand-duplicated parallel enum. A
profile lookup always wins when a tool matches — never a guess. Falls
back to the existing LLM cascade's own generation only for genuinely
open-ended questions no profile field answers, grounded in the resume
Markdown and the job posting text given in the same prompt. Every answer
is logged through step 4's event log (`backend.autoapply.events`).
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from backend import config
from backend.autoapply import events
from backend.db.models import ApplicantProfile, Application
from backend.llm.client import FrontierClient, LLMClient, OllamaClient
from backend.schemas import FormAnswerChoice
from backend.scraper.extractor import ExtractionFailed, Extractor

logger = logging.getLogger(__name__)


def build_answer_extractor(model: str = config.LOCAL_MODEL) -> Extractor[FormAnswerChoice]:
    """Wire the same two-tier cascade `backend.resume.build_resume_extractor`
    does, parameterized for FormAnswerChoice — MAX_ESCALATIONS_PER_RUN
    (config.py) is this extractor's real LLM-spend cap, the same one
    scraping already enforces, not a separate dollar-tracking constant."""
    api_key = config.anthropic_api_key()
    local: LLMClient = OllamaClient(model)
    frontier: LLMClient | None = FrontierClient(api_key) if api_key is not None else None
    return Extractor[FormAnswerChoice](local, frontier=frontier)


def _split_full_name(full_name: str) -> tuple[str, str]:
    """Naive first/last split on the first whitespace run — an honest,
    documented limitation for compound or non-Western names that don't
    split into exactly two parts (PHASE14.md step 2), rather than
    over-engineering a real name parser."""
    parts = full_name.split(None, 1)
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


def get_full_name(profile: ApplicantProfile) -> str | None:
    """The applicant's full name."""
    return profile.full_name


def get_first_name(profile: ApplicantProfile) -> str | None:
    """The applicant's first name, for a form with separate first/last
    name fields."""
    if profile.full_name is None:
        return None
    first, _ = _split_full_name(profile.full_name)
    return first or None


def get_last_name(profile: ApplicantProfile) -> str | None:
    """The applicant's last name, for a form with separate first/last
    name fields."""
    if profile.full_name is None:
        return None
    _, last = _split_full_name(profile.full_name)
    return last or None


def get_email(profile: ApplicantProfile) -> str | None:
    """The applicant's email address."""
    return profile.email


def get_linkedin_url(profile: ApplicantProfile) -> str | None:
    """The applicant's LinkedIn profile URL."""
    return profile.linkedin_url


def get_location(profile: ApplicantProfile) -> str | None:
    """The applicant's current city/location."""
    return profile.location


def get_phone(profile: ApplicantProfile) -> str | None:
    """The applicant's phone number."""
    return profile.phone


def get_current_salary(profile: ApplicantProfile) -> str | None:
    """The applicant's current salary."""
    return profile.current_salary


def get_expected_salary(profile: ApplicantProfile) -> str | None:
    """The applicant's expected or desired salary for this role."""
    return profile.expected_salary


def get_work_authorization(profile: ApplicantProfile) -> str | None:
    """The applicant's work authorization status, e.g. citizenship or
    whether they need visa sponsorship."""
    return profile.work_authorization


def get_relocation_willingness(profile: ApplicantProfile) -> str | None:
    """Whether the applicant is willing to relocate for this role."""
    if profile.relocation is None:
        return None
    return "Yes" if profile.relocation else "No"


def get_start_date_availability(profile: ApplicantProfile) -> str | None:
    """When the applicant is available to start, e.g. notice period."""
    return profile.start_date_availability


@dataclass
class AnswerTool:
    name: str
    description: str
    lookup: Callable[[ApplicantProfile], str | None]


def _tool(func: Callable[[ApplicantProfile], str | None]) -> AnswerTool:
    description = (func.__doc__ or "").strip()
    if not description:
        raise ValueError(f"{func.__name__} needs a docstring for its LLM-visible description")
    return AnswerTool(name=func.__name__, description=description, lookup=func)


ANSWER_TOOLS: list[AnswerTool] = [
    _tool(get_full_name),
    _tool(get_first_name),
    _tool(get_last_name),
    _tool(get_email),
    _tool(get_linkedin_url),
    _tool(get_location),
    _tool(get_phone),
    _tool(get_current_salary),
    _tool(get_expected_salary),
    _tool(get_work_authorization),
    _tool(get_relocation_willingness),
    _tool(get_start_date_availability),
]
_TOOLS_BY_NAME = {tool.name: tool for tool in ANSWER_TOOLS}


def _tools_description() -> str:
    return "\n".join(f"- {tool.name}: {tool.description}" for tool in ANSWER_TOOLS)


@dataclass
class Answer:
    text: str | None
    source: Literal["profile", "llm", "unanswered"]


def answer_field(
    session: Session,
    application: Application,
    extractor: Extractor[FormAnswerChoice],
    profile: ApplicantProfile,
    *,
    question: str,
    resume_markdown: str,
    job_posting_text: str,
) -> Answer:
    """Decide how to answer one application-form question and log the
    outcome through the application's event log. A structured profile
    lookup wins whenever a tool matches (deterministic, never guessed by
    the LLM); otherwise falls back to the LLM cascade for a genuinely
    open-ended, grounded answer."""
    prompt_text = (
        f"Form question: {question}\n\n"
        f"Available answer-tools:\n{_tools_description()}\n\n"
        f"Candidate resume:\n{resume_markdown}\n\n"
        f"Job posting:\n{job_posting_text}\n"
    )

    try:
        result = extractor.extract(prompt_text, FormAnswerChoice)
        choice = result.items[0] if result.items else None
    except ExtractionFailed as error:
        logger.warning("answer_field: extraction failed for %r: %s", question, error)
        choice = None

    answer = _resolve_answer(choice, profile)
    events.record_event(
        session,
        application,
        action=f"answer_field:{question}",
        success=answer.text is not None,
        detail=f"source={answer.source} answer={answer.text!r}",
    )
    return answer


def _resolve_answer(choice: FormAnswerChoice | None, profile: ApplicantProfile) -> Answer:
    if choice is None:
        return Answer(text=None, source="unanswered")
    if choice.tool_name is not None:
        tool = _TOOLS_BY_NAME.get(choice.tool_name)
        value = tool.lookup(profile) if tool is not None else None
        return Answer(text=value, source="profile" if value is not None else "unanswered")
    if choice.answer:
        return Answer(text=choice.answer, source="llm")
    return Answer(text=None, source="unanswered")
