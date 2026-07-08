"""LLM clients behind one tiny protocol so the extractor can be tested with fakes.

The extractor depends only on `LLMClient` (DESIGN.md §3) — it never knows which
tier it is talking to.
"""

import logging
from typing import Protocol, runtime_checkable

import anthropic
import ollama

from backend import config

logger = logging.getLogger(__name__)


@runtime_checkable
class LLMClient(Protocol):
    """Anything that turns a prompt into a completion string."""

    def complete(self, prompt: str) -> str: ...


class OllamaClient:
    """Local tier: the free Ollama model that handles every extraction first."""

    def __init__(self, model: str = config.LOCAL_MODEL) -> None:
        self._model = model

    def complete(self, prompt: str) -> str:
        """Return the model's completion; JSON mode keeps output parseable."""
        response = ollama.generate(model=self._model, prompt=prompt, format="json")
        return response.response


class FrontierClient:
    """Escalation tier: Anthropic API — costs money, capped per run."""

    def __init__(self, api_key: str, model: str = config.FRONTIER_MODEL) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def complete(self, prompt: str) -> str:
        """Return the model's completion as plain text."""
        response = self._client.messages.create(
            model=self._model,
            max_tokens=config.FRONTIER_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in response.content if block.type == "text")


def ollama_available() -> bool:
    """True when the local Ollama server responds; used to fail runs fast."""
    try:
        ollama.list()
    except (ConnectionError, ollama.RequestError, ollama.ResponseError) as error:
        logger.warning("ollama unreachable: %s", error)
        return False
    return True
