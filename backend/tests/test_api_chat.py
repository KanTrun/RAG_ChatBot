import json
import asyncio
from pathlib import Path
import uuid

import pytest
from sqlalchemy import select

from app.models.conversation import Conversation
from app.models.document import Document, DocumentStatus
from app.models.message import Message, MessageRole
from app.services.context_assembler import AssembledContext, SourceReference
from app.services.retrieval_service import RetrievalResult


async def create_indexed_document(db_session, test_user, *, title: str, file_name: str) -> Document:
    upload_path = Path(__file__).parent / "tmp-uploads" / f"{uuid.uuid4()}-{file_name}"
    upload_path.parent.mkdir(parents=True, exist_ok=True)
    upload_path.write_text(f"Contents for {title}", encoding="utf-8")
    document = Document(
        title=title,
        file_name=file_name,
        file_path=str(upload_path),
        file_type="txt",
        file_size=128,
        content_hash=f"hash-{file_name}",
        status=DocumentStatus.indexed,
        owner_id=test_user.id,
        total_chunks=2,
    )
    db_session.add(document)
    await db_session.commit()
    await db_session.refresh(document)
    return document


@pytest.mark.anyio
async def test_list_conversations_returns_owned_conversations(
    async_client,
    auth_headers,
    db_session,
    test_user,
):
    conversation = Conversation(user_id=test_user.id, title="AlphaProject")
    db_session.add(conversation)
    await db_session.flush()
    db_session.add_all(
        [
            Message(conversation_id=conversation.id, role=MessageRole.user, content="Question"),
            Message(conversation_id=conversation.id, role=MessageRole.assistant, content="Answer"),
        ]
    )
    await db_session.commit()

    response = await async_client.get("/api/v1/conversations", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "AlphaProject"
    assert data["items"][0]["message_count"] == 2


@pytest.mark.anyio
async def test_get_conversation_messages_returns_ordered_messages(
    async_client,
    auth_headers,
    db_session,
    test_user,
):
    conversation = Conversation(user_id=test_user.id, title="Messages")
    db_session.add(conversation)
    await db_session.flush()
    db_session.add_all(
        [
            Message(conversation_id=conversation.id, role=MessageRole.user, content="Question"),
            Message(conversation_id=conversation.id, role=MessageRole.assistant, content="Answer"),
        ]
    )
    await db_session.commit()

    response = await async_client.get(
        f"/api/v1/conversations/{conversation.id}/messages",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert [item["content"] for item in response.json()] == ["Question", "Answer"]


@pytest.mark.anyio
async def test_feedback_upserts_for_owned_message(
    async_client,
    auth_headers,
    db_session,
    test_user,
):
    conversation = Conversation(user_id=test_user.id, title="Feedback")
    db_session.add(conversation)
    await db_session.flush()
    message = Message(
        conversation_id=conversation.id,
        role=MessageRole.assistant,
        content="Grounded answer [1]",
    )
    db_session.add(message)
    await db_session.commit()

    first = await async_client.post(
        f"/api/v1/messages/{message.id}/feedback",
        headers=auth_headers,
        json={"score": 1, "comment": "useful"},
    )
    second = await async_client.post(
        f"/api/v1/messages/{message.id}/feedback",
        headers=auth_headers,
        json={"score": -1, "comment": "needs sources"},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["feedback_id"] == second.json()["feedback_id"]


@pytest.mark.anyio
async def test_chat_endpoint_requires_auth(async_client):
    response = await async_client.post("/api/v1/chat", json={"query": "hello"})

    assert response.status_code == 401


@pytest.mark.anyio
async def test_chat_endpoint_reports_missing_provider_config(async_client, auth_headers):
    response = await async_client.post(
        "/api/v1/chat",
        headers=auth_headers,
        json={"query": "What is AlphaProject?", "response_mode": "hybrid_general"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Chat provider is not configured. Missing: OPENAI_API_KEY"


@pytest.mark.anyio
async def test_chat_endpoint_handles_greeting_without_provider(async_client, auth_headers):
    response = await async_client.post(
        "/api/v1/chat",
        headers=auth_headers,
        json={"query": "Hi"},
    )

    assert response.status_code == 200
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]

    assert events[0]["type"] == "chunk"
    assert "ready to help with questions about your documents" in events[0]["content"]
    assert events[-1]["type"] == "done"
    assert events[-1]["conversation_id"]


@pytest.mark.anyio
async def test_chat_endpoint_reports_documents_still_indexing_before_provider_check(
    async_client,
    auth_headers,
    db_session,
    test_user,
):
    upload_path = Path(__file__).parent / "tmp-uploads" / f"{test_user.id}-pending-chat.txt"
    upload_path.parent.mkdir(parents=True, exist_ok=True)
    upload_path.write_text("Pending document", encoding="utf-8")
    db_session.add(
        Document(
            title="Pending chat doc",
            file_name="pending-chat.txt",
            file_path=str(upload_path),
            file_type="txt",
            file_size=16,
            content_hash="pending-chat-hash",
            status=DocumentStatus.pending,
            owner_id=test_user.id,
        )
    )
    await db_session.commit()

    response = await async_client.post(
        "/api/v1/chat",
        headers=auth_headers,
        json={"query": "Tell me about this file"},
    )

    assert response.status_code == 200
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert events[0]["type"] == "chunk"
    assert "still indexing" in events[0]["content"]
    assert events[-1]["type"] == "done"


@pytest.mark.anyio
async def test_chat_endpoint_falls_back_to_general_chat_when_retrieval_fails(
    async_client,
    auth_headers,
    monkeypatch,
):
    from app.api.v1 import chat_router

    class GeneralProvider:
        async def generate(self, *_args, **_kwargs):
            return "unused"

        async def generate_stream(self, *_args, **_kwargs):
            yield "Machine learning is a method where models learn patterns from data."

    async def fail_retrieve(*args, **kwargs):
        raise RuntimeError("embedding backend offline")

    monkeypatch.setattr(chat_router.RetrievalService, "retrieve", fail_retrieve)
    monkeypatch.setattr(chat_router, "ensure_chat_providers_configured", lambda: None)
    monkeypatch.setattr(chat_router, "get_llm_provider", lambda: GeneralProvider())

    response = await async_client.post(
        "/api/v1/chat",
        headers=auth_headers,
        json={"query": "What is machine learning?", "response_mode": "hybrid_general"},
    )

    assert response.status_code == 200
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert any(
        event["type"] == "chunk" and "learn patterns from data" in event["content"]
        for event in events
    )
    assert events[-1]["type"] == "done"


@pytest.mark.anyio
async def test_chat_endpoint_abstains_in_strict_mode_when_support_is_weak(
    async_client,
    auth_headers,
    indexed_document,
    monkeypatch,
):
    from app.api.v1 import chat_router

    class StreamingProvider:
        async def generate(self, *_args, **_kwargs):
            return "unused"

        async def generate_stream(self, *_args, **_kwargs):
            yield "This should not be streamed"

    async def fake_retrieve(*args, **kwargs):
        return RetrievalResult(
            context=AssembledContext(context_text="", sources=[], total_tokens=0),
            query_used="weak query",
            low_confidence=True,
            candidate_count=0,
        )

    monkeypatch.setattr(chat_router, "ensure_chat_providers_configured", lambda: None)
    monkeypatch.setattr(chat_router, "get_llm_provider", lambda: StreamingProvider())
    monkeypatch.setattr(chat_router.RetrievalService, "retrieve", fake_retrieve)

    response = await async_client.post(
        "/api/v1/chat",
        headers=auth_headers,
        json={"query": "Tell me the answer", "document_ids": [str(indexed_document.id)]},
    )

    assert response.status_code == 200
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert events[0]["type"] == "chunk"
    assert "could not find enough support" in events[0]["content"]
    assert events[-1]["type"] == "done"


@pytest.mark.anyio
async def test_chat_endpoint_blocks_hybrid_fallback_for_document_targeted_queries(
    async_client,
    auth_headers,
    indexed_document,
    monkeypatch,
):
    from app.api.v1 import chat_router

    class StreamingProvider:
        async def generate(self, *_args, **_kwargs):
            return "unused"

        async def generate_stream(self, *_args, **_kwargs):
            yield "This should never stream"

    async def fake_retrieve(*args, **kwargs):
        return RetrievalResult(
            context=AssembledContext(
                context_text="",
                sources=[],
                total_tokens=0,
                diagnostics={"low_support_reason": "missing grounded support"},
            ),
            query_used="What skills are listed in this CV?",
            low_confidence=True,
            candidate_count=0,
        )

    monkeypatch.setattr(chat_router, "ensure_chat_providers_configured", lambda: None)
    monkeypatch.setattr(chat_router, "get_llm_provider", lambda: StreamingProvider())
    monkeypatch.setattr(chat_router.RetrievalService, "retrieve", fake_retrieve)

    response = await async_client.post(
        "/api/v1/chat",
        headers=auth_headers,
        json={
            "query": "What skills are listed in this CV?",
            "response_mode": "hybrid_general",
            "document_ids": [str(indexed_document.id)],
        },
    )

    assert response.status_code == 200
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert events[0]["type"] == "chunk"
    assert "could not find enough support" in events[0]["content"]
    assert not any("This should never stream" in event.get("content", "") for event in events)


@pytest.mark.anyio
async def test_chat_endpoint_allows_hybrid_general_fallback_for_general_questions_even_with_active_docs(
    async_client,
    auth_headers,
    indexed_document,
    monkeypatch,
):
    from app.api.v1 import chat_router

    class StreamingProvider:
        async def generate(self, *_args, **_kwargs):
            return "unused"

        async def generate_stream(self, *_args, **_kwargs):
            yield "Caching stores data so repeated requests do less work."

    async def fake_retrieve(*args, **kwargs):
        return RetrievalResult(
            context=AssembledContext(
                context_text="",
                sources=[],
                total_tokens=0,
                diagnostics={"low_support_reason": "no grounded support"},
            ),
            query_used="How does caching work?",
            low_confidence=True,
            candidate_count=0,
        )

    monkeypatch.setattr(chat_router, "ensure_chat_providers_configured", lambda: None)
    monkeypatch.setattr(chat_router, "get_llm_provider", lambda: StreamingProvider())
    monkeypatch.setattr(chat_router.RetrievalService, "retrieve", fake_retrieve)

    response = await async_client.post(
        "/api/v1/chat",
        headers=auth_headers,
        json={
            "query": "How does caching work?",
            "response_mode": "hybrid_general",
            "document_ids": [str(indexed_document.id)],
        },
    )

    assert response.status_code == 200
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert any(
        event["type"] == "chunk" and "repeated requests" in event["content"]
        for event in events
    )
    assert events[-1]["type"] == "done"


@pytest.mark.anyio
async def test_chat_endpoint_falls_back_to_grounded_context_when_stream_fails(
    async_client,
    auth_headers,
    indexed_document,
    monkeypatch,
):
    from app.api.v1 import chat_router

    class FailingProvider:
        async def generate(self, *_args, **_kwargs):
            return "unused"

        async def generate_stream(self, *_args, **_kwargs):
            raise RuntimeError("llm unavailable")
            yield ""

    async def fake_retrieve(*args, **kwargs):
        return RetrievalResult(
            context=AssembledContext(
                context_text=(
                    "[1] Source: sample-article\n"
                    "Hybrid search uses vector similarity and BM25 keyword search.\n"
                ),
                sources=[
                    SourceReference(
                        citation_number=1,
                        document_title="sample-article",
                        file_name="sample-article.txt",
                        page_number=1,
                        section=None,
                        chunk_id="chunk-1",
                        score=1.0,
                    )
                ],
                total_tokens=20,
            ),
            query_used="hybrid search methods",
            low_confidence=False,
            candidate_count=1,
        )

    monkeypatch.setattr(chat_router.RetrievalService, "retrieve", fake_retrieve)
    monkeypatch.setattr(chat_router, "ensure_chat_providers_configured", lambda: None)
    monkeypatch.setattr(chat_router, "get_llm_provider", lambda: FailingProvider())

    response = await async_client.post(
        "/api/v1/chat",
        headers=auth_headers,
        json={"query": "What search methods are used?"},
    )

    assert response.status_code == 200
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert any(
        event["type"] == "chunk" and "According to the retrieved document context" in event["content"]
        for event in events
    )
    assert any(event["type"] == "sources" for event in events)
    assert events[-1]["type"] == "done"


@pytest.mark.anyio
async def test_chat_endpoint_keeps_partial_stream_without_emitting_second_answer(
    async_client,
    auth_headers,
    indexed_document,
    monkeypatch,
):
    from app.api.v1 import chat_router

    class PartiallyFailingProvider:
        async def generate(self, *_args, **_kwargs):
            return "unused"

        async def generate_stream(self, *_args, **_kwargs):
            yield "Hybrid search combines "
            raise RuntimeError("llm stream interrupted")

    async def fake_retrieve(*args, **kwargs):
        return RetrievalResult(
            context=AssembledContext(
                context_text=(
                    "[1] Source: sample-article\n"
                    "Hybrid search uses vector similarity and BM25 keyword search.\n"
                ),
                sources=[
                    SourceReference(
                        citation_number=1,
                        document_title="sample-article",
                        file_name="sample-article.txt",
                        page_number=1,
                        section=None,
                        chunk_id="chunk-1",
                        score=1.0,
                    )
                ],
                total_tokens=20,
            ),
            query_used="hybrid search methods",
            low_confidence=False,
            candidate_count=1,
        )

    monkeypatch.setattr(chat_router.RetrievalService, "retrieve", fake_retrieve)
    monkeypatch.setattr(chat_router, "ensure_chat_providers_configured", lambda: None)
    monkeypatch.setattr(chat_router, "get_llm_provider", lambda: PartiallyFailingProvider())

    response = await async_client.post(
        "/api/v1/chat",
        headers=auth_headers,
        json={"query": "What search methods are used?"},
    )

    assert response.status_code == 200
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    chunk_events = [event for event in events if event["type"] == "chunk"]
    assert chunk_events == [{"type": "chunk", "content": "Hybrid search combines "}]
    assert not any(
        event["type"] == "chunk" and "According to the retrieved document context" in event["content"]
        for event in events
    )
    assert any(event["type"] == "sources" for event in events)
    assert events[-1]["type"] == "done"


@pytest.mark.anyio
async def test_chat_endpoint_falls_back_when_stream_times_out_before_first_chunk(
    async_client,
    auth_headers,
    indexed_document,
    monkeypatch,
):
    from app.api.v1 import chat_router

    class HangingProvider:
        async def generate(self, *_args, **_kwargs):
            return "unused"

        async def generate_stream(self, *_args, **_kwargs):
            yield ""

    async def fake_retrieve(*args, **kwargs):
        return RetrievalResult(
            context=AssembledContext(
                context_text=(
                    "[1] Source: sample-article\n"
                    "Hybrid search uses vector similarity and BM25 keyword search.\n"
                ),
                sources=[
                    SourceReference(
                        citation_number=1,
                        document_title="sample-article",
                        file_name="sample-article.txt",
                        page_number=1,
                        section=None,
                        chunk_id="chunk-1",
                        score=1.0,
                    )
                ],
                total_tokens=20,
            ),
            query_used="hybrid search methods",
            low_confidence=False,
            candidate_count=1,
        )

    async def fail_wait_for(_awaitable, timeout):
        raise asyncio.TimeoutError()

    monkeypatch.setattr(chat_router.RetrievalService, "retrieve", fake_retrieve)
    monkeypatch.setattr(chat_router, "ensure_chat_providers_configured", lambda: None)
    monkeypatch.setattr(chat_router, "get_llm_provider", lambda: HangingProvider())
    monkeypatch.setattr(chat_router.asyncio, "wait_for", fail_wait_for)

    response = await async_client.post(
        "/api/v1/chat",
        headers=auth_headers,
        json={"query": "What search methods are used?"},
    )

    assert response.status_code == 200
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert any(
        event["type"] == "chunk" and "According to the retrieved document context" in event["content"]
        for event in events
    )
    assert any(event["type"] == "sources" for event in events)
    assert events[-1]["type"] == "done"


@pytest.mark.anyio
async def test_chat_endpoint_uses_requested_active_documents_and_persists_them(
    async_client,
    auth_headers,
    db_session,
    test_user,
    indexed_document,
    monkeypatch,
):
    from app.api.v1 import chat_router

    captured_doc_filters: list[list[str] | None] = []

    class StreamingProvider:
        async def generate(self, *_args, **_kwargs):
            return "unused"

        async def generate_stream(self, *_args, **_kwargs):
            yield "Grounded answer"

    async def fake_retrieve(self, query, user_id, user_role_ids, filters=None, **_kwargs):
        captured_doc_filters.append(
            [str(document_id) for document_id in (filters.document_ids if filters else [])]
        )
        return RetrievalResult(
            context=AssembledContext(
                context_text="[1] Source: sample-article\nAlphaProject uses hybrid retrieval.\n",
                sources=[
                    SourceReference(
                        citation_number=1,
                        document_title="sample-article",
                        file_name="sample-article.txt",
                        page_number=1,
                        section=None,
                        chunk_id="chunk-1",
                        score=0.99,
                    )
                ],
                total_tokens=16,
            ),
            query_used=query,
            low_confidence=False,
            candidate_count=1,
        )

    monkeypatch.setattr(chat_router, "ensure_chat_providers_configured", lambda: None)
    monkeypatch.setattr(chat_router, "get_llm_provider", lambda: StreamingProvider())
    monkeypatch.setattr(chat_router.RetrievalService, "retrieve", fake_retrieve)

    first_response = await async_client.post(
        "/api/v1/chat",
        headers=auth_headers,
        json={"query": "What does this file cover?", "document_ids": [str(indexed_document.id)]},
    )

    assert first_response.status_code == 200
    first_events = [
        json.loads(line.removeprefix("data: "))
        for line in first_response.text.splitlines()
        if line.startswith("data: ")
    ]
    first_done = first_events[-1]
    assert first_done["conversation_id"]
    assert first_done["active_documents"][0]["id"] == str(indexed_document.id)

    second_response = await async_client.post(
        "/api/v1/chat",
        headers=auth_headers,
        json={"query": "Tóm tắt nó", "conversation_id": first_done["conversation_id"]},
    )

    assert second_response.status_code == 200
    assert captured_doc_filters == [
        [str(indexed_document.id)],
        [str(indexed_document.id)],
    ]

    conversation = await db_session.get(Conversation, uuid.UUID(first_done["conversation_id"]))
    assert conversation is not None
    assert conversation.active_document_ids == [indexed_document.id]


@pytest.mark.anyio
async def test_conversation_patch_updates_multiple_active_documents(
    async_client,
    auth_headers,
    db_session,
    test_user,
    indexed_document,
):
    second_document = await create_indexed_document(
        db_session,
        test_user,
        title="Second Guide",
        file_name="second-guide.txt",
    )
    conversation = Conversation(user_id=test_user.id, title="Scoped chat")
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)

    response = await async_client.patch(
        f"/api/v1/conversations/{conversation.id}",
        headers=auth_headers,
        json={"document_ids": [str(indexed_document.id), str(second_document.id)]},
    )

    assert response.status_code == 200
    data = response.json()
    assert [document["id"] for document in data["active_documents"]] == [
        str(indexed_document.id),
        str(second_document.id),
    ]

    await db_session.refresh(conversation)
    assert conversation.active_document_ids == [indexed_document.id, second_document.id]


@pytest.mark.anyio
async def test_conversation_patch_updates_title_without_resetting_active_documents(
    async_client,
    auth_headers,
    db_session,
    test_user,
    indexed_document,
):
    conversation = Conversation(
        user_id=test_user.id,
        title="Scoped chat",
        active_document_ids=[indexed_document.id],
    )
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)

    response = await async_client.patch(
        f"/api/v1/conversations/{conversation.id}",
        headers=auth_headers,
        json={"title": "Renamed chat"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Renamed chat"
    assert [document["id"] for document in data["active_documents"]] == [str(indexed_document.id)]

    await db_session.refresh(conversation)
    assert conversation.title == "Renamed chat"
    assert conversation.active_document_ids == [indexed_document.id]


@pytest.mark.anyio
async def test_chat_endpoint_reports_selected_pending_document_status(
    async_client,
    auth_headers,
    db_session,
    test_user,
):
    upload_path = Path(__file__).parent / "tmp-uploads" / f"{uuid.uuid4()}-pending-selected.txt"
    upload_path.parent.mkdir(parents=True, exist_ok=True)
    upload_path.write_text("Pending selected document", encoding="utf-8")
    pending_document = Document(
        title="Pending Selected Doc",
        file_name="pending-selected.txt",
        file_path=str(upload_path),
        file_type="txt",
        file_size=24,
        content_hash="pending-selected-hash",
        status=DocumentStatus.pending,
        owner_id=test_user.id,
    )
    db_session.add(pending_document)
    await db_session.commit()
    await db_session.refresh(pending_document)

    response = await async_client.post(
        "/api/v1/chat",
        headers=auth_headers,
        json={"query": "Summarize it", "document_ids": [str(pending_document.id)]},
    )

    assert response.status_code == 200
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert "still indexing" in events[0]["content"]
    assert events[-1]["active_documents"][0]["id"] == str(pending_document.id)


@pytest.mark.anyio
async def test_chat_endpoint_disables_ordered_document_scan_for_summary_requests(
    async_client,
    auth_headers,
    indexed_document,
    monkeypatch,
):
    from app.api.v1 import chat_router

    captured_kwargs: list[dict] = []

    class StreamingProvider:
        async def generate(self, *_args, **_kwargs):
            return "unused"

        async def generate_stream(self, *_args, **_kwargs):
            yield "Summary answer [1]"

    async def fake_retrieve(self, query, user_id, user_role_ids, filters=None, **kwargs):
        captured_kwargs.append(kwargs)
        return RetrievalResult(
            context=AssembledContext(
                context_text="[1] Source: sample-article\nAlphaProject summary.\n",
                sources=[
                    SourceReference(
                        citation_number=1,
                        document_title="sample-article",
                        file_name="sample-article.txt",
                        page_number=1,
                        section="Overview",
                        chunk_id="chunk-1",
                        score=0.99,
                    )
                ],
                total_tokens=12,
            ),
            query_used=query,
            low_confidence=False,
            candidate_count=1,
        )

    monkeypatch.setattr(chat_router, "ensure_chat_providers_configured", lambda: None)
    monkeypatch.setattr(chat_router, "get_llm_provider", lambda: StreamingProvider())
    monkeypatch.setattr(chat_router.RetrievalService, "retrieve", fake_retrieve)

    response = await async_client.post(
        "/api/v1/chat",
        headers=auth_headers,
        json={"query": "Summarize this document", "document_ids": [str(indexed_document.id)]},
    )

    assert response.status_code == 200
    assert captured_kwargs
    assert captured_kwargs[0]["ordered_document_scan"] is False
    assert captured_kwargs[0]["prefer_document_order"] is True


@pytest.mark.anyio
async def test_chat_endpoint_uses_original_query_as_primary_and_rewrite_as_auxiliary_signal(
    async_client,
    auth_headers,
    indexed_document,
    monkeypatch,
):
    from app.api.v1 import chat_router

    captured_call: dict = {}

    class StreamingProvider:
        async def generate(self, *_args, **_kwargs):
            return "unused"

        async def generate_stream(self, *_args, **_kwargs):
            yield "Detailed grounded answer [1][2]"

    async def fake_rewrite(self, query, conversation_history=None):
        return "standalone rewritten retrieval question"

    async def fake_retrieve(self, query, user_id, user_role_ids, filters=None, **kwargs):
        captured_call["query"] = query
        captured_call["alternate_queries"] = kwargs.get("alternate_queries")
        return RetrievalResult(
            context=AssembledContext(
                context_text="[1] Source: sample-article\nAlphaProject retrieval.\n",
                sources=[
                    SourceReference(
                        citation_number=1,
                        document_title="sample-article",
                        file_name="sample-article.txt",
                        page_number=1,
                        section="Overview",
                        chunk_id="chunk-1",
                        score=0.99,
                        excerpt="AlphaProject retrieval overview.",
                    )
                ],
                total_tokens=18,
            ),
            query_used=query,
            low_confidence=False,
            candidate_count=1,
        )

    monkeypatch.setattr(chat_router, "ensure_chat_providers_configured", lambda: None)
    monkeypatch.setattr(chat_router, "get_llm_provider", lambda: StreamingProvider())
    monkeypatch.setattr(chat_router.QueryRewriter, "rewrite", fake_rewrite)
    monkeypatch.setattr(chat_router.RetrievalService, "retrieve", fake_retrieve)

    response = await async_client.post(
        "/api/v1/chat",
        headers=auth_headers,
        json={"query": "Nó hoạt động như thế nào?", "document_ids": [str(indexed_document.id)]},
    )

    assert response.status_code == 200
    assert captured_call["query"] == "Nó hoạt động như thế nào?"
    assert captured_call["alternate_queries"] == ["standalone rewritten retrieval question"]


@pytest.mark.anyio
async def test_chat_sources_event_includes_source_excerpt(
    async_client,
    auth_headers,
    indexed_document,
    monkeypatch,
):
    from app.api.v1 import chat_router

    class StreamingProvider:
        async def generate(self, *_args, **_kwargs):
            return "unused"

        async def generate_stream(self, *_args, **_kwargs):
            yield "Grounded answer with evidence [1]"

    async def fake_retrieve(self, query, user_id, user_role_ids, filters=None, **kwargs):
        return RetrievalResult(
            context=AssembledContext(
                context_text="[1] Source: sample-article\nAlphaProject uses hybrid retrieval.\n",
                sources=[
                    SourceReference(
                        citation_number=1,
                        document_title="sample-article",
                        file_name="sample-article.txt",
                        page_number=1,
                        section="Overview",
                        section_path="sample-article > Overview",
                        block_type="method",
                        chunk_id="chunk-1",
                        score=0.99,
                        excerpt="AlphaProject uses hybrid retrieval.",
                        parent_block_id="parent-1",
                        heading_level=2,
                        ingestion_version="document-first-v2",
                        selection_reason="method evidence from sample-article > Overview",
                        answer_section="method",
                    )
                ],
                total_tokens=16,
                diagnostics={"intent": "factual", "low_support_reason": None},
            ),
            query_used=query,
            low_confidence=False,
            candidate_count=1,
        )

    monkeypatch.setattr(chat_router, "ensure_chat_providers_configured", lambda: None)
    monkeypatch.setattr(chat_router, "get_llm_provider", lambda: StreamingProvider())
    monkeypatch.setattr(chat_router.RetrievalService, "retrieve", fake_retrieve)

    response = await async_client.post(
        "/api/v1/chat",
        headers=auth_headers,
        json={"query": "Explain the retrieval method", "document_ids": [str(indexed_document.id)]},
    )

    assert response.status_code == 200
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    sources_event = next(event for event in events if event["type"] == "sources")
    assert sources_event["sources"][0]["excerpt"] == "AlphaProject uses hybrid retrieval."
    assert sources_event["sources"][0]["section_path"] == "sample-article > Overview"
    assert sources_event["sources"][0]["block_type"] == "method"
    assert sources_event["sources"][0]["parent_block_id"] == "parent-1"
    assert sources_event["sources"][0]["heading_level"] == 2
    assert sources_event["sources"][0]["ingestion_version"] == "document-first-v2"


@pytest.mark.anyio
async def test_chat_done_event_includes_diagnostics_for_admin_debug_requests(
    async_client,
    admin_headers,
    test_admin,
    db_session,
    monkeypatch,
):
    from app.api.v1 import chat_router

    upload_path = Path(__file__).parent / "tmp-uploads" / f"{uuid.uuid4()}-admin-debug.txt"
    upload_path.parent.mkdir(parents=True, exist_ok=True)
    upload_path.write_text("Admin debug document", encoding="utf-8")
    admin_document = Document(
        title="Admin Debug Doc",
        file_name="admin-debug.txt",
        file_path=str(upload_path),
        file_type="txt",
        file_size=32,
        content_hash="admin-debug-hash",
        status=DocumentStatus.indexed,
        owner_id=test_admin.id,
        total_chunks=1,
    )
    db_session.add(admin_document)
    await db_session.commit()
    await db_session.refresh(admin_document)

    class StreamingProvider:
        async def generate(self, *_args, **_kwargs):
            return "unused"

        async def generate_stream(self, *_args, **_kwargs):
            yield "Grounded answer with evidence [1]"

    async def fake_retrieve(self, query, user_id, user_role_ids, filters=None, **kwargs):
        return RetrievalResult(
            context=AssembledContext(
                context_text="[1] Source: sample-article\nAlphaProject uses hybrid retrieval.\n",
                sources=[
                    SourceReference(
                        citation_number=1,
                        document_title="sample-article",
                        file_name="sample-article.txt",
                        page_number=1,
                        section="Overview",
                        chunk_id="chunk-1",
                        score=0.99,
                    )
                ],
                total_tokens=16,
                diagnostics={
                    "intent": "factual",
                    "selected_query_variants": ["primary", "factual_method"],
                    "low_support_reason": None,
                },
            ),
            query_used=query,
            low_confidence=False,
            candidate_count=1,
        )

    monkeypatch.setattr(chat_router, "ensure_chat_providers_configured", lambda: None)
    monkeypatch.setattr(chat_router, "get_llm_provider", lambda: StreamingProvider())
    monkeypatch.setattr(chat_router.RetrievalService, "retrieve", fake_retrieve)

    response = await async_client.post(
        "/api/v1/chat",
        headers=admin_headers,
        json={
            "query": "Explain the retrieval method",
            "response_mode": "hybrid_general",
            "include_diagnostics": True,
            "document_ids": [str(admin_document.id)],
        },
    )

    assert response.status_code == 200
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    done_event = next(event for event in events if event["type"] == "done")
    assert done_event["diagnostics"]["intent"] == "factual"
    assert done_event["diagnostics"]["selected_query_variants"] == ["primary", "factual_method"]
    assert done_event["diagnostics"]["document_target_required"] is True
    assert done_event["diagnostics"]["query_classification"] == "document-targeted"
    assert done_event["diagnostics"]["outside_knowledge_blocked_reason"] is not None


@pytest.mark.anyio
async def test_delete_conversation_hard_deletes_messages(
    async_client,
    auth_headers,
    db_session,
    test_user,
):
    conversation = Conversation(user_id=test_user.id, title="Delete me")
    db_session.add(conversation)
    await db_session.flush()
    db_session.add_all(
        [
            Message(conversation_id=conversation.id, role=MessageRole.user, content="Question"),
            Message(conversation_id=conversation.id, role=MessageRole.assistant, content="Answer"),
        ]
    )
    await db_session.commit()

    response = await async_client.delete(
        f"/api/v1/conversations/{conversation.id}",
        headers=auth_headers,
    )

    assert response.status_code == 204
    remaining_conversation = await db_session.execute(
        select(Conversation).where(Conversation.id == conversation.id)
    )
    assert remaining_conversation.scalar_one_or_none() is None
    remaining = await db_session.execute(
        select(Message).where(Message.conversation_id == conversation.id)
    )
    assert remaining.scalars().all() == []


@pytest.mark.anyio
async def test_delete_conversation_message_pair_keeps_history_coherent(
    async_client,
    auth_headers,
    db_session,
    test_user,
):
    conversation = Conversation(user_id=test_user.id, title="Delete pair")
    db_session.add(conversation)
    await db_session.flush()
    first_user = Message(conversation_id=conversation.id, role=MessageRole.user, content="Question one")
    first_assistant = Message(
        conversation_id=conversation.id,
        role=MessageRole.assistant,
        content="Answer one",
    )
    second_user = Message(conversation_id=conversation.id, role=MessageRole.user, content="Question two")
    second_assistant = Message(
        conversation_id=conversation.id,
        role=MessageRole.assistant,
        content="Answer two",
    )
    db_session.add_all([first_user, first_assistant, second_user, second_assistant])
    await db_session.commit()

    first_response = await async_client.delete(
        f"/api/v1/conversations/{conversation.id}/messages/{first_user.id}",
        headers=auth_headers,
    )

    assert first_response.status_code == 204
    first_remaining = await async_client.get(
        f"/api/v1/conversations/{conversation.id}/messages",
        headers=auth_headers,
    )
    assert [item["content"] for item in first_remaining.json()] == ["Question two", "Answer two"]

    second_response = await async_client.delete(
        f"/api/v1/conversations/{conversation.id}/messages/{second_assistant.id}",
        headers=auth_headers,
    )

    assert second_response.status_code == 204
    second_remaining = await async_client.get(
        f"/api/v1/conversations/{conversation.id}/messages",
        headers=auth_headers,
    )
    assert second_remaining.json() == []


@pytest.mark.anyio
async def test_chat_endpoint_replaces_an_existing_exchange_after_successful_resend(
    async_client,
    auth_headers,
    db_session,
    test_user,
    monkeypatch,
):
    from app.api.v1 import chat_router

    conversation = Conversation(user_id=test_user.id, title="Replace exchange")
    db_session.add(conversation)
    await db_session.flush()
    original_user = Message(
        conversation_id=conversation.id,
        role=MessageRole.user,
        content="Original question",
    )
    original_assistant = Message(
        conversation_id=conversation.id,
        role=MessageRole.assistant,
        content="Original answer",
    )
    db_session.add_all([original_user, original_assistant])
    await db_session.commit()

    class StreamingProvider:
        async def generate(self, *_args, **_kwargs):
            return "unused"

        async def generate_stream(self, *_args, **_kwargs):
            yield "Replacement answer"

    monkeypatch.setattr(chat_router, "ensure_chat_providers_configured", lambda: None)
    monkeypatch.setattr(chat_router, "get_llm_provider", lambda: StreamingProvider())

    response = await async_client.post(
        "/api/v1/chat",
        headers=auth_headers,
        json={
            "query": "Updated question",
            "conversation_id": str(conversation.id),
            "replace_message_id": str(original_assistant.id),
            "response_mode": "hybrid_general",
        },
    )

    assert response.status_code == 200
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    done_event = next(event for event in events if event["type"] == "done")
    assert done_event["user_message_id"]
    assert done_event["message_id"]

    remaining = await async_client.get(
        f"/api/v1/conversations/{conversation.id}/messages",
        headers=auth_headers,
    )
    contents = [item["content"] for item in remaining.json()]
    assert contents == ["Updated question", "Replacement answer"]


def test_chat_provider_config_accepts_ollama_without_openai_key(monkeypatch):
    import app.config as app_config
    from app.api.v1.chat_router import ensure_chat_providers_configured

    monkeypatch.setenv("EMBEDDING_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama:11434")
    monkeypatch.setenv("OLLAMA_EMBEDDING_MODEL", "mxbai-embed-large")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    app_config._settings = None

    ensure_chat_providers_configured()


def test_chat_provider_config_accepts_gemini_with_local_env(monkeypatch):
    import app.config as app_config
    from app.api.v1.chat_router import ensure_chat_providers_configured

    monkeypatch.setenv("EMBEDDING_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama:11434")
    monkeypatch.setenv("OLLAMA_EMBEDDING_MODEL", "mxbai-embed-large")
    monkeypatch.setenv("GEMINI_API_KEY", "local-test-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-pro")
    app_config._settings = None

    ensure_chat_providers_configured()


def test_gemini_provider_uses_gemini_model_not_default_llm_model(monkeypatch):
    import app.config as app_config
    from app.services.llm.provider_factory import get_llm_provider

    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_MODEL", "qwen2.5:7b")
    monkeypatch.setenv("GEMINI_API_KEY", "local-test-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-pro")
    app_config._settings = None
    get_llm_provider.cache_clear()

    provider = get_llm_provider(provider="gemini")

    assert getattr(provider, "default_model") == "gemini-2.5-pro"
    get_llm_provider.cache_clear()


@pytest.mark.integration
@pytest.mark.skipif(
    not __import__("os").environ.get("OPENAI_API_KEY"),
    reason="Real chat streaming requires OPENAI_API_KEY",
)
@pytest.mark.anyio
async def test_chat_stream_returns_sse_events(async_client, auth_headers, indexed_document):
    response = await async_client.post(
        "/api/v1/chat",
        headers=auth_headers,
        json={"query": "What does AlphaProject use?"},
    )

    assert response.status_code == 200
    payload = response.text
    assert "data:" in payload
    events = [
        json.loads(line.removeprefix("data: "))
        for line in payload.splitlines()
        if line.startswith("data: ")
    ]
    done_events = [event for event in events if event["type"] == "done"]
    assert done_events
    assert done_events[0]["conversation_id"]
