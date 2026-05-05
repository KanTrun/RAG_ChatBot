"""Abstract LLM provider interface."""

from dataclasses import dataclass, field
from typing import AsyncIterator, Protocol, runtime_checkable


@dataclass
class LLMConfig:
    """Configuration for LLM generation."""

    model: str | None = None
    temperature: float = 0.1
    max_tokens: int = 1024
    top_p: float = 1.0
    stop: list[str] = field(default_factory=list)


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for LLM providers (OpenAI, Anthropic, Ollama)."""

    async def generate(
        self,
        messages: list[dict],
        config: LLMConfig | None = None,
    ) -> str:
        """Generate a complete response."""
        ...

    async def generate_stream(
        self,
        messages: list[dict],
        config: LLMConfig | None = None,
    ) -> AsyncIterator[str]:
        """Generate a streaming response, yielding text chunks."""
        ...
