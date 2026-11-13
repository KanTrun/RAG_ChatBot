"""Prompt injection detection, chunk sanitization, and structural hardening."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Patterns commonly used in prompt injection attempts (English + Vietnamese)
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
    r"(?i)bỏ\s+qua\s+(mọi\s+|tất\s+cả\s+)?hướng\s+dẫn\s+trước",
    r"(?i)quên\s+hết\s+chỉ\s+thị",
]

_compiled_patterns = [re.compile(p) for p in _INJECTION_PATTERNS]

# Canary token embedded in system prompts for leak detection
CANARY_TOKEN = "<<CANARY_7f3a2b1e>>"


def check_injection(text: str) -> bool:
    """Return True if text contains likely prompt injection patterns."""
    if not text:
        return False
    for pattern in _compiled_patterns:
        if pattern.search(text):
            logger.warning("Prompt injection pattern detected: %s", pattern.pattern)
            return True
    return False


def sanitize_input(text: str) -> str:
    """Light sanitization: normalize whitespace, strip control chars."""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text or "")
    return text.strip()


def sanitize_context_chunks(context_text: str) -> str:
    """Neutralize prompt injection directives embedded inside retrieved document chunks.

    Preserves surrounding factual content while disarming imperative override strings
    and escaping raw XML delimiter tags.
    """
    if not context_text:
        return ""

    sanitized = context_text.replace("</retrieved_context>", "[/retrieved_context]")
    sanitized = sanitized.replace("<system_instructions>", "[system_instructions]")
    sanitized = sanitized.replace("</system_instructions>", "[/system_instructions]")

    for pattern in _compiled_patterns:
        sanitized = pattern.sub("[untrusted-document-directive-ignored]", sanitized)

    return sanitized


def build_hardened_prompt(
    system_prompt: str,
    context: str,
    user_query: str,
) -> list[dict]:
    """Build structurally hardened prompt with XML delimiters and sanitized context."""
    system_with_canary = f"{system_prompt}\n\nInternal verification token: {CANARY_TOKEN}"

    system_content = f"""<system_instructions>
{system_with_canary}
</system_instructions>"""

    safe_context = sanitize_context_chunks(context)
    user_content = f"""<retrieved_context>
{safe_context}
</retrieved_context>

<user_query>
{sanitize_input(user_query)}
</user_query>"""

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]
