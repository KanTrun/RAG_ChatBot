"""Output validation: detect canary leaks, strip hallucinated citations, and validate format."""

from __future__ import annotations

import logging
import re

from app.security.prompt_guard import CANARY_TOKEN

logger = logging.getLogger(__name__)

_CITATION_PATTERN = re.compile(r"\[(\d+)\]")


def validate_output(response: str) -> tuple[bool, str | None]:
    """Validate LLM output. Returns (is_valid, reason_if_invalid)."""
    if not response or not response.strip():
        return True, None

    if CANARY_TOKEN in response:
        logger.error("Canary token detected in LLM output — potential prompt leak")
        return False, "system_prompt_leak"

    suspicious_fragments = [
        "<system_instructions>",
        "</system_instructions>",
        "Internal verification token:",
    ]
    for fragment in suspicious_fragments:
        if fragment in response:
            logger.warning("Suspicious fragment in output: %s", fragment)
            return False, "suspicious_content"

    return True, None


def validate_and_clean_citations(
    response: str,
    max_citation_number: int,
) -> tuple[str, list[int]]:
    """Verify all [n] citations in response are within 1..max_citation_number.

    Strips any out-of-range citation [n] (e.g. [9] when only 3 sources exist)
    and returns (cleaned_response, list_of_removed_citation_numbers).
    """
    if not response:
        return response, []

    removed: list[int] = []

    def _replace_match(match: re.Match[str]) -> str:
        num = int(match.group(1))
        if max_citation_number <= 0 or num < 1 or num > max_citation_number:
            removed.append(num)
            return ""
        return match.group(0)

    cleaned = _CITATION_PATTERN.sub(_replace_match, response)
    if removed:
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()
        logger.warning(
            "Removed out-of-range citations %s (valid range: 1..%d)",
            removed,
            max_citation_number,
        )
    return cleaned, removed


def safe_response(response: str, max_citation_number: int | None = None) -> str:
    """Return response if valid (and with valid citations), or a safe fallback."""
    is_valid, reason = validate_output(response)
    if not is_valid:
        logger.error("Output validation failed: %s", reason)
        return "I'm sorry, I encountered an issue generating a response. Please try again."
    if max_citation_number is not None:
        cleaned, _removed = validate_and_clean_citations(response, max_citation_number)
        return cleaned
    return response
