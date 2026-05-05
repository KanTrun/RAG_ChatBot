"""Langfuse client singleton for tracing."""

import logging
from functools import lru_cache

from app.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_langfuse():
    """Return cached Langfuse client. Returns None if not configured."""
    settings = get_settings()
    if not settings.langfuse_secret_key or not settings.langfuse_public_key:
        logger.info("Langfuse not configured — tracing disabled")
        return None

    try:
        from langfuse import Langfuse

        client = Langfuse(
            secret_key=settings.langfuse_secret_key,
            public_key=settings.langfuse_public_key,
            host=settings.langfuse_host or "http://localhost:3001",
        )
        logger.info("Langfuse client initialized")
        return client
    except Exception as e:
        logger.warning(f"Failed to initialize Langfuse: {e}")
        return None


def create_trace(name: str, user_id: str | None = None, metadata: dict | None = None):
    """Create a Langfuse trace. Returns trace object or None."""
    client = get_langfuse()
    if client is None:
        return None
    try:
        return client.trace(name=name, user_id=user_id, metadata=metadata or {})
    except Exception as e:
        logger.warning(f"Failed to create trace: {e}")
        return None


def add_score(trace_id: str, name: str, value: float, comment: str | None = None):
    """Add a score to a Langfuse trace."""
    client = get_langfuse()
    if client is None:
        return
    try:
        client.score(trace_id=trace_id, name=name, value=value, comment=comment)
    except Exception as e:
        logger.warning(f"Failed to add Langfuse score: {e}")
