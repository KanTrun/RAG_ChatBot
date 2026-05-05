"""Dispatch document ingestion through the configured runtime path."""

import asyncio
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models.document import Document, DocumentStatus
from app.workers.ingestion_tasks import process_document_task

logger = logging.getLogger(__name__)


async def process_document_in_process(document_id: str) -> None:
    """Run ingestion inside the API process for local/dev reliability."""
    from app.services.ingestion_pipeline import IngestionPipeline

    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_size=2, max_overflow=3)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as session:
            pipeline = IngestionPipeline(session=session)
            await pipeline.process_document(UUID(document_id))
    finally:
        await engine.dispose()


async def process_document_if_still_pending(
    document_id: str,
    delay_seconds: float = 10.0,
) -> None:
    """Fallback to in-process ingestion only when the queued job does not start."""
    from app.services.ingestion_pipeline import IngestionPipeline

    await asyncio.sleep(delay_seconds)

    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_size=2, max_overflow=3)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as session:
            parsed_document_id = UUID(document_id)
            document = await session.get(Document, parsed_document_id)
            if document is None or document.status != DocumentStatus.pending:
                return

            pipeline = IngestionPipeline(session=session)
            await pipeline.process_document(parsed_document_id)
    finally:
        await engine.dispose()


def dispatch_document_ingestion(
    document_id: UUID,
    schedule_background_task,
) -> None:
    """Send ingestion work to background mode or Celery based on settings."""
    settings = get_settings()
    mode = settings.ingestion_dispatch_mode.lower().strip()

    if mode == "background":
        schedule_background_task(process_document_in_process, str(document_id))
        logger.info("Document %s ingestion dispatched via in-process background task", document_id)
        return

    try:
        process_document_task.delay(str(document_id))
        logger.info("Document %s ingestion dispatched via celery", document_id)
    except Exception as exc:
        if mode == "celery":
            raise

        logger.warning(
            "Document %s celery dispatch failed; falling back to in-process background task: %s",
            document_id,
            exc,
        )
        schedule_background_task(process_document_in_process, str(document_id))
        logger.info("Document %s ingestion dispatched via in-process background task", document_id)
        return

    if mode == "auto":
        schedule_background_task(process_document_if_still_pending, str(document_id))
        logger.info("Document %s queued with celery and auto fallback watchdog", document_id)
