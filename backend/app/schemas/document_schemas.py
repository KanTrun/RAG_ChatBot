"""Document schemas for CRUD and upload."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: UUID
    title: str
    file_name: str
    file_type: str
    file_size: int
    status: str
    total_chunks: int
    created_at: datetime
    updated_at: datetime
    duplicate_of_existing: bool = False

    model_config = {"from_attributes": True}


class DocumentDetailResponse(DocumentResponse):
    metadata_: dict | None = None
    error_message: str | None = None
    owner_id: UUID
    allowed_roles: list[UUID] = []


class DocumentListFilters(BaseModel):
    status: str | None = None
    file_type: str | None = None
    search: str | None = None
