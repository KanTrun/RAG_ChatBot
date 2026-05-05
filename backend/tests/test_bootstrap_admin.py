import pytest
from sqlalchemy import select

from app.models.user import Role, User
from app.services.bootstrap_admin_service import ensure_bootstrap_admin


@pytest.mark.anyio
async def test_ensure_bootstrap_admin_creates_admin_user_and_role(db_session):
    await ensure_bootstrap_admin(
        session=db_session,
        email="admin123@gmail.com",
        password="admin123",
        display_name="Local Admin",
    )

    user_result = await db_session.execute(
        select(User).where(User.email == "admin123@gmail.com")
    )
    user = user_result.scalar_one()
    assert user.is_superuser is True
    assert any(role.name == "admin" for role in user.roles)

    role_result = await db_session.execute(select(Role).where(Role.name == "admin"))
    assert role_result.scalar_one().description == "Administrator"


@pytest.mark.anyio
async def test_ensure_bootstrap_admin_repairs_existing_user(db_session):
    user = User(
        email="admin123@gmail.com",
        hashed_password="stale-password",
        display_name="Old Name",
        is_active=False,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.commit()

    await ensure_bootstrap_admin(
        session=db_session,
        email="admin123@gmail.com",
        password="admin123",
        display_name="Local Admin",
    )

    refreshed = await db_session.get(User, user.id)
    assert refreshed is not None
    assert refreshed.display_name == "Local Admin"
    assert refreshed.is_active is True
    assert refreshed.is_superuser is True
    assert any(role.name == "admin" for role in refreshed.roles)
