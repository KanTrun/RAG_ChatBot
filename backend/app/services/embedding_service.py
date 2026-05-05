"""Embedding service with provider-agnostic interface. BGE-M3 + OpenAI fallback."""

import hashlib
import logging
import math
import re
from dataclasses import dataclass
from typing import Protocol

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingResult:
    """Embedding output for a single text chunk."""

    dense: list[float]  # 1024-dim vector
    sparse: dict[str, float] | None = None  # term:weight for hybrid retrieval


class EmbeddingProvider(Protocol):
    """Provider-agnostic embedding interface."""

    async def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]:
        """Embed a batch of texts, returning dense (+ optional sparse) vectors."""
        ...

    @property
    def dimension(self) -> int:
        """Vector dimension."""
        ...


class OpenAIEmbeddingService:
    """OpenAI text-embedding-3-small fallback (no GPU needed)."""

    def __init__(self):
        from openai import AsyncOpenAI
        settings = get_settings()
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = "text-embedding-3-small"

    @property
    def dimension(self) -> int:
        return 1024  # request 1024 dims via dimensions param

    async def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]:
        response = await self._client.embeddings.create(
            input=texts,
            model=self._model,
            dimensions=1024,
        )
        return [
            EmbeddingResult(dense=item.embedding, sparse=None)
            for item in response.data
        ]


class OllamaEmbeddingService:
    """Ollama embedding provider for local-first RAG."""

    def __init__(self, base_url: str | None = None, model: str | None = None):
        settings = get_settings()
        self._base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self._model = model or settings.ollama_embedding_model

    @property
    def dimension(self) -> int:
        return 1024

    def _build_fallback_embedding(self, text: str) -> EmbeddingResult:
        vector = [0.0] * self.dimension
        tokens = re.findall(r"\w+", text.lower())
        if not tokens:
            tokens = [text.lower() or "empty"]

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            primary_index = int.from_bytes(digest[:2], "big") % self.dimension
            secondary_index = int.from_bytes(digest[2:4], "big") % self.dimension
            weight = 1.0 + (digest[4] / 255.0)

            vector[primary_index] += weight
            vector[secondary_index] -= weight * 0.5

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            vector[0] = 1.0
            norm = 1.0

        dense = [value / norm for value in vector]
        return EmbeddingResult(dense=dense, sparse=None)

    async def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]:
        if not texts:
            return []

        import httpx

        payload = {"model": self._model, "input": texts}
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(f"{self._base_url}/api/embed", json=payload)
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, OSError) as exc:
            logger.warning(
                "Ollama embedding unavailable at %s for model %s; using deterministic fallback embeddings. Error: %s",
                self._base_url,
                self._model,
                exc,
            )
            return [self._build_fallback_embedding(text) for text in texts]

        embeddings = data.get("embeddings")
        if embeddings is None:
            embedding = data.get("embedding")
            embeddings = [embedding] if embedding is not None else None
        if not isinstance(embeddings, list):
            raise ValueError(f"Ollama embedding model '{self._model}' returned no embeddings")
        if len(embeddings) != len(texts):
            raise ValueError(
                f"Ollama embedding model '{self._model}' returned {len(embeddings)} embeddings for {len(texts)} texts"
            )

        results: list[EmbeddingResult] = []
        for embedding in embeddings:
            if not isinstance(embedding, list):
                raise ValueError(f"Ollama embedding model '{self._model}' returned malformed embedding")
            if len(embedding) != self.dimension:
                raise ValueError(
                    f"Ollama embedding model '{self._model}' returned {len(embedding)} dimensions; expected {self.dimension}"
                )
            results.append(EmbeddingResult(dense=[float(value) for value in embedding], sparse=None))
        return results


class BGEEmbeddingService:
    """BGE-M3 self-hosted embedding (dense + sparse in one forward pass)."""

    def __init__(self):
        self._model = None  # lazy-loaded

    def _load_model(self):
        if self._model is None:
            from FlagEmbedding import BGEM3FlagModel
            settings = get_settings()
            self._model = BGEM3FlagModel(
                settings.bge_model_name, use_fp16=True
            )

    @property
    def dimension(self) -> int:
        return 1024

    async def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]:
        import asyncio
        self._load_model()

        # Run CPU/GPU-bound embedding in thread pool
        loop = asyncio.get_event_loop()
        output = await loop.run_in_executor(
            None,
            lambda: self._model.encode(
                texts,
                batch_size=32,
                return_dense=True,
                return_sparse=True,
                return_colbert_vecs=False,
            ),
        )

        results: list[EmbeddingResult] = []
        dense_vecs = output["dense_vecs"]
        sparse_weights = output.get("lexical_weights", [None] * len(texts))

        for i in range(len(texts)):
            sparse_dict = None
            if sparse_weights and sparse_weights[i] is not None:
                sparse_dict = {
                    str(k): float(v)
                    for k, v in sparse_weights[i].items()
                }

            results.append(EmbeddingResult(
                dense=dense_vecs[i].tolist(),
                sparse=sparse_dict,
            ))

        return results


# Provider factory
_embedding_service: EmbeddingProvider | None = None


def get_embedding_service() -> EmbeddingProvider:
    """Return cached embedding service based on config."""
    global _embedding_service
    if _embedding_service is None:
        settings = get_settings()
        if settings.embedding_provider == "ollama":
            _embedding_service = OllamaEmbeddingService()
        elif settings.embedding_provider == "bge-m3":
            _embedding_service = BGEEmbeddingService()
        else:
            _embedding_service = OpenAIEmbeddingService()
    return _embedding_service
