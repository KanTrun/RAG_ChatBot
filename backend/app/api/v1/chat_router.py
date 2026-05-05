"""Chat router: SSE streaming, conversations, messages."""

import asyncio
import json
import logging
import re
import time
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_pagination
from app.dependencies import get_db
from app.models.conversation import Conversation
from app.models.document import Document, DocumentStatus
from app.models.message import Message, MessageRole
from app.config import get_settings
from app.prompts.rag_prompt_template import build_rag_messages
from app.prompts.system_prompt import (
    GENERAL_ONLY_PROMPT,
    HYBRID_SYSTEM_PROMPT,
    STRICT_DOCUMENT_PROMPT,
)
from app.schemas.chat_schemas import (
    ChatRequest,
    ChatResponseMode,
    ConversationResponse,
    ConversationUpdateRequest,
    MessageResponse,
)
from app.schemas.common_schemas import PaginatedResponse, PaginationParams
from app.services.context_assembler import AssembledContext
from app.services.conversation_document_context import (
    load_active_document_context,
    serialize_active_documents,
)
from app.services.grounded_answer_fallback import build_grounded_fallback_answer
from app.services.llm import get_llm_provider
from app.services.llm.base_provider import LLMConfig
from app.services.query_rewriter import QueryRewriter
from app.services.retrieval_intent_service import build_retrieval_plan
from app.services.retrieval_service import RetrievalService, RetrievalResult, SearchFilters

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

GREETING_PATTERNS = (
    re.compile(r"^\s*(hi|hello|hey|yo|alo)\s*[!.?]*\s*$", re.IGNORECASE),
    re.compile(r"^\s*(xin chao|xin chào|chao|chào)\s*[!.?]*\s*$", re.IGNORECASE),
)

GREETING_RESPONSE = (
    "Hello. I'm ready to help with questions about your documents. "
    "Upload a file or ask about one you've already indexed."
)
INDEXING_RESPONSE = (
    "Your document is still indexing. Wait until its status becomes Indexed, then ask again."
)
FAILED_ACTIVE_DOCUMENT_RESPONSE = (
    "The selected document failed indexing. Re-index or upload it again before asking about it."
)
STRICT_NO_DOCUMENTS_RESPONSE = (
    "Strict document mode is on, but no indexed documents are available yet. "
    "Upload or finish indexing the relevant documents, or explicitly enable outside knowledge."
)
STRICT_LOW_SUPPORT_RESPONSE = (
    "I could not find enough support in the current document context to answer that. "
    "Try selecting the relevant documents, waiting for indexing to finish, or ask a question that is more directly covered by the documents."
)


def ensure_chat_providers_configured() -> None:
    settings = get_settings()
    missing: list[str] = []

    if "ollama" in {settings.embedding_provider, settings.llm_provider}:
        if not settings.ollama_base_url:
            missing.append("OLLAMA_BASE_URL")
    if settings.embedding_provider == "ollama" and not settings.ollama_embedding_model:
        missing.append("OLLAMA_EMBEDDING_MODEL")
    if settings.llm_provider == "openai" and not settings.openai_api_key:
        missing.append("OPENAI_API_KEY")
    if settings.embedding_provider == "openai" and not settings.openai_api_key:
        missing.append("OPENAI_API_KEY")
    if settings.llm_provider == "anthropic" and not settings.anthropic_api_key:
        missing.append("ANTHROPIC_API_KEY")

    if missing:
        unique_missing = ", ".join(sorted(set(missing)))
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"Chat provider is not configured. Missing: {unique_missing}",
        )


def get_small_talk_reply(query: str) -> str | None:
    normalized = query.strip()
    if not normalized:
        return None

    if any(pattern.fullmatch(normalized) for pattern in GREETING_PATTERNS):
        return GREETING_RESPONSE

    return None


def raise_chat_service_unavailable(stage: str, error: Exception) -> None:
    logger.exception("Chat %s failed", stage)
    raise HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        f"Chat {stage} is temporarily unavailable. Please try again in a moment.",
    ) from error


async def stream_static_reply(
    db: AsyncSession,
    conv: Conversation,
    content: str,
    start_time: float,
    active_documents: list[dict] | None = None,
):
    assistant_msg = Message(
        conversation_id=conv.id,
        role=MessageRole.assistant,
        content=content,
        sources=[],
        latency_ms=int((time.time() - start_time) * 1000),
    )
    db.add(assistant_msg)
    await db.commit()

    yield f"data: {json.dumps({'type': 'chunk', 'content': content})}\n\n"
    done_payload = {
        "type": "done",
        "message_id": str(assistant_msg.id),
        "conversation_id": str(conv.id),
        "active_documents": active_documents or [],
    }
    yield f"data: {json.dumps(done_payload)}\n\n"


async def user_has_index_ready_documents(db: AsyncSession, user_id: UUID) -> bool:
    indexed_count = await db.execute(
        select(func.count(Document.id)).where(
            Document.owner_id == user_id,
            Document.status == DocumentStatus.indexed,
        )
    )
    return (indexed_count.scalar() or 0) > 0


async def user_has_documents_still_indexing(db: AsyncSession, user_id: UUID) -> bool:
    indexing_count = await db.execute(
        select(func.count(Document.id)).where(
            Document.owner_id == user_id,
            Document.status.in_([DocumentStatus.pending, DocumentStatus.processing]),
        )
    )
    return (indexing_count.scalar() or 0) > 0


def build_empty_retrieval_result(query: str) -> RetrievalResult:
    return RetrievalResult(
        context=AssembledContext(context_text="", sources=[], total_tokens=0),
        query_used=query,
        low_confidence=True,
        candidate_count=0,
    )


def build_indexing_status_reply(active_document_names: list[str]) -> str:
    if not active_document_names:
        return INDEXING_RESPONSE
    joined_names = ", ".join(active_document_names[:3])
    return (
        f"{joined_names} is still indexing. Wait until it becomes Indexed, then ask again."
        if len(active_document_names) == 1
        else f"Some selected documents are still indexing: {joined_names}. "
        "Wait until they become Indexed, then ask again."
    )


def build_failed_document_reply(active_document_names: list[str]) -> str:
    if not active_document_names:
        return FAILED_ACTIVE_DOCUMENT_RESPONSE
    joined_names = ", ".join(active_document_names[:3])
    return (
        f"{joined_names} failed indexing. Re-index or upload it again before asking about it."
        if len(active_document_names) == 1
        else f"Some selected documents failed indexing: {joined_names}. "
        "Re-index or upload them again before asking about them."
    )


async def build_conversation_response(
    db: AsyncSession,
    conv: Conversation,
) -> ConversationResponse:
    msg_count = await db.execute(select(func.count()).where(Message.conversation_id == conv.id))
    context = await load_active_document_context(db, conv.user_id, conv.active_document_ids or [])
    return ConversationResponse(
        id=conv.id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        message_count=msg_count.scalar() or 0,
        active_documents=serialize_active_documents(context.documents),
    )


def has_grounded_context(result: RetrievalResult) -> bool:
    return bool(result.context.context_text.strip()) and bool(result.context.sources)


def build_chat_generation_config(
    *,
    strict_mode: bool,
    allow_general_answer: bool,
    context_tokens: int,
) -> LLMConfig:
    max_tokens = 1800 if context_tokens >= 3500 else 1500
    if allow_general_answer:
        return LLMConfig(temperature=0.2, max_tokens=max_tokens)
    if strict_mode:
        return LLMConfig(temperature=0.05, max_tokens=max_tokens)
    return LLMConfig(temperature=0.12, max_tokens=max_tokens)


@router.post("/chat")
async def chat(
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Chat endpoint with SSE streaming response."""
    start_time = time.time()

    # Load or create conversation
    if body.conversation_id:
        conv = await db.get(Conversation, body.conversation_id)
        if conv is None or conv.user_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    else:
        conv = Conversation(user_id=user.id, title=body.query[:100])
        db.add(conv)
        await db.flush()

    if body.document_ids is not None:
        requested_document_ids = list(dict.fromkeys(body.document_ids))
        active_context = await load_active_document_context(db, user.id, requested_document_ids)
        if active_context.missing_document_ids:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "One or more documents were not found")
        conv.active_document_ids = requested_document_ids
    else:
        active_context = await load_active_document_context(
            db,
            user.id,
            conv.active_document_ids or [],
        )
        if active_context.missing_document_ids:
            conv.active_document_ids = [document.id for document in active_context.documents]

    active_documents_payload = [
        item.model_dump(mode="json")
        for item in serialize_active_documents(active_context.documents)
    ]

    # Save user message
    user_msg = Message(
        conversation_id=conv.id,
        role=MessageRole.user,
        content=body.query,
    )
    db.add(user_msg)
    await db.flush()

    small_talk_reply = get_small_talk_reply(body.query)
    if small_talk_reply:
        return StreamingResponse(
            stream_static_reply(
                db,
                conv,
                small_talk_reply,
                start_time,
                active_documents=active_documents_payload,
            ),
            media_type="text/event-stream",
        )

    has_active_indexed_documents = len(active_context.indexed_documents) > 0
    if active_context.pending_documents and not has_active_indexed_documents:
        return StreamingResponse(
            stream_static_reply(
                db,
                conv,
                build_indexing_status_reply(
                    [document.file_name for document in active_context.pending_documents]
                ),
                start_time,
                active_documents=active_documents_payload,
            ),
            media_type="text/event-stream",
        )

    if active_context.failed_documents and not has_active_indexed_documents:
        return StreamingResponse(
            stream_static_reply(
                db,
                conv,
                build_failed_document_reply(
                    [document.file_name for document in active_context.failed_documents]
                ),
                start_time,
                active_documents=active_documents_payload,
            ),
            media_type="text/event-stream",
        )

    has_indexed_documents = await user_has_index_ready_documents(db, user.id)
    if (
        not active_context.documents
        and not has_indexed_documents
        and await user_has_documents_still_indexing(db, user.id)
    ):
        return StreamingResponse(
            stream_static_reply(
                db,
                conv,
                INDEXING_RESPONSE,
                start_time,
                active_documents=active_documents_payload,
            ),
            media_type="text/event-stream",
        )

    strict_mode = body.response_mode == ChatResponseMode.strict_documents
    if strict_mode and not has_indexed_documents and not has_active_indexed_documents:
        return StreamingResponse(
            stream_static_reply(
                db,
                conv,
                STRICT_NO_DOCUMENTS_RESPONSE,
                start_time,
                active_documents=active_documents_payload,
            ),
            media_type="text/event-stream",
        )

    ensure_chat_providers_configured()

    # Get conversation history for query rewriting
    history_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conv.id)
        .order_by(Message.created_at)
        .limit(10)
    )
    history = [
        {"role": m.role.value, "content": m.content}
        for m in history_result.scalars().all()
        if m.id != user_msg.id
    ]

    llm_provider = get_llm_provider()
    result = build_empty_retrieval_result(body.query)
    active_indexed_document_count = len(active_context.indexed_documents)
    retrieval_plan = build_retrieval_plan(body.query, active_indexed_document_count)

    if has_indexed_documents or has_active_indexed_documents:
        try:
            rewriter = QueryRewriter(llm_provider)
            rewritten_query = await rewriter.rewrite(body.query, history)
            alternate_queries = (
                [rewritten_query]
                if rewritten_query.strip() and rewritten_query.strip() != body.query.strip()
                else None
            )

            retrieval_svc = RetrievalService(session=db)
            retrieval_filters = (
                SearchFilters(
                    document_ids=[document.id for document in active_context.indexed_documents]
                )
                if active_context.indexed_documents
                else None
            )
            result = await retrieval_svc.retrieve(
                query=body.query,
                user_id=user.id,
                user_role_ids=[role.id for role in user.roles] if user.roles else [],
                filters=retrieval_filters,
                alternate_queries=alternate_queries,
                top_k_search=retrieval_plan.top_k_search,
                top_k_rerank=retrieval_plan.top_k_rerank,
                confidence_threshold=retrieval_plan.confidence_threshold,
                prefer_document_order=retrieval_plan.prefer_document_order,
                context_max_tokens=retrieval_plan.context_max_tokens,
                balanced_per_document=retrieval_plan.balanced_per_document,
                ordered_document_scan=retrieval_plan.ordered_document_scan,
            )
        except HTTPException:
            raise
        except Exception:
            if strict_mode:
                logger.exception("Chat retrieval failed in strict mode; returning abstention")
            else:
                logger.exception("Chat retrieval degraded; continuing with hybrid general mode")
            result = build_empty_retrieval_result(body.query)

    if strict_mode and (result.low_confidence or not has_grounded_context(result)):
        return StreamingResponse(
            stream_static_reply(
                db,
                conv,
                STRICT_LOW_SUPPORT_RESPONSE,
                start_time,
                active_documents=active_documents_payload,
            ),
            media_type="text/event-stream",
        )

    allow_general_answer = (
        body.response_mode == ChatResponseMode.hybrid_general
        and (result.low_confidence or not has_grounded_context(result))
    )
    prompt = GENERAL_ONLY_PROMPT if allow_general_answer else (
        STRICT_DOCUMENT_PROMPT if strict_mode else HYBRID_SYSTEM_PROMPT
    )
    prompt_context = "" if allow_general_answer else result.context.context_text
    generation_config = build_chat_generation_config(
        strict_mode=strict_mode,
        allow_general_answer=allow_general_answer,
        context_tokens=result.context.total_tokens,
    )

    # Build LLM messages
    messages = build_rag_messages(
        context=prompt_context,
        query=body.query,
        system_prompt=prompt,
        conversation_history=history[-4:] if history else None,
        answer_brief=None if allow_general_answer else result.context.answer_brief,
    )

    # Prepare sources metadata for SSE
    sources_data = (
        []
        if allow_general_answer
        else [
            {
                "citation_number": s.citation_number,
                "document_title": s.document_title,
                "file_name": s.file_name,
                "page_number": s.page_number,
                "section": s.section,
                "section_path": s.section_path,
                "block_type": s.block_type,
                "page_start": s.page_start,
                "page_end": s.page_end,
                "score": round(s.score, 4),
                "excerpt": s.excerpt,
                "selection_reason": s.selection_reason,
                "answer_section": s.answer_section,
            }
            for s in result.context.sources
        ]
    )

    async def event_stream():
        full_content = ""
        try:
            stream = llm_provider.generate_stream(messages, generation_config).__aiter__()
            while True:
                try:
                    chunk = await asyncio.wait_for(stream.__anext__(), timeout=30)
                except StopAsyncIteration:
                    break
                full_content += chunk
                event = {"type": "chunk", "content": chunk}
                yield f"data: {json.dumps(event)}\n\n"

            # Sources event
            yield f"data: {json.dumps({'type': 'sources', 'sources': sources_data})}\n\n"

            # Save assistant message
            latency_ms = int((time.time() - start_time) * 1000)
            assistant_msg = Message(
                conversation_id=conv.id,
                role=MessageRole.assistant,
                content=full_content,
                sources=sources_data,
                latency_ms=latency_ms,
            )
            db.add(assistant_msg)
            await db.commit()

            # Done event
            done = {
                "type": "done",
                "message_id": str(assistant_msg.id),
                "conversation_id": str(conv.id),
                "active_documents": active_documents_payload,
            }
            yield f"data: {json.dumps(done)}\n\n"

        except Exception:
            logger.exception("Stream error")
            if full_content.strip():
                latency_ms = int((time.time() - start_time) * 1000)
                assistant_msg = Message(
                    conversation_id=conv.id,
                    role=MessageRole.assistant,
                    content=full_content,
                    sources=sources_data,
                    latency_ms=latency_ms,
                )
                db.add(assistant_msg)
                await db.commit()

                yield f"data: {json.dumps({'type': 'sources', 'sources': sources_data})}\n\n"
                done = {
                    "type": "done",
                    "message_id": str(assistant_msg.id),
                    "conversation_id": str(conv.id),
                    "active_documents": active_documents_payload,
                }
                yield f"data: {json.dumps(done)}\n\n"
                return

            fallback_content = build_grounded_fallback_answer(
                body.query,
                result.context.context_text,
            )
            if fallback_content:
                latency_ms = int((time.time() - start_time) * 1000)
                assistant_msg = Message(
                    conversation_id=conv.id,
                    role=MessageRole.assistant,
                    content=fallback_content,
                    sources=sources_data,
                    latency_ms=latency_ms,
                )
                db.add(assistant_msg)
                await db.commit()

                yield f"data: {json.dumps({'type': 'chunk', 'content': fallback_content})}\n\n"
                yield f"data: {json.dumps({'type': 'sources', 'sources': sources_data})}\n\n"
                done = {
                    "type": "done",
                    "message_id": str(assistant_msg.id),
                    "conversation_id": str(conv.id),
                    "active_documents": active_documents_payload,
                }
                yield f"data: {json.dumps(done)}\n\n"
                return

            error = {"type": "error", "content": "Chat stream failed. Please try again."}
            yield f"data: {json.dumps(error)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/conversations", response_model=PaginatedResponse[ConversationResponse])
async def list_conversations(
    pagination: PaginationParams = Depends(get_pagination),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """List user's conversations, newest first."""
    base = select(Conversation).where(Conversation.user_id == user.id)
    total_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_result.scalar() or 0

    rows = await db.execute(
        base.order_by(Conversation.updated_at.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    )
    conversations = rows.scalars().all()

    items = []
    for c in conversations:
        msg_count = await db.execute(
            select(func.count()).where(Message.conversation_id == c.id)
        )
        items.append(
            ConversationResponse(
                id=c.id,
                title=c.title,
                created_at=c.created_at,
                updated_at=c.updated_at,
                message_count=msg_count.scalar() or 0,
            )
        )

    return PaginatedResponse(
        items=items,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        total_pages=(total + pagination.page_size - 1) // pagination.page_size,
    )


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationResponse,
)
async def get_conversation(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Get conversation metadata, including active document context."""
    conv = await db.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")

    return await build_conversation_response(db, conv)


@router.patch(
    "/conversations/{conversation_id}",
    response_model=ConversationResponse,
)
async def update_conversation(
    conversation_id: UUID,
    body: ConversationUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Update active document context for a conversation."""
    conv = await db.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")

    requested_document_ids = list(dict.fromkeys(body.document_ids))
    active_context = await load_active_document_context(db, user.id, requested_document_ids)
    if active_context.missing_document_ids:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "One or more documents were not found")

    conv.active_document_ids = requested_document_ids
    await db.commit()
    await db.refresh(conv)
    return await build_conversation_response(db, conv)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[MessageResponse],
)
async def get_conversation_messages(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Get all messages for a conversation."""
    conv = await db.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")

    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    return result.scalars().all()
