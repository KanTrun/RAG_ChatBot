"""Build answer briefs from selected grounded sources."""

from __future__ import annotations

from collections import defaultdict
import re

from app.services.context_assembler import SourceReference
from app.services.evidence_clusterer import SUMMARY_AXIS_CONFIG


def build_answer_brief(
    intent: str,
    sources: list[SourceReference],
    *,
    query: str | None = None,
    low_confidence: bool = False,
) -> str | None:
    """Create a structured evidence map for the answer composer."""
    if not sources and not low_confidence:
        return None

    if _should_use_profile_brief(intent, query):
        return _build_profile_brief(sources, query=query)

    if intent == "summary":
        return _build_summary_brief(sources, query=query)

    if intent in {"factual", "definition", "extract", "multi_hop", "compare", "question"}:
        return _build_claim_brief(intent, sources, query=query, low_confidence=low_confidence)

    return None


def build_profile_support_map(
    sources: list[SourceReference],
    *,
    query: str | None = None,
) -> dict[str, dict]:
    field_specs = {
        "name": ("Name", {"profile_name"}, (" name", "candidate", "full name")),
        "role_title": ("Role/title", {"profile_current_role"}, ("headline", "position", "title", "role")),
        "contacts": ("Contacts", {"profile_contacts"}, ("contact", "email", "phone", "github", "linkedin")),
        "skills_tools": ("Skills/tools", {"profile_skills"}, ("skill", "tool", "technology", "framework", "language")),
        "experience": ("Experience", {"profile_experience"}, ("experience", "employment", "company", "responsibility")),
        "projects": ("Projects", {"profile_projects"}, ("project", "product", "achievement", "portfolio")),
        "education": ("Education", {"profile_education"}, ("education", "university", "degree", "major")),
        "certifications": ("Certifications", {"profile_certifications"}, ("certification", "certificate", "course", "license")),
    }
    support_map = {
        field: {"title": title, "citations": [], "evidence": [], "supported": False}
        for field, (title, _labels, _markers) in field_specs.items()
    }

    for source in sources:
        labels = {label.lower() for label in (source.coverage_labels or [])}
        searchable = " ".join(
            part
            for part in (
                source.section_path or "",
                source.section or "",
                source.excerpt or "",
                source.document_title or "",
            )
            if part
        ).lower()
        contact_values = _extract_contact_values(source.excerpt or "")
        evidence_text = _build_profile_evidence_text(source, contact_values)
        citation = source.citation_number

        for field, (_title, field_labels, field_markers) in field_specs.items():
            if labels.intersection(field_labels) or any(marker in searchable for marker in field_markers):
                entry = support_map[field]
                if citation not in entry["citations"]:
                    entry["citations"].append(citation)
                if evidence_text and evidence_text not in entry["evidence"]:
                    entry["evidence"].append(evidence_text)
                entry["supported"] = True

    return support_map


def build_section_support_map(
    sources: list[SourceReference],
    *,
    limit: int = 8,
) -> dict[str, dict]:
    support_map: dict[str, dict] = {}

    for source in sources:
        key = (
            source.answer_section
            or source.section_path
            or source.block_type
            or source.section
            or source.document_title
        )
        if not key:
            continue

        title = source.section_path or source.section or source.block_type or source.document_title
        entry = support_map.setdefault(
            str(key),
            {
                "title": title,
                "block_type": source.block_type,
                "citations": [],
                "evidence": [],
                "supported": True,
            },
        )
        if source.citation_number not in entry["citations"]:
            entry["citations"].append(source.citation_number)
        evidence_text = source.excerpt or source.section_path or source.document_title
        if evidence_text and evidence_text not in entry["evidence"]:
            entry["evidence"].append(evidence_text)

    ordered_items = sorted(
        support_map.items(),
        key=lambda item: (
            -len(item[1]["citations"]),
            -len(item[1]["evidence"]),
            item[1]["title"] or "",
        ),
    )[:limit]
    return {key: value for key, value in ordered_items}


def _is_profile_query(query: str | None) -> bool:
    if not query:
        return False
    normalized = query.lower()
    return any(marker in normalized for marker in ("cv", "resume", "ho so", "profile"))


def _should_use_profile_brief(intent: str, query: str | None) -> bool:
    if not _is_profile_query(query):
        return False
    if intent == "summary":
        return True
    if not query:
        return False
    normalized = query.lower()
    return intent in {"extract", "question"} and any(
        marker in normalized
        for marker in (
            "thong tin",
            "thông tin",
            "information",
            "liet ke",
            "liệt kê",
            "list",
            "overview",
            "tom tat",
            "tóm tắt",
            "summary",
        )
    )


def _summary_axis_titles(query: str | None) -> dict[str, str]:
    if _is_profile_query(query):
        return {
            "topic": "Profile overview",
            "objective_problem": "Objective and experience",
            "method": "Skills and technology",
            "results_contributions": "Projects and achievements",
            "limitations_scope": "Education and supporting details",
        }

    return {axis: title for axis, title, _hint in SUMMARY_AXIS_CONFIG}


def _build_summary_brief(
    sources: list[SourceReference],
    *,
    query: str | None,
) -> str | None:
    if not sources:
        return "Structured evidence brief:\n- Summary evidence is insufficient in the current document context."

    axis_titles = _summary_axis_titles(query)
    lines = [
        "Structured evidence brief:",
        "Use this as the answer map. If a section says evidence is insufficient, say that explicitly instead of filling gaps.",
    ]
    if query:
        lines.append(f"Question focus: {query}")

    for axis, title, _hint in SUMMARY_AXIS_CONFIG:
        rendered_title = axis_titles.get(axis, title)
        matched = [source for source in sources if source.answer_section == axis]
        if not matched:
            lines.append(f"- {rendered_title}: khong tim thay du bang chung trong tai lieu.")
            continue

        citations = " ".join(f"[{source.citation_number}]" for source in matched[:2])
        evidence_parts: list[str] = []
        for source in matched[:2]:
            label = source.section_path or source.section or source.document_title
            if label:
                evidence_parts.append(label)
            if source.excerpt:
                evidence_parts.append(source.excerpt)
        lines.append(
            f"- {rendered_title}: supported by {citations}. Evidence: {' | '.join(evidence_parts[:3])}"
        )

    return "\n".join(lines)


def _build_profile_brief(
    sources: list[SourceReference],
    *,
    query: str | None,
) -> str:
    support_map = build_profile_support_map(sources, query=query)
    lines = [
        "Structured profile support map:",
        "Answer by field. Only state fields that are supported below. For missing fields, say evidence is insufficient.",
    ]
    if query:
        lines.append(f"Question focus: {query}")
    lines.append(
        "Summary lenses: Profile overview | Objective and experience | Skills and technology | Projects and achievements | Education and supporting details."
    )

    for field in (
        "name",
        "role_title",
        "contacts",
        "skills_tools",
        "experience",
        "projects",
        "education",
        "certifications",
    ):
        entry = support_map[field]
        if not entry["supported"]:
            lines.append(f"- {entry['title']}: khong thay du bang chung truc tiep trong tai lieu.")
            continue
        citations = " ".join(f"[{citation}]" for citation in entry["citations"][:3])
        evidence_text = " | ".join(entry["evidence"][:3])
        lines.append(f"- {entry['title']}: supported by {citations}. Evidence: {evidence_text}")

    return "\n".join(lines)


def _build_claim_brief(
    intent: str,
    sources: list[SourceReference],
    *,
    query: str | None,
    low_confidence: bool,
) -> str:
    lines = [
        "Structured evidence brief:",
        "Answer only from the supported evidence map below. If the map is weak, say evidence is insufficient.",
    ]
    if query:
        lines.append(f"Question focus: {query}")

    if low_confidence or not sources:
        lines.append("- Support status: insufficient evidence in the current document context.")
        return "\n".join(lines)

    grouped_sources: dict[str, list[SourceReference]] = defaultdict(list)
    for source in sources:
        key = source.answer_section or source.section_path or source.section or source.document_title
        grouped_sources[key].append(source)

    for key, matched in grouped_sources.items():
        citations = " ".join(f"[{source.citation_number}]" for source in matched[:2])
        excerpt = next((source.excerpt for source in matched if source.excerpt), None)
        label = key.replace("_", " ")
        if excerpt:
            lines.append(f"- {label}: supported by {citations}. Evidence: {excerpt}")
        else:
            lines.append(f"- {label}: supported by {citations}.")

    if intent == "multi_hop" and len(grouped_sources) < 2:
        lines.append("- Cross-section synthesis: insufficient multi-section support; do not over-synthesize.")

    return "\n".join(lines)


def _extract_contact_values(text: str) -> list[str]:
    if not text:
        return []
    patterns = (
        r"[\w.+-]+@[\w.-]+\.\w+",
        r"https?://(?:www\.)?linkedin\.com/[^\s|,]+",
        r"https?://(?:www\.)?github\.com/[^\s|,]+",
        r"(?:\+?\d[\d\s().-]{7,}\d)",
    )
    values: list[str] = []
    for pattern in patterns:
        values.extend(re.findall(pattern, text, flags=re.IGNORECASE))
    deduped: list[str] = []
    seen = set()
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped[:5]


def _build_profile_evidence_text(source: SourceReference, contact_values: list[str]) -> str:
    if contact_values:
        return ", ".join(contact_values)
    if source.excerpt:
        return source.excerpt
    if source.section_path:
        return source.section_path
    return source.document_title
