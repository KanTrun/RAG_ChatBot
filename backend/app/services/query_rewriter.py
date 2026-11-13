"""Conditional LLM + rule-based query rewriter for conversational follow-up queries."""

import asyncio
import logging
import re

from app.config import get_settings
from app.services.llm.base_provider import LLMConfig, LLMProvider

logger = logging.getLogger(__name__)

_REWRITE_PROMPT = """Given the conversation history below, rewrite the latest user \
query as a standalone search query in the SAME language as the latest user query.
The rewritten query must:
- Replace pronouns or references (e.g. "it", "that", "its", "nó", "cái đó", "ở trên") with the exact entity/topic from history
- Preserve the user's original intent and language
- Be concise and optimized for hybrid keyword + vector search

If the query is already standalone, return it unchanged.
Return ONLY the rewritten query, nothing else."""

# Contextual reference markers (English & Vietnamese) that indicate a query depends on history
_CONTEXTUAL_PRONOUN_RE = re.compile(
    r"\b("
    r"it|its|that|this|those|these|they|them|their|he|she|his|her|"
    r"what about|how about|and for|also|same|"
    r"nó|của nó|cái đó|điều đó|vấn đề đó|phần đó|mục đó|tài liệu đó|"
    r"ở trên|như trên|vừa nêu|vừa rồi|còn|thế còn|vậy còn|họ|ông ấy|bà ấy"
    r")\b",
    re.IGNORECASE,
)


def needs_contextual_rewrite(query: str, conversation_history: list[dict] | None) -> bool:
    """Return True only when conversation history exists and the query depends on prior context."""
    if not conversation_history:
        return False
    cleaned = query.strip()
    if not cleaned:
        return False
    if _CONTEXTUAL_PRONOUN_RE.search(cleaned):
        return True
    # Very short follow-up fragment (<= 4 words) when prior context exists
    words = cleaned.split()
    if len(words) <= 4 and not cleaned.lower().startswith(("what is", "who is", "define")):
        return True
    return False


def resolve_followup_with_rules(query: str, conversation_history: list[dict]) -> str:
    """Fast deterministic fallback that anchors a follow-up question to the prior user topic."""
    prior_user_msgs = [
        m.get("content", "").strip()
        for m in reversed(conversation_history)
        if m.get("role") == "user" and m.get("content", "").strip()
    ]
    if not prior_user_msgs:
        return query
    last_topic = prior_user_msgs[0]
    # Extract key nouns/entities from the previous question
    topic_clean = re.sub(
        r"^(what is|how does|how do|explain|summarize|compare|tại sao|là gì|tóm tắt|so sánh)\s+",
        "",
        last_topic,
        flags=re.IGNORECASE,
    ).strip(" ?.!")
    if not topic_clean or topic_clean.lower() in query.lower():
        return query
    return f"{query.rstrip(' ?.!')} ({topic_clean})?"


class QueryRewriter:
    """Rewrites conversational queries into standalone search queries only when needed."""

    def __init__(self, llm_provider: LLMProvider):
        self.llm = llm_provider
        self.config = LLMConfig(temperature=0.0, max_tokens=100)

    async def rewrite(
        self,
        query: str,
        conversation_history: list[dict] | None = None,
    ) -> str:
        """Rewrite a conversational query into a standalone search query."""
        if not conversation_history or not needs_contextual_rewrite(query, conversation_history):
            return query

        settings = get_settings()
        if settings.fast_mode:
            return resolve_followup_with_rules(query, conversation_history)

        recent = conversation_history[-6:]
        history_text = "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in recent
        )

        messages = [
            {"role": "system", "content": _REWRITE_PROMPT},
            {
                "role": "user",
                "content": f"Conversation history:\n{history_text}\n\n"
                f"Latest query: {query}\n\nRewritten query:",
            },
        ]

        try:
            rewritten = await asyncio.wait_for(
                self.llm.generate(messages, self.config),
                timeout=6,
            )
            rewritten = rewritten.strip().strip('"').strip("'")
            if rewritten:
                logger.debug(f"Query rewritten: '{query}' → '{rewritten}'")
                return rewritten
        except Exception as e:
            logger.warning(f"Query rewrite failed, falling back to rule-based expansion: {e}")
            return resolve_followup_with_rules(query, conversation_history)

        return query
