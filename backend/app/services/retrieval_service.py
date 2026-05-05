"""Retrieval service: hybrid search, balanced multi-doc retrieval, and strict grounding helpers."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from uuid import UUID

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.answer_brief_builder import (
    build_answer_brief,
    build_profile_support_map,
    build_section_support_map,
)
from app.services.context_assembler import AssembledContext, ContextAssembler
from app.services.embedding_service import EmbeddingProvider, get_embedding_service
from app.services.evidence_clusterer import (
    LOW_VALUE_BLOCK_TYPES,
    build_evidence_clusters,
    select_evidence_chunks,
)
from app.services.retrieval_intent_service import (
    RetrievalPlan,
    build_query_variants,
    build_retrieval_plan,
    is_profile_query,
)
from app.services.retrieval_section_policy import evaluate_chunk_policy
from app.services.reranking_service import RerankingService, get_reranking_service
from app.services.reranking_service import RankedChunk

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
        query_analysis: RetrievalPlan | None = None,
    ) -> RetrievalResult:
        """Run a multi-stage retrieval pipeline with evidence clustering."""
        active_document_count = len(filters.document_ids) if filters and filters.document_ids else 0
        plan = query_analysis or build_retrieval_plan(query, active_document_count)
        intent = plan.intent.value
        variant_specs: list[tuple[str, str]] = [("primary", query)]
        variant_specs.extend(build_query_variants(query, plan, alternate_queries))

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

        if ordered_document_scan and filters and filters.document_ids:
            try:
                ordered_scan = await self._document_order_scan(
                    user_id,
                    filters,
                    per_document_limit=max(3, top_k_rerank // max(1, active_document_count or 1)),
                )
                for item in ordered_scan:
                    item["query_label"] = "ordered_scan"
                bm25_results.extend(ordered_scan)
            except Exception as exc:
                logger.warning("Ordered document scan failed: %s", exc)

        if not vector_results and not bm25_results and retrieval_failures:
            raise RuntimeError("all retrieval strategies failed") from retrieval_failures[0]

        merged = self._rrf_merge(vector_results, bm25_results)
        if not merged:
            return RetrievalResult(
                context=AssembledContext(
                    context_text="",
                    sources=[],
                    total_tokens=0,
                    diagnostics={
                        "intent": intent,
                        "selected_query_variants": [label for label, _text in variant_specs],
                        "low_support_reason": plan.low_support_hint,
                    },
                ),
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

        reranked_children = await self.reranking_service.rerank(query, chunks_for_rerank, top_k=top_k_search)
        parent_candidates = self._build_parent_candidates(deduped[:top_k_search])
        parent_scores: dict[str, float] = {}
        if parent_candidates:
            parent_ranked = await self.reranking_service.rerank(
                query,
                parent_candidates,
                top_k=min(len(parent_candidates), max(4, top_k_rerank)),
            )
            parent_scores = {
                str(item.metadata.get("parent_block_id") or item.chunk_id): item.score
                for item in parent_ranked
            }

        clusters = build_evidence_clusters(
            reranked_children,
            parent_scores=parent_scores,
            target_block_types=plan.target_block_types,
        )
        selected_chunks, diagnostics = select_evidence_chunks(
            intent,
            clusters,
            top_k=top_k_rerank,
            target_block_types=plan.target_block_types,
            require_multi_section=plan.require_multi_section,
        )
        if plan.exhaustive_mode:
            selected_chunks, exhaustive_diagnostics = self._expand_exhaustive_selection(
                selected_chunks,
                clusters,
                top_k=top_k_rerank,
                coverage_min_sections=plan.coverage_min_sections,
            )
            diagnostics["exhaustive_expansion"] = exhaustive_diagnostics
        confidence_chunks = selected_chunks or reranked_children
        low_confidence_reason = self._build_low_support_reason(
            plan=plan,
            confidence_chunks=confidence_chunks,
            confidence_threshold=confidence_threshold,
            selected_chunks=selected_chunks,
        )
        low_confidence = low_confidence_reason is not None

        context = self.context_assembler.assemble(
            selected_chunks or reranked_children[:top_k_rerank],
            prefer_document_order=prefer_document_order,
            max_tokens=context_max_tokens,
        )
        context.answer_brief = build_answer_brief(
            intent,
            context.sources,
            query=query,
            low_confidence=low_confidence,
        )
        diagnostics["support_map"] = build_section_support_map(context.sources)
        if plan.document_target_required and is_profile_query(query):
            diagnostics["profile_support"] = build_profile_support_map(context.sources, query=query)
        diagnostics.update(
            {
                "intent": intent,
                "query_classification": plan.query_classification,
                "document_target_required": plan.document_target_required,
                "outside_knowledge_blocked_reason": plan.outside_knowledge_blocked_reason,
                "classification_reason": plan.classification_reason,
                "selected_query_variants": [label for label, _text in variant_specs],
                "target_block_types": list(plan.target_block_types),
                "parent_candidate_sections": [
                    candidate["metadata"].get("section_path")
                    for candidate in parent_candidates[:6]
                    if candidate["metadata"].get("section_path")
                ],
                "dropped_boilerplate_reasons": self._collect_dropped_boilerplate(deduped),
                "dropped_low_signal_reasons": self._collect_low_signal_chunks(deduped),
                "low_support_reason": low_confidence_reason,
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
            metadata["section_relevance_reason"] = policy.reason
            metadata["derived_block_type"] = policy.kind
            if not metadata.get("block_type") or metadata.get("block_type") == "body":
                metadata["block_type"] = policy.kind

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
                "chunk_id": str(row["id"]),
                "content": row["content"],
                "score": 0.05,
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
                    "semantic_score": round(1.0 - float(row["distance"]), 4),
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
                    "lexical_score": round(float(row["rank"]), 4),
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
                chunk_map[chunk_id].setdefault("metadata", {})
                merged_labels = set(chunk_map[chunk_id].get("query_labels", []))
                merged_labels.update(item.get("query_labels", []))
                if item.get("query_label"):
                    merged_labels.add(item["query_label"])
                chunk_map[chunk_id]["query_labels"] = sorted(merged_labels)
                chunk_map[chunk_id]["metadata"]["semantic_score"] = max(
                    float(chunk_map[chunk_id]["metadata"].get("semantic_score") or 0.0),
                    float(item.get("metadata", {}).get("semantic_score") or 0.0),
                )
            else:
                entry = item.copy()
                entry["metadata"] = dict(entry.get("metadata") or {})
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
                entry["metadata"] = dict(entry.get("metadata") or {})
                labels = set(entry.get("query_labels", []))
                if entry.get("query_label"):
                    labels.add(entry["query_label"])
                entry["query_labels"] = sorted(labels)
                chunk_map[chunk_id] = entry
            else:
                chunk_map[chunk_id].setdefault("metadata", {})
                merged_labels = set(chunk_map[chunk_id].get("query_labels", []))
                merged_labels.update(item.get("query_labels", []))
                if item.get("query_label"):
                    merged_labels.add(item["query_label"])
                chunk_map[chunk_id]["query_labels"] = sorted(merged_labels)
                chunk_map[chunk_id]["metadata"]["lexical_score"] = max(
                    float(chunk_map[chunk_id]["metadata"].get("lexical_score") or 0.0),
                    float(item.get("metadata", {}).get("lexical_score") or 0.0),
                )

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

    @staticmethod
    def _build_parent_candidates(chunks: list[dict]) -> list[dict]:
        grouped: dict[str, list[dict]] = {}
        for chunk in chunks:
            metadata = chunk.get("metadata") or {}
            cluster_key = str(
                metadata.get("parent_block_id")
                or metadata.get("section_path")
                or metadata.get("section")
                or chunk.get("chunk_id")
            )
            grouped.setdefault(cluster_key, []).append(chunk)

        parent_candidates: list[dict] = []
        for cluster_key, items in grouped.items():
            first = items[0]
            metadata = dict(first.get("metadata") or {})
            snippet_parts: list[str] = []
            for item in items[:3]:
                content = " ".join(str(item.get("content") or "").split())
                if content:
                    snippet_parts.append(content[:320])
            if not snippet_parts:
                continue
            section_label = metadata.get("section_path") or metadata.get("section") or metadata.get("document_title")
            parent_text = f"Section summary: {section_label}\n" + "\n".join(snippet_parts)
            metadata["candidate_kind"] = "parent_summary"
            metadata["parent_block_id"] = cluster_key
            parent_candidates.append(
                {
                    "id": f"parent::{cluster_key}",
                    "content": parent_text,
                    "metadata": metadata,
                }
            )

        parent_candidates.sort(
            key=lambda item: float(item["metadata"].get("semantic_score") or item["metadata"].get("lexical_score") or 0.0),
            reverse=True,
        )
        return parent_candidates[:12]

    @staticmethod
    def _collect_dropped_boilerplate(chunks: list[dict]) -> list[dict]:
        dropped: list[dict] = []
        for chunk in chunks:
            metadata = chunk.get("metadata") or {}
            kind = str(metadata.get("section_kind") or metadata.get("block_type") or "")
            if kind not in LOW_VALUE_BLOCK_TYPES:
                continue
            bias = float(metadata.get("section_relevance_bias") or 0.0)
            if bias >= 0:
                continue
            dropped.append(
                {
                    "section_path": metadata.get("section_path") or metadata.get("section"),
                    "block_type": kind,
                    "reason": metadata.get("section_relevance_reason"),
                }
            )
        return dropped[:12]

    @staticmethod
    def _collect_low_signal_chunks(chunks: list[dict]) -> list[dict]:
        dropped: list[dict] = []
        for chunk in chunks:
            metadata = chunk.get("metadata") or {}
            kind = str(metadata.get("section_kind") or metadata.get("block_type") or "")
            bias = float(metadata.get("section_relevance_bias") or 0.0)
            if kind not in {"contact", "header_footer", "cover", "table_of_contents", "figure_caption"} or bias >= 0:
                continue
            dropped.append(
                {
                    "section_path": metadata.get("section_path") or metadata.get("section"),
                    "block_type": kind,
                    "reason": metadata.get("section_relevance_reason"),
                }
            )
        return dropped[:12]

    @staticmethod
    def _build_low_support_reason(
        *,
        plan: RetrievalPlan,
        confidence_chunks: list,
        confidence_threshold: float,
        selected_chunks: list,
    ) -> str | None:
        if not confidence_chunks:
            return plan.low_support_hint

        if plan.target_block_types and not selected_chunks:
            return (
                f"{plan.low_support_hint} "
                "Retrieval did not produce claim-level support from the preferred document sections."
            )

        top_score = float(confidence_chunks[0].score)
        unique_sections = {
            chunk.metadata.get("section_path") or chunk.metadata.get("section")
            for chunk in selected_chunks
            if chunk.metadata.get("section_path") or chunk.metadata.get("section")
        }
        block_types = {str(chunk.metadata.get("block_type") or "") for chunk in confidence_chunks[:3]}

        if top_score < confidence_threshold:
            return (
                f"{plan.low_support_hint} "
                f"Top evidence score {top_score:.2f} is below threshold {confidence_threshold:.2f}."
            )
        if plan.require_multi_section and len(unique_sections) < 2:
            return (
                f"{plan.low_support_hint} "
                "Retrieval did not cover enough distinct sections for a grounded synthesis."
            )
        if plan.exhaustive_mode and len(unique_sections) < plan.coverage_min_sections:
            return (
                f"{plan.low_support_hint} "
                f"Coverage only reached {len(unique_sections)} supported sections; expected at least {plan.coverage_min_sections} for an exhaustive answer."
            )
        if block_types and block_types.issubset(LOW_VALUE_BLOCK_TYPES):
            return (
                f"{plan.low_support_hint} "
                "Only low-value or boilerplate sections were retrieved near the top."
            )
        return None

    @staticmethod
    def _expand_exhaustive_selection(
        selected_chunks: list,
        clusters: list,
        *,
        top_k: int,
        coverage_min_sections: int,
    ) -> tuple[list, dict]:
        expanded = list(selected_chunks)
        selected_cluster_ids = {
            chunk.metadata.get("cluster_id")
            or chunk.metadata.get("parent_block_id")
            or chunk.chunk_id
            for chunk in expanded
        }
        covered_sections = {
            chunk.metadata.get("section_path") or chunk.metadata.get("section")
            for chunk in expanded
            if chunk.metadata.get("section_path") or chunk.metadata.get("section")
        }
        added_sections: list[str] = []

        for cluster in clusters:
            if len(expanded) >= top_k and len(covered_sections) >= coverage_min_sections:
                break
            if cluster.cluster_id in selected_cluster_ids:
                continue
            section_key = cluster.section_path or str(cluster.chunks[0].metadata.get("section") or "")
            if section_key and section_key in covered_sections and len(expanded) >= top_k:
                continue

            chunk = cluster.chunks[0]
            metadata = dict(chunk.metadata)
            metadata["cluster_id"] = metadata.get("cluster_id") or cluster.cluster_id
            metadata["section_path"] = metadata.get("section_path") or cluster.section_path
            metadata["block_type"] = metadata.get("block_type") or cluster.block_type
            metadata["selection_reason"] = metadata.get("selection_reason") or (
                f"exhaustive fallback coverage from {cluster.section_path or metadata.get('section') or 'document body'}"
            )
            expanded.append(
                RankedChunk(
                    chunk_id=chunk.chunk_id,
                    content=chunk.content,
                    score=chunk.score,
                    original_rank=chunk.original_rank,
                    metadata=metadata,
                )
            )
            selected_cluster_ids.add(cluster.cluster_id)
            if section_key and section_key not in covered_sections:
                covered_sections.add(section_key)
                added_sections.append(section_key)

        return expanded[:top_k], {
            "requested_min_sections": coverage_min_sections,
            "covered_sections": len(covered_sections),
            "added_sections": added_sections[:8],
        }
