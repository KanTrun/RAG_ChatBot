"""Structure-aware, block-first chunking for document ingestion."""

from dataclasses import dataclass, field
from uuid import UUID

import tiktoken

from app.services.document_structure import (
    INGESTION_VERSION,
    build_contextualized_chunk_text,
    build_semantic_blocks,
)
from app.services.parsers.base_parser import ParsedPage


@dataclass
class ChunkData:
    """Single chunk with metadata ready for embedding and storage."""

    content: str
    chunk_index: int
    page_number: int | None = None
    section: str | None = None
    token_count: int = 0
    metadata: dict = field(default_factory=dict)
    contextualized_text: str | None = None


class ChunkingEngine:
    """Recursive character splitter with token-based size measurement."""

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        separators: list[str] | None = None,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or ["\n\n", "\n", ". ", " "]
        self._tokenizer = tiktoken.get_encoding("cl100k_base")

    def _count_tokens(self, text: str) -> int:
        return len(self._tokenizer.encode(text))

    def _split_text(self, text: str, separators: list[str]) -> list[str]:
        """Recursively split text by separators until chunks are within size limit."""
        if not text:
            return []

        token_count = self._count_tokens(text)
        if token_count <= self.chunk_size:
            return [text]

        # Find the first separator that actually exists in the text
        chosen_sep = ""
        for sep in separators:
            if sep in text:
                chosen_sep = sep
                break

        if not chosen_sep:
            # No separator found; hard split by tokens
            tokens = self._tokenizer.encode(text)
            chunks = []
            for i in range(0, len(tokens), self.chunk_size - self.chunk_overlap):
                chunk_tokens = tokens[i : i + self.chunk_size]
                chunks.append(self._tokenizer.decode(chunk_tokens))
            return chunks

        # Split by chosen separator
        parts = text.split(chosen_sep)
        remaining_separators = separators[separators.index(chosen_sep) + 1 :]

        # Merge parts into chunks that fit within size limit
        chunks: list[str] = []
        current_parts: list[str] = []
        current_tokens = 0

        for part in parts:
            part_tokens = self._count_tokens(part)

            if part_tokens > self.chunk_size and remaining_separators:
                # Part too large, recursively split with finer separator
                if current_parts:
                    chunks.append(chosen_sep.join(current_parts))
                    current_parts = []
                    current_tokens = 0
                chunks.extend(self._split_text(part, remaining_separators))
                continue

            if current_tokens + part_tokens > self.chunk_size and current_parts:
                chunks.append(chosen_sep.join(current_parts))
                # Keep overlap: retain last part(s) up to overlap token budget
                overlap_parts: list[str] = []
                overlap_tokens = 0
                for p in reversed(current_parts):
                    p_tokens = self._count_tokens(p)
                    if overlap_tokens + p_tokens > self.chunk_overlap:
                        break
                    overlap_parts.insert(0, p)
                    overlap_tokens += p_tokens
                current_parts = overlap_parts
                current_tokens = overlap_tokens

            current_parts.append(part)
            current_tokens += part_tokens

        if current_parts:
            chunks.append(chosen_sep.join(current_parts))

        return [c.strip() for c in chunks if c.strip()]

    def chunk_document(
        self, pages: list[ParsedPage], document_id: UUID
    ) -> list[ChunkData]:
        """Split parsed pages into semantic chunks with structural metadata."""
        chunks: list[ChunkData] = []
        chunk_index = 0

        for block in build_semantic_blocks(pages):
            page_chunks = self._split_text(block.text, self.separators)
            for child_index, chunk_text in enumerate(page_chunks):
                token_count = self._count_tokens(chunk_text)
                metadata = {
                    **block.metadata,
                    "document_id": str(document_id),
                    "block_id": block.block_id,
                    "parent_block_id": block.parent_block_id,
                    "block_type": block.block_type,
                    "section_path": " > ".join(block.section_path),
                    "heading_level": block.heading_level,
                    "page_start": block.page_start,
                    "page_end": block.page_end,
                    "child_chunk_index": child_index,
                    "ingestion_version": INGESTION_VERSION,
                }
                contextualized_text = build_contextualized_chunk_text(chunk_text, metadata)
                metadata["contextualized_text"] = contextualized_text
                chunks.append(
                    ChunkData(
                        content=chunk_text,
                        chunk_index=chunk_index,
                        page_number=block.page_start,
                        section=block.section_path[-1] if block.section_path else block.metadata.get("section"),
                        token_count=token_count,
                        metadata=metadata,
                        contextualized_text=contextualized_text,
                    )
                )
                chunk_index += 1

        return chunks
