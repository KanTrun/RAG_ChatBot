import json
from typing import Any

try:
    from pydantic import field_validator
    from pydantic_settings import BaseSettings, NoDecode
    from typing_extensions import Annotated

    _PYDANTIC_V2 = True
except ImportError:
    from pydantic import BaseSettings, validator as field_validator  # type: ignore

    _PYDANTIC_V2 = False
    NoDecode = Any  # type: ignore
    Annotated = Any  # type: ignore


def _parse_cors_origins_value(value: Any) -> list[str]:
    """Accept JSON list strings, comma-separated strings, or Python lists."""
    if isinstance(value, list):
        return [str(origin).strip() for origin in value if str(origin).strip()]
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        if raw.startswith("[") and raw.endswith("]"):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            except Exception:
                pass
        return [origin.strip().strip("\"'") for origin in raw.split(",") if origin.strip().strip("\"'")]
    return ["http://localhost:3000"]


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = "postgresql+asyncpg://rag:rag@localhost:5432/ragdb"
    database_sync_url: str = "postgresql://rag:rag@localhost:5432/ragdb"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # CORS (NoDecode + JSON/CSV validator)
    if _PYDANTIC_V2:
        backend_cors_origins: Annotated[list[str], NoDecode] = [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]

        @field_validator("backend_cors_origins", mode="before")
        @classmethod
        def parse_backend_cors_origins(cls, value: Any) -> list[str]:
            return _parse_cors_origins_value(value)
    else:
        backend_cors_origins: Any = [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]

        @field_validator("backend_cors_origins", pre=True)  # type: ignore
        def parse_backend_cors_origins(cls, value: Any) -> list[str]:
            return _parse_cors_origins_value(value)

    # App
    debug: bool = True
    log_level: str = "info"
    app_version: str = "0.3.0"
    fast_mode: bool = False

    # Embedding
    embedding_provider: str = "ollama"
    bge_model_name: str = "BAAI/bge-m3"
    ollama_base_url: str = "http://ollama:11434"
    ollama_embedding_model: str = "mxbai-embed-large"
    ollama_keep_alive: str = "30m"
    embedding_batch_size: int = 32
    embedding_concurrency: int = 4
    query_embedding_cache_size: int = 512
    query_embedding_cache_ttl_seconds: int = 1800

    # LLM
    llm_provider: str = "ollama"
    llm_model: str = "qwen2.5:7b"
    ollama_num_ctx: int = 4096
    first_token_timeout_seconds: int = 120
    stream_chunk_timeout_seconds: int = 60
    ollama_warmup_on_startup: bool = True
    strict_startup_model_check: bool = False
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-pro"

    # Retrieval & Reranker (unified default: "none" for CPU local-first)
    enable_bm25: bool = True
    hnsw_ef_search: int = 64
    reranker_provider: str = "none"  # "bge-reranker" or "none"
    bge_reranker_model: str = "BAAI/bge-reranker-v2-m3"

    # Auth
    nextauth_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 60 * 24  # 24 hours
    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = ""
    bootstrap_admin_display_name: str = "Local Admin"

    # Langfuse
    langfuse_secret_key: str = ""
    langfuse_public_key: str = ""
    langfuse_host: str = ""

    # Upload
    upload_dir: str = "/app/uploads"
    max_upload_size: int = 50 * 1024 * 1024  # 50MB

    # Rate limiting (requests per minute)
    rate_limit_chat: int = 30
    rate_limit_upload: int = 10
    rate_limit_default: int = 100

    # Chunking
    chunk_size: int = 512
    chunk_overlap: int = 51

    # Ingestion dispatch
    ingestion_dispatch_mode: str = "auto"

    if _PYDANTIC_V2:
        model_config = {"env_file": ".env", "case_sensitive": False, "extra": "ignore"}
    else:
        class Config:
            env_file = ".env"
            case_sensitive = False
            extra = "ignore"


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return cached settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
