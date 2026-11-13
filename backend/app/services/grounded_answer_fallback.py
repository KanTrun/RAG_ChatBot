"""Build a grounded fallback answer directly from retrieved context with language and intent awareness."""

from __future__ import annotations

import re

from app.prompts.system_prompt import detect_query_language
from app.security.prompt_guard import sanitize_context_chunks

_STOP_WORDS = {
    "the", "and", "are", "from", "that", "this", "with", "what", "which", "into",
    "your", "have", "about", "does", "used", "uses", "document", "uploaded", "mentioned",
    "la", "gi", "nhu", "the", "nao", "trong", "cua", "va", "cac", "nhung", "mot",
}


def build_grounded_fallback_answer(
    query: str,
    context_text: str,
    *,
    intent: str | None = None,
) -> str | None:
    """Return a grounded fallback answer when the LLM stream is unavailable."""
    safe_context = sanitize_context_chunks(context_text)
    evidence = _extract_evidence_sentences(safe_context)
    if not evidence:
        return None

    query_terms = {
        token
        for token in re.findall(r"\w+", query.lower())
        if len(token) > 2 and token not in _STOP_WORDS
    }
    ranked = sorted(
        evidence,
        key=lambda item: _sentence_score(item["sentence"], query_terms),
        reverse=True,
    )

    selected: list[dict] = []
    seen_sentences: set[str] = set()
    for item in ranked:
        normalized = item["sentence"].lower()
        if normalized in seen_sentences:
            continue
        selected.append(item)
        seen_sentences.add(normalized)
        if len(selected) == 4:
            break

    if not selected:
        return None

    language = detect_query_language(query)
    lead = _ensure_terminal_punctuation(selected[0]["sentence"])
    lead_citation = f"[{selected[0]['citation']}]"
    support = [
        f"- {_ensure_terminal_punctuation(item['sentence'])} [{item['citation']}]"
        for item in selected[1:]
    ]
    all_citations = "".join(
        f"[{c}]" for c in dict.fromkeys(item["citation"] for item in selected)
    )

    if intent == "compare" and len(selected) >= 2:
        table_rows = [
            "| Nguồn / Mục | Nội dung đối chiếu | Trích dẫn |"
            if language == "vi"
            else "| Source / Aspect | Grounded Comparison Point | Citation |",
            "|---|---|---|",
        ]
        for item in selected:
            source_label = item.get("source") or f"Source {item['citation']}"
            clean_cell = _ensure_terminal_punctuation(item["sentence"]).replace("|", "/")
            table_rows.append(f"| {source_label} | {clean_cell} | [{item['citation']}] |")
        table_block = "\n".join(table_rows)
        if language == "vi":
            return f"{lead} {lead_citation} {all_citations}\n\n{table_block}".strip()
        return (
            f"According to the retrieved document context, {lead} {lead_citation} {all_citations}\n\n"
            f"{table_block}"
        ).strip()

    if language == "vi":
        response = f"{lead} {lead_citation} {all_citations}".strip()
        if support:
            response += "\n\nCác chi tiết từ tài liệu:\n" + "\n".join(support)
        return response

    response = f"According to the retrieved document context, {lead} {lead_citation} {all_citations}".strip()
    if support:
        response += "\n\nSupporting evidence:\n" + "\n".join(support)
    return response


def _extract_evidence_sentences(context_text: str) -> list[dict]:
    current_citation: int | None = None
    current_source: str = ""
    evidence: list[dict] = []

    for raw_line in context_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        header_match = re.match(r"^\[(\d+)\]\s+Source:\s*(.*)$", line)
        if header_match:
            current_citation = int(header_match.group(1))
            current_source = header_match.group(2).strip()
            continue

        if current_citation is None:
            continue

        if line.startswith("#"):
            continue

        for sentence in re.split(r"(?<=[.!?])\s+", line):
            cleaned = sentence.strip()
            if cleaned and not cleaned.startswith("#"):
                evidence.append(
                    {
                        "citation": current_citation,
                        "source": current_source,
                        "sentence": cleaned,
                    }
                )

    return evidence


def _sentence_score(sentence: str, query_terms: set[str]) -> tuple[int, int]:
    tokens = set(re.findall(r"\w+", sentence.lower()))
    overlap = len(tokens & query_terms)
    return overlap, len(sentence)


def _ensure_terminal_punctuation(sentence: str) -> str:
    return sentence if sentence.endswith((".", "!", "?")) else f"{sentence}."
