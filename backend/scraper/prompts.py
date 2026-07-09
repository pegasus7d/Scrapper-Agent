"""Extraction prompt templates — part of the contract (DESIGN.md §3).

Prompts live here as constants so they can be reviewed and changed in one
place; extractor.py never builds prompt strings inline.
"""

from pydantic import BaseModel

_SCHEMA_LABELS = {
    "JobExtract": "job posting",
    "QuestionExtract": "interview question",
}

# Extra criteria per schema, appended to the base template — the relevance gate
# that keeps the local model from extracting things that merely mention the
# label word (DESIGN.md §9 step 2: e.g. "exit interview questions for a school"
# is not an interview question).
_SCHEMA_CRITERIA = {
    "JobExtract": "",
    "QuestionExtract": (
        "Only extract a question if ALL of these hold: (1) it was actually asked "
        "to a candidate in a real job interview for a tech/engineering role — not "
        "general advice, chit-chat, or a question about something else (school, "
        "immigration, personal life); (2) a specific company or employer is named "
        "in the text; (3) the question itself is stated concretely, not merely "
        "referenced ('they asked good questions' does not count). If nothing in "
        'the text meets all three, respond with {"items": []} — do not force an '
        "extraction."
    ),
}

_EXTRACTION_TEMPLATE = """You are a precise data extraction engine.
Extract every {label} from the text below.
{criteria}

Respond with ONLY valid JSON of the shape {{"items": [...]}}, where each item
matches this JSON schema exactly:
{schema}

If the text contains no {label}, respond with {{"items": []}}.

Text:
{text}
"""

_RETRY_TEMPLATE = """{previous}

Your previous response was invalid: {error}
Respond again with ONLY valid JSON matching the schema.
"""


def extraction_prompt(schema: type[BaseModel], text: str) -> str:
    """Build the extraction prompt for one chunk of page text."""
    label = _SCHEMA_LABELS.get(schema.__name__)
    if label is None:
        raise ValueError(f"no prompt label defined for schema {schema.__name__}")
    criteria = _SCHEMA_CRITERIA.get(schema.__name__, "")
    return _EXTRACTION_TEMPLATE.format(
        label=label, criteria=criteria, schema=schema.model_json_schema(), text=text
    )


def retry_prompt(previous: str, error: str) -> str:
    """Build the one-shot retry prompt, feeding the validation error back."""
    return _RETRY_TEMPLATE.format(previous=previous, error=error)
