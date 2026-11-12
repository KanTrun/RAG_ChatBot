"""Ollama LLM provider (local models via HTTP API)."""

import json
import logging
from typing import AsyncIterator

import httpx

from app.config import get_settings
from app.services.llm.base_provider import LLMConfig

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG = LLMConfig(model="qwen2.5:7b")


class OllamaProvider:
    """Ollama local LLM provider via HTTP API."""

    def __init__(self, base_url: str = "http://ollama:11434", model: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.default_model = model or "qwen2.5:7b"

    def _get_timeout(self) -> httpx.Timeout:
        settings = get_settings()
        read_timeout = float(max(settings.first_token_timeout_seconds, 120))
        return httpx.Timeout(read_timeout, connect=10.0)

    async def generate(
        self,
        messages: list[dict],
        config: LLMConfig | None = None,
    ) -> str:
        cfg = config or _DEFAULT_CONFIG
        payload = self._build_payload(messages, cfg, stream=False)
        async with httpx.AsyncClient(timeout=self._get_timeout()) as client:
            resp = await client.post(f"{self.base_url}/api/chat", json=payload)
            resp.raise_for_status()
            return resp.json()["message"]["content"]

    async def generate_stream(
        self,
        messages: list[dict],
        config: LLMConfig | None = None,
    ) -> AsyncIterator[str]:
        cfg = config or _DEFAULT_CONFIG
        payload = self._build_payload(messages, cfg, stream=True)
        async with httpx.AsyncClient(timeout=self._get_timeout()) as client:
            async with client.stream(
                "POST", f"{self.base_url}/api/chat", json=payload
            ) as resp:
                resp.raise_for_status()

                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    content = data.get("message", {}).get("content", "")
                    if content:
                        yield content
                    if data.get("done"):
                        break

    def _build_payload(
        self, messages: list[dict], cfg: LLMConfig, stream: bool
    ) -> dict:
        return {
            "model": cfg.model or self.default_model,
            "messages": messages,
            "stream": stream,
            "options": {
                "temperature": cfg.temperature,
                "num_predict": cfg.max_tokens,
                "top_p": cfg.top_p,
            },
        }
