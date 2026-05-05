"""Gemini LLM provider using the Google Generative Language REST API."""

from __future__ import annotations

import json
import logging
from typing import AsyncIterator

import httpx

from app.config import get_settings
from app.services.llm.base_provider import LLMConfig

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG = LLMConfig(model="gemini-2.5-pro", max_tokens=2048)


class GeminiProvider:
    """Gemini chat provider with OpenAI-style message input."""

    def __init__(self, model: str | None = None):
        settings = get_settings()
        self.api_key = settings.gemini_api_key
        self.default_model = model or settings.gemini_model or settings.llm_model
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"

    async def generate(
        self,
        messages: list[dict],
        config: LLMConfig | None = None,
    ) -> str:
        cfg = config or _DEFAULT_CONFIG
        payload = self._build_payload(messages, cfg)
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.base_url}/models/{cfg.model or self.default_model}:generateContent",
                params={"key": self.api_key},
                json=payload,
            )
            response.raise_for_status()
            return self._extract_text(response.json())

    async def generate_stream(
        self,
        messages: list[dict],
        config: LLMConfig | None = None,
    ) -> AsyncIterator[str]:
        cfg = config or _DEFAULT_CONFIG
        payload = self._build_payload(messages, cfg)
        emitted = ""

        async with httpx.AsyncClient(timeout=60) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/models/{cfg.model or self.default_model}:streamGenerateContent",
                params={"key": self.api_key, "alt": "sse"},
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    payload_text = line[5:].strip()
                    if payload_text in {"", "[DONE]"}:
                        continue
                    try:
                        event = json.loads(payload_text)
                    except json.JSONDecodeError:
                        logger.debug("Skipping malformed Gemini SSE event: %s", payload_text)
                        continue

                    text = self._extract_text(event)
                    if not text:
                        continue
                    if text.startswith(emitted):
                        delta = text[len(emitted) :]
                        emitted = text
                        if delta:
                            yield delta
                        continue

                    emitted += text
                    yield text

    def _build_payload(self, messages: list[dict], cfg: LLMConfig) -> dict:
        system_instruction, contents = self._split_messages(messages)
        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": cfg.temperature,
                "topP": cfg.top_p,
                "maxOutputTokens": cfg.max_tokens,
            },
        }
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
        if cfg.stop:
            payload["generationConfig"]["stopSequences"] = cfg.stop
        return payload

    @staticmethod
    def _split_messages(messages: list[dict]) -> tuple[str, list[dict]]:
        system_parts: list[str] = []
        contents: list[dict] = []

        for message in messages:
            role = message.get("role", "user")
            content = str(message.get("content", "") or "")
            if not content:
                continue
            if role == "system":
                system_parts.append(content)
                continue

            contents.append(
                {
                    "role": "model" if role == "assistant" else "user",
                    "parts": [{"text": content}],
                }
            )

        return "\n\n".join(system_parts), contents

    @staticmethod
    def _extract_text(payload: dict) -> str:
        texts: list[str] = []
        for candidate in payload.get("candidates", []):
            content = candidate.get("content") or {}
            for part in content.get("parts", []):
                text = part.get("text")
                if text:
                    texts.append(text)
        return "".join(texts)
