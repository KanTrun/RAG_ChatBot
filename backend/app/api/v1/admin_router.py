"""Admin router: system stats, user management, document management, ingestion status, and evaluation history."""

from datetime import datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_pagination, require_role
from app.dependencies import get_db
from app.models.chunk import DocumentChunk
from app.models.conversation import Conversation
from app.models.document import Document, DocumentStatus
from app.models.message import Message, MessageRole
from app.models.user import Role, User
from app.schemas.admin_schemas import (
    AdminUserResponse,
    AdminUserUpdateRequest,
    BulkReindexResponse,
    DocumentIndexDiagnosticsResponse,
    DocumentOutlineBlock,
    EvaluationDashboardResponse,
    EvaluationRunSummary,
    IndexedChunkDebug,
    IngestionJobStatus,
    SystemStats,
)
from app.schemas.common_schemas import PaginatedResponse, PaginationParams
from app.schemas.document_schemas import (
    DocumentDetailResponse,
    DocumentReindexRequest,
    DocumentResponse,
)
from app.services.document_ingestion_dispatcher import dispatch_document_ingestion
from app.services.document_structure import (
    INGESTION_VERSION,
    build_semantic_blocks,
    serialize_semantic_blocks,
)
from app.services.parser_factory import get_parser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

_EVAL_HISTORY_PATH = Path(__file__).resolve().parents[2] / "evaluation" / "evaluation_history.json"


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

    total_questions = (
        await db.execute(
            select(func.count(Message.id)).where(Message.role == MessageRole.user)
        )
    ).scalar() or 0

    assistant_msgs = (
        await db.execute(
            select(Message.content, Message.latency_ms, Message.tokens_used).where(
                Message.role == MessageRole.assistant
            )
        )
    ).all()

    abstained_count = 0
    latencies: list[int] = []
    tokens_list: list[int] = []
    for content, latency_ms, tokens_used in assistant_msgs:
        text_lower = (content or "").lower()
        if (
            "could not find enough support" in text_lower
            or "strict document mode is on, but no indexed documents" in text_lower
            or "không tìm thấy đủ bằng chứng" in text_lower
        ):
            abstained_count += 1
        if latency_ms is not None and latency_ms >= 0:
            latencies.append(int(latency_ms))
        if tokens_used is not None and tokens_used >= 0:
            tokens_list.append(int(tokens_used))

    total_assistant = len(assistant_msgs)
    abstention_rate = round(abstained_count / total_assistant, 4) if total_assistant > 0 else 0.0
    avg_latency_ms = round(sum(latencies) / len(latencies), 1) if latencies else 0.0
    avg_tokens = round(sum(tokens_list) / len(tokens_list), 1) if tokens_list else 0.0

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
        total_questions=total_questions,
        abstention_rate=abstention_rate,
        avg_latency_ms=avg_latency_ms,
        avg_tokens_per_answer=avg_tokens,
    )


@router.get("/users", response_model=list[AdminUserResponse])
async def list_users(
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role("admin")),
):
    """List all users with their roles, active status, and document count."""
    users = (
        await db.execute(select(User).order_by(User.created_at.desc()))
    ).scalars().all()

    doc_counts_rows = await db.execute(
        select(Document.owner_id, func.count(Document.id)).group_by(Document.owner_id)
    )
    doc_counts = {row[0]: int(row[1]) for row in doc_counts_rows.all()}

    return [
        AdminUserResponse(
            id=u.id,
            email=u.email,
            display_name=u.display_name,
            is_active=u.is_active,
            is_superuser=u.is_superuser,
            roles=[r.name for r in (u.roles or [])],
            document_count=doc_counts.get(u.id, 0),
            created_at=u.created_at,
        )
        for u in users
    ]


@router.patch("/users/{user_id}", response_model=AdminUserResponse)
async def update_user_admin(
    user_id: UUID,
    body: AdminUserUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_admin=Depends(require_role("admin")),
):
    """Update a user's role (admin/user/viewer/editor) or active status (lock/unlock)."""
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    if body.is_active is False and user.id == current_admin.id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Cannot lock your own currently logged-in admin account.",
        )

    if body.is_active is not None:
        user.is_active = body.is_active

    if body.role is not None:
        normalized_role = body.role.strip().lower()
        if normalized_role not in {"admin", "user", "editor", "viewer"}:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Invalid role '{body.role}'. Allowed: admin, user, editor, viewer.",
            )
        role_obj = (
            await db.execute(select(Role).where(Role.name == normalized_role))
        ).scalar_one_or_none()
        if role_obj is None:
            role_obj = Role(name=normalized_role, description=f"Role {normalized_role}")
            db.add(role_obj)
            await db.flush()
        user.roles = [role_obj]
        user.is_superuser = normalized_role == "admin"

    await db.commit()
    await db.refresh(user)

    doc_count = (
        await db.execute(
            select(func.count(Document.id)).where(Document.owner_id == user.id)
        )
    ).scalar() or 0

    return AdminUserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_active=user.is_active,
        is_superuser=user.is_superuser,
        roles=[r.name for r in (user.roles or [])],
        document_count=doc_count,
        created_at=user.created_at,
    )


@router.get("/evaluations", response_model=EvaluationDashboardResponse)
async def get_evaluations(
    _user=Depends(require_role("admin")),
):
    """Return the most recent RAG evaluation results and historical runs."""
    if not _EVAL_HISTORY_PATH.exists():
        return EvaluationDashboardResponse(latest=None, history=[])

    try:
        raw = json.loads(_EVAL_HISTORY_PATH.read_text(encoding="utf-8"))
        runs_data = raw if isinstance(raw, list) else raw.get("history", [])
        runs = [EvaluationRunSummary.model_validate(item) for item in runs_data]
        return EvaluationDashboardResponse(
            latest=runs[-1] if runs else None,
            history=list(reversed(runs)),
        )
    except Exception as exc:
        logger.warning("Failed to read evaluation history: %s", exc)
        return EvaluationDashboardResponse(latest=None, history=[])


@router.post("/evaluations/run", response_model=EvaluationDashboardResponse)
async def trigger_evaluation_run(
    _user=Depends(require_role("admin")),
):
    """Run the golden dataset evaluation pipeline and record the new run in history."""
    from app.evaluation.ragas_evaluator import run_evaluation

    await run_evaluation()
    return await get_evaluations(_user=_user)


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
    chunk_size: int | None = Query(default=None, ge=64, le=4096),
    chunk_overlap: int | None = Query(default=None, ge=0, le=1024),
    body: DocumentReindexRequest | None = Body(default=None),
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role("admin")),
):
    """Re-index any document with optional chunking parameters."""
    doc = await db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")

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
    logger.info("Admin re-index dispatched for document %s", doc.id)
    return doc


@router.post("/documents/reindex-all", response_model=BulkReindexResponse)
async def reindex_all_documents(
    background_tasks: BackgroundTasks,
    stale_only: bool = False,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role("admin")),
):
    """Queue a full re-index pass, optionally scoped to stale ingestion versions."""
    base = select(Document)
    if stale_only:
        base = base.where(
            (Document.metadata_.is_(None))
            | (Document.metadata_["ingestion_version"].astext != INGESTION_VERSION)
        )

    documents = (await db.execute(base)).scalars().all()
    if not documents:
        return BulkReindexResponse(
            queued_documents=0,
            stale_only=stale_only,
            ingestion_version=INGESTION_VERSION,
        )

    document_ids = [document.id for document in documents]
    await db.execute(
        update(Document)
        .where(Document.id.in_(document_ids))
        .values(status=DocumentStatus.pending, error_message=None)
    )
    await db.commit()

    for document_id in document_ids:
        dispatch_document_ingestion(document_id, background_tasks.add_task)

    logger.info("Admin bulk re-index queued for %s documents", len(document_ids))
    return BulkReindexResponse(
        queued_documents=len(document_ids),
        stale_only=stale_only,
        ingestion_version=INGESTION_VERSION,
    )


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


@router.get("/documents/{document_id}/debug-index", response_model=DocumentIndexDiagnosticsResponse)
async def get_document_index_debug(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role("admin")),
):
    """Inspect parse outline and indexed chunk metadata for one document."""
    doc = await db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")

    parser = get_parser(doc.file_path)
    pages = parser.parse(doc.file_path)
    blocks = build_semantic_blocks(pages)
    indexed_chunks = (
        await db.execute(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
        )
    ).scalars().all()

    return DocumentIndexDiagnosticsResponse(
        document_id=doc.id,
        title=doc.title,
        file_name=doc.file_name,
        status=doc.status.value,
        ingestion_version=(doc.metadata_ or {}).get("ingestion_version"),
        parsed_outline=[
            DocumentOutlineBlock.model_validate(item)
            for item in serialize_semantic_blocks(blocks)
        ],
        indexed_chunks=[
            IndexedChunkDebug(
                chunk_id=chunk.id,
                chunk_index=chunk.chunk_index,
                page_number=chunk.page_number,
                section=chunk.section,
                block_type=(chunk.metadata_ or {}).get("block_type"),
                section_path=(chunk.metadata_ or {}).get("section_path"),
                parent_block_id=(chunk.metadata_ or {}).get("parent_block_id"),
                heading_level=(chunk.metadata_ or {}).get("heading_level"),
                ingestion_version=(chunk.metadata_ or {}).get("ingestion_version"),
                contextualized_text=(chunk.metadata_ or {}).get("contextualized_text"),
                selection_reason=(chunk.metadata_ or {}).get("selection_reason"),
            )
            for chunk in indexed_chunks
        ],
    )
