"""Ingestion pipeline: parse → chunk → embed → store in pgvector."""

import hashlib
import logging
from uuid import UUID

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.chunk import DocumentChunk
from app.models.document import Document, DocumentStatus
from app.services.chunking_engine import ChunkData, ChunkingEngine
from app.services.document_structure import INGESTION_VERSION
from app.services.embedding_service import EmbeddingProvider, get_embedding_service
from app.services.parser_factory import get_parser

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """Orchestrates document processing: parse → chunk → embed → store."""

    def __init__(
        self,
        session: AsyncSession,
        embedding_service: EmbeddingProvider | None = None,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ):
        self.session = session
        self.embedding_service = embedding_service or get_embedding_service()
        settings = get_settings()
        self.default_chunk_size = chunk_size or settings.chunk_size
        self.default_chunk_overlap = (
            chunk_overlap if chunk_overlap is not None else settings.chunk_overlap
        )
        self.chunking_engine = ChunkingEngine(
            chunk_size=self.default_chunk_size,
            chunk_overlap=self.default_chunk_overlap,
        )

    async def process_document(self, document_id: UUID) -> None:
        """Full ingestion pipeline for a single document."""
        # 1. Load document from DB
        result = await self.session.execute(
            select(Document).where(Document.id == document_id)
        )
        document = result.scalar_one_or_none()
        if document is None:
            raise ValueError(f"Document {document_id} not found")

        # 2. Claim the document so only one dispatcher path indexes it at a time.
        updated = await self.session.execute(
            update(Document)
            .where(
                Document.id == document_id,
                Document.status != DocumentStatus.processing,
            )
            .values(status=DocumentStatus.processing)
        )
        await self.session.commit()
        if not updated.rowcount:
            logger.info("Document %s is already being processed", document_id)
            return

        document.status = DocumentStatus.processing

        try:
            # 3. Compute file hash for incremental indexing
            file_hash = self._compute_file_hash(document.file_path)

            # 4. Parse document
            parser = get_parser(document.file_path)
            pages = parser.parse(document.file_path)

            if not pages:
                raise ValueError("Document produced no parseable content")

            # 5. Chunk document (respect per-document chunking config if set)
            doc_meta = document.metadata_ or {}
            doc_chunk_size = int(doc_meta.get("chunk_size") or self.default_chunk_size)
            doc_chunk_overlap = int(
                doc_meta.get("chunk_overlap")
                if doc_meta.get("chunk_overlap") is not None
                else self.default_chunk_overlap
            )
            chunker = ChunkingEngine(
                chunk_size=doc_chunk_size,
                chunk_overlap=min(doc_chunk_overlap, max(0, doc_chunk_size - 1)),
            )
            chunks = chunker.chunk_document(pages, document_id)
            logger.info(
                "Document %s: %s pages → %s chunks (size=%s, overlap=%s)",
                document_id,
                len(pages),
                len(chunks),
                doc_chunk_size,
                doc_chunk_overlap,
            )

            # 6. Embed in batches
            embedded_chunks = await self._embed_chunks(chunks)

            # 7. Delete existing chunks (re-index case)
            await self.session.execute(
                delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
            )

            # 8. Bulk insert new chunks with search_vector explicitly populated for BM25
            chunk_rows = [
                DocumentChunk(
                    document_id=document_id,
                    content=chunk.content,
                    embedding=emb_result.dense,
                    sparse_vector=emb_result.sparse,
                    search_vector=func.to_tsvector("simple", chunk.content),
                    chunk_index=chunk.chunk_index,
                    page_number=chunk.page_number,
                    section=chunk.section,
                    token_count=chunk.token_count,
                    metadata_=chunk.metadata,
                )
                for chunk, emb_result in embedded_chunks
            ]
            self.session.add_all(chunk_rows)
            await self.session.flush()

            # Ensure search_vector is populated even if trigger was bypassed
            await self.session.execute(
                text(
                    """
                    UPDATE document_chunks
                    SET search_vector = to_tsvector('simple', COALESCE(content, ''))
                    WHERE document_id = CAST(:doc_id AS uuid)
                      AND search_vector IS NULL
                    """
                ),
                {"doc_id": str(document_id)},
            )

            distinct_sections = sorted(
                {chunk.section for chunk in chunks if chunk.section}
            )

            # 9. Update document status
            await self.session.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(
                    status=DocumentStatus.indexed,
                    content_hash=file_hash,
                    total_chunks=len(chunk_rows),
                    metadata_={
                        **doc_meta,
                        "ingestion_version": INGESTION_VERSION,
                        "chunking_strategy": "structure-aware-block-first",
                        "chunk_size": doc_chunk_size,
                        "chunk_overlap": doc_chunk_overlap,
                        "sections": distinct_sections,
                    },
                    error_message=None,
                )
            )
            await self.session.commit()
            logger.info(
                "Document %s: indexed %s chunks across %s sections with %s",
                document_id,
                len(chunk_rows),
                len(distinct_sections),
                INGESTION_VERSION,
            )

        except Exception as e:
            await self.session.rollback()
            # Set document status to failed with clear human-readable reason
            await self.session.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(
                    status=DocumentStatus.failed,
                    error_message=str(e)[:1000],
                )
            )
            await self.session.commit()
            logger.error(f"Document {document_id} ingestion failed: {e}")
            raise

    async def _embed_chunks(
        self, chunks: list[ChunkData]
    ) -> list[tuple[ChunkData, "EmbeddingResult"]]:
        """Embed chunks in batches, returning (chunk, embedding) pairs."""
        from app.services.embedding_service import EmbeddingResult

        batch_size = 32
        results: list[tuple[ChunkData, EmbeddingResult]] = []

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            texts = [c.contextualized_text or c.content for c in batch]
            embeddings = await self.embedding_service.embed_texts(texts)
            results.extend(zip(batch, embeddings))

        return results

    @staticmethod
    def _compute_file_hash(file_path: str) -> str:
        """SHA-256 hash of file content for change detection."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for block in iter(lambda: f.read(8192), b""):
                sha256.update(block)
        return sha256.hexdigest()
