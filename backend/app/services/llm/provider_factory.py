"""Factory for creating LLM provider instances."""

import logging
from functools import lru_cache

from app.config import get_settings
from app.services.llm.base_provider import LLMProvider

logger = logging.getLogger(__name__)


@lru_cache(maxsize=4)
def get_llm_provider(
    provider: str | None = None,
    model: str | None = None,
) -> LLMProvider:
    """Return a cached LLM provider instance based on config."""
    settings = get_settings()
    provider = provider or settings.llm_provider
    model = model or settings.llm_model

    if provider == "openai":
        from app.services.llm.openai_provider import OpenAIProvider

        return OpenAIProvider(model=model)

    if provider == "anthropic":
        from app.services.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(model=model)

    if provider == "ollama":
        from app.services.llm.ollama_provider import OllamaProvider

        return OllamaProvider(base_url=settings.ollama_base_url, model=model)

    raise ValueError(f"Unknown LLM provider: {provider}")
