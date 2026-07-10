"""Tests for project configuration."""

import logging
from pathlib import Path

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


@pytest.fixture
def clean_root_logger(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> logging.Logger:
    """The root logger's handler list is real global state shared across
    the whole pytest process — configure_logging()'s own "safe to call
    more than once" guard means once anything has called it, later calls
    become no-ops. Save/restore it so this test proves real behavior
    regardless of test order, and point LOG_FILE at a real tmp path so
    the suite never writes a log file into the actual project directory.

    The clearing itself can't happen here: pytest's own logging plugin
    re-installs a fresh LogCaptureHandler on the root logger at the start
    of each test's *call* phase, which runs after fixture setup — so a
    clear() done in this fixture body is wiped out before the test even
    starts. Each test clears handlers itself, right before calling
    configure_logging(), so nothing re-populates the list in between."""
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    monkeypatch.setattr(config, "LOG_FILE", str(tmp_path / "hirable.log"))
    yield root
    root.handlers.clear()
    root.handlers.extend(saved_handlers)


def test_configure_logging_can_be_called_twice(clean_root_logger: logging.Logger) -> None:
    clean_root_logger.handlers.clear()
    config.configure_logging()
    config.configure_logging()
    assert len(clean_root_logger.handlers) == 2  # stderr + rotating file, not 4


def test_configure_logging_creates_a_real_log_file(
    clean_root_logger: logging.Logger, tmp_path: Path
) -> None:
    clean_root_logger.handlers.clear()
    config.configure_logging()
    logging.getLogger("test").info("a real log line")
    log_file = tmp_path / "hirable.log"
    assert log_file.exists()
    assert "a real log line" in log_file.read_text()
