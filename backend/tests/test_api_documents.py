import hashlib
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.auth.jwt_handler import create_access_token, hash_password
from app.models.chunk import DocumentChunk
from app.models.document import Document, DocumentStatus
from app.models.user import User


async def create_foreign_document(db_session) -> tuple[Document, dict[str, str]]:
    user = User(
        email="other-viewer@example.com",
        hashed_password=hash_password("Password123!"),
        display_name="Other Viewer",
    )
    db_session.add(user)
    await db_session.flush()

    upload_path = Path(__file__).parent / "tmp-uploads" / f"{user.id}-private.txt"
    upload_path.parent.mkdir(parents=True, exist_ok=True)
    upload_path.write_text("Private document", encoding="utf-8")
    document = Document(
        title="Other Private Guide",
        file_name="private.txt",
        file_path=str(upload_path),
        file_type="txt",
        file_size=32,
        content_hash="other-content-hash",
        status=DocumentStatus.indexed,
        owner_id=user.id,
    )
    db_session.add(document)
    await db_session.commit()
    await db_session.refresh(document)

    token = create_access_token(str(user.id), user.email, [])
    return document, {"Authorization": f"Bearer {token}"}


@pytest.mark.anyio
async def test_upload_document_creates_pending_record(
    async_client,
    auth_headers,
    db_session,
    fixtures_dir,
    test_user,
):
    sample = fixtures_dir / "sample-article.txt"
    with sample.open("rb") as file:
        response = await async_client.post(
            "/api/v1/documents/upload",
            headers=auth_headers,
            files={"file": ("sample-article.txt", file, "text/plain")},
            data={"chunk_size": "256", "chunk_overlap": "32"},
        )

    assert response.status_code == 201
    data = response.json()
    assert data["file_name"] == "sample-article.txt"
    assert data["status"] == "pending"
    document = await db_session.get(Document, UUID(data["id"]))
    assert document is not None
    assert document.owner_id == test_user.id
    assert (document.metadata_ or {}).get("chunk_size") == 256
    assert (document.metadata_ or {}).get("chunk_overlap") == 32


@pytest.mark.anyio
async def test_upload_duplicate_document_reuses_existing_record(
    async_client,
    auth_headers,
    db_session,
    fixtures_dir,
):
    sample = fixtures_dir / "sample-article.txt"

    with sample.open("rb") as file:
        first = await async_client.post(
            "/api/v1/documents/upload",
            headers=auth_headers,
            files={"file": ("sample-article.txt", file, "text/plain")},
        )

    with sample.open("rb") as file:
        second = await async_client.post(
            "/api/v1/documents/upload",
            headers=auth_headers,
            files={"file": ("sample-article.txt", file, "text/plain")},
        )

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["duplicate_of_existing"] is True

    result = await db_session.execute(select(func.count(Document.id)))
    assert result.scalar_one() == 1


@pytest.mark.anyio
async def test_upload_duplicate_failed_document_requeues_existing_record(
    async_client,
    auth_headers,
    db_session,
    fixtures_dir,
    test_user,
):
    sample = fixtures_dir / "sample-article.txt"
    content = sample.read_bytes()
    upload_path = Path(__file__).parent / "tmp-uploads" / f"{test_user.id}-failed-sample.txt"
    upload_path.parent.mkdir(parents=True, exist_ok=True)
    upload_path.write_bytes(content)

    existing = Document(
        title="Failed AlphaProject",
        file_name="failed-sample.txt",
        file_path=str(upload_path),
        file_type="txt",
        file_size=len(content),
        content_hash=hashlib.sha256(content).hexdigest(),
        status=DocumentStatus.failed,
        error_message="previous parse failed",
        owner_id=test_user.id,
    )
    db_session.add(existing)
    await db_session.commit()
    await db_session.refresh(existing)

    with sample.open("rb") as file:
        response = await async_client.post(
            "/api/v1/documents/upload",
            headers=auth_headers,
            files={"file": ("sample-article.txt", file, "text/plain")},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(existing.id)
    assert data["status"] == "pending"
    assert data["duplicate_of_existing"] is True

    await db_session.refresh(existing)
    assert existing.status == DocumentStatus.pending
    assert existing.error_message is None


@pytest.mark.anyio
async def test_upload_rejects_unsupported_extension(async_client, auth_headers):
    response = await async_client.post(
        "/api/v1/documents/upload",
        headers=auth_headers,
        files={"file": ("malware.exe", b"content", "application/octet-stream")},
    )

    assert response.status_code == 400


@pytest.mark.anyio
async def test_list_documents_returns_indexed_fixture(async_client, auth_headers, indexed_document):
    response = await async_client.get("/api/v1/documents", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == str(indexed_document.id)


@pytest.mark.anyio
async def test_get_document_chunks_returns_chunk_list(async_client, auth_headers, indexed_document):
    response = await async_client.get(
        f"/api/v1/documents/{indexed_document.id}/chunks",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == str(indexed_document.id)
    assert data["total_chunks"] == 1
    assert len(data["chunks"]) == 1
    assert "AlphaProject" in data["chunks"][0]["content"]


@pytest.mark.anyio
async def test_user_document_list_excludes_foreign_documents(
    async_client,
    auth_headers,
    db_session,
    indexed_document,
):
    await create_foreign_document(db_session)

    response = await async_client.get("/api/v1/documents", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == str(indexed_document.id)


@pytest.mark.anyio
async def test_user_cannot_manage_foreign_documents(async_client, auth_headers, db_session):
    foreign_document, _headers = await create_foreign_document(db_session)

    detail = await async_client.get(
        f"/api/v1/documents/{foreign_document.id}",
        headers=auth_headers,
    )
    reindex = await async_client.post(
        f"/api/v1/documents/{foreign_document.id}/reindex",
        headers=auth_headers,
    )
    delete_response = await async_client.delete(
        f"/api/v1/documents/{foreign_document.id}",
        headers=auth_headers,
    )

    assert detail.status_code == 404
    assert reindex.status_code == 404
    assert delete_response.status_code == 404


@pytest.mark.anyio
async def test_get_document_detail_returns_metadata(async_client, auth_headers, indexed_document):
    response = await async_client.get(
        f"/api/v1/documents/{indexed_document.id}",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "AlphaProject RAG Guide"
    assert data["owner_id"]


@pytest.mark.anyio
async def test_reindex_sets_pending_status_and_updates_chunk_config(
    async_client,
    auth_headers,
    db_session,
    indexed_document,
):
    response = await async_client.post(
        f"/api/v1/documents/{indexed_document.id}/reindex",
        headers=auth_headers,
        json={"chunk_size": 384, "chunk_overlap": 40},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    await db_session.refresh(indexed_document)
    assert (indexed_document.metadata_ or {}).get("chunk_size") == 384
    assert (indexed_document.metadata_ or {}).get("chunk_overlap") == 40


@pytest.mark.anyio
async def test_delete_document_removes_chunks(
    async_client,
    auth_headers,
    db_session,
    indexed_document,
):
    document_id = indexed_document.id
    response = await async_client.delete(
        f"/api/v1/documents/{document_id}",
        headers=auth_headers,
    )

    assert response.status_code == 204
    db_session.expire_all()
    document = await db_session.get(Document, document_id)
    chunks = await db_session.execute(
        select(DocumentChunk).where(DocumentChunk.document_id == document_id)
    )
    assert document is None
    assert chunks.scalars().all() == []


@pytest.mark.anyio
async def test_admin_can_manage_foreign_documents(async_client, admin_headers, db_session):
    foreign_document, _headers = await create_foreign_document(db_session)

    list_response = await async_client.get("/api/v1/admin/documents", headers=admin_headers)
    reindex_response = await async_client.post(
        f"/api/v1/admin/documents/{foreign_document.id}/reindex",
        headers=admin_headers,
    )
    delete_response = await async_client.delete(
        f"/api/v1/admin/documents/{foreign_document.id}",
        headers=admin_headers,
    )

    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
    assert reindex_response.status_code == 200
    assert reindex_response.json()["status"] == "pending"
    assert delete_response.status_code == 204
