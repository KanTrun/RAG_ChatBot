"""Prompt injection detection and structural hardening."""

import re
import logging

logger = logging.getLogger(__name__)

# Patterns commonly used in prompt injection attempts
_INJECTION_PATTERNS = [
    r"(?i)ignore\s+(all\s+)?previous\s+instructions",
    r"(?i)ignore\s+(all\s+)?above",
    r"(?i)disregard\s+(all\s+)?prior",
    r"(?i)you\s+are\s+now\s+(?:a|an|the)",
    r"(?i)new\s+system\s+prompt",
    r"(?i)override\s+system",
    r"(?i)forget\s+everything",
    r"(?i)\bsystem:\s*",
    r"(?i)act\s+as\s+(if\s+)?you",
    r"(?i)pretend\s+(that\s+)?you",
]

_compiled_patterns = [re.compile(p) for p in _INJECTION_PATTERNS]

# Canary token embedded in system prompts for leak detection
CANARY_TOKEN = "<<CANARY_7f3a2b1e>>"


def check_injection(text: str) -> bool:
    """Return True if text contains likely prompt injection patterns."""
    for pattern in _compiled_patterns:
        if pattern.search(text):
            logger.warning(f"Prompt injection pattern detected: {pattern.pattern}")
            return True
    return False


def sanitize_input(text: str) -> str:
    """Light sanitization: normalize whitespace, strip control chars."""
    # Remove null bytes and control characters (except newline/tab)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return text.strip()


def build_hardened_prompt(
    system_prompt: str,
    context: str,
    user_query: str,
) -> list[dict]:
    """Build structurally hardened prompt with XML delimiters."""
    system_with_canary = f"{system_prompt}\n\nInternal verification token: {CANARY_TOKEN}"

    system_content = f"""<system_instructions>
{system_with_canary}
</system_instructions>"""

    user_content = f"""<retrieved_context>
{context}
</retrieved_context>

<user_query>
{user_query}
</user_query>"""

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]
