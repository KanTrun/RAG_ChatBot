import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
import logging
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.api.middleware import RateLimitMiddleware, register_error_handlers
from app.api.v1.admin_router import router as admin_router
from app.api.v1.chat_router import router as chat_router
from app.api.v1.document_router import router as document_router
from app.api.v1.feedback_router import router as feedback_router
from app.auth.auth_router import router as auth_router
from app.config import get_settings
from app.observability.tracing_middleware import TracingMiddleware
from app.services.bootstrap_admin_service import ensure_bootstrap_admin
from app.services.provider_health import (
    ProviderConfigurationError,
    check_ollama_models,
    validate_provider_settings,
    warmup_ollama_models,
)

logger = logging.getLogger(__name__)


async def _ensure_search_vector_trigger_and_backfill(conn) -> int:
    """Ensure document_chunks has the search_vector trigger and backfill any NULL rows."""
    await conn.execute(
        text(
            """
            CREATE OR REPLACE FUNCTION update_search_vector()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.search_vector := to_tsvector('simple', COALESCE(NEW.content, ''));
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
    )
    await conn.execute(
        text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name = 'document_chunks'
                ) THEN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_trigger
                        WHERE tgname = 'trg_chunks_search_vector'
                    ) THEN
                        CREATE TRIGGER trg_chunks_search_vector
                        BEFORE INSERT OR UPDATE OF content ON document_chunks
                        FOR EACH ROW EXECUTE FUNCTION update_search_vector();
                    END IF;
                END IF;
            END;
            $$;
            """
        )
    )
    table_exists = await conn.execute(
        text(
            "SELECT 1 FROM information_schema.tables WHERE table_name = 'document_chunks'"
        )
    )
    if table_exists.scalar():
        updated = await conn.execute(
            text(
                """
                UPDATE document_chunks
                SET search_vector = to_tsvector('simple', COALESCE(content, ''))
                WHERE search_vector IS NULL
                """
            )
        )
        return updated.rowcount or 0
    return 0


async def _check_redis_health(redis_url: str) -> dict:
    """Check Redis connectivity using TCP/RESP PING without requiring extra packages."""
    parsed = urlparse(redis_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 6379
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=1.5,
        )
        writer.write(b"*1\r\n$4\r\nPING\r\n")
        await writer.drain()
        line = await asyncio.wait_for(reader.readline(), timeout=1.5)
        writer.close()
        await writer.wait_closed()
        if line.startswith(b"+PONG") or line.startswith(b"-NOAUTH"):
            return {"status": "healthy", "host": host, "port": port}
        return {
            "status": "degraded",
            "host": host,
            "port": port,
            "response": line.decode("utf-8", errors="ignore").strip(),
        }
    except Exception as exc:
        return {"status": "unreachable", "host": host, "port": port, "error": str(exc)}


async def _check_celery_worker_health(redis_reachable: bool) -> dict:
    """Verify Celery task registration AND live worker ping when Redis broker is reachable."""
    from app.workers.celery_app import celery_app

    registered_tasks = sorted(
        name for name in celery_app.tasks.keys() if not name.startswith("celery.")
    )
    task_registered = "ingestion.process_document" in registered_tasks
    active_workers: list[str] = []
    ping_ok = False
    ping_error: str | None = None

    if redis_reachable:
        try:
            ping_resp = await asyncio.wait_for(
                asyncio.to_thread(
                    lambda: celery_app.control.inspect(timeout=0.8).ping()
                ),
                timeout=1.5,
            )
            if isinstance(ping_resp, dict) and ping_resp:
                active_workers = sorted(ping_resp.keys())
                ping_ok = True
        except Exception as exc:
            ping_error = str(exc)

    return {
        "status": "healthy" if (task_registered and (ping_ok or not redis_reachable)) else "degraded",
        "ingestion_task_registered": task_registered,
        "worker_ping_ok": ping_ok,
        "active_workers": active_workers,
        "registered_tasks": registered_tasks,
        **({"ping_error": ping_error} if ping_error else {}),
    }


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Startup/shutdown lifecycle. Initializes DB engine, verifies pgvector, backfills BM25, and warms up models."""
    settings = get_settings()

    config_errors = validate_provider_settings(settings)
    app.state.provider_config_errors = config_errors
    if config_errors:
        for err in config_errors:
            logger.error("Startup provider configuration error: %s", err)
        if settings.strict_startup_model_check:
            raise ProviderConfigurationError("; ".join(config_errors))

    engine: AsyncEngine = create_async_engine(
        settings.database_url,
        echo=settings.debug,
        pool_size=10,
        max_overflow=20,
    )
    app.state.engine = engine
    app.state.model_warmup_status = "idle"
    app.state.model_warmup_error = None
    app.state.ollama_check = None

    async with engine.begin() as conn:
        result = await conn.execute(
            text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        )
        if not result.scalar():
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        backfilled = await _ensure_search_vector_trigger_and_backfill(conn)
        if backfilled:
            logger.info("Backfilled search_vector for %s existing document chunks", backfilled)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        await ensure_bootstrap_admin(
            session=session,
            email=settings.bootstrap_admin_email,
            password=settings.bootstrap_admin_password,
            display_name=settings.bootstrap_admin_display_name,
        )

    warmup_task: asyncio.Task | None = None
    if settings.ollama_warmup_on_startup and "ollama" in {
        settings.embedding_provider,
        settings.llm_provider,
    }:
        warmup_task = asyncio.create_task(warmup_ollama_models(app.state, settings))

    yield

    if warmup_task and not warmup_task.done():
        warmup_task.cancel()
    await engine.dispose()


def create_app() -> FastAPI:
    """FastAPI application factory."""
    settings = get_settings()

    app = FastAPI(
        title="RAG Chatbot API",
        version=settings.app_version,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan,
    )
    app.state.model_warmup_status = "ready"
    app.state.model_warmup_error = None
    app.state.provider_config_errors = []
    app.state.ollama_check = None

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.backend_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health_check():
        current_settings = get_settings()
        db_status = {"status": "healthy", "pgvector": True}
        engine = getattr(app.state, "engine", None)
        if engine is not None:
            try:
                async with engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
            except Exception as exc:
                db_status = {"status": "unhealthy", "error": str(exc)}
        else:
            db_status = {"status": "uninitialized"}

        redis_status = await _check_redis_health(current_settings.redis_url)
        redis_ok = redis_status.get("status") == "healthy"
        celery_status = await _check_celery_worker_health(redis_ok)

        ollama_status = getattr(app.state, "ollama_check", None)
        if ollama_status is None:
            ollama_status = await check_ollama_models(current_settings, timeout=2.0)
        warmup_state = getattr(app.state, "model_warmup_status", "ready")
        config_errors = validate_provider_settings(current_settings)

        return {
            "status": "ok",
            "version": current_settings.app_version,
            "model_ready": warmup_state == "ready" and not ollama_status.get("missing_models"),
            "warmup_status": warmup_state,
            "provider_config_errors": config_errors,
            "components": {
                "database": db_status,
                "redis": redis_status,
                "ollama": {
                    **ollama_status,
                    "embedding_provider": current_settings.embedding_provider,
                    "embedding_model": current_settings.ollama_embedding_model,
                    "llm_provider": current_settings.llm_provider,
                    "llm_model": current_settings.llm_model,
                    "warmup_status": warmup_state,
                },
                "celery_worker": celery_status,
            },
        }

    from fastapi import APIRouter

    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(chat_router)
    api_v1.include_router(document_router)
    api_v1.include_router(admin_router)
    api_v1.include_router(feedback_router)
    api_v1.include_router(auth_router)
    app.include_router(api_v1)

    register_error_handlers(app)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(TracingMiddleware)

    return app


app = create_app()
