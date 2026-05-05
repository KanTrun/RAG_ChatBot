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


class BulkReindexResponse(BaseModel):
    queued_documents: int
    stale_only: bool
    ingestion_version: str


class DocumentOutlineBlock(BaseModel):
    block_id: str
    parent_block_id: str
    section_path: str
    block_type: str
    heading_level: int | None = None
    page_start: int | None = None
    page_end: int | None = None
    preview_text: str


class IndexedChunkDebug(BaseModel):
    chunk_id: UUID
    chunk_index: int
    page_number: int | None = None
    section: str | None = None
    block_type: str | None = None
    section_path: str | None = None
    parent_block_id: str | None = None
    heading_level: int | None = None
    ingestion_version: str | None = None
    contextualized_text: str | None = None
    selection_reason: str | None = None


class DocumentIndexDiagnosticsResponse(BaseModel):
    document_id: UUID
    title: str
    file_name: str
    status: str
    ingestion_version: str | None = None
    parsed_outline: list[DocumentOutlineBlock]
    indexed_chunks: list[IndexedChunkDebug]
