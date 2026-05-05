"""DocumentChunk model with vector embedding and full-text search support."""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin


class DocumentChunk(UUIDMixin, Base):
    __tablename__ = "document_chunks"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Vector embedding (BGE-M3 produces 1024-dim dense vectors)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True)
    # Sparse vector as term:weight dict (for hybrid retrieval RRF)
    sparse_vector: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Full-text search vector (auto-populated)
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)

    # Chunk positioning
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section: Mapped[str | None] = mapped_column(String(500), nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Arbitrary metadata
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    document: Mapped["Document"] = relationship(back_populates="chunks", lazy="selectin")  # noqa: F821

    __table_args__ = (
        # HNSW index for fast cosine similarity search
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 200},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        # GIN index for full-text search
        Index("ix_chunks_search_vector_gin", "search_vector", postgresql_using="gin"),
        # Composite index for document chunk ordering
        Index("ix_chunks_document_index", "document_id", "chunk_index"),
    )
