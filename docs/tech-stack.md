# Tech Stack - RAG Chatbot

## Architecture Overview

**Pattern:** Async ingestion pipeline + sync retrieval service
**Deployment:** Self-hosted, Docker Compose (dev) → Kubernetes (prod)

## Stack Selection

| Layer | Technology | Version | Rationale |
|-------|-----------|---------|-----------|
| **Backend API** | FastAPI (Python 3.12+) | ≥0.115 | Async native, SSE streaming, Pydantic v2, auto OpenAPI |
| **Database** | PostgreSQL + pgvector | PG 16+, pgvector 0.7+ | Single DB for relational + vector. HNSW index. tsvector for BM25 |
| **Embeddings** | BGE-M3 (BAAI) | latest | Self-hosted, free, multilingual (Vietnamese), dense+sparse+colbert |
| **LLM** | GPT-4o-mini (primary) | latest | Best cost/quality. Abstract behind provider interface for swappability |
| **Reranker** | BGE-Reranker-v2-m3 | latest | Self-hosted, multilingual, free |
| **Doc Parsing** | PyMuPDF (primary) | ≥1.24 | Fast PDF extraction. Marker for complex/scanned docs |
| **Ingestion** | LlamaIndex (doc loaders + node parsers) | ≥0.11 | Good abstractions for chunking. Query logic stays custom |
| **Frontend** | Next.js 15 + React 19 | latest | App Router, Vercel AI SDK for streaming chat |
| **UI Components** | shadcn/ui + Tailwind CSS v4 | latest | Consistent design system, accessible components |
| **Observability** | Langfuse (self-hosted) | latest | OSS tracing, prompt mgmt, eval integration |
| **Evaluation** | RAGAS + DeepEval | latest | Offline eval + CI gating |
| **Testing** | pytest + Vitest + Playwright | latest | Backend API/integration tests, frontend component tests, gated E2E |
| **Auth** | NextAuth.js v5 | latest | Session-based, JWT, OAuth support |
| **Task Queue** | Celery + Redis | latest | Async document ingestion pipeline |
| **File Storage** | Local FS (dev) → S3/MinIO (prod) | — | Raw document storage before processing |

## Key Design Decisions

### 1. Single DB (PostgreSQL + pgvector)
- One backup, one connection pool, ACID across relational + vector data
- pgvector HNSW for vector similarity search (<10ms p99 at 1M vectors)
- tsvector for Vietnamese BM25 full-text search (hybrid retrieval)
- Upgrade path: Qdrant when scale exceeds ~5-10M vectors

### 2. Self-hosted Embedding + Reranker
- BGE-M3: dense + sparse embeddings in one model (enables hybrid search)
- BGE-Reranker: cross-encoder reranking without API costs
- GPU required: ~4GB VRAM minimum (8GB+ recommended)
- Fallback: OpenAI text-embedding-3-small for dev without GPU

### 3. LLM Abstraction Layer
- Provider-agnostic interface (OpenAI, Anthropic, Ollama)
- GPT-4o-mini default (cost-effective, good Vietnamese)
- GPT-4o/Claude for complex queries (configurable per use case)
- Qwen 2.5 14B via Ollama for offline/air-gapped deployments

### 4. Hybrid Retrieval from Day One
- BM25 (tsvector) + vector search (pgvector HNSW)
- Reciprocal Rank Fusion (RRF) to merge results
- Cross-encoder reranking: top-20 → top-5
- 5-15% recall improvement over vector-only

## Python Dependencies (Core)

```
fastapi[standard], uvicorn, sqlalchemy[asyncio], asyncpg
pgvector, sentence-transformers, FlagEmbedding
openai, anthropic, tiktoken
pymupdf, llama-index-core, llama-index-readers-file
celery, redis, pydantic-settings
langfuse, ragas, deepeval
python-jose, passlib, python-multipart
```

## Node Dependencies (Frontend)

```
next, react, react-dom, ai (vercel AI SDK)
@radix-ui/*, tailwindcss, class-variance-authority
next-auth, zod, lucide-react
```

## Infrastructure

```
docker, docker-compose
postgresql:16-bookworm + pgvector extension
redis:7-alpine
python:3.12-slim (backend)
node:22-alpine (frontend)
```

## Test Infrastructure

- Backend: pytest, pytest-asyncio, httpx, coverage; tests cover auth, health, documents, chat, retrieval, ingestion.
- Frontend: Vitest + React Testing Library; chat and admin component coverage.
- E2E: Playwright specs/config under frontend; runs only when enabled.
- CI: GitHub Actions with PostgreSQL pgvector + Redis test services, frontend tests/build, backend import/compile checks.
- Local blocker logged: Docker Desktop returned 500 pulling/running `pgvector/pgvector:pg16`, so DB-backed backend pytest not validated locally yet.
