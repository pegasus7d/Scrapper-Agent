"""Tests for the LLM clients — no real network or LLM calls (CLAUDE.md)."""

from types import SimpleNamespace
from typing import Any

import pytest

from backend import config
from backend.llm import client as client_module
from backend.llm.client import FrontierClient, LLMClient, OllamaClient, ollama_available


def test_ollama_client_conforms_to_protocol() -> None:
    assert isinstance(OllamaClient(), LLMClient)


def test_ollama_client_calls_generate_with_json_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, Any] = {}

    def fake_generate(**kwargs: Any) -> SimpleNamespace:
        calls.update(kwargs)
        return SimpleNamespace(response='{"title": "x"}')

    monkeypatch.setattr(client_module.ollama, "generate", fake_generate)
    result = OllamaClient(model="test-model").complete("extract this")
    assert result == '{"title": "x"}'
    assert calls["model"] == "test-model"
    assert calls["format"] == "json"
    assert calls["prompt"] == "extract this"


def test_ollama_client_passes_real_schema_when_given(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, Any] = {}
    schema = {"type": "object", "properties": {"items": {"type": "array"}}}

    def fake_generate(**kwargs: Any) -> SimpleNamespace:
        calls.update(kwargs)
        return SimpleNamespace(response='{"items": []}')

    monkeypatch.setattr(client_module.ollama, "generate", fake_generate)
    OllamaClient(model="test-model").complete("extract this", schema=schema)
    assert calls["format"] == schema


def test_frontier_client_joins_text_blocks() -> None:
    frontier = FrontierClient(api_key="sk-test")

    def fake_create(**kwargs: Any) -> SimpleNamespace:
        assert kwargs["model"] == config.FRONTIER_MODEL
        assert kwargs["max_tokens"] == config.FRONTIER_MAX_TOKENS
        return SimpleNamespace(
            content=[
                SimpleNamespace(type="text", text='{"a":'),
                SimpleNamespace(type="tool_use", text="ignored"),
                SimpleNamespace(type="text", text=" 1}"),
            ]
        )

    frontier._client = SimpleNamespace(messages=SimpleNamespace(create=fake_create))  # type: ignore[assignment]
    assert frontier.complete("extract this") == '{"a": 1}'


def test_frontier_client_conforms_to_protocol() -> None:
    assert isinstance(FrontierClient(api_key="sk-test"), LLMClient)


def test_ollama_available_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client_module.ollama, "list", lambda: SimpleNamespace(models=[]))
    assert ollama_available() is True


def test_ollama_available_false_when_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail() -> None:
        raise ConnectionError("connection refused")

    monkeypatch.setattr(client_module.ollama, "list", fail)
    assert ollama_available() is False
