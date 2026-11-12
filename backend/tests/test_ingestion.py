import os
from uuid import uuid4

import pytest

from app.models.document import DocumentStatus
from app.services.chunking_engine import ChunkingEngine
from app.services.parser_factory import get_parser
from app.services.parsers.base_parser import ParsedPage
from app.workers.celery_app import celery_app
from app.workers.ingestion_tasks import _process_document_async


def test_celery_worker_registers_ingestion_process_document_task():
    """Bug 1 regression test: celery_app must register ingestion.process_document at import time."""
    assert "ingestion.process_document" in celery_app.tasks


@pytest.mark.anyio
async def test_text_parser_and_chunker_extract_real_fixture(fixtures_dir):
    parser = get_parser(str(fixtures_dir / "sample-article.txt"))
    pages = parser.parse(str(fixtures_dir / "sample-article.txt"))
    chunks = ChunkingEngine().chunk_document(pages, uuid4())

    assert any("AlphaProject" in page.text for page in pages)
    assert len(chunks) >= 1
    assert chunks[0].content
    assert chunks[0].token_count > 0


def test_chunker_emits_structure_aware_metadata():
    pages = [
        ParsedPage(
            text=(
                "LOI CAM ON\n"
                "Chung toi xin chan thanh cam on thay co.\n\n"
                "1. Phuong phap\n"
                "He thong su dung hybrid retrieval va evidence clustering.\n\n"
                "Ket qua\n"
                "Chatbot giam doan boilerplate trong top evidence."
            ),
            page_number=1,
            metadata={"source_type": "text", "title": "Bao cao RAG"},
        )
    ]

    chunks = ChunkingEngine(chunk_size=120).chunk_document(pages, uuid4())

    assert any(chunk.metadata["block_type"] == "acknowledgement" for chunk in chunks)
    assert any(chunk.metadata["block_type"] in {"method", "results"} for chunk in chunks)
    assert all(chunk.metadata["ingestion_version"] for chunk in chunks)
    assert all("Section path:" in (chunk.contextualized_text or "") for chunk in chunks)


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="Real ingestion pipeline requires OPENAI_API_KEY for embeddings",
)
@pytest.mark.anyio
async def test_ingestion_pipeline_indexes_document(db_session, indexed_document):
    indexed_document.status = DocumentStatus.pending
    indexed_document.total_chunks = 0
    await db_session.commit()

    await _process_document_async(str(indexed_document.id))
    await db_session.refresh(indexed_document)

    assert indexed_document.status == DocumentStatus.indexed
    assert indexed_document.total_chunks > 0
