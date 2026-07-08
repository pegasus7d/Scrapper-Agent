"""Pydantic contracts for what the LLM must extract from one page chunk.

Kept separate from the DB models on purpose: the extraction contract and the
storage schema evolve independently (DESIGN.md §3).
"""

from typing import Annotated

from pydantic import BaseModel, StringConstraints

# Required text fields reject empty/whitespace-only values so that a lazy LLM
# response fails validation and triggers the cascade retry.
NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class JobExtract(BaseModel):
    """One job posting extracted from a chunk."""

    title: NonEmptyStr
    company: NonEmptyStr
    location: str | None
    salary: str | None
    requirements: list[str]
    apply_url: str | None


class QuestionExtract(BaseModel):
    """One interview question extracted from a chunk."""

    company: NonEmptyStr
    role: str | None
    question: NonEmptyStr
    round: str | None
