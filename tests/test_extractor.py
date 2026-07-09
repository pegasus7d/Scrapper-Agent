"""Tests for the extraction cascade — every branch in DESIGN.md §3."""

import json

import pytest

from backend.schemas import JobExtract
from backend.scraper.extractor import ExtractionFailed, Extractor

VALID_ITEM = {
    "title": "Backend Engineer",
    "company": "Acme",
    "location": None,
    "salary": None,
    "requirements": ["Python"],
    "apply_url": None,
}
VALID_RESPONSE = json.dumps({"items": [VALID_ITEM]})
EMPTY_RESPONSE = json.dumps({"items": []})
INVALID_RESPONSE = json.dumps({"items": [{"title": ""}]})


class ScriptedClient:
    """Fake LLMClient returning queued responses and recording every prompt."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []
        self.schemas: list[dict | None] = []

    def complete(self, prompt: str, *, schema: dict | None = None) -> str:
        self.prompts.append(prompt)
        self.schemas.append(schema)
        return self._responses.pop(0)


def test_local_succeeds_first_try() -> None:
    local = ScriptedClient([VALID_RESPONSE])
    extractor: Extractor[JobExtract] = Extractor(local, frontier=None)
    result = extractor.extract("some chunk", JobExtract)
    assert result.tier == "local"
    assert result.items[0].company == "Acme"
    assert len(local.prompts) == 1


def test_local_call_passes_wrapper_json_schema() -> None:
    local = ScriptedClient([VALID_RESPONSE])
    extractor: Extractor[JobExtract] = Extractor(local, frontier=None)
    extractor.extract("some chunk", JobExtract)
    assert local.schemas[0] is not None
    assert local.schemas[0]["type"] == "object"
    assert local.schemas[0]["properties"]["items"]["type"] == "array"
    assert local.schemas[0]["properties"]["items"]["items"] == JobExtract.model_json_schema()


def test_empty_items_is_success_not_failure() -> None:
    local = ScriptedClient([EMPTY_RESPONSE])
    extractor: Extractor[JobExtract] = Extractor(local, frontier=None)
    result = extractor.extract("no jobs here", JobExtract)
    assert result.items == []
    assert result.tier == "local"


def test_local_fails_then_retry_succeeds_with_error_fed_back() -> None:
    local = ScriptedClient([INVALID_RESPONSE, VALID_RESPONSE])
    extractor: Extractor[JobExtract] = Extractor(local, frontier=None)
    result = extractor.extract("chunk", JobExtract)
    assert result.tier == "local"
    assert len(local.prompts) == 2
    assert "invalid" in local.prompts[1].lower()  # validation error fed back


def test_retry_fails_then_frontier_succeeds() -> None:
    local = ScriptedClient(["not json", INVALID_RESPONSE])
    frontier = ScriptedClient([VALID_RESPONSE])
    extractor: Extractor[JobExtract] = Extractor(local, frontier)
    result = extractor.extract("chunk", JobExtract)
    assert result.tier == "frontier"
    assert extractor.escalations_used == 1


def test_frontier_also_fails_raises() -> None:
    local = ScriptedClient(["not json", "not json"])
    frontier = ScriptedClient(["also not json"])
    extractor: Extractor[JobExtract] = Extractor(local, frontier)
    with pytest.raises(ExtractionFailed, match="frontier model also failed"):
        extractor.extract("chunk", JobExtract)


def test_no_frontier_raises_after_two_local_failures() -> None:
    local = ScriptedClient(["not json", "not json"])
    extractor: Extractor[JobExtract] = Extractor(local, frontier=None)
    with pytest.raises(ExtractionFailed, match="escalation disabled"):
        extractor.extract("chunk", JobExtract)


def test_escalation_cap_blocks_frontier_call() -> None:
    local = ScriptedClient(["not json", "not json"])
    frontier = ScriptedClient([VALID_RESPONSE])
    extractor: Extractor[JobExtract] = Extractor(local, frontier, max_escalations=0)
    with pytest.raises(ExtractionFailed, match="cap reached"):
        extractor.extract("chunk", JobExtract)
    assert frontier.prompts == []  # frontier was never called


def test_malformed_json_is_invalid_not_a_crash() -> None:
    local = ScriptedClient(["{{{ garbage", VALID_RESPONSE])
    extractor: Extractor[JobExtract] = Extractor(local, frontier=None)
    result = extractor.extract("chunk", JobExtract)
    assert result.tier == "local"


def test_fenced_json_response_accepted() -> None:
    fenced = f"```json\n{VALID_RESPONSE}\n```"
    local = ScriptedClient([fenced])
    extractor: Extractor[JobExtract] = Extractor(local, frontier=None)
    result = extractor.extract("chunk", JobExtract)
    assert result.items[0].title == "Backend Engineer"


def test_non_dict_response_is_invalid() -> None:
    local = ScriptedClient([json.dumps([VALID_ITEM]), VALID_RESPONSE])
    extractor: Extractor[JobExtract] = Extractor(local, frontier=None)
    extractor.extract("chunk", JobExtract)
    assert len(local.prompts) == 2  # first shape was rejected, retry used
