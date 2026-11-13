"""Ollama LLM provider with connection pooling, keep_alive, and optimized context window."""

import json
import logging
from typing import AsyncIterator

import httpx

from app.config import get_settings
from app.services.llm.base_provider import LLMConfig

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG = LLMConfig(model="qwen2.5:7b")
_shared_llm_client: httpx.AsyncClient | None = None


def _get_shared_llm_client(timeout_sec: float) -> httpx.AsyncClient:
    global _shared_llm_client
    if _shared_llm_client is None or _shared_llm_client.is_closed:
        _shared_llm_client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_sec, connect=10.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    return _shared_llm_client


class OllamaProvider:
    """Ollama local LLM provider via HTTP API with keep_alive and connection pooling."""

    def __init__(self, base_url: str = "http://ollama:11434", model: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.default_model = model or "qwen2.5:7b"

    def _get_timeout_seconds(self) -> float:
        settings = get_settings()
        return float(max(settings.first_token_timeout_seconds, 120))

    async def generate(
        self,
        messages: list[dict],
        config: LLMConfig | None = None,
    ) -> str:
        cfg = config or _DEFAULT_CONFIG
        payload = self._build_payload(messages, cfg, stream=False)
        client = _get_shared_llm_client(self._get_timeout_seconds())
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
        client = _get_shared_llm_client(self._get_timeout_seconds())
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
        settings = get_settings()
        return {
            "model": cfg.model or self.default_model,
            "messages": messages,
            "stream": stream,
            "keep_alive": settings.ollama_keep_alive,
            "options": {
                "temperature": cfg.temperature,
                "num_predict": cfg.max_tokens,
                "num_ctx": settings.ollama_num_ctx,
                "top_p": cfg.top_p,
            },
        }
