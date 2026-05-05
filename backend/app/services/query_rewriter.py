"""LLM-based query rewriter for conversational queries."""

import asyncio
import logging

from app.services.llm.base_provider import LLMConfig, LLMProvider

logger = logging.getLogger(__name__)

_REWRITE_PROMPT = """Given the conversation history below, rewrite the latest user \
query as a standalone search query. The rewritten query should:
- Be self-contained (no pronouns referencing prior messages)
- Preserve the user's intent
- Be concise and optimized for semantic search

If the query is already standalone, return it unchanged.
Return ONLY the rewritten query, nothing else."""


class QueryRewriter:
    """Rewrites conversational queries into standalone search queries."""

    def __init__(self, llm_provider: LLMProvider):
        self.llm = llm_provider
        self.config = LLMConfig(temperature=0.0, max_tokens=100)

    async def rewrite(
        self,
        query: str,
        conversation_history: list[dict] | None = None,
    ) -> str:
        """Rewrite a conversational query into a standalone search query."""
        if not conversation_history:
            return query

        # Build rewrite prompt with recent history (last 6 messages max)
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
                timeout=10,
            )
            rewritten = rewritten.strip().strip('"').strip("'")
            if rewritten:
                logger.debug(f"Query rewritten: '{query}' → '{rewritten}'")
                return rewritten
        except Exception as e:
            logger.warning(f"Query rewrite failed, using original: {e}")

        return query
