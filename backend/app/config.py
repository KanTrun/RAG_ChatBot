from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode
from typing_extensions import Annotated


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = "postgresql+asyncpg://rag:rag@localhost:5432/ragdb"
    database_sync_url: str = "postgresql://rag:rag@localhost:5432/ragdb"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # CORS
    backend_cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    @field_validator("backend_cors_origins", mode="before")
    @classmethod
    def parse_backend_cors_origins(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    # App
    debug: bool = True
    log_level: str = "info"
    app_version: str = "0.1.0"

    # Embedding
    embedding_provider: str = "ollama"
    bge_model_name: str = "BAAI/bge-m3"
    ollama_base_url: str = "http://ollama:11434"
    ollama_embedding_model: str = "mxbai-embed-large"

    # LLM
    llm_provider: str = "ollama"
    llm_model: str = "qwen2.5:7b"
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # Reranker
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
    rate_limit_default: int = 100

    # Chunking
    chunk_size: int = 512
    chunk_overlap: int = 51

    # Ingestion dispatch
    ingestion_dispatch_mode: str = "auto"

    model_config = {"env_file": ".env", "case_sensitive": False, "extra": "ignore"}


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return cached settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
