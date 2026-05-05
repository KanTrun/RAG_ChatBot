"""Admin router: system stats, document management, and ingestion status."""

import logging
import os
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_pagination, require_role
from app.dependencies import get_db
from app.models.chunk import DocumentChunk
from app.models.conversation import Conversation
from app.models.document import Document, DocumentStatus
from app.models.message import Message
from app.schemas.admin_schemas import IngestionJobStatus, SystemStats
from app.schemas.common_schemas import PaginatedResponse, PaginationParams
from app.schemas.document_schemas import DocumentDetailResponse, DocumentResponse
from app.services.document_ingestion_dispatcher import dispatch_document_ingestion

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats", response_model=SystemStats)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role("admin")),
):
    """Aggregate system statistics for admin dashboard."""
    total_docs = (await db.execute(select(func.count(Document.id)))).scalar() or 0
    total_chunks = (await db.execute(select(func.count(DocumentChunk.id)))).scalar() or 0
    total_convs = (await db.execute(select(func.count(Conversation.id)))).scalar() or 0
    total_msgs = (await db.execute(select(func.count(Message.id)))).scalar() or 0

    # Documents grouped by status
    status_rows = await db.execute(
        select(Document.status, func.count()).group_by(Document.status)
    )
    docs_by_status = {row[0].value: row[1] for row in status_rows.all()}

    return SystemStats(
        total_documents=total_docs,
        total_chunks=total_chunks,
        total_conversations=total_convs,
        total_messages=total_msgs,
        docs_by_status=docs_by_status,
    )


@router.get("/documents", response_model=PaginatedResponse[DocumentResponse])
async def list_admin_documents(
    status_filter: str | None = None,
    file_type: str | None = None,
    search: str | None = None,
    pagination: PaginationParams = Depends(get_pagination),
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role("admin")),
):
    """List all documents for system administration."""
    base = select(Document)

    if status_filter:
        base = base.where(Document.status == status_filter)
    if file_type:
        base = base.where(Document.file_type == file_type)
    if search:
        base = base.where(Document.title.ilike(f"%{search}%"))

    total_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_result.scalar() or 0
    result = await db.execute(
        base.order_by(Document.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    )

    return PaginatedResponse(
        items=result.scalars().all(),
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        total_pages=(total + pagination.page_size - 1) // pagination.page_size,
    )


@router.get("/documents/{document_id}", response_model=DocumentDetailResponse)
async def get_admin_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role("admin")),
):
    """Get any document detail for system administration."""
    doc = await db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return doc


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_admin_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role("admin")),
):
    """Delete any document and its chunks."""
    doc = await db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")

    try:
        if os.path.exists(doc.file_path):
            os.remove(doc.file_path)
    except OSError as exc:
        logger.warning("Failed to delete file %s: %s", doc.file_path, exc)

    await db.delete(doc)
    await db.commit()


@router.post("/documents/{document_id}/reindex", response_model=DocumentResponse)
async def reindex_admin_document(
    document_id: UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role("admin")),
):
    """Re-index any document."""
    doc = await db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")

    doc.status = DocumentStatus.pending
    doc.error_message = None
    await db.commit()
    await db.refresh(doc)

    dispatch_document_ingestion(doc.id, background_tasks.add_task)
    logger.info("Admin re-index dispatched for document %s", doc.id)
    return doc


@router.get("/ingestion-status", response_model=list[IngestionJobStatus])
async def get_ingestion_status(
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role("admin")),
):
    """List queued, processing, or recently failed ingestion jobs."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    result = await db.execute(
        select(Document)
        .where(
            (Document.status == DocumentStatus.pending)
            | (Document.status == DocumentStatus.processing)
            | (
                (Document.status == DocumentStatus.failed)
                & (Document.updated_at >= cutoff)
            )
        )
        .order_by(Document.updated_at.desc())
        .limit(50)
    )

    return [
        IngestionJobStatus(
            document_id=doc.id,
            title=doc.title,
            status=doc.status.value,
            created_at=doc.created_at,
            error_message=doc.error_message,
        )
        for doc in result.scalars().all()
    ]
