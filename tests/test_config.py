"""Tests for project configuration."""

import pytest

from backend import config


def test_constants_are_sane() -> None:
    assert config.MAX_ESCALATIONS_PER_RUN > 0
    assert config.FETCH_TIMEOUT_S > 0
    assert config.FETCH_RETRIES >= 0
    assert config.MAX_PAGES_PER_RUN > 0
    assert config.REQUEST_DELAY_S >= 0
    assert config.LOCAL_MODEL
    assert config.FRONTIER_MODEL
    assert config.USER_AGENT
    assert config.DATABASE_URL.startswith("sqlite:///")


def test_anthropic_api_key_returns_none_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert config.anthropic_api_key() is None


def test_anthropic_api_key_returns_value_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert config.anthropic_api_key() == "sk-test"


def test_configure_logging_can_be_called_twice() -> None:
    config.configure_logging()
    config.configure_logging()
