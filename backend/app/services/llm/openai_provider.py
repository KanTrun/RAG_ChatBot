"""OpenAI LLM provider (GPT-4o-mini, GPT-4o)."""

import logging
from typing import AsyncIterator

from openai import AsyncOpenAI, RateLimitError

from app.config import get_settings
from app.services.llm.base_provider import LLMConfig, LLMProvider

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG = LLMConfig()


class OpenAIProvider:
    """OpenAI chat completions provider."""

    def __init__(self, model: str | None = None):
        settings = get_settings()
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.default_model = model or settings.llm_model

    async def generate(
        self,
        messages: list[dict],
        config: LLMConfig | None = None,
    ) -> str:
        cfg = config or _DEFAULT_CONFIG
        response = await self._call_with_retry(messages, cfg, stream=False)
        return response.choices[0].message.content or ""

    async def generate_stream(
        self,
        messages: list[dict],
        config: LLMConfig | None = None,
    ) -> AsyncIterator[str]:
        cfg = config or _DEFAULT_CONFIG
        stream = await self._call_with_retry(messages, cfg, stream=True)
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    async def _call_with_retry(
        self,
        messages: list[dict],
        cfg: LLMConfig,
        stream: bool,
        max_retries: int = 3,
    ):
        import asyncio

        model = cfg.model or self.default_model
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": cfg.temperature,
            "max_tokens": cfg.max_tokens,
            "top_p": cfg.top_p,
            "stream": stream,
        }
        if cfg.stop:
            kwargs["stop"] = cfg.stop

        for attempt in range(max_retries):
            try:
                return await self.client.chat.completions.create(**kwargs)
            except RateLimitError:
                if attempt == max_retries - 1:
                    raise
                wait = 2**attempt
                logger.warning(f"OpenAI rate limit, retrying in {wait}s")
                await asyncio.sleep(wait)
