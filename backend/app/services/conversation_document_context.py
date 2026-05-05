"""Helpers for conversation-scoped active document context."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentStatus
from app.schemas.chat_schemas import ActiveDocumentResponse


@dataclass
class ActiveDocumentContext:
    documents: list[Document]
    indexed_documents: list[Document]
    pending_documents: list[Document]
    failed_documents: list[Document]
    missing_document_ids: list[UUID]


async def load_active_document_context(
    session: AsyncSession,
    user_id: UUID,
    document_ids: list[UUID],
) -> ActiveDocumentContext:
    if not document_ids:
        return ActiveDocumentContext([], [], [], [], [])

    rows = await session.execute(
        select(Document)
        .where(
            Document.owner_id == user_id,
            Document.id.in_(document_ids),
        )
        .order_by(Document.created_at.desc())
    )
    documents = rows.scalars().all()
    document_map = {document.id: document for document in documents}
    ordered_documents = [document_map[doc_id] for doc_id in document_ids if doc_id in document_map]

    indexed_documents = [
        document for document in ordered_documents if document.status == DocumentStatus.indexed
    ]
    pending_documents = [
        document
        for document in ordered_documents
        if document.status in {DocumentStatus.pending, DocumentStatus.processing}
    ]
    failed_documents = [
        document for document in ordered_documents if document.status == DocumentStatus.failed
    ]

    return ActiveDocumentContext(
        documents=ordered_documents,
        indexed_documents=indexed_documents,
        pending_documents=pending_documents,
        failed_documents=failed_documents,
        missing_document_ids=[doc_id for doc_id in document_ids if doc_id not in document_map],
    )


def serialize_active_documents(documents: list[Document]) -> list[ActiveDocumentResponse]:
    return [
        ActiveDocumentResponse(
            id=document.id,
            title=document.title,
            file_name=document.file_name,
            status=document.status.value,
            total_chunks=document.total_chunks,
        )
        for document in documents
    ]
