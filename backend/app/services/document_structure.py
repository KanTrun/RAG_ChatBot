"""Structure-aware document helpers for block-first ingestion."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import re

from app.services.parsers.base_parser import ParsedPage

INGESTION_VERSION = "document-first-v2"

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_NUMBERED_HEADING_RE = re.compile(r"^(\d+(?:\.\d+)*)[\).\s-]+(.+)$")
_TOC_RE = re.compile(r"\.{2,}\s*\d+$")

_BLOCK_TYPE_MARKERS: dict[str, tuple[str, ...]] = {
    "abstract": ("abstract", "tom tat", "tóm tắt", "executive summary"),
    "introduction": ("introduction", "gioi thieu", "giới thiệu", "mo dau", "mở đầu"),
    "problem_statement": (
        "problem statement",
        "research problem",
        "muc tieu",
        "mục tiêu",
        "bai toan",
        "bài toán",
        "objective",
        "scope",
    ),
    "method": ("method", "methodology", "approach", "phuong phap", "phương pháp"),
    "results": (
        "result",
        "evaluation",
        "experiment",
        "discussion",
        "ket qua",
        "kết quả",
        "danh gia",
        "đánh giá",
    ),
    "conclusion": ("conclusion", "ket luan", "kết luận", "closing", "future work"),
    "acknowledgement": ("acknowledg", "loi cam on", "lời cảm ơn", "thanks"),
    "references": ("reference", "bibliograph", "tai lieu tham khao", "tài liệu tham khảo"),
    "appendix": ("appendix", "annex", "phu luc", "phụ lục"),
    "table_of_contents": ("table of contents", "contents", "muc luc", "mục lục"),
    "limitations_scope": ("limitation", "scope", "constraint", "gioi han", "giới hạn"),
}


@dataclass
class SemanticBlock:
    """A structure-aware semantic block extracted from one or more pages."""

    block_id: str
    parent_block_id: str
    text: str
    section_path: list[str] = field(default_factory=list)
    block_type: str = "body"
    heading_level: int | None = None
    page_start: int | None = None
    page_end: int | None = None
    metadata: dict = field(default_factory=dict)


def build_semantic_blocks(pages: list[ParsedPage]) -> list[SemanticBlock]:
    """Convert parsed pages into structure-aware semantic blocks."""
    blocks: list[SemanticBlock] = []
    outline_path: list[str] = []
    block_counter = 0

    for page in pages:
        title = str(page.metadata.get("title") or "").strip()
        if not outline_path and title:
            outline_path = [title]

        seeded_path = _seed_section_path(outline_path, page.metadata)
        current_path = seeded_path[:]
        current_level = len(current_path) - 1 if current_path else None
        current_lines: list[str] = []

        def flush() -> None:
            nonlocal block_counter
            text = "\n".join(current_lines).strip()
            if not text:
                current_lines.clear()
                return

            block_counter += 1
            section_path = current_path[:] or outline_path[:] or ["Document"]
            block_type = detect_block_type(section_path, text, block_counter, page.page_number)
            parent_block_id = _stable_identifier(
                "parent",
                "|".join(section_path),
                block_type,
            )
            block_id = _stable_identifier(
                "block",
                parent_block_id,
                str(page.page_number or 0),
                str(block_counter),
            )
            blocks.append(
                SemanticBlock(
                    block_id=block_id,
                    parent_block_id=parent_block_id,
                    text=text,
                    section_path=section_path,
                    block_type=block_type,
                    heading_level=current_level,
                    page_start=page.page_number,
                    page_end=page.page_number,
                    metadata={
                        **page.metadata,
                        "section": section_path[-1] if section_path else None,
                    },
                )
            )
            current_lines.clear()

        for raw_line in page.text.splitlines():
            line = raw_line.strip()
            heading = detect_heading(line)
            if heading:
                flush()
                level, heading_text = heading
                if outline_path:
                    current_path = outline_path[:]
                else:
                    current_path = []
                current_path = _apply_heading(current_path, level, heading_text)
                current_level = level
                outline_path = current_path[:]
                continue

            if not line:
                flush()
                continue

            current_lines.append(raw_line.rstrip())

        flush()

    return blocks


def build_contextualized_chunk_text(content: str, metadata: dict) -> str:
    """Prepend structural context to chunk text before embedding."""
    title = str(metadata.get("title") or metadata.get("document_title") or "").strip()
    section_path = str(metadata.get("section_path") or metadata.get("section") or "").strip()
    block_type = str(metadata.get("block_type") or "body").replace("_", " ")
    page_start = metadata.get("page_start")
    page_end = metadata.get("page_end")

    context_lines = []
    if title:
        context_lines.append(f"Document title: {title}")
    if section_path:
        context_lines.append(f"Section path: {section_path}")
    context_lines.append(f"Block type: {block_type}")
    if page_start is not None:
        page_label = f"{page_start}" if page_start == page_end or page_end is None else f"{page_start}-{page_end}"
        context_lines.append(f"Page range: {page_label}")
    context_lines.append("Chunk text:")
    context_lines.append(content.strip())
    return "\n".join(context_lines)


def detect_block_type(
    section_path: list[str],
    text: str,
    block_index: int,
    page_number: int | None,
) -> str:
    """Classify a semantic block by section label and content hints."""
    normalized_path = _normalize(" ".join(section_path))
    normalized_text = _normalize(text)
    searchable = f"{normalized_path} {normalized_text[:400]}".strip()

    if _looks_like_table_of_contents(text):
        return "table_of_contents"
    if _looks_like_figure_caption(text):
        return "figure_caption"
    if _looks_like_cover_page(searchable, text, block_index, page_number):
        return "cover"

    for block_type, markers in _BLOCK_TYPE_MARKERS.items():
        if any(marker in searchable for marker in markers):
            return block_type

    return "body"


def detect_heading(line: str) -> tuple[int, str] | None:
    """Detect heading lines and infer a heading level."""
    if not line or len(line) > 120:
        return None

    markdown_match = _HEADING_RE.match(line)
    if markdown_match:
        return len(markdown_match.group(1)), markdown_match.group(2).strip(" :")

    numbered_match = _NUMBERED_HEADING_RE.match(line)
    if numbered_match:
        level = min(numbered_match.group(1).count(".") + 1, 6)
        return level, numbered_match.group(2).strip(" :")

    if line.upper() == line and any(char.isalpha() for char in line) and not line.endswith((".", "!", "?")):
        return 1, line.strip(" :")

    if line == line.title() and len(line.split()) <= 10 and not line.endswith((".", "!", "?")):
        return 2, line.strip(" :")

    return None


def _seed_section_path(outline_path: list[str], metadata: dict) -> list[str]:
    title = str(metadata.get("title") or "").strip()
    section = str(metadata.get("section") or "").strip()
    path = outline_path[:] or ([title] if title else [])
    if section and section not in {"Document", title}:
        path = _apply_heading(path, max(2, len(path) + 1), section)
    return path


def _apply_heading(current_path: list[str], level: int, heading_text: str) -> list[str]:
    base = current_path[: max(0, level - 1)]
    base.append(heading_text.strip())
    return [item for item in base if item]


def _looks_like_table_of_contents(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 3:
        return False
    toc_hits = sum(1 for line in lines[:8] if _TOC_RE.search(line))
    return toc_hits >= 2


def _looks_like_figure_caption(text: str) -> bool:
    compact = " ".join(text.split()).lower()
    if not compact:
        return False
    prefixes = ("figure ", "fig. ", "fig ", "table ", "chart ", "hình ", "bang ", "bảng ")
    return any(compact.startswith(prefix) for prefix in prefixes)


def _looks_like_cover_page(
    searchable: str,
    text: str,
    block_index: int,
    page_number: int | None,
) -> bool:
    if block_index > 2 and (page_number or 1) > 1:
        return False
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) > 12:
        return False
    return any(
        term in searchable
        for term in ("university", "faculty", "student", "advisor", "supervisor", "thesis", "đề tài", "de tai")
    )


def _stable_identifier(*parts: str) -> str:
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()
    return digest[:16]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()
