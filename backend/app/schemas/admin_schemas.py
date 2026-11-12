"""Admin dashboard schemas: system metrics, user management, ingestion status, and evaluation history."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class SystemStats(BaseModel):
    total_documents: int
    total_chunks: int
    total_conversations: int
    total_messages: int
    docs_by_status: dict[str, int]
    total_questions: int = 0
    abstention_rate: float = 0.0
    avg_latency_ms: float = 0.0
    avg_tokens_per_answer: float = 0.0


class AdminUserResponse(BaseModel):
    id: UUID
    email: str
    display_name: str
    is_active: bool
    is_superuser: bool
    roles: list[str] = Field(default_factory=list)
    document_count: int = 0
    created_at: datetime | None = None


class AdminUserUpdateRequest(BaseModel):
    role: str | None = None
    is_active: bool | None = None


class EvaluationRunSummary(BaseModel):
    run_id: str
    timestamp: str
    total_questions: int
    faithfulness: float
    context_precision: float
    context_recall: float
    latency_p50_ms: float
    latency_p95_ms: float
    avg_tokens_per_answer: float
    bm25_enabled: bool = True


class EvaluationDashboardResponse(BaseModel):
    latest: EvaluationRunSummary | None = None
    history: list[EvaluationRunSummary] = Field(default_factory=list)


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
