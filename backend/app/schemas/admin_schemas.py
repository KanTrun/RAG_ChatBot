"""Admin dashboard schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class SystemStats(BaseModel):
    total_documents: int
    total_chunks: int
    total_conversations: int
    total_messages: int
    docs_by_status: dict[str, int]


class IngestionJobStatus(BaseModel):
    document_id: UUID
    title: str
    status: str
    created_at: datetime
    error_message: str | None = None

    model_config = {"from_attributes": True}
