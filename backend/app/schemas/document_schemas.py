"""Document schemas for CRUD, chunk inspection, and configurable chunking."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DocumentResponse(BaseModel):
    id: UUID
    title: str
    file_name: str
    file_type: str
    file_size: int
    status: str
    total_chunks: int
    error_message: str | None = None
    metadata_: dict | None = None
    created_at: datetime
    updated_at: datetime
    duplicate_of_existing: bool = False

    model_config = {"from_attributes": True}


class DocumentDetailResponse(DocumentResponse):
    owner_id: UUID
    allowed_roles: list[UUID] = []


class DocumentReindexRequest(BaseModel):
    chunk_size: int | None = Field(default=None, ge=64, le=4096)
    chunk_overlap: int | None = Field(default=None, ge=0, le=1024)


class DocumentChunkItem(BaseModel):
    id: UUID
    chunk_index: int
    content: str
    page_number: int | None = None
    section: str | None = None
    section_path: str | None = None
    block_type: str | None = None
    token_count: int = 0


class DocumentChunksResponse(BaseModel):
    document_id: UUID
    title: str
    file_name: str
    chunk_size: int
    chunk_overlap: int
    total_chunks: int
    sections: list[str] = Field(default_factory=list)
    chunks: list[DocumentChunkItem] = Field(default_factory=list)


class DocumentListFilters(BaseModel):
    status: str | None = None
    file_type: str | None = None
    search: str | None = None
