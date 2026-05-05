"""Section-aware retrieval heuristics for suppressing boilerplate chunks."""

from __future__ import annotations

from dataclasses import dataclass
import re


SUMMARY_QUERY_MARKERS = (
    "summary",
    "summarize",
    "overview",
    "abstract",
    "tom tat",
    "tóm tắt",
    "noi dung chinh",
    "nội dung chính",
    "dai y",
    "đại ý",
)

SECTION_TARGET_MARKERS: dict[str, tuple[str, ...]] = {
    "acknowledgement": ("acknowledg", "loi cam on", "lời cảm ơn", "thanks"),
    "references": ("reference", "bibliograph", "works cited", "tai lieu tham khao", "tài liệu tham khảo"),
    "table_of_contents": ("table of contents", "contents", "muc luc", "mục lục"),
    "figure_caption": ("figure", "fig.", "hinh", "hình", "table", "bang", "bảng", "chart", "caption"),
    "appendix": ("appendix", "phu luc", "phụ lục", "annex"),
    "problem_statement": ("problem", "objective", "muc tieu", "mục tiêu", "bai toan", "bài toán"),
    "method": ("method", "methodology", "approach", "phuong phap", "phương pháp"),
    "results": ("result", "evaluation", "experiment", "ket qua", "kết quả", "danh gia", "đánh giá"),
}

SECTION_KIND_MARKERS: dict[str, tuple[str, ...]] = {
    "abstract": ("abstract", "executive summary", "tom tat", "tóm tắt", "overview"),
    "introduction": ("introduction", "background", "mo dau", "mở đầu", "gioi thieu", "giới thiệu"),
    "problem_statement": SECTION_TARGET_MARKERS["problem_statement"],
    "method": SECTION_TARGET_MARKERS["method"],
    "results": SECTION_TARGET_MARKERS["results"],
    "limitations_scope": ("limitation", "constraint", "scope", "gioi han", "giới hạn"),
    "conclusion": ("conclusion", "closing", "ket luan", "kết luận", "final remarks"),
    "acknowledgement": SECTION_TARGET_MARKERS["acknowledgement"],
    "references": SECTION_TARGET_MARKERS["references"],
    "table_of_contents": SECTION_TARGET_MARKERS["table_of_contents"],
    "appendix": SECTION_TARGET_MARKERS["appendix"],
}


@dataclass(frozen=True)
class SectionPolicy:
    kind: str
    relevance_bias: float


def evaluate_chunk_policy(query: str, content: str, metadata: dict | None = None) -> SectionPolicy:
    """Return a small relevance prior based on the likely section type."""
    metadata = metadata or {}
    normalized_query = _normalize(query)
    normalized_content = _normalize(content)
    normalized_section = _normalize(
        " ".join(
            part
            for part in (
                str(metadata.get("section_path") or ""),
                str(metadata.get("section") or ""),
            )
            if part
        )
    )
    searchable = " ".join(part for part in (normalized_section, normalized_content[:500]) if part)

    explicit_block_type = str(metadata.get("block_type") or "").strip()
    kind = explicit_block_type or _classify_section_kind(searchable, normalized_content, metadata)
    targeted_kinds = _query_targets(normalized_query)

    if kind in targeted_kinds:
        return SectionPolicy(kind=kind, relevance_bias=0.28)

    bias = _base_bias(kind)
    if _is_summary_query(normalized_query):
        if kind == "abstract":
            bias += 0.22
        elif kind in {
            "introduction",
            "problem_statement",
            "method",
            "results",
            "conclusion",
            "limitations_scope",
            "body",
        }:
            bias += 0.08

    if kind == "figure_caption" and len(normalized_content.split()) <= 24:
        bias -= 0.12
    if kind == "cover" and metadata.get("chunk_index") == 0:
        bias -= 0.08

    return SectionPolicy(kind=kind, relevance_bias=bias)


def _classify_section_kind(searchable: str, content: str, metadata: dict) -> str:
    if _looks_like_figure_caption(content):
        return "figure_caption"
    if _looks_like_cover_page(searchable, content, metadata):
        return "cover"

    for kind, markers in SECTION_KIND_MARKERS.items():
        if any(marker in searchable for marker in markers):
            return kind

    return "body"


def _query_targets(query: str) -> set[str]:
    return {
        kind
        for kind, markers in SECTION_TARGET_MARKERS.items()
        if any(marker in query for marker in markers)
    }


def _base_bias(kind: str) -> float:
    return {
        "abstract": 0.18,
        "introduction": 0.08,
        "problem_statement": 0.14,
        "method": 0.16,
        "results": 0.16,
        "limitations_scope": 0.1,
        "conclusion": 0.12,
        "body": 0.06,
        "appendix": -0.08,
        "figure_caption": -0.35,
        "acknowledgement": -0.6,
        "references": -0.72,
        "table_of_contents": -0.85,
        "cover": -0.58,
    }.get(kind, 0.0)


def _is_summary_query(query: str) -> bool:
    return any(marker in query for marker in SUMMARY_QUERY_MARKERS)


def _looks_like_cover_page(searchable: str, content: str, metadata: dict) -> bool:
    if metadata.get("chunk_index") not in {0, 1}:
        return False
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if len(lines) > 12:
        return False
    return any(
        term in searchable
        for term in ("university", "faculty", "student", "advisor", "supervisor", "thesis", "luan van", "đề tài", "de tai")
    )


def _looks_like_figure_caption(content: str) -> bool:
    compact = " ".join(content.split()).lower()
    if not compact:
        return False
    prefixes = ("figure ", "fig. ", "fig ", "table ", "chart ", "hinh ", "hình ", "bang ", "bảng ")
    return any(compact.startswith(prefix) for prefix in prefixes)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()
