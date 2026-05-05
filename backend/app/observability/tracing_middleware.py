"""FastAPI tracing middleware: correlation IDs and request logging."""

import logging
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.observability.langfuse_client import create_trace

logger = logging.getLogger(__name__)


class TracingMiddleware(BaseHTTPMiddleware):
    """Assigns correlation ID and creates Langfuse trace per request."""

    async def dispatch(self, request: Request, call_next):
        correlation_id = str(uuid.uuid4())
        request.state.correlation_id = correlation_id
        start = time.time()

        # Create Langfuse trace for API requests
        user_id = None
        if hasattr(request.state, "user"):
            user_id = str(getattr(request.state.user, "id", None))

        trace = create_trace(
            name=request.url.path,
            user_id=user_id,
            metadata={"method": request.method, "correlation_id": correlation_id},
        )
        request.state.langfuse_trace = trace

        response = await call_next(request)

        latency_ms = int((time.time() - start) * 1000)
        response.headers["X-Correlation-ID"] = correlation_id

        logger.info(
            "request_completed",
            extra={
                "correlation_id": correlation_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "latency_ms": latency_ms,
            },
        )

        return response
