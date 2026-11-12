"""Error handling and rate limiting middleware."""

from collections import defaultdict
import logging
import time

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
    """Sliding window rate limiter for chat, upload, and general API endpoints."""

    def __init__(self, app: FastAPI):
        super().__init__(app)
        settings = get_settings()
        self.chat_limit = settings.rate_limit_chat
        self.upload_limit = settings.rate_limit_upload
        self.default_limit = settings.rate_limit_default
        self.window = 60  # seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    @staticmethod
    def _extract_client_identity(request: Request) -> str:
        auth_header = request.headers.get("authorization") or ""
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
            if token:
                return f"token:{token[-24:]}"
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next):
        client_id = self._extract_client_identity(request)
        path = request.url.path

        if "/chat" in path:
            limit = self.chat_limit
            bucket = "chat"
        elif "/upload" in path:
            limit = self.upload_limit
            bucket = "upload"
        else:
            limit = self.default_limit
            bucket = path

        key = f"{client_id}:{bucket}"
        now = time.time()

        self._requests[key] = [
            t for t in self._requests[key] if t > now - self.window
        ]

        if len(self._requests[key]) >= limit:
            retry_after = int(self.window - (now - self._requests[key][0]))
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": f"Rate limit exceeded ({limit} requests/min for {bucket}). Please wait before retrying.",
                    "code": "rate_limited",
                },
                headers={"Retry-After": str(max(1, retry_after))},
            )

        self._requests[key].append(now)
        return await call_next(request)
