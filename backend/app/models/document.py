"""Document model with status tracking and access control."""

import enum
import uuid

from sqlalchemy import BigInteger, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin, TimestampMixin


class DocumentStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    indexed = "indexed"
    failed = "failed"


class Document(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "documents"

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)  # pdf, docx, html, txt
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus), default=DocumentStatus.pending, index=True, nullable=False
    )
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_chunks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Access control
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    allowed_roles: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), default=list, nullable=False
    )

    # Relationships
    owner: Mapped["User"] = relationship(back_populates="documents", lazy="selectin")  # noqa: F821
    chunks: Mapped[list["DocumentChunk"]] = relationship(  # noqa: F821
        back_populates="document", cascade="all, delete-orphan", lazy="noload"
    )
