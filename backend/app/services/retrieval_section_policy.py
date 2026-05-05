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
    "skills": ("skill", "skills", "tool", "tools", "technology", "stack", "framework", "ky nang"),
    "experience": ("experience", "employment", "work history", "company", "responsibility", "kinh nghiem"),
    "project": ("project", "product", "achievement", "deliverable", "du an", "thanh tich"),
    "education": ("education", "university", "degree", "major", "hoc van", "truong"),
    "certification": ("certification", "certificate", "course", "license", "chung chi", "khoa hoc"),
    "contact": ("email", "phone", "github", "linkedin", "contact", "lien he", "dien thoai"),
    "current_role": ("current role", "position", "title", "headline", "chuc danh", "vai tro"),
    "procedure": ("procedure", "workflow", "step", "setup", "install", "instruction", "usage", "guide", "configuration"),
    "requirements": ("requirement", "requirements", "criteria", "must", "shall", "condition", "specification"),
    "legal_clause": ("clause", "term", "obligation", "agreement", "contract", "policy", "compliance"),
    "timeline": ("date", "deadline", "duration", "period", "schedule", "timeline", "milestone"),
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
    "skills": SECTION_TARGET_MARKERS["skills"],
    "experience": SECTION_TARGET_MARKERS["experience"],
    "project": SECTION_TARGET_MARKERS["project"],
    "education": SECTION_TARGET_MARKERS["education"],
    "certification": SECTION_TARGET_MARKERS["certification"],
    "contact": SECTION_TARGET_MARKERS["contact"],
    "current_role": SECTION_TARGET_MARKERS["current_role"],
    "procedure": SECTION_TARGET_MARKERS["procedure"],
    "requirements": SECTION_TARGET_MARKERS["requirements"],
    "legal_clause": SECTION_TARGET_MARKERS["legal_clause"],
    "timeline": SECTION_TARGET_MARKERS["timeline"],
}


@dataclass(frozen=True)
class SectionPolicy:
    kind: str
    relevance_bias: float
    reason: str


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
        return SectionPolicy(
            kind=kind,
            relevance_bias=0.28,
            reason=f"query explicitly targets {kind.replace('_', ' ')} evidence",
        )

    bias = _base_bias(kind)
    reasons = [_default_reason(kind)]
    if _is_summary_query(normalized_query):
        if kind == "abstract":
            bias += 0.22
            reasons.append("summary query boosts abstract coverage")
        elif kind in {
            "introduction",
            "problem_statement",
            "method",
            "results",
            "conclusion",
            "limitations_scope",
            "body",
            "skills",
            "experience",
            "project",
            "education",
            "certification",
            "current_role",
            "procedure",
            "requirements",
            "legal_clause",
            "timeline",
        }:
            bias += 0.08
            reasons.append("summary query prefers broad section coverage")

    if kind == "figure_caption" and len(normalized_content.split()) <= 24:
        bias -= 0.12
        reasons.append("short caption penalty")
    if kind == "contact" and kind not in targeted_kinds:
        bias -= 0.24
        reasons.append("contact-only sections are demoted for broader questions")
    if kind == "header_footer":
        bias -= 0.4
        reasons.append("header/footer boilerplate penalty")
    if kind == "cover" and metadata.get("chunk_index") == 0:
        bias -= 0.08
        reasons.append("early cover-page penalty")

    return SectionPolicy(kind=kind, relevance_bias=bias, reason="; ".join(reasons))


def _classify_section_kind(searchable: str, content: str, metadata: dict) -> str:
    if _looks_like_figure_caption(content):
        return "figure_caption"
    if _looks_like_header_footer(searchable, content):
        return "header_footer"
    if _looks_like_contact_card(searchable, content):
        return "contact"
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
        "skills": 0.16,
        "experience": 0.18,
        "project": 0.18,
        "education": 0.12,
        "certification": 0.1,
        "contact": -0.12,
        "current_role": 0.16,
        "procedure": 0.16,
        "requirements": 0.16,
        "legal_clause": 0.14,
        "timeline": 0.12,
        "figure_caption": -0.35,
        "acknowledgement": -0.6,
        "references": -0.72,
        "table_of_contents": -0.85,
        "cover": -0.58,
        "header_footer": -0.52,
    }.get(kind, 0.0)


def _default_reason(kind: str) -> str:
    return {
        "abstract": "abstract sections are usually high-signal for broad questions",
        "introduction": "introduction sections often define scope and framing",
        "problem_statement": "problem statements often contain explicit objectives",
        "method": "method sections usually contain technical answers",
        "results": "results sections usually contain factual outcomes",
        "limitations_scope": "limitations sections help keep grounded scope",
        "conclusion": "conclusion sections often summarize supported findings",
        "body": "body section has neutral prior",
        "appendix": "appendix sections often contain peripheral detail",
        "skills": "skills sections often answer capability questions directly",
        "experience": "experience sections often contain company and responsibility evidence",
        "project": "project sections often contain achievement evidence",
        "education": "education sections contain academic background evidence",
        "certification": "certification sections contain credential evidence",
        "contact": "contact sections are useful only for direct contact-detail questions",
        "current_role": "headline sections often state the candidate's current role",
        "procedure": "procedure sections often answer how-to and workflow questions directly",
        "requirements": "requirements sections often contain constraints and acceptance criteria",
        "legal_clause": "legal or policy clauses often contain explicit obligations and terms",
        "timeline": "timeline sections often contain dates, durations, and sequencing evidence",
        "figure_caption": "captions are usually too narrow without an explicit caption query",
        "acknowledgement": "acknowledgements are boilerplate for content questions",
        "references": "reference lists are boilerplate for content questions",
        "table_of_contents": "table of contents is structural boilerplate",
        "cover": "cover pages are rarely answer-bearing",
        "header_footer": "headers and footers are repetitive boilerplate",
    }.get(kind, "section prior applied")


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


def _looks_like_contact_card(searchable: str, content: str) -> bool:
    compact = " ".join(content.split()).lower()
    if len(compact.split()) > 80:
        return False
    patterns = (
        r"[\w.+-]+@[\w.-]+\.\w+",
        r"(?:\+?\d[\d\s().-]{7,}\d)",
        r"github\.com",
        r"linkedin\.com",
    )
    return any(re.search(pattern, searchable) for pattern in patterns)


def _looks_like_header_footer(searchable: str, content: str) -> bool:
    compact = " ".join(content.split()).lower()
    if not compact or len(compact.split()) > 12:
        return False
    return any(
        marker in searchable
        for marker in ("page ", "trang ", "curriculum vitae", "resume", "confidential")
    )


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()
