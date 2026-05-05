"""Error handling and rate limiting middleware."""

import logging
import time
from collections import defaultdict

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings

logger = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    """Register global exception handlers."""

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = []
        for err in exc.errors():
            loc = " → ".join(str(l) for l in err["loc"])
            errors.append(f"{loc}: {err['msg']}")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": "; ".join(errors), "code": "validation_error"},
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception("Unhandled exception")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error", "code": "internal_error"},
        )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory sliding window rate limiter."""

    def __init__(self, app: FastAPI):
        super().__init__(app)
        settings = get_settings()
        self.chat_limit = settings.rate_limit_chat
        self.default_limit = settings.rate_limit_default
        self.window = 60  # seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        # Identify client (IP-based for now; Phase 6 switches to user ID)
        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path

        # Pick limit based on route
        if "/chat" in path:
            limit = self.chat_limit
        elif "/upload" in path:
            limit = 10
        else:
            limit = self.default_limit

        key = f"{client_ip}:{path}"
        now = time.time()

        # Clean old entries
        self._requests[key] = [
            t for t in self._requests[key] if t > now - self.window
        ]

        if len(self._requests[key]) >= limit:
            retry_after = int(self.window - (now - self._requests[key][0]))
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Rate limit exceeded", "code": "rate_limited"},
                headers={"Retry-After": str(max(1, retry_after))},
            )

        self._requests[key].append(now)
        return await call_next(request)
