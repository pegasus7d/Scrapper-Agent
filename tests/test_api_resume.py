"""Tests for the resume upload/derived-position endpoints (PHASE7.md steps
2-3) — TestClient over an in-memory DB; no real Ollama call happens
(mocked)."""

import pymupdf
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool

from backend import config
from backend.api import routes_resume
from backend.api.main import create_app
from backend.db import migrate, vectors
from backend.scraper.extractor import ExtractionFailed


@pytest.fixture
def engine() -> Engine:
    database_url = "sqlite://"
    engine = create_engine(
        database_url, connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    vectors.register_vec_extension(engine)
    migrate.run_migrations(engine, database_url)
    return engine


@pytest.fixture
def client(engine: Engine) -> TestClient:
    return TestClient(create_app(engine, start_consumer=False))


def _minimal_pdf_bytes(text: str) -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), text)
    return doc.tobytes()  # type: ignore[no-any-return]


def test_upload_resume_returns_real_markdown(client: TestClient) -> None:
    pdf_bytes = _minimal_pdf_bytes("Backend Engineer with Python experience.")
    response = client.post(
        "/api/resume", files={"file": ("resume.pdf", pdf_bytes, "application/pdf")}
    )
    assert response.status_code == 200
    assert "Backend Engineer" in response.json()["markdown"]


def test_upload_resume_rejects_non_pdf(client: TestClient) -> None:
    response = client.post(
        "/api/resume",
        files={"file": ("resume.pdf", b"not a real pdf", "application/pdf")},
    )
    assert response.status_code == 422


def test_upload_resume_rejects_wrong_content_type(client: TestClient) -> None:
    """A real, well-formed PDF, but sent with the wrong Content-Type — the
    type guard (PHASE9.md step 7) rejects it before ever calling
    pdf_to_markdown, distinct from test_upload_resume_rejects_non_pdf's
    garbage-bytes-with-a-correct-header case."""
    pdf_bytes = _minimal_pdf_bytes("Backend Engineer with Python experience.")
    response = client.post("/api/resume", files={"file": ("resume.pdf", pdf_bytes, "text/plain")})
    assert response.status_code == 422
    assert "unsupported file type" in response.json()["detail"]


def test_upload_resume_rejects_oversized_file(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real PDF, genuinely larger than a (lowered, for a fast test)
    RESUME_MAX_BYTES — proves the guard checks a real byte count, not a
    hardcoded pass."""
    monkeypatch.setattr(config, "RESUME_MAX_BYTES", 10)
    pdf_bytes = _minimal_pdf_bytes("Backend Engineer with Python experience.")
    assert len(pdf_bytes) > 10  # the real PDF must actually exceed the lowered bound
    response = client.post(
        "/api/resume", files={"file": ("resume.pdf", pdf_bytes, "application/pdf")}
    )
    assert response.status_code == 413


def test_resume_positions_returns_derived_titles(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        routes_resume, "derive_search_positions", lambda markdown, extractor: ["Backend Engineer"]
    )
    response = client.post("/api/resume/positions", json={"markdown": "some resume text"})
    assert response.status_code == 200
    assert response.json() == {"positions": ["Backend Engineer"]}


def test_resume_positions_maps_extraction_failure_to_502(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(markdown: str, extractor: object) -> list[str]:
        raise ExtractionFailed("local model failed twice, escalation disabled: bad json")

    monkeypatch.setattr(routes_resume, "derive_search_positions", fail)
    response = client.post("/api/resume/positions", json={"markdown": "some resume text"})
    assert response.status_code == 502
