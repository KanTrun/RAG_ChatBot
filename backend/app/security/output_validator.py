"""Output validation: detect canary leaks and format issues."""

import logging

from app.security.prompt_guard import CANARY_TOKEN

logger = logging.getLogger(__name__)


def validate_output(response: str) -> tuple[bool, str | None]:
    """Validate LLM output. Returns (is_valid, reason_if_invalid)."""
    if not response or not response.strip():
        return True, None

    # Check canary token leak (system prompt exfiltration)
    if CANARY_TOKEN in response:
        logger.error("Canary token detected in LLM output — potential prompt leak")
        return False, "system_prompt_leak"

    # Check for raw system instruction fragments
    suspicious_fragments = [
        "<system_instructions>",
        "</system_instructions>",
        "Internal verification token:",
    ]
    for fragment in suspicious_fragments:
        if fragment in response:
            logger.warning(f"Suspicious fragment in output: {fragment}")
            return False, "suspicious_content"

    return True, None


def safe_response(response: str) -> str:
    """Return response if valid, or a safe fallback."""
    is_valid, reason = validate_output(response)
    if is_valid:
        return response
    logger.error(f"Output validation failed: {reason}")
    return "I'm sorry, I encountered an issue generating a response. Please try again."
