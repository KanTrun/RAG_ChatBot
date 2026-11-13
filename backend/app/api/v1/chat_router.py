"""Chat router: SSE streaming, conversations, messages, structured logging, and diagnostics."""

import asyncio
from datetime import datetime, timezone
import json
import logging
import re
import time
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
import tiktoken

from app.api.dependencies import get_current_user, get_pagination
from app.auth.auth_middleware import is_admin
from app.config import get_settings
from app.dependencies import get_db
from app.models.conversation import Conversation
from app.models.document import Document, DocumentStatus
from app.models.message import Message, MessageRole
from app.prompts.rag_prompt_template import build_rag_messages
from app.prompts.system_prompt import (
    GENERAL_ONLY_PROMPT,
    HYBRID_SYSTEM_PROMPT,
    STRICT_DOCUMENT_PROMPT,
    detect_query_language,
)
from app.schemas.chat_schemas import (
    ChatRequest,
    ChatResponseMode,
    ConversationResponse,
    ConversationUpdateRequest,
    MessageResponse,
)
from app.schemas.common_schemas import PaginatedResponse, PaginationParams
from app.security.output_validator import validate_and_clean_citations
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
from app.services.retrieval_service import (
    RetrievalResult,
    RetrievalService,
    SearchFilters,
)

logger = logging.getLogger(__name__)
_tokenizer = tiktoken.get_encoding("cl100k_base")

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


def build_low_support_abstention_reply(
    query: str,
    available_doc_titles: list[str] | None = None,
) -> str:
    """Build a language-aware abstention reply suggesting available documents when present."""
    lang = detect_query_language(query)
    titles = [t.strip() for t in (available_doc_titles or []) if t and t.strip()]
    if lang == "vi":
        base = (
            "Hiện chưa có thông tin về nội dung này trong tài liệu đã tải lên "
            "(I could not find enough support in the current document context to answer that)."
        )
        if titles:
            joined = ", ".join(f"'{t}'" for t in titles[:4])
            return f"{base} Bạn có thể đặt câu hỏi xoay quanh các tài liệu hiện có: {joined}."
        return f"{base} Vui lòng chọn đúng tài liệu liên quan hoặc tải thêm tài liệu mới."

    if titles:
        joined = ", ".join(f"'{t}'" for t in titles[:4])
        return f"{STRICT_LOW_SUPPORT_RESPONSE} Available indexed documents: {joined}."
    return STRICT_LOW_SUPPORT_RESPONSE


def _count_tokens(text_value: str) -> int:
    if not text_value:
        return 0
    return len(_tokenizer.encode(text_value))


def _emit_structured_chat_log(
    *,
    conversation_id: UUID,
    user_id: UUID,
    query: str,
    response_mode: str,
    abstained: bool,
    used_outside_knowledge: bool,
    diagnostics: dict,
) -> None:
    latency = diagnostics.get("latency_breakdown_ms") or {}
    tokens = diagnostics.get("tokens") or {}
    payload = {
        "event": "chat_query_completed",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "conversation_id": str(conversation_id),
        "user_id": str(user_id),
        "query": query[:200],
        "response_mode": response_mode,
        "intent": diagnostics.get("intent"),
        "candidate_count": diagnostics.get("candidate_count", 0),
        "vector_candidates_count": diagnostics.get("vector_candidates_count", 0),
        "bm25_candidates_count": diagnostics.get("bm25_candidates_count", 0),
        "bm25_used": diagnostics.get("bm25_used", False),
        "bm25_contributed": diagnostics.get("bm25_contributed", False),
        "top_k_scores": diagnostics.get("top_k_scores", []),
        "latency_ms": {
            "rewrite_ms": latency.get("rewrite_ms", 0),
            "retrieval_ms": latency.get("retrieval_ms", 0),
            "rerank_ms": latency.get("rerank_ms", 0),
            "generation_ms": latency.get("generation_ms", 0),
            "total_ms": latency.get("total_ms", 0),
        },
        "tokens": {
            "prompt_tokens": tokens.get("prompt_tokens", 0),
            "completion_tokens": tokens.get("completion_tokens", 0),
            "total_tokens": tokens.get("total_tokens", 0),
        },
        "abstained": abstained,
        "used_outside_knowledge": used_outside_knowledge,
    }
    logger.info("STRUCTURED_CHAT_LOG %s", json.dumps(payload, ensure_ascii=False))


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
    if settings.llm_provider == "gemini":
        if not settings.gemini_api_key:
            missing.append("GEMINI_API_KEY")
        if not settings.gemini_model:
            missing.append("GEMINI_MODEL")

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
    user_message_id: UUID | None = None,
    replace_messages: list[Message] | None = None,
    active_documents: list[dict] | None = None,
    diagnostics: dict | None = None,
    abstained: bool = False,
):
    total_ms = int((time.time() - start_time) * 1000)
    completion_tokens = _count_tokens(content)
    enriched_diag = dict(diagnostics or {})
    latency_breakdown = dict(enriched_diag.get("latency_breakdown_ms") or {})
    latency_breakdown.setdefault("rewrite_ms", 0)
    latency_breakdown.setdefault("retrieval_ms", enriched_diag.get("retrieval_ms", 0))
    latency_breakdown.setdefault("rerank_ms", enriched_diag.get("rerank_ms", 0))
    latency_breakdown.setdefault("generation_ms", 0)
    latency_breakdown["total_ms"] = total_ms
    enriched_diag["latency_breakdown_ms"] = latency_breakdown
    enriched_diag["tokens"] = {
        "prompt_tokens": 0,
        "completion_tokens": completion_tokens,
        "total_tokens": completion_tokens,
    }
    enriched_diag["abstained"] = abstained
    enriched_diag["used_outside_knowledge"] = False

    assistant_msg = Message(
        conversation_id=conv.id,
        role=MessageRole.assistant,
        content=content,
        sources=[],
        tokens_used=completion_tokens,
        latency_ms=total_ms,
    )
    db.add(assistant_msg)
    if replace_messages:
        for message in replace_messages:
            await db.delete(message)
    await db.commit()

    _emit_structured_chat_log(
        conversation_id=conv.id,
        user_id=conv.user_id,
        query=conv.title or "",
        response_mode="strict_documents",
        abstained=abstained,
        used_outside_knowledge=False,
        diagnostics=enriched_diag,
    )

    yield f"data: {json.dumps({'type': 'chunk', 'content': content})}\n\n"
    done_payload = {
        "type": "done",
        "user_message_id": str(user_message_id) if user_message_id else None,
        "message_id": str(assistant_msg.id),
        "conversation_id": str(conv.id),
        "active_documents": active_documents or [],
        "abstained": abstained,
        "used_outside_knowledge": False,
        "diagnostics": enriched_diag,
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


def enrich_chat_diagnostics(diagnostics: dict | None, retrieval_plan) -> dict:
    enriched = dict(diagnostics or {})
    enriched.setdefault("intent", retrieval_plan.intent.value)
    enriched.setdefault("candidate_count", 0)
    enriched.setdefault("vector_candidates_count", 0)
    enriched.setdefault("bm25_candidates_count", 0)
    enriched.setdefault("bm25_used", bool(get_settings().enable_bm25))
    enriched.setdefault("bm25_contributed", False)
    enriched.setdefault("top_k_scores", [])
    enriched["query_classification"] = retrieval_plan.query_classification
    enriched["document_target_required"] = retrieval_plan.document_target_required
    enriched["classification_reason"] = retrieval_plan.classification_reason
    enriched["outside_knowledge_blocked_reason"] = retrieval_plan.outside_knowledge_blocked_reason
    return enriched


def collect_message_pair_ids(messages: list[Message], target_message_id: UUID) -> set[UUID]:
    for index, message in enumerate(messages):
        if message.id != target_message_id:
            continue

        delete_ids = {message.id}
        if message.role == MessageRole.user:
            for next_message in messages[index + 1 :]:
                if next_message.role == MessageRole.assistant:
                    delete_ids.add(next_message.id)
                    break
                if next_message.role == MessageRole.user:
                    break
        elif message.role == MessageRole.assistant:
            for previous_message in reversed(messages[:index]):
                if previous_message.role == MessageRole.user:
                    delete_ids.add(previous_message.id)
                    break
                if previous_message.role == MessageRole.assistant:
                    break
        return delete_ids

    return set()


async def load_conversation_messages(
    db: AsyncSession,
    conversation_id: UUID,
) -> list[Message]:
    statement = select(Message).where(Message.conversation_id == conversation_id)
    dialect_name = db.get_bind().dialect.name
    if dialect_name == "postgresql":
        statement = statement.order_by(Message.created_at, text("ctid"))
    else:
        statement = statement.order_by(Message.created_at, Message.id)
    result = await db.execute(statement)
    return result.scalars().all()


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
    message_counts = await load_message_counts(db, [conv.id])
    context = await load_active_document_context(db, conv.user_id, conv.active_document_ids or [])
    return ConversationResponse(
        id=conv.id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        message_count=message_counts.get(conv.id, 0),
        active_documents=serialize_active_documents(context.documents),
    )


async def load_message_counts(
    db: AsyncSession,
    conversation_ids: list[UUID],
) -> dict[UUID, int]:
    if not conversation_ids:
        return {}

    rows = await db.execute(
        select(Message.conversation_id, func.count(Message.id))
        .where(Message.conversation_id.in_(conversation_ids))
        .group_by(Message.conversation_id)
    )
    return {
        conversation_id: int(count)
        for conversation_id, count in rows.all()
    }


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
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Chat endpoint with SSE streaming response, 120s first-token timeout, fast abstention, and citation validation."""
    start_time = time.time()
    settings = get_settings()

    if body.conversation_id:
        conv = await db.get(Conversation, body.conversation_id)
        if conv is None or conv.user_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    else:
        conv = Conversation(user_id=user.id, title=body.query[:100])
        db.add(conv)
        await db.flush()

    replace_messages: list[Message] = []
    if body.replace_message_id:
        if not body.conversation_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "replace_message_id requires a conversation")
        replace_candidates = await load_conversation_messages(db, conv.id)
        replace_ids = collect_message_pair_ids(replace_candidates, body.replace_message_id)
        if not replace_ids:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
        replace_messages = [message for message in replace_candidates if message.id in replace_ids]

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

    user_msg = Message(
        conversation_id=conv.id,
        role=MessageRole.user,
        content=body.query,
        tokens_used=_count_tokens(body.query),
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
                user_message_id=user_msg.id,
                replace_messages=replace_messages,
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
                user_message_id=user_msg.id,
                replace_messages=replace_messages,
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
                user_message_id=user_msg.id,
                replace_messages=replace_messages,
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
                user_message_id=user_msg.id,
                replace_messages=replace_messages,
                active_documents=active_documents_payload,
            ),
            media_type="text/event-stream",
        )

    strict_mode = body.response_mode == ChatResponseMode.strict_documents
    preview_retrieval_plan = build_retrieval_plan(
        body.query,
        len(active_context.indexed_documents),
        has_active_document_scope=bool(active_context.documents),
    )
    if strict_mode and not has_indexed_documents and not has_active_indexed_documents:
        return StreamingResponse(
            stream_static_reply(
                db,
                conv,
                STRICT_NO_DOCUMENTS_RESPONSE,
                start_time,
                user_message_id=user_msg.id,
                replace_messages=replace_messages,
                active_documents=active_documents_payload,
                diagnostics=enrich_chat_diagnostics(
                    {"low_support_reason": STRICT_NO_DOCUMENTS_RESPONSE},
                    preview_retrieval_plan,
                ),
                abstained=True,
            ),
            media_type="text/event-stream",
        )

    ensure_chat_providers_configured()

    history_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conv.id)
        .order_by(Message.created_at, Message.id)
        .limit(10)
    )
    replace_message_ids = {message.id for message in replace_messages}
    history = [
        {"role": m.role.value, "content": m.content}
        for m in history_result.scalars().all()
        if m.id != user_msg.id and m.id not in replace_message_ids
    ]

    llm_provider = get_llm_provider()
    result = build_empty_retrieval_result(body.query)
    retrieval_plan = preview_retrieval_plan
    rewrite_ms = 0

    if has_indexed_documents or has_active_indexed_documents:
        try:
            rewrite_start = time.perf_counter()
            rewriter = QueryRewriter(llm_provider)
            rewritten_query = await rewriter.rewrite(body.query, history)
            rewrite_ms = int((time.perf_counter() - rewrite_start) * 1000)
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
                query_analysis=retrieval_plan,
            )
        except HTTPException:
            raise
        except Exception:
            if strict_mode:
                logger.exception("Chat retrieval failed in strict mode; returning abstention")
            else:
                logger.exception("Chat retrieval degraded; continuing with hybrid general mode")
            result = build_empty_retrieval_result(body.query)

    result.context.diagnostics = enrich_chat_diagnostics(result.context.diagnostics, retrieval_plan)
    result.context.diagnostics["candidate_count"] = result.candidate_count
    result.context.diagnostics["rewrite_ms"] = rewrite_ms

    available_doc_titles = [
        doc.title or doc.file_name for doc in (active_context.indexed_documents or [])
    ]
    abstention_reply = build_low_support_abstention_reply(body.query, available_doc_titles)

    if strict_mode and (result.low_confidence or not has_grounded_context(result)):
        return StreamingResponse(
            stream_static_reply(
                db,
                conv,
                abstention_reply,
                start_time,
                user_message_id=user_msg.id,
                replace_messages=replace_messages,
                active_documents=active_documents_payload,
                diagnostics=result.context.diagnostics,
                abstained=True,
            ),
            media_type="text/event-stream",
        )

    if retrieval_plan.document_target_required and (result.low_confidence or not has_grounded_context(result)):
        return StreamingResponse(
            stream_static_reply(
                db,
                conv,
                abstention_reply,
                start_time,
                user_message_id=user_msg.id,
                replace_messages=replace_messages,
                active_documents=active_documents_payload,
                diagnostics=result.context.diagnostics,
                abstained=True,
            ),
            media_type="text/event-stream",
        )

    allow_general_answer = (
        body.response_mode == ChatResponseMode.hybrid_general
        and not retrieval_plan.document_target_required
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

    messages = build_rag_messages(
        context=prompt_context,
        query=body.query,
        system_prompt=prompt,
        conversation_history=history[-4:] if history else None,
        answer_brief=None if allow_general_answer else result.context.answer_brief,
        intent=retrieval_plan.intent.value,
    )
    prompt_tokens = sum(_count_tokens(m.get("content", "")) for m in messages)

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
                "parent_block_id": s.parent_block_id,
                "heading_level": s.heading_level,
                "ingestion_version": s.ingestion_version,
                "score": round(s.score, 4),
                "excerpt": s.excerpt,
                "selection_reason": s.selection_reason,
                "answer_section": s.answer_section,
                "coverage_labels": s.coverage_labels,
            }
            for s in result.context.sources
        ]
    )

    first_token_timeout = max(int(settings.first_token_timeout_seconds), 120)
    chunk_timeout = max(int(settings.stream_chunk_timeout_seconds), 60)
    warmup_status = getattr(getattr(request, "app", None), "state", None)
    current_warmup = getattr(warmup_status, "model_warmup_status", "ready") if warmup_status else "ready"

    def _finalize_diagnostics(
        content_text: str,
        gen_ms: int,
        total_ms: int,
        removed_citations: list[int] | None = None,
    ) -> dict:
        completion_tokens = _count_tokens(content_text)
        diag = dict(result.context.diagnostics or {})
        retrieval_ms = int(diag.get("retrieval_ms") or 0)
        rerank_ms = int(diag.get("rerank_ms") or 0)
        diag["latency_breakdown_ms"] = {
            "rewrite_ms": rewrite_ms,
            "retrieval_ms": retrieval_ms,
            "rerank_ms": rerank_ms,
            "generation_ms": gen_ms,
            "total_ms": total_ms,
        }
        diag["tokens"] = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }
        diag["abstained"] = False
        diag["used_outside_knowledge"] = allow_general_answer
        diag["response_mode"] = body.response_mode.value
        if removed_citations:
            diag["invalid_citations_removed"] = removed_citations
        return diag

    async def event_stream():
        full_content = ""
        gen_start = time.perf_counter()
        first_chunk_received = False
        try:
            if current_warmup == "warming_up":
                yield f"data: {json.dumps({'type': 'status', 'stage': 'loading_model', 'status': 'loading_model', 'content': 'Đang tải model, vui lòng chờ...'})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'status', 'stage': 'generating', 'status': 'generating', 'content': 'Đang tổng hợp câu trả lời...'})}\n\n"

            stream = llm_provider.generate_stream(messages, generation_config).__aiter__()
            while True:
                try:
                    wait_seconds = first_token_timeout if not first_chunk_received else chunk_timeout
                    chunk = await asyncio.wait_for(stream.__anext__(), timeout=wait_seconds)
                except StopAsyncIteration:
                    break
                first_chunk_received = True
                full_content += chunk
                event = {"type": "chunk", "content": chunk}
                yield f"data: {json.dumps(event)}\n\n"

            cleaned_content, removed_citations = validate_and_clean_citations(
                full_content,
                len(sources_data),
            )
            full_content = cleaned_content

            yield f"data: {json.dumps({'type': 'sources', 'sources': sources_data})}\n\n"

            gen_ms = int((time.perf_counter() - gen_start) * 1000)
            latency_ms = int((time.time() - start_time) * 1000)
            final_diag = _finalize_diagnostics(
                full_content,
                gen_ms,
                latency_ms,
                removed_citations=removed_citations,
            )
            completion_tokens = final_diag["tokens"]["completion_tokens"]

            assistant_msg = Message(
                conversation_id=conv.id,
                role=MessageRole.assistant,
                content=full_content,
                sources=sources_data,
                tokens_used=completion_tokens,
                latency_ms=latency_ms,
            )
            db.add(assistant_msg)
            for message in replace_messages:
                await db.delete(message)
            await db.commit()

            _emit_structured_chat_log(
                conversation_id=conv.id,
                user_id=user.id,
                query=body.query,
                response_mode=body.response_mode.value,
                abstained=False,
                used_outside_knowledge=allow_general_answer,
                diagnostics=final_diag,
            )

            done = {
                "type": "done",
                "user_message_id": str(user_msg.id),
                "message_id": str(assistant_msg.id),
                "conversation_id": str(conv.id),
                "active_documents": active_documents_payload,
                "used_outside_knowledge": allow_general_answer,
                "abstained": False,
                "diagnostics": final_diag,
            }
            yield f"data: {json.dumps(done)}\n\n"

        except Exception:
            logger.exception("Stream error")
            gen_ms = int((time.perf_counter() - gen_start) * 1000)
            if full_content.strip():
                cleaned_content, removed_citations = validate_and_clean_citations(
                    full_content,
                    len(sources_data),
                )
                full_content = cleaned_content
                latency_ms = int((time.time() - start_time) * 1000)
                final_diag = _finalize_diagnostics(
                    full_content,
                    gen_ms,
                    latency_ms,
                    removed_citations=removed_citations,
                )
                assistant_msg = Message(
                    conversation_id=conv.id,
                    role=MessageRole.assistant,
                    content=full_content,
                    sources=sources_data,
                    tokens_used=final_diag["tokens"]["completion_tokens"],
                    latency_ms=latency_ms,
                )
                db.add(assistant_msg)
                for message in replace_messages:
                    await db.delete(message)
                await db.commit()

                _emit_structured_chat_log(
                    conversation_id=conv.id,
                    user_id=user.id,
                    query=body.query,
                    response_mode=body.response_mode.value,
                    abstained=False,
                    used_outside_knowledge=allow_general_answer,
                    diagnostics=final_diag,
                )

                yield f"data: {json.dumps({'type': 'sources', 'sources': sources_data})}\n\n"
                done = {
                    "type": "done",
                    "user_message_id": str(user_msg.id),
                    "message_id": str(assistant_msg.id),
                    "conversation_id": str(conv.id),
                    "active_documents": active_documents_payload,
                    "used_outside_knowledge": allow_general_answer,
                    "abstained": False,
                    "diagnostics": final_diag,
                }
                yield f"data: {json.dumps(done)}\n\n"
                return

            fallback_content = build_grounded_fallback_answer(
                body.query,
                result.context.context_text,
                intent=retrieval_plan.intent.value,
            )
            if fallback_content:
                latency_ms = int((time.time() - start_time) * 1000)
                final_diag = _finalize_diagnostics(fallback_content, gen_ms, latency_ms)
                assistant_msg = Message(
                    conversation_id=conv.id,
                    role=MessageRole.assistant,
                    content=fallback_content,
                    sources=sources_data,
                    tokens_used=final_diag["tokens"]["completion_tokens"],
                    latency_ms=latency_ms,
                )
                db.add(assistant_msg)
                for message in replace_messages:
                    await db.delete(message)
                await db.commit()

                _emit_structured_chat_log(
                    conversation_id=conv.id,
                    user_id=user.id,
                    query=body.query,
                    response_mode=body.response_mode.value,
                    abstained=False,
                    used_outside_knowledge=allow_general_answer,
                    diagnostics=final_diag,
                )

                yield f"data: {json.dumps({'type': 'chunk', 'content': fallback_content})}\n\n"
                yield f"data: {json.dumps({'type': 'sources', 'sources': sources_data})}\n\n"
                done = {
                    "type": "done",
                    "user_message_id": str(user_msg.id),
                    "message_id": str(assistant_msg.id),
                    "conversation_id": str(conv.id),
                    "active_documents": active_documents_payload,
                    "used_outside_knowledge": allow_general_answer,
                    "abstained": False,
                    "diagnostics": final_diag,
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

    message_counts = await load_message_counts(db, [conversation.id for conversation in conversations])
    items = []
    for c in conversations:
        items.append(
            ConversationResponse(
                id=c.id,
                title=c.title,
                created_at=c.created_at,
                updated_at=c.updated_at,
                message_count=message_counts.get(c.id, 0),
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
    """Update a conversation title and/or active document context."""
    conv = await db.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")

    if body.title is not None:
        normalized_title = body.title.strip()
        conv.title = normalized_title or None

    if body.document_ids is not None:
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

    return await load_conversation_messages(db, conversation_id)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Permanently delete an owned conversation and all related messages."""
    conv = await db.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")

    await db.delete(conv)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/conversations/{conversation_id}/messages/{message_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_conversation_message_pair(
    conversation_id: UUID,
    message_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Delete one logical chat exchange, keeping conversation history coherent."""
    conv = await db.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")

    messages = await load_conversation_messages(db, conversation_id)
    delete_ids = collect_message_pair_ids(messages, message_id)
    if not delete_ids:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")

    for message in messages:
        if message.id in delete_ids:
            await db.delete(message)

    await db.flush()
    conv.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
