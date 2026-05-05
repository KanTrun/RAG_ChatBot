"""API dependencies: auth, pagination, common deps."""

from fastapi import Query

from app.auth.auth_middleware import get_current_user, require_role  # noqa: F401
from app.schemas.common_schemas import PaginationParams


async def get_pagination(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> PaginationParams:
    return PaginationParams(page=page, page_size=page_size)
