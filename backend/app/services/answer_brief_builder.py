"""Build answer briefs from selected grounded sources."""

from __future__ import annotations

from app.services.context_assembler import SourceReference
from app.services.evidence_clusterer import SUMMARY_AXIS_CONFIG


def build_answer_brief(intent: str, sources: list[SourceReference]) -> str | None:
    """Create a structured evidence map for the answer composer."""
    if intent != "summary" or not sources:
        return None

    lines = [
        "Structured evidence brief:",
        "Use this as the answer map. If a section says evidence is insufficient, say that explicitly instead of filling gaps.",
    ]

    for axis, title, _hint in SUMMARY_AXIS_CONFIG:
        matched = [source for source in sources if source.answer_section == axis]
        if not matched:
            lines.append(f"- {title}: khong tim thay du bang chung trong tai lieu.")
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
            f"- {title}: supported by {citations}. Evidence: {' | '.join(evidence_parts[:3])}"
        )

    return "\n".join(lines)
