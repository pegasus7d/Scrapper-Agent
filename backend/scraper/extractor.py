"""The extraction cascade: local model first, one retry, then capped escalation.

One Extractor instance lives for one scrape run — it owns that run's escalation
budget. It depends only on the LLMClient protocol, so tests drive it with
scripted fakes (DESIGN.md §3).
"""

import json
import logging
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ValidationError

from backend import config
from backend.llm.client import LLMClient
from backend.scraper.prompts import extraction_prompt, retry_prompt

logger = logging.getLogger(__name__)


class ExtractionFailed(Exception):
    """Raised only after every available tier has been exhausted."""


@dataclass
class ExtractResult[T: BaseModel]:
    items: list[T]
    tier: Literal["local", "frontier"]


def _strip_code_fences(response: str) -> str:
    """Small models often wrap JSON in markdown fences despite instructions."""
    text = response.strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").strip()
        text = text.removesuffix("```").strip()
    return text


def _parse_items[T: BaseModel](response: str, schema: type[T]) -> list[T]:
    """Parse a {"items": [...]} response; raises on any malformed content.

    An explicit empty list is a valid answer ("this chunk contains no items") —
    it must not trigger a retry or waste an escalation.
    """
    payload = json.loads(_strip_code_fences(response))
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise ValueError('response is not of the shape {"items": [...]}')
    return [schema.model_validate(item) for item in payload["items"]]


class Extractor[T: BaseModel]:
    """Runs the cascade for one scrape run, tracking its escalation budget."""

    def __init__(
        self,
        local: LLMClient,
        frontier: LLMClient | None,
        max_escalations: int = config.MAX_ESCALATIONS_PER_RUN,
    ) -> None:
        self._local = local
        self._frontier = frontier
        self._max_escalations = max_escalations
        self.escalations_used = 0

    def extract(self, text: str, schema: type[T]) -> ExtractResult[T]:
        """Extract validated items from one chunk of page text.

        Raises ExtractionFailed when the local tier fails twice and escalation
        is unavailable (disabled, capped, or also failing).
        """
        prompt = extraction_prompt(schema, text)

        items, error = self._attempt(self._local, prompt, schema)
        if items is not None:
            return ExtractResult(items, "local")

        items, error = self._attempt(self._local, retry_prompt(prompt, error), schema)
        if items is not None:
            return ExtractResult(items, "local")

        if self._frontier is None:
            raise ExtractionFailed(f"local model failed twice, escalation disabled: {error}")
        if self.escalations_used >= self._max_escalations:
            raise ExtractionFailed(f"local model failed twice, escalation cap reached: {error}")

        self.escalations_used += 1
        logger.warning("escalating to frontier (%d used)", self.escalations_used)
        items, error = self._attempt(self._frontier, prompt, schema)
        if items is not None:
            return ExtractResult(items, "frontier")
        raise ExtractionFailed(f"frontier model also failed: {error}")

    def _attempt(
        self, client: LLMClient, prompt: str, schema: type[T]
    ) -> tuple[list[T] | None, str]:
        """One model call; returns (items, "") on success or (None, error)."""
        response = client.complete(prompt)
        try:
            return _parse_items(response, schema), ""
        except (json.JSONDecodeError, ValueError, ValidationError) as error:
            logger.debug("invalid extraction response: %s", error)
            return None, str(error)
