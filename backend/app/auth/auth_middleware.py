"""FastAPI auth dependencies: JWT validation, role checks."""

import logging
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt_handler import decode_token
from app.dependencies import get_db
from app.models.user import User

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Extract and validate JWT, return the User object."""
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")

    try:
        payload = decode_token(credentials.credentials)
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")

    if payload.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token type")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token payload")

    user = await db.get(User, UUID(user_id))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")

    return user


def require_role(role_name: str):
    """Dependency factory: checks the user has the specified role."""

    async def _check(user: User = Depends(get_current_user)) -> User:
        if user.is_superuser:
            return user
        # Check user's roles
        user_role_names = [r.name for r in user.roles] if user.roles else []
        if role_name not in user_role_names:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Role '{role_name}' required",
            )
        return user

    return _check


def is_admin(user: User) -> bool:
    """Return whether a user can access admin-only resources."""
    if user.is_superuser:
        return True
    return role_name_in_user(user, "admin")


def role_name_in_user(user: User, role_name: str) -> bool:
    role_names = [role.name for role in user.roles] if user.roles else []
    return role_name in role_names


def require_document_access(document, user: User) -> None:
    """Allow owners and admins; hide foreign documents from regular users."""
    if document.owner_id == user.id or is_admin(user):
        return
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
