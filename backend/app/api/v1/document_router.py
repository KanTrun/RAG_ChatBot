"""Document router: upload, CRUD, configurable chunking re-index, and chunk inspection."""

import hashlib
import logging
import os
from pathlib import Path
import uuid

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    Depends,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_pagination
from app.auth.auth_middleware import require_document_access
from app.config import get_settings
from app.dependencies import get_db
from app.models.chunk import DocumentChunk
from app.models.conversation import Conversation
from app.models.document import Document, DocumentStatus
from app.schemas.common_schemas import PaginatedResponse, PaginationParams
from app.schemas.document_schemas import (
    DocumentChunkItem,
    DocumentChunksResponse,
    DocumentDetailResponse,
    DocumentReindexRequest,
    DocumentResponse,
)
from app.services.document_ingestion_dispatcher import dispatch_document_ingestion
from app.services.parser_factory import SUPPORTED_EXTENSIONS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB


def _compute_content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _serialize_document(doc: Document, duplicate_of_existing: bool = False) -> DocumentResponse:
    return DocumentResponse.model_validate(doc).model_copy(
        update={"duplicate_of_existing": duplicate_of_existing}
    )


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile,
    response: Response,
    background_tasks: BackgroundTasks,
    chunk_size: int | None = Form(default=None),
    chunk_overlap: int | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Upload a document for ingestion with optional chunk_size and chunk_overlap."""
    ext = Path(file.filename or "").suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unsupported file type: {ext}. Supported: {', '.join(SUPPORTED_EXTENSIONS)}",
        )

    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File exceeds 50MB limit")

    settings = get_settings()
    resolved_chunk_size = max(64, min(int(chunk_size or settings.chunk_size), 4096))
    resolved_chunk_overlap = max(
        0,
        min(
            int(chunk_overlap if chunk_overlap is not None else settings.chunk_overlap),
            resolved_chunk_size - 1,
        ),
    )

    content_hash = _compute_content_hash(content)

    existing_result = await db.execute(
        select(Document)
        .where(
            Document.owner_id == user.id,
            Document.content_hash == content_hash,
        )
        .order_by(Document.updated_at.desc())
        .limit(1)
    )
    existing = existing_result.scalar_one_or_none()

    if existing is not None:
        if existing.status == DocumentStatus.failed:
            file_path = Path(existing.file_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(content)

            existing.title = Path(file.filename or existing.file_name).stem
            existing.file_name = file.filename or existing.file_name
            existing.file_type = ext.lstrip(".")
            existing.file_size = len(content)
            existing.status = DocumentStatus.pending
            existing.error_message = None
            existing.total_chunks = 0
            existing.metadata_ = {
                **(existing.metadata_ or {}),
                "chunk_size": resolved_chunk_size,
                "chunk_overlap": resolved_chunk_overlap,
            }
            await db.commit()
            await db.refresh(existing)
            dispatch_document_ingestion(existing.id, background_tasks.add_task)
            logger.info("Document %s duplicate upload re-queued after prior failure", existing.id)
        else:
            logger.info("Document %s duplicate upload skipped for owner %s", existing.id, user.id)

        response.status_code = status.HTTP_200_OK
        return _serialize_document(existing, duplicate_of_existing=True)

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_id = uuid.uuid4()
    safe_name = f"{file_id}_{file.filename}"
    file_path = upload_dir / safe_name

    with open(file_path, "wb") as f:
        f.write(content)

    doc = Document(
        title=Path(file.filename or "untitled").stem,
        file_name=file.filename or "untitled",
        file_path=str(file_path),
        file_type=ext.lstrip("."),
        file_size=len(content),
        content_hash=content_hash,
        status=DocumentStatus.pending,
        owner_id=user.id,
        metadata_={
            "chunk_size": resolved_chunk_size,
            "chunk_overlap": resolved_chunk_overlap,
        },
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    dispatch_document_ingestion(doc.id, background_tasks.add_task)
    logger.info("Document %s uploaded, ingestion task dispatched", doc.id)

    return _serialize_document(doc)


@router.get("", response_model=PaginatedResponse[DocumentResponse])
async def list_documents(
    status_filter: str | None = None,
    file_type: str | None = None,
    search: str | None = None,
    pagination: PaginationParams = Depends(get_pagination),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """List documents with optional filters."""
    base = select(Document).where(Document.owner_id == user.id)

    if status_filter:
        base = base.where(Document.status == status_filter)
    if file_type:
        base = base.where(Document.file_type == file_type)
    if search:
        base = base.where(
            (Document.title.ilike(f"%{search}%"))
            | (Document.file_name.ilike(f"%{search}%"))
        )

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


@router.get("/{document_id}", response_model=DocumentDetailResponse)
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Get document details."""
    doc = await db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    require_document_access(doc, user)
    return doc


@router.get("/{document_id}/chunks", response_model=DocumentChunksResponse)
async def get_document_chunks(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Inspect all indexed chunks and extracted sections of a document."""
    doc = await db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    require_document_access(doc, user)

    settings = get_settings()
    rows = (
        await db.execute(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
        )
    ).scalars().all()

    meta = doc.metadata_ or {}
    chunk_size = int(meta.get("chunk_size") or settings.chunk_size)
    chunk_overlap = int(
        meta.get("chunk_overlap")
        if meta.get("chunk_overlap") is not None
        else settings.chunk_overlap
    )
    sections = sorted({c.section for c in rows if c.section})

    return DocumentChunksResponse(
        document_id=doc.id,
        title=doc.title,
        file_name=doc.file_name,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        total_chunks=len(rows),
        sections=sections,
        chunks=[
            DocumentChunkItem(
                id=c.id,
                chunk_index=c.chunk_index,
                content=c.content,
                page_number=c.page_number,
                section=c.section,
                section_path=(c.metadata_ or {}).get("section_path") or c.section,
                block_type=(c.metadata_ or {}).get("block_type") or "body",
                token_count=c.token_count,
            )
            for c in rows
        ],
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Delete document, its chunks, and the file from disk."""
    doc = await db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    require_document_access(doc, user)

    conversations = await db.execute(
        select(Conversation).where(Conversation.user_id == user.id)
    )
    for conversation in conversations.scalars().all():
        if document_id in (conversation.active_document_ids or []):
            conversation.active_document_ids = [
                active_document_id
                for active_document_id in conversation.active_document_ids
                if active_document_id != document_id
            ]

    try:
        if os.path.exists(doc.file_path):
            os.remove(doc.file_path)
    except OSError as e:
        logger.warning(f"Failed to delete file {doc.file_path}: {e}")

    await db.delete(doc)
    await db.commit()


@router.post("/{document_id}/reindex", response_model=DocumentResponse)
async def reindex_document(
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    chunk_size: int | None = Query(default=None, ge=64, le=4096),
    chunk_overlap: int | None = Query(default=None, ge=0, le=1024),
    body: DocumentReindexRequest | None = Body(default=None),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Re-index a document with optional updated chunk_size and chunk_overlap."""
    doc = await db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    require_document_access(doc, user)

    meta = dict(doc.metadata_ or {})
    req_size = (body.chunk_size if body and body.chunk_size is not None else chunk_size)
    req_overlap = (body.chunk_overlap if body and body.chunk_overlap is not None else chunk_overlap)
    if req_size is not None:
        meta["chunk_size"] = req_size
    if req_overlap is not None:
        meta["chunk_overlap"] = req_overlap

    doc.metadata_ = meta
    doc.status = DocumentStatus.pending
    doc.error_message = None
    await db.commit()
    await db.refresh(doc)

    dispatch_document_ingestion(doc.id, background_tasks.add_task)
    logger.info("Document %s re-index dispatched (metadata=%s)", doc.id, meta)

    return doc
