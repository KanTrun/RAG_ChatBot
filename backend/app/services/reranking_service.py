"""Reranking service using BGE-Reranker-v2-m3 cross-encoder with hybrid lexical/semantic fallback."""

import asyncio
from dataclasses import dataclass
from functools import lru_cache
import logging
import re

from app.config import get_settings
from app.services.retrieval_section_policy import evaluate_chunk_policy

logger = logging.getLogger(__name__)

_STOP_WORDS = {
    "the", "and", "for", "that", "this", "with", "from", "into", "your", "about",
    "what", "which", "when", "where", "does", "have", "has", "been", "were", "will",
    "cua", "cho", "voi", "trong", "nhung", "mot", "cac", "la", "ve", "nay", "gioi",
}


@dataclass
class RankedChunk:
    """A chunk with its reranking score."""

    chunk_id: str
    content: str
    score: float
    original_rank: int
    metadata: dict


class RerankingService:
    """Cross-encoder reranking using BGE-Reranker-v2-m3 or fast lexical/structural fallback."""

    def __init__(self):
        self._model = None
        settings = get_settings()
        self._enabled = settings.reranker_provider != "none"
        self._warned_fallback = False
        if not self._enabled:
            logger.warning(
                "RERANKER_PROVIDER is 'none'; using fast lexical/structural reranking fallback."
            )
            self._warned_fallback = True

    def _load_model(self):
        """Lazy-load the reranker model."""
        if self._model is not None:
            return
        settings = get_settings()
        try:
            from FlagEmbedding import FlagReranker

            self._model = FlagReranker(
                settings.bge_reranker_model,
                use_fp16=True,
            )
            logger.info(f"Loaded reranker: {settings.bge_reranker_model}")
        except Exception as e:
            logger.warning(
                f"Failed to load reranker model '{settings.bge_reranker_model}': {e}. "
                "Falling back to lexical/structural scoring."
            )
            self._enabled = False
            self._warned_fallback = True

    async def rerank(
        self,
        query: str,
        chunks: list[dict],
        top_k: int = 5,
    ) -> list[RankedChunk]:
        """Rerank chunks by relevance to query."""
        if not chunks:
            return []

        if not self._enabled:
            if not self._warned_fallback:
                logger.warning("Reranker disabled; using lexical/structural scoring fallback.")
                self._warned_fallback = True
            return self._fallback(query, chunks, top_k)

        self._load_model()
        if not self._enabled:
            return self._fallback(query, chunks, top_k)

        pairs = [(query, c["content"]) for c in chunks]
        scores = await asyncio.to_thread(self._model.compute_score, pairs)

        if isinstance(scores, float):
            scores = [scores]

        ranked = []
        for i in range(len(chunks)):
            metadata = chunks[i].get("metadata", {})
            ranked.append(
                RankedChunk(
                    chunk_id=chunks[i]["id"],
                    content=chunks[i]["content"],
                    score=self._apply_section_bias(query, float(scores[i]), chunks[i]),
                    original_rank=i,
                    metadata=metadata,
                )
            )
        ranked.sort(key=lambda r: r.score, reverse=True)
        return ranked[:top_k]

    def _fallback(self, query: str, chunks: list[dict], top_k: int) -> list[RankedChunk]:
        query_terms = self._tokenize(query)
        ranked = []
        for i, chunk in enumerate(chunks):
            score = self._fallback_score(query, query_terms, chunk, i)
            ranked.append(
                RankedChunk(
                    chunk_id=chunk["id"],
                    content=chunk["content"],
                    score=score,
                    original_rank=i,
                    metadata=chunk.get("metadata", {}),
                )
            )

        ranked.sort(key=lambda item: (item.score, -item.original_rank), reverse=True)
        return ranked[:top_k]

    def _fallback_score(
        self,
        query: str,
        query_terms: set[str],
        chunk: dict,
        original_rank: int,
    ) -> float:
        chunk_content = chunk.get("content", "")
        metadata = chunk.get("metadata", {})
        searchable_text = " ".join(
            [
                chunk_content,
                str(metadata.get("document_title", "")),
                str(metadata.get("section_path", "")),
                str(metadata.get("section", "")),
                str(metadata.get("block_type", "")),
            ]
        ).lower()
        content_terms = self._tokenize(searchable_text)

        overlap = len(query_terms & content_terms)
        overlap_ratio = overlap / max(1, len(query_terms))
        exact_phrase_bonus = 0.2 if query.strip().lower() in searchable_text else 0.0
        section_bonus = 0.08 if metadata.get("section") else 0.0
        original_rank_bonus = max(0.0, 0.15 - (original_rank * 0.01))
        section_bias = self._resolve_section_bias(query, chunk)
        entity_bonus = self._entity_match_bonus(query, chunk)
        lexical_bonus = min(float(metadata.get("lexical_score") or 0.0) * 0.08, 0.16)

        return (
            overlap_ratio
            + exact_phrase_bonus
            + section_bonus
            + original_rank_bonus
            + section_bias
            + entity_bonus
            + lexical_bonus
        )

    def _apply_section_bias(self, query: str, base_score: float, chunk: dict) -> float:
        return (
            base_score
            + (self._resolve_section_bias(query, chunk) * 1.5)
            + self._entity_match_bonus(query, chunk)
        )

    @staticmethod
    def _resolve_section_bias(query: str, chunk: dict) -> float:
        metadata = chunk.get("metadata", {})
        if "section_relevance_bias" in metadata:
            return float(metadata["section_relevance_bias"])

        policy = evaluate_chunk_policy(query, chunk.get("content", ""), metadata)
        return policy.relevance_bias

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return {
            token
            for token in re.findall(r"\w+", text.lower())
            if len(token) > 2 and token not in _STOP_WORDS
        }

    @classmethod
    def _entity_match_bonus(cls, query: str, chunk: dict) -> float:
        metadata = chunk.get("metadata", {})
        searchable_text = " ".join(
            [
                str(chunk.get("content", "")),
                str(metadata.get("document_title", "")),
                str(metadata.get("section_path", "")),
                str(metadata.get("section", "")),
            ]
        ).lower()
        query_lower = query.lower()
        bonus = 0.0

        exact_entities = re.findall(
            r"[\w.+-]+@[\w.-]+\.\w+|github(?:\.com)?/[^\s,]+|linkedin(?:\.com)?/[^\s,]+|\+?\d[\d\s().-]{7,}\d",
            query_lower,
        )
        for entity in exact_entities:
            if entity in searchable_text:
                bonus += 0.18

        priority_terms = [
            term
            for term in cls._tokenize(query_lower)
            if term not in {"resume", "profile", "document", "question"}
        ]
        exact_matches = sum(1 for term in priority_terms if term in searchable_text)
        bonus += min(exact_matches * 0.04, 0.22)

        semantic_families = (
            (("skill", "ky nang", "technology", "tool", "framework", "language"), 0.08),
            (("company", "experience", "kinh nghiem", "organization", "vendor", "customer", "party"), 0.08),
            (("education", "hoc van", "university", "degree", "major", "certification"), 0.06),
            (("step", "procedure", "workflow", "setup", "install", "instruction", "configuration"), 0.07),
            (("requirement", "criteria", "must", "shall", "condition", "clause", "term", "policy"), 0.07),
            (("date", "deadline", "duration", "timeline", "schedule", "milestone"), 0.06),
            (("result", "metric", "score", "accuracy", "performance", "amount", "budget", "total"), 0.06),
        )
        for markers, family_bonus in semantic_families:
            if any(marker in query_lower for marker in markers) and any(
                marker in searchable_text for marker in markers
            ):
                bonus += family_bonus

        return bonus


@lru_cache(maxsize=1)
def get_reranking_service() -> RerankingService:
    """Return cached reranking service instance."""
    return RerankingService()
