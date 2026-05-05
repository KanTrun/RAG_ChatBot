"""RBAC service: role checks and document permission evaluation."""

from uuid import UUID

from app.models.user import User


def user_can_access_document(
    user: User,
    doc_allowed_roles: list[UUID],
) -> bool:
    """Check if user has access to a document based on its allowed_roles.

    Empty allowed_roles = public (accessible to all authenticated users).
    """
    if user.is_superuser:
        return True
    if not doc_allowed_roles:
        return True  # public document
    user_role_ids = {r.id for r in user.roles} if user.roles else set()
    return bool(user_role_ids & set(doc_allowed_roles))


def get_user_role_ids(user: User) -> list[UUID]:
    """Extract role UUIDs from user for retrieval ACL filtering."""
    if user.is_superuser:
        return []  # empty = bypass filter (superuser sees all)
    return [r.id for r in user.roles] if user.roles else []
