"""Chat and conversation schemas."""

from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ChatResponseMode(str, Enum):
    strict_documents = "strict_documents"
    hybrid_general = "hybrid_general"


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    conversation_id: UUID | None = None
    replace_message_id: UUID | None = None
    document_ids: list[UUID] | None = None
    response_mode: ChatResponseMode = ChatResponseMode.strict_documents
    include_diagnostics: bool = False


class ConversationUpdateRequest(BaseModel):
    title: str | None = None
    document_ids: list[UUID] | None = None


class ActiveDocumentResponse(BaseModel):
    id: UUID
    title: str
    file_name: str
    status: str
    total_chunks: int

    model_config = {"from_attributes": True}


class ChatStreamEvent(BaseModel):
    type: Literal["chunk", "sources", "done", "error"]
    content: str | None = None
    sources: list[dict] | None = None
    user_message_id: UUID | None = None
    message_id: UUID | None = None
    conversation_id: UUID | None = None
    active_documents: list[ActiveDocumentResponse] | None = None
    diagnostics: dict | None = None


class ConversationResponse(BaseModel):
    id: UUID
    title: str | None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    active_documents: list[ActiveDocumentResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    id: UUID
    role: str
    content: str
    sources: list[dict] | None = None
    created_at: datetime
    tokens_used: int | None = None
    latency_ms: int | None = None

    model_config = {"from_attributes": True}
