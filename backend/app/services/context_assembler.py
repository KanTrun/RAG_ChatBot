"""Context assembler: orders chunks, deduplicates, adds citations."""

import logging
from dataclasses import dataclass, field

import tiktoken

from app.services.reranking_service import RankedChunk

logger = logging.getLogger(__name__)

_enc = tiktoken.get_encoding("cl100k_base")


@dataclass
class SourceReference:
    """Citation source metadata for a single chunk."""

    citation_number: int
    document_title: str
    file_name: str
    page_number: int | None
    section: str | None
    chunk_id: str
    score: float
    section_path: str | None = None
    block_type: str | None = None
    excerpt: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    parent_block_id: str | None = None
    heading_level: int | None = None
    ingestion_version: str | None = None
    selection_reason: str | None = None
    answer_section: str | None = None
    coverage_labels: list[str] | None = None


@dataclass
class AssembledContext:
    """Final assembled context ready for LLM consumption."""

    context_text: str
    sources: list[SourceReference] = field(default_factory=list)
    total_tokens: int = 0
    answer_brief: str | None = None
    diagnostics: dict = field(default_factory=dict)


class ContextAssembler:
    """Assembles reranked chunks into a formatted context block with citations."""

    def __init__(self, max_tokens: int = 3000):
        self.max_tokens = max_tokens

    def assemble(
        self,
        ranked_chunks: list[RankedChunk],
        *,
        prefer_document_order: bool = False,
        max_tokens: int | None = None,
    ) -> AssembledContext:
        """Build context text with numbered citations from ranked chunks.

        Chunks are already sorted by reranker score (highest first).
        Deduplicates exact-substring overlaps and enforces token budget.
        """
        if not ranked_chunks:
            return AssembledContext(context_text="", sources=[], total_tokens=0)

        # Deduplicate near-identical content (exact substring check)
        unique_chunks = self._deduplicate(ranked_chunks)
        if prefer_document_order:
            unique_chunks = sorted(
                unique_chunks,
                key=lambda chunk: (
                    chunk.metadata.get("document_title", ""),
                    chunk.metadata.get("page_number") or 0,
                    chunk.metadata.get("chunk_index") or 0,
                    chunk.original_rank,
                ),
            )

        context_parts: list[str] = []
        sources: list[SourceReference] = []
        total_tokens = 0
        token_budget = max_tokens or self.max_tokens

        for i, chunk in enumerate(unique_chunks):
            citation_num = i + 1
            meta = chunk.metadata
            doc_title = meta.get("document_title", "Unknown")
            file_name = meta.get("file_name", "")
            page = meta.get("page_number")
            section = meta.get("section")
            section_path = meta.get("section_path")
            block_type = meta.get("block_type")
            page_start = meta.get("page_start") or page
            page_end = meta.get("page_end") or page

            # Format chunk with citation header
            header_parts = [f"[{citation_num}] Source: {doc_title}"]
            if page_start is not None:
                page_label = f"{page_start}" if page_start == page_end or page_end is None else f"{page_start}-{page_end}"
                header_parts.append(f"Page {page_label}")
            if section_path:
                header_parts.append(f"Section: {section_path}")
            elif section:
                header_parts.append(f"Section: {section}")
            if block_type:
                header_parts.append(f"Type: {block_type}")
            header = " | ".join(header_parts)

            block = f"{header}\n{chunk.content}\n"

            # Check token budget
            block_tokens = len(_enc.encode(block))
            if total_tokens + block_tokens > token_budget:
                # Try to fit a truncated version
                remaining = token_budget - total_tokens
                if remaining > 50:
                    tokens = _enc.encode(block)[:remaining]
                    block = _enc.decode(tokens)
                    context_parts.append(block)
                    total_tokens += remaining
                    sources.append(
                        SourceReference(
                            citation_number=citation_num,
                            document_title=doc_title,
                            file_name=file_name,
                            page_number=page,
                            section=section,
                            section_path=section_path,
                            block_type=block_type,
                            chunk_id=chunk.chunk_id,
                            score=chunk.score,
                            excerpt=self._build_excerpt(chunk.content),
                            page_start=page_start,
                            page_end=page_end,
                            parent_block_id=meta.get("parent_block_id"),
                            heading_level=meta.get("heading_level"),
                            ingestion_version=meta.get("ingestion_version"),
                            selection_reason=meta.get("selection_reason"),
                            answer_section=meta.get("answer_section"),
                            coverage_labels=meta.get("coverage_labels"),
                        )
                    )
                break

            context_parts.append(block)
            total_tokens += block_tokens
            sources.append(
                SourceReference(
                    citation_number=citation_num,
                    document_title=doc_title,
                    file_name=file_name,
                    page_number=page,
                    section=section,
                    section_path=section_path,
                    block_type=block_type,
                    chunk_id=chunk.chunk_id,
                    score=chunk.score,
                    excerpt=self._build_excerpt(chunk.content),
                    page_start=page_start,
                    page_end=page_end,
                    parent_block_id=meta.get("parent_block_id"),
                    heading_level=meta.get("heading_level"),
                    ingestion_version=meta.get("ingestion_version"),
                    selection_reason=meta.get("selection_reason"),
                    answer_section=meta.get("answer_section"),
                    coverage_labels=meta.get("coverage_labels"),
                )
            )

        return AssembledContext(
            context_text="\n".join(context_parts),
            sources=sources,
            total_tokens=total_tokens,
        )

    @staticmethod
    def _deduplicate(chunks: list[RankedChunk]) -> list[RankedChunk]:
        """Remove chunks whose content is a substring of a higher-ranked chunk."""
        unique: list[RankedChunk] = []
        seen_contents: list[str] = []

        for chunk in chunks:
            content = chunk.content.strip()
            is_dup = False
            for seen in seen_contents:
                # Check if either is a substantial substring of the other
                shorter, longer = sorted([content, seen], key=len)
                if len(shorter) > 50 and shorter in longer:
                    is_dup = True
                    break
            if not is_dup:
                unique.append(chunk)
                seen_contents.append(content)

        return unique

    @staticmethod
    def _build_excerpt(content: str, limit: int = 280) -> str | None:
        normalized = " ".join(content.split())
        if not normalized:
            return None
        if len(normalized) <= limit:
            return normalized
        return normalized[: limit - 3].rstrip() + "..."
