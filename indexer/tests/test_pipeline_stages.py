"""Unit tests for the indexing pipeline stages (clean, chunk, embed, store)."""

from __future__ import annotations

from unittest.mock import MagicMock

from pipeline.clean import clean
from pipeline.chunk import chunk
from pipeline.config import get_settings
from pipeline.embed import embed
from pipeline.models import Chunk, Document, Page
from pipeline.store import store


def test_clean_strips_headers_footers() -> None:
    doc = Document(
        source="test.pdf",
        doc_version="2026",
        superseded=False,
        pages=[
            Page(
                source="test.pdf",
                page=1,
                text="Page 1 of 5\nFAST-NUCES - Academic Rules\n1.1 Attendance\nStudents must have 80% attendance.\n1 / 5",
                ocr=False,
            )
        ],
    )
    cleaned = clean(doc)
    assert len(cleaned.pages) == 1
    assert "Page 1 of 5" not in cleaned.pages[0].text
    assert "1.1 Attendance" in cleaned.pages[0].text
    assert "80% attendance" in cleaned.pages[0].text


def test_chunk_creates_structure_aware_chunks() -> None:
    doc = Document(
        source="test.pdf",
        doc_version="2026",
        superseded=False,
        pages=[
            Page(
                source="test.pdf",
                page=1,
                text="1.1 Attendance\nStudents must attend at least 80% of classes.\n\n1.2 Grading\nLetter grades range from A to F.",
                ocr=False,
            )
        ],
    )
    chunks = chunk(doc, size=50, overlap=10)
    assert len(chunks) >= 2
    assert chunks[0].source == "test.pdf"
    assert chunks[0].doc_version == "2026"
    assert chunks[0].superseded is False
    assert any("Attendance" in c.section or "1.1 Attendance" in c.text for c in chunks)


def test_embed_fallback() -> None:
    settings = get_settings()
    vectors = embed(["Test sentence 1", "Test sentence 2"], settings)
    assert len(vectors) == 2
    assert len(vectors[0]) > 0


def test_store_upsert(monkeypatch) -> None:
    fake_client = MagicMock()
    fake_collection = MagicMock()
    fake_client.get_or_create_collection.return_value = fake_collection

    monkeypatch.setattr("pipeline.store.get_client", lambda s: fake_client)

    settings = get_settings()
    chunk_item = Chunk(
        id="c1",
        text="Sample text",
        source="doc.pdf",
        section="Sec 1",
        page=1,
        doc_version="2026",
        superseded=False,
    )
    count = store([chunk_item], [[0.1, 0.2]], settings)
    assert count == 1
    assert fake_collection.upsert.called
