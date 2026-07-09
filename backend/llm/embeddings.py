"""Ollama embeddings for sqlite-vec search (PHASE6.md step 7).

Kept separate from client.py: embeddings and completions are different
Ollama API calls with different return shapes, and only the save path below
needs this, not the extraction cascade.
"""

import ollama
import sqlite_vec

from backend import config


def embed_text(text: str, model: str = config.EMBED_MODEL) -> bytes:
    """Embed one string, packed as the BLOB format sqlite-vec's vec0 expects."""
    response = ollama.embed(model=model, input=text)
    return sqlite_vec.serialize_float32(response.embeddings[0])  # type: ignore[no-any-return]
