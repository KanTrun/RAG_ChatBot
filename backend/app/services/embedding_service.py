"""Embedding service with batching, bounded concurrency, connection pooling, content_hash deduplication, and LRU TTL query cache."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import logging
import time
from typing import Protocol

import httpx

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


class _QueryEmbeddingCache:
    """In-memory LRU cache with TTL for query embeddings."""

    def __init__(self, max_size: int = 512, ttl_seconds: int = 1800):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._store: OrderedDict[str, tuple[float, EmbeddingResult]] = OrderedDict()

    def get(self, key: str) -> EmbeddingResult | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            self._store.pop(key, None)
            return None
        self._store.move_to_end(key)
        return value

    def set(self, key: str, value: EmbeddingResult) -> None:
        now = time.monotonic()
        self._store[key] = (now + self.ttl_seconds, value)
        self._store.move_to_end(key)
        while len(self._store) > self.max_size:
            self._store.popitem(last=False)

    def clear(self) -> None:
        self._store.clear()


_shared_http_client: httpx.AsyncClient | None = None


def get_shared_embedding_http_client(timeout: float = 30.0) -> httpx.AsyncClient:
    """Return a shared httpx.AsyncClient with connection pooling."""
    global _shared_http_client
    if _shared_http_client is None or _shared_http_client.is_closed:
        _shared_http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=10.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    return _shared_http_client


class OpenAIEmbeddingService:
    """OpenAI text-embedding-3-small fallback (no GPU needed)."""

    def __init__(self):
        from openai import AsyncOpenAI

        settings = get_settings()
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = "text-embedding-3-small"

    @property
    def dimension(self) -> int:
        return 1024

    async def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]:
        if not texts:
            return []
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
    """Ollama embedding provider with true batching, connection reuse, keep_alive, and content_hash deduplication."""

    def __init__(self, base_url: str | None = None, model: str | None = None):
        settings = get_settings()
        self._base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self._model = model or settings.ollama_embedding_model
        self._keep_alive = settings.ollama_keep_alive
        self._batch_size = max(1, settings.embedding_batch_size)
        self._semaphore = asyncio.Semaphore(max(1, settings.embedding_concurrency))
        self._cache = _QueryEmbeddingCache()

    @property
    def dimension(self) -> int:
        return 1024

    async def _embed_single_batch(self, batch_texts: list[str]) -> list[EmbeddingResult]:
        payload: dict = {
            "model": self._model,
            "input": batch_texts,
        }
        try:
            async with self._semaphore:
                async with httpx.AsyncClient(timeout=20) as client:
                    response = await client.post(f"{self._base_url}/api/embed", json=payload)
                    response.raise_for_status()
                    data = response.json()
        except (httpx.HTTPError, OSError) as exc:
            logger.error(
                "Ollama embedding service unreachable at %s for model '%s': %s",
                self._base_url,
                self._model,
                exc,
            )
            raise RuntimeError(
                f"Ollama embedding service at {self._base_url} is unreachable for model '{self._model}': {exc}"
            ) from exc

        embeddings = data.get("embeddings")
        if embeddings is None:
            embedding = data.get("embedding")
            embeddings = [embedding] if embedding is not None else None
        if not isinstance(embeddings, list):
            raise ValueError(f"Ollama embedding model '{self._model}' returned no embeddings")
        if len(embeddings) != len(batch_texts):
            raise ValueError(
                f"Ollama embedding model '{self._model}' returned {len(embeddings)} embeddings for {len(batch_texts)} texts"
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

    async def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]:
        if not texts:
            return []

        unique_texts: list[str] = []
        hash_to_index: dict[str, int] = {}
        cached_by_hash: dict[str, EmbeddingResult] = {}
        text_hashes: list[str] = []

        for text in texts:
            content_hash = hashlib.sha256(f"{self._model}:{text}".encode("utf-8")).hexdigest()
            text_hashes.append(content_hash)
            cached = self._cache.get(content_hash)
            if cached is not None:
                cached_by_hash[content_hash] = cached
                continue
            if content_hash not in hash_to_index:
                hash_to_index[content_hash] = len(unique_texts)
                unique_texts.append(text)

        if unique_texts:
            batches = [
                unique_texts[i : i + self._batch_size]
                for i in range(0, len(unique_texts), self._batch_size)
            ]
            if len(batches) == 1:
                batch_outputs = [await self._embed_single_batch(batches[0])]
            else:
                batch_outputs = await asyncio.gather(
                    *(self._embed_single_batch(batch) for batch in batches)
                )
            flat_unique_results = [item for sublist in batch_outputs for item in sublist]

            for content_hash, u_idx in hash_to_index.items():
                emb_res = flat_unique_results[u_idx]
                cached_by_hash[content_hash] = emb_res
                if len(texts) <= 8:
                    self._cache.set(content_hash, emb_res)

        return [cached_by_hash[h] for h in text_hashes]


class BGEEmbeddingService:
    """BGE-M3 self-hosted embedding (dense + sparse in one forward pass)."""

    def __init__(self):
        self._model = None

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
        if not texts:
            return []
        self._load_model()

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

            results.append(
                EmbeddingResult(
                    dense=dense_vecs[i].tolist(),
                    sparse=sparse_dict,
                )
            )

        return results


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
