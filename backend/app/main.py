from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.api.middleware import RateLimitMiddleware, register_error_handlers
from app.observability.tracing_middleware import TracingMiddleware
from app.api.v1.admin_router import router as admin_router
from app.api.v1.chat_router import router as chat_router
from app.api.v1.document_router import router as document_router
from app.api.v1.feedback_router import router as feedback_router
from app.auth.auth_router import router as auth_router
from app.config import get_settings
from app.services.bootstrap_admin_service import ensure_bootstrap_admin


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Startup/shutdown lifecycle. Initializes DB engine, verifies pgvector."""
    settings = get_settings()

    engine: AsyncEngine = create_async_engine(
        settings.database_url,
        echo=settings.debug,
        pool_size=10,
        max_overflow=20,
    )
    app.state.engine = engine

    # Verify pgvector extension is available
    async with engine.begin() as conn:
        result = await conn.execute(
            __import__("sqlalchemy").text(
                "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
            )
        )
        if not result.scalar():
            await conn.execute(
                __import__("sqlalchemy").text("CREATE EXTENSION IF NOT EXISTS vector")
            )

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        await ensure_bootstrap_admin(
            session=session,
            email=settings.bootstrap_admin_email,
            password=settings.bootstrap_admin_password,
            display_name=settings.bootstrap_admin_display_name,
        )

    yield

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

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.backend_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health check
    @app.get("/health")
    async def health_check():
        return {"status": "ok", "version": settings.app_version}

    # API v1 routers
    from fastapi import APIRouter

    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(chat_router)
    api_v1.include_router(document_router)
    api_v1.include_router(admin_router)
    api_v1.include_router(feedback_router)
    api_v1.include_router(auth_router)
    app.include_router(api_v1)

    # Error handlers
    register_error_handlers(app)

    # Rate limiting
    app.add_middleware(RateLimitMiddleware)

    # Tracing (Langfuse)
    app.add_middleware(TracingMiddleware)

    return app


app = create_app()
