"""Retrieval service: hybrid search, balanced multi-doc retrieval, and strict grounding helpers."""

import asyncio
import logging
from dataclasses import dataclass
from uuid import UUID

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.answer_brief_builder import build_answer_brief
from app.services.context_assembler import AssembledContext, ContextAssembler
from app.services.embedding_service import EmbeddingProvider, get_embedding_service
from app.services.evidence_clusterer import (
    build_evidence_clusters,
    build_summary_subqueries,
    select_evidence_chunks,
)
from app.services.retrieval_intent_service import detect_retrieval_intent
from app.services.retrieval_section_policy import evaluate_chunk_policy
from app.services.reranking_service import RerankingService, get_reranking_service

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """Result of the full retrieval pipeline."""

    context: AssembledContext
    query_used: str
    low_confidence: bool = False
    candidate_count: int = 0


@dataclass
class SearchFilters:
    """Optional filters for retrieval."""

    document_ids: list[UUID] | None = None
    file_types: list[str] | None = None
    date_from: str | None = None
    date_to: str | None = None


class RetrievalService:
    """Orchestrates document-grounded retrieval."""

    def __init__(
        self,
        session: AsyncSession,
        embedding_service: EmbeddingProvider | None = None,
        reranking_service: RerankingService | None = None,
        context_assembler: ContextAssembler | None = None,
    ):
        self.session = session
        self.embedding_service = embedding_service or get_embedding_service()
        self.reranking_service = reranking_service or get_reranking_service()
        self.context_assembler = context_assembler or ContextAssembler()

    async def retrieve(
        self,
        query: str,
        user_id: UUID,
        user_role_ids: list[UUID],
        filters: SearchFilters | None = None,
        alternate_queries: list[str] | None = None,
        top_k_search: int = 20,
        top_k_rerank: int = 5,
        confidence_threshold: float = 0.3,
        prefer_document_order: bool = False,
        context_max_tokens: int | None = None,
        balanced_per_document: bool = False,
        ordered_document_scan: bool = False,
    ) -> RetrievalResult:
        """Run a multi-stage retrieval pipeline with evidence clustering."""
        intent = detect_retrieval_intent(query).value
        normalized_alternates = [
            item.strip()
            for item in (alternate_queries or [])
            if item and item.strip() and item.strip() != query.strip()
        ]

        variant_specs: list[tuple[str, str]] = [("primary", query)]
        variant_specs.extend(("rewrite", item) for item in normalized_alternates)
        if intent == "summary":
            variant_specs.extend(build_summary_subqueries(query))

        embeddings_by_variant: dict[str, list[float] | None] = {}
        variant_texts = [text_value for _label, text_value in variant_specs]
        try:
            embeddings = await self.embedding_service.embed_texts(variant_texts)
            for index, (label, _text) in enumerate(variant_specs):
                embeddings_by_variant[f"{label}:{index}"] = embeddings[index].dense
        except Exception as exc:
            logger.warning("Query embedding failed, falling back to keyword-only retrieval: %s", exc)
            embeddings_by_variant = {
                f"{label}:{index}": None for index, (label, _text) in enumerate(variant_specs)
            }

        vector_results: list[dict] = []
        bm25_results: list[dict] = []
        retrieval_failures: list[Exception] = []
        for index, (variant_label, variant_query) in enumerate(variant_specs):
            variant_embedding = embeddings_by_variant.get(f"{variant_label}:{index}")
            try:
                if balanced_per_document and filters and filters.document_ids:
                    variant_vector_results, variant_bm25_results = await self._balanced_hybrid_search(
                        query=variant_query,
                        query_embedding=variant_embedding,
                        user_id=user_id,
                        user_role_ids=user_role_ids,
                        filters=filters,
                        top_k_search=top_k_search,
                    )
                else:
                    variant_vector_results, variant_bm25_results = await self._default_hybrid_search(
                        query=variant_query,
                        query_embedding=variant_embedding,
                        user_id=user_id,
                        user_role_ids=user_role_ids,
                        filters=filters,
                        top_k_search=top_k_search,
                    )
            except Exception as exc:
                logger.warning("Retrieval failed for query variant '%s': %s", variant_query, exc)
                retrieval_failures.append(exc)
                continue

            for item in variant_vector_results + variant_bm25_results:
                item["query_label"] = variant_label
            vector_results.extend(variant_vector_results)
            bm25_results.extend(variant_bm25_results)

        if not vector_results and not bm25_results and retrieval_failures:
            raise RuntimeError("all retrieval strategies failed") from retrieval_failures[0]

        merged = self._rrf_merge(vector_results, bm25_results)
        if not merged:
            return RetrievalResult(
                context=AssembledContext(context_text="", sources=[], total_tokens=0),
                query_used=query,
                low_confidence=True,
                candidate_count=0,
            )

        deduped = self._deduplicate_by_embedding(merged)
        deduped = self._apply_section_policy(query, deduped)
        chunks_for_rerank = [
            {
                "id": str(chunk["chunk_id"]),
                "content": chunk["content"],
                "metadata": chunk["metadata"],
            }
            for chunk in deduped[:top_k_search]
        ]

        reranked = await self.reranking_service.rerank(query, chunks_for_rerank, top_k=top_k_search)
        clusters = build_evidence_clusters(reranked)
        selected_chunks, diagnostics = select_evidence_chunks(intent, clusters, top_k=top_k_rerank)
        confidence_chunks = selected_chunks or reranked
        low_confidence = not confidence_chunks or confidence_chunks[0].score < confidence_threshold
        context = self.context_assembler.assemble(
            selected_chunks or reranked[:top_k_rerank],
            prefer_document_order=prefer_document_order,
            max_tokens=context_max_tokens,
        )
        context.answer_brief = build_answer_brief(intent, context.sources)
        diagnostics.update(
            {
                "intent": intent,
                "dropped_boilerplate_sections": sorted(
                    {
                        str(chunk.get("metadata", {}).get("block_type"))
                        for chunk in deduped
                        if (chunk.get("metadata", {}).get("block_type") in {"acknowledgement", "references", "table_of_contents", "figure_caption", "cover"})
                    }
                ),
            }
        )
        context.diagnostics = diagnostics

        return RetrievalResult(
            context=context,
            query_used=query,
            low_confidence=low_confidence,
            candidate_count=len(merged),
        )

    @staticmethod
    def _apply_section_policy(query: str, chunks: list[dict]) -> list[dict]:
        """Nudge chunk ordering away from boilerplate before reranking."""
        annotated: list[dict] = []
        for chunk in chunks:
            metadata = dict(chunk.get("metadata") or {})
            policy = evaluate_chunk_policy(query, chunk.get("content", ""), metadata)
            metadata["section_kind"] = policy.kind
            metadata["section_relevance_bias"] = policy.relevance_bias

            updated = chunk.copy()
            updated["metadata"] = metadata
            updated["section_policy_score"] = float(updated.get("rrf_score", updated.get("score", 0.0))) + policy.relevance_bias
            annotated.append(updated)

        annotated.sort(
            key=lambda item: (
                item.get("section_policy_score", 0.0),
                item.get("rrf_score", item.get("score", 0.0)),
            ),
            reverse=True,
        )
        return annotated

    async def _default_hybrid_search(
        self,
        query: str,
        query_embedding: list[float] | None,
        user_id: UUID,
        user_role_ids: list[UUID],
        filters: SearchFilters | None,
        top_k_search: int,
    ) -> tuple[list[dict], list[dict]]:
        vector_task = (
            self._vector_search(query_embedding, user_id, user_role_ids, filters, top_k_search)
            if query_embedding is not None
            else None
        )
        bm25_task = self._bm25_search(query, user_id, user_role_ids, filters, top_k_search)

        if vector_task is None:
            try:
                return [], await bm25_task
            except Exception as exc:
                logger.exception("BM25 retrieval failed")
                raise RuntimeError("keyword retrieval failed") from exc

        vector_out, bm25_out = await asyncio.gather(
            vector_task,
            bm25_task,
            return_exceptions=True,
        )
        vector_results: list[dict] = []
        bm25_results: list[dict] = []

        if isinstance(vector_out, Exception):
            logger.warning("Vector retrieval failed, continuing without it: %s", vector_out)
        else:
            vector_results = vector_out

        if isinstance(bm25_out, Exception):
            logger.warning("BM25 retrieval failed, continuing without it: %s", bm25_out)
        else:
            bm25_results = bm25_out

        if not vector_results and not bm25_results:
            raise RuntimeError("all retrieval strategies failed")

        return vector_results, bm25_results

    async def _balanced_hybrid_search(
        self,
        query: str,
        query_embedding: list[float] | None,
        user_id: UUID,
        user_role_ids: list[UUID],
        filters: SearchFilters,
        top_k_search: int,
    ) -> tuple[list[dict], list[dict]]:
        vector_results: list[dict] = []
        bm25_results: list[dict] = []
        document_ids = filters.document_ids or []
        per_document_k = max(4, top_k_search // max(1, len(document_ids)))

        for document_id in document_ids:
            scoped_filters = SearchFilters(
                document_ids=[document_id],
                file_types=filters.file_types,
                date_from=filters.date_from,
                date_to=filters.date_to,
            )

            if query_embedding is not None:
                try:
                    vector_results.extend(
                        await self._vector_search(
                            query_embedding,
                            user_id,
                            user_role_ids,
                            scoped_filters,
                            per_document_k,
                        )
                    )
                except Exception as exc:
                    logger.warning("Balanced vector retrieval failed for %s: %s", document_id, exc)

            try:
                bm25_results.extend(
                    await self._bm25_search(
                        query,
                        user_id,
                        user_role_ids,
                        scoped_filters,
                        per_document_k,
                    )
                )
            except Exception as exc:
                logger.warning("Balanced BM25 retrieval failed for %s: %s", document_id, exc)

        if not vector_results and not bm25_results:
            raise RuntimeError("all balanced retrieval strategies failed")

        return vector_results, bm25_results

    async def _document_order_scan(
        self,
        user_id: UUID,
        filters: SearchFilters,
        per_document_limit: int,
    ) -> list[dict]:
        if not filters.document_ids:
            return []

        sql = text(
            """
            WITH ranked_chunks AS (
                SELECT
                    d.id AS document_id,
                    c.id,
                    c.content,
                    c.page_number,
                    c.section,
                    c.chunk_index,
                    c.embedding,
                    c.metadata,
                    d.title AS doc_title,
                    d.file_name,
                    ROW_NUMBER() OVER (PARTITION BY d.id ORDER BY c.chunk_index) AS doc_rank
                FROM document_chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE d.status = 'indexed'
                  AND d.owner_id = CAST(:user_id AS uuid)
                  AND d.id = ANY(:doc_ids)
            )
            SELECT *
            FROM ranked_chunks
            WHERE doc_rank <= :per_document_limit
            """
        )
        rows = (
            await self.session.execute(
                sql,
                {
                    "user_id": str(user_id),
                    "doc_ids": [str(doc_id) for doc_id in filters.document_ids],
                    "per_document_limit": per_document_limit,
                },
            )
        ).mappings().all()

        document_order = {
            str(document_id): index
            for index, document_id in enumerate(filters.document_ids)
        }
        ordered_rows = sorted(
            rows,
            key=lambda row: (
                document_order.get(str(row["document_id"]), 999),
                row["chunk_index"] or 0,
            ),
        )

        return [
            {
                "id": str(row["id"]),
                "content": row["content"],
                "metadata": {
                    "document_id": str(row["document_id"]),
                    "document_title": row["doc_title"],
                    "file_name": row["file_name"],
                    "page_number": row["page_number"],
                    "section": row["section"],
                    "chunk_index": row["chunk_index"],
                    **(row["metadata"] or {}),
                },
            }
            for row in ordered_rows
        ]

    async def _vector_search(
        self,
        query_embedding: list[float],
        user_id: UUID,
        user_role_ids: list[UUID],
        filters: SearchFilters | None,
        top_k: int,
    ) -> list[dict]:
        """Cosine similarity search via pgvector HNSW index."""
        embedding_str = "[" + ",".join(str(value) for value in query_embedding) + "]"
        where_clauses = [
            "d.status = 'indexed'",
            "d.owner_id = CAST(:user_id AS uuid)",
        ]
        params: dict = {"user_id": str(user_id), "top_k": top_k}

        if filters:
            if filters.document_ids:
                where_clauses.append("d.id = ANY(:doc_ids)")
                params["doc_ids"] = [str(document_id) for document_id in filters.document_ids]
            if filters.file_types:
                where_clauses.append("d.file_type = ANY(:file_types)")
                params["file_types"] = filters.file_types

        sql = text(
            f"""
            SELECT c.id, c.content, c.page_number, c.section, c.chunk_index,
                   c.embedding, c.metadata,
                   d.id AS document_id, d.title as doc_title, d.file_name,
                   (c.embedding <=> CAST(:embedding AS vector)) as distance
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE {' AND '.join(where_clauses)}
              AND c.embedding IS NOT NULL
            ORDER BY c.embedding <=> CAST(:embedding AS vector)
            LIMIT :top_k
            """
        )

        params["embedding"] = embedding_str
        rows = (await self.session.execute(sql, params)).mappings().all()

        return [
            {
                "chunk_id": str(row["id"]),
                "content": row["content"],
                "distance": float(row["distance"]),
                "score": 1.0 - float(row["distance"]),
                "embedding": row["embedding"],
                "metadata": {
                    "document_id": str(row["document_id"]),
                    "document_title": row["doc_title"],
                    "file_name": row["file_name"],
                    "page_number": row["page_number"],
                    "section": row["section"],
                    "chunk_index": row["chunk_index"],
                    **(row["metadata"] or {}),
                },
            }
            for row in rows
        ]

    async def _bm25_search(
        self,
        query: str,
        user_id: UUID,
        user_role_ids: list[UUID],
        filters: SearchFilters | None,
        top_k: int,
    ) -> list[dict]:
        """BM25-style full-text search via tsvector + ts_rank."""
        where_clauses = [
            "d.status = 'indexed'",
            "d.owner_id = CAST(:user_id AS uuid)",
            "c.search_vector @@ plainto_tsquery('simple', :query)",
        ]
        params: dict = {"user_id": str(user_id), "query": query, "top_k": top_k}

        if filters:
            if filters.document_ids:
                where_clauses.append("d.id = ANY(:doc_ids)")
                params["doc_ids"] = [str(document_id) for document_id in filters.document_ids]
            if filters.file_types:
                where_clauses.append("d.file_type = ANY(:file_types)")
                params["file_types"] = filters.file_types

        sql = text(
            f"""
            SELECT c.id, c.content, c.page_number, c.section, c.chunk_index,
                   c.embedding, c.metadata,
                   d.id AS document_id, d.title as doc_title, d.file_name,
                   ts_rank(c.search_vector, plainto_tsquery('simple', :query)) as rank
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE {' AND '.join(where_clauses)}
            ORDER BY rank DESC
            LIMIT :top_k
            """
        )

        rows = (await self.session.execute(sql, params)).mappings().all()

        return [
            {
                "chunk_id": str(row["id"]),
                "content": row["content"],
                "score": float(row["rank"]),
                "embedding": row["embedding"],
                "metadata": {
                    "document_id": str(row["document_id"]),
                    "document_title": row["doc_title"],
                    "file_name": row["file_name"],
                    "page_number": row["page_number"],
                    "section": row["section"],
                    "chunk_index": row["chunk_index"],
                    **(row["metadata"] or {}),
                },
            }
            for row in rows
        ]

    @staticmethod
    def _rrf_merge(
        vector_results: list[dict],
        bm25_results: list[dict],
        k: int = 60,
    ) -> list[dict]:
        """Reciprocal Rank Fusion: score = sum(1 / (k + rank))."""
        scores: dict[str, float] = {}
        chunk_map: dict[str, dict] = {}

        for rank, item in enumerate(vector_results):
            chunk_id = item["chunk_id"]
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank + 1)
            if chunk_id in chunk_map:
                merged_labels = set(chunk_map[chunk_id].get("query_labels", []))
                merged_labels.update(item.get("query_labels", []))
                if item.get("query_label"):
                    merged_labels.add(item["query_label"])
                chunk_map[chunk_id]["query_labels"] = sorted(merged_labels)
            else:
                entry = item.copy()
                labels = set(entry.get("query_labels", []))
                if entry.get("query_label"):
                    labels.add(entry["query_label"])
                entry["query_labels"] = sorted(labels)
                chunk_map[chunk_id] = entry

        for rank, item in enumerate(bm25_results):
            chunk_id = item["chunk_id"]
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank + 1)
            if chunk_id not in chunk_map:
                entry = item.copy()
                labels = set(entry.get("query_labels", []))
                if entry.get("query_label"):
                    labels.add(entry["query_label"])
                entry["query_labels"] = sorted(labels)
                chunk_map[chunk_id] = entry
            else:
                merged_labels = set(chunk_map[chunk_id].get("query_labels", []))
                merged_labels.update(item.get("query_labels", []))
                if item.get("query_label"):
                    merged_labels.add(item["query_label"])
                chunk_map[chunk_id]["query_labels"] = sorted(merged_labels)

        merged: list[dict] = []
        for chunk_id in sorted(scores, key=lambda value: scores[value], reverse=True):
            item = chunk_map[chunk_id].copy()
            item["rrf_score"] = scores[chunk_id]
            item_metadata = dict(item.get("metadata") or {})
            item_metadata["query_labels"] = item.get("query_labels", [])
            item["metadata"] = item_metadata
            merged.append(item)

        return merged

    @staticmethod
    def _deduplicate_by_embedding(
        chunks: list[dict],
        threshold: float = 0.95,
    ) -> list[dict]:
        """Remove near-duplicate chunks (cosine similarity > threshold)."""
        if len(chunks) <= 1:
            return chunks

        unique: list[dict] = [chunks[0]]
        for chunk in chunks[1:]:
            vec = RetrievalService._coerce_embedding(chunk.get("embedding"))
            if vec is None:
                unique.append(chunk)
                continue

            vec_norm = np.linalg.norm(vec)
            if vec_norm == 0:
                unique.append(chunk)
                continue

            is_duplicate = False
            for kept in unique:
                kept_vec = RetrievalService._coerce_embedding(kept.get("embedding"))
                if kept_vec is None:
                    continue
                kept_norm = np.linalg.norm(kept_vec)
                if kept_norm == 0:
                    continue
                cosine = float(np.dot(vec, kept_vec) / (vec_norm * kept_norm))
                if cosine > threshold:
                    kept_metadata = dict(kept.get("metadata") or {})
                    candidate_labels = set(kept_metadata.get("query_labels", []))
                    candidate_labels.update((chunk.get("metadata") or {}).get("query_labels", []))
                    kept_metadata["query_labels"] = sorted(candidate_labels)
                    kept["metadata"] = kept_metadata
                    is_duplicate = True
                    break

            if not is_duplicate:
                unique.append(chunk)

        return unique

    @staticmethod
    def _coerce_embedding(embedding: object) -> np.ndarray | None:
        """Normalize pgvector outputs that may arrive as lists or stringified vectors."""
        if embedding is None:
            return None

        if isinstance(embedding, str):
            cleaned = embedding.strip().strip("[]")
            if not cleaned:
                return None
            return np.fromstring(cleaned, sep=",", dtype=np.float32)

        return np.array(embedding, dtype=np.float32)
