"""Build a grounded fallback answer directly from retrieved context."""

import re

_STOP_WORDS = {
    "the", "and", "are", "from", "that", "this", "with", "what", "which", "into",
    "your", "have", "about", "does", "used", "uses", "document", "uploaded", "mentioned",
}


def build_grounded_fallback_answer(query: str, context_text: str) -> str | None:
    """Return a grounded fallback answer when the LLM stream is unavailable."""
    evidence = _extract_evidence_sentences(context_text)
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
        if len(selected) == 3:
            break

    if not selected:
        return None

    lead = _ensure_terminal_punctuation(selected[0]["sentence"])
    support = [
        f"- {_ensure_terminal_punctuation(item['sentence'])} [{item['citation']}]"
        for item in selected[1:]
    ]
    citations = "".join(f"[{item['citation']}]" for item in selected)

    response = f"According to the retrieved document context, {lead} {citations}".strip()
    if support:
        response += "\n\nSupporting evidence:\n" + "\n".join(support)
    return response


def _extract_evidence_sentences(context_text: str) -> list[dict]:
    current_citation: int | None = None
    evidence: list[dict] = []

    for raw_line in context_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        header_match = re.match(r"^\[(\d+)\]\s+Source:", line)
        if header_match:
            current_citation = int(header_match.group(1))
            continue

        if current_citation is None:
            continue

        for sentence in re.split(r"(?<=[.!?])\s+", line):
            cleaned = sentence.strip()
            if cleaned:
                evidence.append({"citation": current_citation, "sentence": cleaned})

    return evidence


def _sentence_score(sentence: str, query_terms: set[str]) -> tuple[int, int]:
    tokens = set(re.findall(r"\w+", sentence.lower()))
    overlap = len(tokens & query_terms)
    return overlap, len(sentence)


def _ensure_terminal_punctuation(sentence: str) -> str:
    return sentence if sentence.endswith((".", "!", "?")) else f"{sentence}."
