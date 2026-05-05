"""Anthropic LLM provider (Claude Sonnet)."""

import logging
from typing import AsyncIterator

from anthropic import AsyncAnthropic

from app.config import get_settings
from app.services.llm.base_provider import LLMConfig

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG = LLMConfig(model="claude-sonnet-4-20250514", max_tokens=1024)


class AnthropicProvider:
    """Anthropic messages API provider."""

    def __init__(self, model: str | None = None):
        settings = get_settings()
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.default_model = model or "claude-sonnet-4-20250514"

    async def generate(
        self,
        messages: list[dict],
        config: LLMConfig | None = None,
    ) -> str:
        cfg = config or _DEFAULT_CONFIG
        system, user_msgs = self._split_messages(messages)
        response = await self.client.messages.create(
            model=cfg.model or self.default_model,
            max_tokens=cfg.max_tokens,
            temperature=cfg.temperature,
            system=system,
            messages=user_msgs,
        )
        return response.content[0].text

    async def generate_stream(
        self,
        messages: list[dict],
        config: LLMConfig | None = None,
    ) -> AsyncIterator[str]:
        cfg = config or _DEFAULT_CONFIG
        system, user_msgs = self._split_messages(messages)
        async with self.client.messages.stream(
            model=cfg.model or self.default_model,
            max_tokens=cfg.max_tokens,
            temperature=cfg.temperature,
            system=system,
            messages=user_msgs,
        ) as stream:
            async for text in stream.text_stream:
                yield text

    @staticmethod
    def _split_messages(
        messages: list[dict],
    ) -> tuple[str, list[dict]]:
        """Split OpenAI-style messages into Anthropic system + messages."""
        system = ""
        user_msgs = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                user_msgs.append({"role": msg["role"], "content": msg["content"]})
        return system, user_msgs
