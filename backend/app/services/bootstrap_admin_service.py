"""Bootstrap a local admin account when configured for dev/runtime."""

import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.jwt_handler import hash_password, verify_password
from app.models.user import Role, User

logger = logging.getLogger(__name__)


def _password_matches(password: str, hashed_password: str | None) -> bool:
    if not hashed_password:
        return False
    try:
        return verify_password(password, hashed_password)
    except Exception:
        return False


async def ensure_bootstrap_admin(
    session: AsyncSession,
    email: str,
    password: str,
    display_name: str,
) -> None:
    """Create or repair a bootstrap admin account when envs are provided."""
    if not email.strip() or not password.strip():
        return

    admin_role = await _get_or_create_admin_role(session)

    user_result = await session.execute(
        select(User)
        .options(selectinload(User.roles))
        .where(User.email == email)
    )
    user = user_result.scalar_one_or_none()

    if user is None:
        user = User(
            email=email,
            hashed_password=hash_password(password),
            display_name=display_name,
            is_active=True,
            is_superuser=True,
            roles=[admin_role],
        )
        session.add(user)
        try:
            await session.commit()
            logger.info("Bootstrap admin account created for %s", email)
            return
        except IntegrityError:
            await session.rollback()
            user_result = await session.execute(
                select(User)
                .options(selectinload(User.roles))
                .where(User.email == email)
            )
            user = user_result.scalar_one()

    user.display_name = display_name
    user.is_active = True
    user.is_superuser = True

    if not _password_matches(password, user.hashed_password):
        user.hashed_password = hash_password(password)

    if not any(role.name == "admin" for role in user.roles):
        user.roles.append(admin_role)

    await session.commit()
    logger.info("Bootstrap admin account ensured for %s", email)


async def _get_or_create_admin_role(session: AsyncSession) -> Role:
    role_result = await session.execute(select(Role).where(Role.name == "admin"))
    admin_role = role_result.scalar_one_or_none()
    if admin_role is not None:
        return admin_role

    admin_role = Role(name="admin", description="Administrator")
    session.add(admin_role)
    try:
        await session.flush()
        return admin_role
    except IntegrityError:
        await session.rollback()
        role_result = await session.execute(select(Role).where(Role.name == "admin"))
        return role_result.scalar_one()
