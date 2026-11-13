"""Ingestion pipeline: parse → chunk → deduplicated batch embed → bulk store in pgvector with granular stage tracking."""

import hashlib
import logging
import unicodedata
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


def strip_vietnamese_accents(value: str) -> str:
    """Normalize Vietnamese text to unaccented ASCII for bilingual/accent-insensitive BM25 matching."""
    if not value:
        return ""
    replaced = value.replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", replaced)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


class IngestionPipeline:
    """Orchestrates document processing: parse → chunk → embed → store with live stage updates."""

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
        self.batch_size = max(1, settings.embedding_batch_size)
        self.chunking_engine = ChunkingEngine(
            chunk_size=self.default_chunk_size,
            chunk_overlap=self.default_chunk_overlap,
        )

    async def _update_stage(
        self,
        document_id: UUID,
        base_meta: dict,
        stage: str,
        progress_pct: int,
        detail: str | None = None,
    ) -> dict:
        next_meta = {
            **base_meta,
            "ingestion_stage": stage,
            "ingestion_progress": progress_pct,
            "ingestion_detail": detail or stage,
        }
        await self.session.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(metadata_=next_meta)
        )
        await self.session.commit()
        return next_meta

    async def process_document(self, document_id: UUID) -> None:
        """Full ingestion pipeline for a single document with stage-by-stage progress."""
        result = await self.session.execute(
            select(Document).where(Document.id == document_id)
        )
        document = result.scalar_one_or_none()
        if document is None:
            raise ValueError(f"Document {document_id} not found")

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
        doc_meta = dict(document.metadata_ or {})

        try:
            # Stage 1: Parsing
            doc_meta = await self._update_stage(
                document_id, doc_meta, "parsing", 15, "Parsing document structure"
            )
            file_hash = self._compute_file_hash(document.file_path)
            parser = get_parser(document.file_path)
            pages = parser.parse(document.file_path)

            if not pages:
                raise ValueError("Document produced no parseable content")

            # Stage 2: Chunking
            doc_meta = await self._update_stage(
                document_id, doc_meta, "chunking", 30, f"Chunking {len(pages)} pages"
            )
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
            total_chunks = len(chunks)
            logger.info(
                "Document %s: %s pages → %s chunks (size=%s, overlap=%s)",
                document_id,
                len(pages),
                total_chunks,
                doc_chunk_size,
                doc_chunk_overlap,
            )

            # Stage 3: Deduplicated Batch Embedding with progress tracking
            embedded_chunks = await self._embed_chunks(
                chunks, document_id=document_id, doc_meta=doc_meta
            )

            # Stage 4: Bulk DB Insert
            doc_meta = await self._update_stage(
                document_id,
                doc_meta,
                "storing",
                90,
                f"Storing {total_chunks} chunks in pgvector",
            )
            await self.session.execute(
                delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
            )

            chunk_rows = []
            for chunk, emb_result in embedded_chunks:
                unaccented = strip_vietnamese_accents(chunk.content)
                searchable_content = (
                    f"{chunk.content} {unaccented}"
                    if unaccented != chunk.content
                    else chunk.content
                )
                chunk_meta = {
                    **chunk.metadata,
                    "content_hash": hashlib.sha256(chunk.content.encode("utf-8")).hexdigest(),
                }
                chunk_rows.append(
                    DocumentChunk(
                        document_id=document_id,
                        content=chunk.content,
                        embedding=emb_result.dense,
                        sparse_vector=emb_result.sparse,
                        search_vector=func.to_tsvector("simple", searchable_content),
                        chunk_index=chunk.chunk_index,
                        page_number=chunk.page_number,
                        section=chunk.section,
                        token_count=chunk.token_count,
                        metadata_=chunk_meta,
                    )
                )

            self.session.add_all(chunk_rows)
            await self.session.flush()

            distinct_sections = sorted(
                {chunk.section for chunk in chunks if chunk.section}
            )

            # Stage 5: Indexed
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
                        "ingestion_stage": "indexed",
                        "ingestion_progress": 100,
                        "ingestion_detail": f"Indexed {len(chunk_rows)} chunks across {len(distinct_sections)} sections",
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
            await self.session.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(
                    status=DocumentStatus.failed,
                    metadata_={
                        **doc_meta,
                        "ingestion_stage": "failed",
                        "ingestion_progress": 0,
                        "ingestion_detail": str(e)[:300],
                    },
                    error_message=str(e)[:1000],
                )
            )
            await self.session.commit()
            logger.error(f"Document {document_id} ingestion failed: {e}")
            raise

    async def _embed_chunks(
        self,
        chunks: list[ChunkData],
        *,
        document_id: UUID | None = None,
        doc_meta: dict | None = None,
    ) -> list[tuple[ChunkData, "EmbeddingResult"]]:
        """Embed chunks with content_hash deduplication and stage progress reporting."""
        from app.services.embedding_service import EmbeddingResult

        if not chunks:
            return []

        total = len(chunks)
        if document_id is not None and doc_meta is not None:
            await self._update_stage(
                document_id,
                doc_meta,
                f"embedding 0/{total}",
                35,
                f"Embedding chunks (0/{total})",
            )

        # Deduplicate identical chunk texts before calling the embedding service
        unique_texts: list[str] = []
        hash_to_unique_idx: dict[str, int] = {}
        chunk_hashes: list[str] = []

        for chunk in chunks:
            text_val = chunk.contextualized_text or chunk.content
            h = hashlib.sha256(text_val.encode("utf-8")).hexdigest()
            chunk_hashes.append(h)
            if h not in hash_to_unique_idx:
                hash_to_unique_idx[h] = len(unique_texts)
                unique_texts.append(text_val)

        unique_embeddings: list[EmbeddingResult] = []
        step = max(1, self.batch_size * 2)
        for start in range(0, len(unique_texts), step):
            sub_texts = unique_texts[start : start + step]
            sub_embs = await self.embedding_service.embed_texts(sub_texts)
            unique_embeddings.extend(sub_embs)
            if document_id is not None and doc_meta is not None:
                done_count = min(total, int((len(unique_embeddings) / max(1, len(unique_texts))) * total))
                pct = 35 + int((done_count / max(1, total)) * 50)
                await self._update_stage(
                    document_id,
                    doc_meta,
                    f"embedding {done_count}/{total}",
                    pct,
                    f"Embedding chunks ({done_count}/{total})",
                )

        return [
            (chunk, unique_embeddings[hash_to_unique_idx[h]])
            for chunk, h in zip(chunks, chunk_hashes)
        ]

    @staticmethod
    def _compute_file_hash(file_path: str) -> str:
        """SHA-256 hash of file content for change detection."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for block in iter(lambda: f.read(8192), b""):
                sha256.update(block)
        return sha256.hexdigest()
