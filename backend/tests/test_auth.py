from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from app.auth.jwt_handler import create_access_token
from app.config import get_settings


@pytest.mark.anyio
async def test_register_creates_user_and_tokens(async_client):
    response = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "new-user@example.com",
            "password": "Password123!",
            "display_name": "New User",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["token_type"] == "bearer"
    assert data["access_token"]
    assert data["refresh_token"]


@pytest.mark.anyio
async def test_register_rejects_duplicate_email(async_client, test_user):
    response = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": test_user.email,
            "password": "Password123!",
            "display_name": "Duplicate User",
        },
    )

    assert response.status_code == 409


@pytest.mark.anyio
async def test_login_accepts_valid_credentials(async_client, test_user):
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": test_user.email, "password": "Password123!"},
    )

    assert response.status_code == 200
    assert response.json()["access_token"]


@pytest.mark.anyio
async def test_login_rejects_invalid_password(async_client, test_user):
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": test_user.email, "password": "wrong-password"},
    )

    assert response.status_code == 401


@pytest.mark.anyio
async def test_protected_endpoint_rejects_missing_token(async_client):
    response = await async_client.get("/api/v1/conversations")

    assert response.status_code == 401


@pytest.mark.anyio
async def test_protected_endpoint_rejects_malformed_token(async_client):
    response = await async_client.get(
        "/api/v1/conversations",
        headers={"Authorization": "Bearer not-a-token"},
    )

    assert response.status_code == 401


@pytest.mark.anyio
async def test_protected_endpoint_rejects_expired_token(async_client, test_user):
    settings = get_settings()
    token = jwt.encode(
        {
            "sub": str(test_user.id),
            "email": test_user.email,
            "roles": ["viewer"],
            "type": "access",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        },
        settings.nextauth_secret,
        algorithm=settings.jwt_algorithm,
    )

    response = await async_client.get(
        "/api/v1/conversations",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


@pytest.mark.anyio
async def test_admin_endpoint_enforces_role(async_client, auth_headers, admin_headers):
    viewer_response = await async_client.get("/api/v1/admin/stats", headers=auth_headers)
    admin_response = await async_client.get("/api/v1/admin/stats", headers=admin_headers)

    assert viewer_response.status_code == 403
    assert admin_response.status_code == 200


@pytest.mark.anyio
async def test_refresh_token_returns_new_pair(async_client, test_user):
    login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": test_user.email, "password": "Password123!"},
    )
    refresh_token = login.json()["refresh_token"]

    response = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )

    assert response.status_code == 200
    assert response.json()["access_token"]
    assert response.json()["refresh_token"]


@pytest.mark.anyio
async def test_refresh_rejects_access_token(async_client, test_user):
    token = create_access_token(str(test_user.id), test_user.email, ["viewer"])

    response = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": token},
    )

    assert response.status_code == 401
