"""Tests for the form-filler answer-tool system (PHASE10.md step 7) — no
network, no LLM (CLAUDE.md): a scripted fake LLMClient, same pattern
test_extractor.py already uses.
"""

import json

import pytest
from sqlalchemy.orm import Session

from backend.autoapply import answers, events
from backend.db import repo
from backend.db.models import Application
from backend.schemas import FormAnswerChoice
from backend.scraper.extractor import Extractor


class ScriptedClient:
    """Fake LLMClient returning one queued response per call."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []

    def complete(self, prompt: str, *, schema: dict | None = None) -> str:
        self.prompts.append(prompt)
        return self._responses.pop(0)


def _response(items: list[dict]) -> str:
    return json.dumps({"items": items})


@pytest.fixture
def session() -> Session:
    return Session(repo.make_engine("sqlite:///:memory:"))


@pytest.fixture
def application(session: Session) -> Application:
    repo.save_company(session, "Acme")
    companies, _ = repo.list_companies(session)
    return events.start_application(session, company_id=companies[0].id)


def test_answer_field_uses_a_tool_when_the_llm_names_one(
    session: Session, application: Application
) -> None:
    profile = answers.ApplicantProfile(phone="555-0100")
    local = ScriptedClient([_response([{"tool_name": "get_phone", "answer": None}])])
    extractor: Extractor[FormAnswerChoice] = Extractor(local, frontier=None)

    answer = answers.answer_field(
        session,
        application,
        extractor,
        profile,
        question="What is your phone number?",
        resume_markdown="",
        job_posting_text="",
    )
    assert answer.text == "555-0100"
    assert answer.source == "profile"


def test_answer_field_falls_back_to_an_open_ended_llm_answer(
    session: Session, application: Application
) -> None:
    profile = answers.ApplicantProfile()
    local = ScriptedClient(
        [_response([{"tool_name": None, "answer": "I am excited about this role."}])]
    )
    extractor: Extractor[FormAnswerChoice] = Extractor(local, frontier=None)

    answer = answers.answer_field(
        session,
        application,
        extractor,
        profile,
        question="Why do you want to work here?",
        resume_markdown="",
        job_posting_text="",
    )
    assert answer.text == "I am excited about this role."
    assert answer.source == "llm"


def test_answer_field_is_unanswered_when_the_matched_tool_has_no_value(
    session: Session, application: Application
) -> None:
    profile = answers.ApplicantProfile(phone=None)
    local = ScriptedClient([_response([{"tool_name": "get_phone", "answer": None}])])
    extractor: Extractor[FormAnswerChoice] = Extractor(local, frontier=None)

    answer = answers.answer_field(
        session,
        application,
        extractor,
        profile,
        question="What is your phone number?",
        resume_markdown="",
        job_posting_text="",
    )
    assert answer.text is None
    assert answer.source == "unanswered"


def test_answer_field_is_unanswered_when_nothing_applies(
    session: Session, application: Application
) -> None:
    profile = answers.ApplicantProfile()
    local = ScriptedClient([_response([])])
    extractor: Extractor[FormAnswerChoice] = Extractor(local, frontier=None)

    answer = answers.answer_field(
        session,
        application,
        extractor,
        profile,
        question="Anything else we should know?",
        resume_markdown="",
        job_posting_text="",
    )
    assert answer.text is None
    assert answer.source == "unanswered"


def test_answer_field_ignores_an_unknown_tool_name(
    session: Session, application: Application
) -> None:
    profile = answers.ApplicantProfile(phone="555-0100")
    local = ScriptedClient([_response([{"tool_name": "get_carrier_pigeon", "answer": None}])])
    extractor: Extractor[FormAnswerChoice] = Extractor(local, frontier=None)

    answer = answers.answer_field(
        session,
        application,
        extractor,
        profile,
        question="What is your phone number?",
        resume_markdown="",
        job_posting_text="",
    )
    assert answer.text is None
    assert answer.source == "unanswered"


def test_answer_field_logs_every_answer_through_the_event_log(
    session: Session, application: Application
) -> None:
    profile = answers.ApplicantProfile(phone="555-0100")
    local = ScriptedClient([_response([{"tool_name": "get_phone", "answer": None}])])
    extractor: Extractor[FormAnswerChoice] = Extractor(local, frontier=None)

    answers.answer_field(
        session,
        application,
        extractor,
        profile,
        question="What is your phone number?",
        resume_markdown="",
        job_posting_text="",
    )
    log = events.list_events(session, application)
    assert len(log) == 1
    assert log[0].action == "answer_field:What is your phone number?"
    assert log[0].success is True


def test_answer_tools_all_have_docstrings() -> None:
    for tool in answers.ANSWER_TOOLS:
        assert tool.description


def test_get_relocation_willingness_reports_yes_no_or_unset() -> None:
    assert answers.get_relocation_willingness(answers.ApplicantProfile(relocation=True)) == "Yes"
    assert answers.get_relocation_willingness(answers.ApplicantProfile(relocation=False)) == "No"
    assert answers.get_relocation_willingness(answers.ApplicantProfile(relocation=None)) is None
