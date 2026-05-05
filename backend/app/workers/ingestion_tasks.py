"""Celery tasks for document ingestion."""

import asyncio
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _get_async_session() -> AsyncSession:
    """Create a fresh async session for the worker (not shared with web app)."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_size=2, max_overflow=3)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return factory()


@celery_app.task(
    bind=True,
    name="ingestion.process_document",
    max_retries=3,
    default_retry_delay=30,
)
def process_document_task(self, document_id: str) -> dict:
    """Process a document through the full ingestion pipeline.

    Celery tasks are sync; we run the async pipeline in an event loop.
    """
    try:
        result = asyncio.run(_process_document_async(document_id))
        return result
    except Exception as exc:
        logger.error(f"Task failed for document {document_id}: {exc}")
        countdown = 2 ** self.request.retries * 30  # exponential backoff
        raise self.retry(exc=exc, countdown=countdown)


async def _process_document_async(document_id: str) -> dict:
    """Async wrapper for the ingestion pipeline."""
    from app.services.ingestion_pipeline import IngestionPipeline

    async with _get_async_session() as session:
        pipeline = IngestionPipeline(session=session)
        await pipeline.process_document(UUID(document_id))
        return {"document_id": document_id, "status": "indexed"}
