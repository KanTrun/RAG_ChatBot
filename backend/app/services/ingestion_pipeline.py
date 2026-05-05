"""Ingestion pipeline: parse → chunk → embed → store in pgvector."""

import hashlib
import logging
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentStatus
from app.models.chunk import DocumentChunk
from app.services.parser_factory import get_parser
from app.services.document_structure import INGESTION_VERSION
from app.services.chunking_engine import ChunkingEngine, ChunkData
from app.services.embedding_service import EmbeddingProvider, get_embedding_service
from app.config import get_settings

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """Orchestrates document processing: parse → chunk → embed → store."""

    def __init__(
        self,
        session: AsyncSession,
        embedding_service: EmbeddingProvider | None = None,
    ):
        self.session = session
        self.embedding_service = embedding_service or get_embedding_service()
        settings = get_settings()
        self.chunking_engine = ChunkingEngine(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
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

            # 5. Chunk document
            chunks = self.chunking_engine.chunk_document(pages, document_id)
            logger.info(f"Document {document_id}: {len(pages)} pages → {len(chunks)} chunks")

            # 6. Embed in batches
            embedded_chunks = await self._embed_chunks(chunks)

            # 7. Delete existing chunks (re-index case)
            await self.session.execute(
                delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
            )

            # 8. Bulk insert new chunks
            chunk_rows = [
                DocumentChunk(
                    document_id=document_id,
                    content=chunk.content,
                    embedding=emb_result.dense,
                    sparse_vector=emb_result.sparse,
                    chunk_index=chunk.chunk_index,
                    page_number=chunk.page_number,
                    section=chunk.section,
                    token_count=chunk.token_count,
                    metadata_=chunk.metadata,
                )
                for chunk, emb_result in embedded_chunks
            ]
            self.session.add_all(chunk_rows)

            # 9. Update document status
            await self.session.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(
                    status=DocumentStatus.indexed,
                    content_hash=file_hash,
                    total_chunks=len(chunk_rows),
                    metadata_={
                        **(document.metadata_ or {}),
                        "ingestion_version": INGESTION_VERSION,
                        "chunking_strategy": "structure-aware-block-first",
                    },
                    error_message=None,
                )
            )
            await self.session.commit()
            logger.info(
                "Document %s: indexed %s chunks with %s",
                document_id,
                len(chunk_rows),
                INGESTION_VERSION,
            )

        except Exception as e:
            await self.session.rollback()
            # Set document status to failed
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
