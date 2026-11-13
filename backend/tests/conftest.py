import os
import sys
from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://rag_test:rag_test@localhost:5433/rag_test_db",
)
os.environ.setdefault(
    "DATABASE_SYNC_URL",
    "postgresql://rag_test:rag_test@localhost:5433/rag_test_db",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6380/0")
os.environ.setdefault("NEXTAUTH_SECRET", "test-secret")
os.environ.setdefault("UPLOAD_DIR", str(Path(__file__).parent / "tmp-uploads"))
os.environ.setdefault("EMBEDDING_PROVIDER", "openai")
os.environ.setdefault("LLM_PROVIDER", "openai")
os.environ.setdefault("OLLAMA_BASE_URL", "http://ollama:11434")
os.environ.setdefault("OLLAMA_EMBEDDING_MODEL", "mxbai-embed-large")
os.environ.setdefault("RERANKER_PROVIDER", "none")
os.environ.setdefault("INGESTION_DISPATCH_MODE", "celery")


def verify_test_database_safety(db_url: str | None = None, sync_url: str | None = None) -> None:
    """Refuse to run tests unless DATABASE_URL explicitly targets a rag_test database."""
    active_db_url = db_url if db_url is not None else os.environ.get("DATABASE_URL", "")
    active_sync_url = sync_url if sync_url is not None else os.environ.get("DATABASE_SYNC_URL", "")
    if "rag_test" not in active_db_url or (active_sync_url and "rag_test" not in active_sync_url):
        pytest.exit(
            "CRITICAL SAFETY GUARD: Refusing to run pytest because DATABASE_URL "
            f"('{active_db_url}') does not contain 'rag_test'. Never run pytest inside "
            "the production rag-backend container or against ragdb! Use docker-compose.test.yml.",
            returncode=1,
        )


def pytest_configure(config) -> None:
    verify_test_database_safety()


verify_test_database_safety()

from app.auth.jwt_handler import create_access_token, hash_password  # noqa: E402
from app.dependencies import get_db  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Base  # noqa: E402
from app.models.chunk import DocumentChunk  # noqa: E402
from app.models.conversation import Conversation  # noqa: E402
from app.models.document import Document, DocumentStatus  # noqa: E402
from app.models.feedback import Feedback  # noqa: E402
from app.models.message import Message  # noqa: E402
from app.models.user import Role, User, user_roles  # noqa: E402


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    verify_test_database_safety()
    engine = create_async_engine(os.environ["DATABASE_URL"], echo=False, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        for table in [
            Feedback.__table__,
            Message.__table__,
            Conversation.__table__,
            DocumentChunk.__table__,
            Document.__table__,
            user_roles,
            User.__table__,
            Role.__table__,
        ]:
            await session.execute(delete(table))
        await session.commit()


@pytest_asyncio.fixture
async def async_client(test_engine) -> AsyncGenerator[AsyncClient, None]:
    app = create_app()
    app.state.engine = test_engine

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def admin_role(db_session: AsyncSession) -> Role:
    role = Role(name="admin", description="Administrator")
    db_session.add(role)
    await db_session.commit()
    await db_session.refresh(role)
    return role


@pytest_asyncio.fixture
async def viewer_role(db_session: AsyncSession) -> Role:
    role = Role(name="viewer", description="Viewer")
    db_session.add(role)
    await db_session.commit()
    await db_session.refresh(role)
    return role


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession, viewer_role: Role) -> User:
    user = User(
        email="viewer@example.com",
        hashed_password=hash_password("Password123!"),
        display_name="Viewer User",
        roles=[viewer_role],
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_admin(db_session: AsyncSession, admin_role: Role) -> User:
    user = User(
        email="admin@example.com",
        hashed_password=hash_password("Password123!"),
        display_name="Admin User",
        is_superuser=True,
        roles=[admin_role],
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(test_user: User) -> dict[str, str]:
    token = create_access_token(str(test_user.id), test_user.email, ["viewer"])
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers(test_admin: User) -> dict[str, str]:
    token = create_access_token(str(test_admin.id), test_admin.email, ["admin"])
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def indexed_document(db_session: AsyncSession, test_user: User) -> Document:
    upload_path = Path(__file__).parent / "tmp-uploads" / f"{test_user.id}-sample-article.txt"
    upload_path.parent.mkdir(parents=True, exist_ok=True)
    upload_path.write_text("AlphaProject uses hybrid retrieval and citations.", encoding="utf-8")
    document = Document(
        title="AlphaProject RAG Guide",
        file_name="sample-article.txt",
        file_path=str(Path(__file__).parent / "tmp-uploads" / f"{test_user.id}-sample-article.txt"),
        file_type="txt",
        file_size=256,
        content_hash="test-content-hash",
        status=DocumentStatus.indexed,
        owner_id=test_user.id,
        total_chunks=1,
    )
    db_session.add(document)
    await db_session.flush()
    chunk = DocumentChunk(
        document_id=document.id,
        content="AlphaProject uses hybrid retrieval, BM25, vector search, citations, and access control.",
        embedding=[0.1] * 1024,
        sparse_vector={"alphaproject": 1.0},
        search_vector="alphaproject retrieval citations access control",
        chunk_index=0,
        page_number=1,
        section="Overview",
        token_count=12,
        metadata_={"source": "fixture"},
    )
    db_session.add(chunk)
    await db_session.commit()
    await db_session.refresh(document)
    return document


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def isolate_external_dispatch(monkeypatch) -> Generator[None, None, None]:
    import app.config as app_config
    from app.services import document_ingestion_dispatcher

    app_config._settings = None
    monkeypatch.setattr(
        document_ingestion_dispatcher,
        "dispatch_document_ingestion",
        lambda *_args, **_kwargs: None,
    )
    yield
    import app.services.embedding_service as embedding_service
    import app.services.llm.provider_factory as provider_factory

    app_config._settings = None
    embedding_service._embedding_service = None
    provider_factory.get_llm_provider.cache_clear()
