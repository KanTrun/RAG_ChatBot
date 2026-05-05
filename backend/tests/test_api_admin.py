from pathlib import Path
import uuid

import pytest

from app.models.chunk import DocumentChunk
from app.models.document import Document, DocumentStatus


@pytest.mark.anyio
async def test_admin_debug_index_returns_outline_and_chunk_metadata(
    async_client,
    admin_headers,
    db_session,
    test_user,
):
    upload_path = Path(__file__).parent / "tmp-uploads" / f"{uuid.uuid4()}-debug-doc.txt"
    upload_path.parent.mkdir(parents=True, exist_ok=True)
    upload_path.write_text("# Tong quan\nHe thong su dung hybrid retrieval.\n", encoding="utf-8")
    document = Document(
        title="Debug Doc",
        file_name="debug-doc.txt",
        file_path=str(upload_path),
        file_type="txt",
        file_size=64,
        content_hash="debug-doc-hash",
        status=DocumentStatus.indexed,
        owner_id=test_user.id,
        total_chunks=1,
        metadata_={"ingestion_version": "document-first-v2"},
    )
    db_session.add(document)
    await db_session.flush()
    db_session.add(
        DocumentChunk(
            document_id=document.id,
            content="He thong su dung hybrid retrieval.",
            embedding=[0.1] * 1024,
            sparse_vector={"hybrid": 1.0},
            search_vector="hybrid retrieval",
            chunk_index=0,
            page_number=1,
            section="Tong quan",
            token_count=8,
            metadata_={
                "block_type": "method",
                "section_path": "Debug Doc > Tong quan",
                "parent_block_id": "parent-debug",
                "heading_level": 1,
                "ingestion_version": "document-first-v2",
                "contextualized_text": "Document title: Debug Doc\nSection path: Debug Doc > Tong quan\nChunk text:\nHe thong su dung hybrid retrieval.",
            },
        )
    )
    await db_session.commit()

    response = await async_client.get(
        f"/api/v1/admin/documents/{document.id}/debug-index",
        headers=admin_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["ingestion_version"] == "document-first-v2"
    assert data["parsed_outline"]
    assert data["indexed_chunks"][0]["block_type"] == "method"
    assert data["indexed_chunks"][0]["contextualized_text"]


@pytest.mark.anyio
async def test_admin_reindex_all_can_scope_to_stale_documents(
    async_client,
    admin_headers,
    db_session,
    test_user,
):
    for title, version in [("Old Doc", "document-first-v1"), ("New Doc", "document-first-v2")]:
        upload_path = Path(__file__).parent / "tmp-uploads" / f"{uuid.uuid4()}-{title}.txt"
        upload_path.parent.mkdir(parents=True, exist_ok=True)
        upload_path.write_text(title, encoding="utf-8")
        db_session.add(
            Document(
                title=title,
                file_name=f"{title}.txt",
                file_path=str(upload_path),
                file_type="txt",
                file_size=32,
                content_hash=f"hash-{title}",
                status=DocumentStatus.indexed,
                owner_id=test_user.id,
                total_chunks=1,
                metadata_={"ingestion_version": version},
            )
        )
    await db_session.commit()

    response = await async_client.post(
        "/api/v1/admin/documents/reindex-all?stale_only=true",
        headers=admin_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["queued_documents"] == 1
    assert data["stale_only"] is True
