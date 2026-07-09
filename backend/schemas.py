"""Pydantic contracts for what the LLM must extract from one page chunk.

Kept separate from the DB models on purpose: the extraction contract and the
storage schema evolve independently (DESIGN.md §3).
"""

from typing import Annotated, Any

from pydantic import BaseModel, StringConstraints, field_validator

# Required text fields reject empty/whitespace-only values so that a lazy LLM
# response fails validation and triggers the cascade retry.
NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

# A local model sometimes emits the JSON string "null" instead of an actual
# JSON null for a nullable field — confirmed for real in production data
# (github-questions, local tier: one row landed with role="null" AND
# round="null"). Schema-constrained decoding (PHASE6.md step 2) doesn't
# prevent this: the string "null" still satisfies a `string | null` field's
# type, so it isn't a shape violation. Every nullable field below treats
# these as the absence they were clearly meant to be.
_NULL_LIKE = {"null", "none", "n/a", "na"}


def _none_if_null_like(value: Any) -> Any:
    if isinstance(value, str) and value.strip().lower() in _NULL_LIKE:
        return None
    return value


class JobExtract(BaseModel):
    """One job posting extracted from a chunk."""

    title: NonEmptyStr
    company: NonEmptyStr
    location: str | None
    salary: str | None
    requirements: list[str]
    apply_url: str | None

    _normalize_nullable = field_validator("location", "salary", "apply_url", mode="before")(
        _none_if_null_like
    )


class QuestionExtract(BaseModel):
    """One interview question extracted from a chunk.

    `company` is nullable: curated GitHub question banks (PHASE3.md step 4)
    are generic and topic-based, with no interview account behind them — that
    is a real absence, not missing data.
    """

    company: NonEmptyStr | None
    role: str | None
    question: NonEmptyStr
    round: str | None

    _normalize_nullable = field_validator("company", "role", "round", mode="before")(
        _none_if_null_like
    )
