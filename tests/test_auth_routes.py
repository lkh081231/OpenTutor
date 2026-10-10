"""Authentication HTTP regressions without the unrelated application lifespan."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from config import settings
from database import get_db
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from jose import jwt
from models.user import User
from routers.auth import router
from services.auth.jwt import create_access_token, create_refresh_token


@pytest_asyncio.fixture
async def auth_client(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_allow_registration", True)
    monkeypatch.setattr(settings, "jwt_secret_key", "test-auth-routes-secret-key")
    monkeypatch.setattr(settings, "deployment_mode", "single_user")
    app = FastAPI()
    app.include_router(router, prefix="/api/auth")
    db = AsyncMock()
    db.add = MagicMock()
    user = User(id=uuid.uuid4(), name="Student", email="student@example.com", is_active=True)
    result = MagicMock()
    result.scalar_one_or_none.return_value = user
    db.execute.return_value = result

    async def database_override():
        yield db

    app.dependency_overrides[get_db] = database_override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, db, user, result


@pytest.mark.asyncio
async def test_disabled_registration_rejects_even_empty_body_without_db_write(auth_client, monkeypatch):
    client, db, _, _ = auth_client
    monkeypatch.setattr(settings, "auth_allow_registration", False)
    for kwargs in ({}, {"json": {}}, {"json": {"email": "student@example.com", "password": "password123"}}):
        response = await client.post("/api/auth/register", **kwargs)
        assert response.status_code == 403
    db.execute.assert_not_called()
    db.add.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_enabled_registration_keeps_existing_behavior(auth_client):
    client, db, _, result = auth_client
    result.scalar_one_or_none.return_value = None

    async def assign_id(user):
        user.id = uuid.uuid4()

    db.refresh.side_effect = assign_id
    response = await client.post("/api/auth/register", json={"email": "new@example.com", "password": "password123", "name": "New Student"})
    assert response.status_code == 201
    assert response.json()["email"] == "new@example.com"
    db.add.assert_called_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_me_requires_access_token_and_returns_current_user(auth_client):
    client, _, user, _ = auth_client
    assert (await client.get("/api/auth/me")).status_code == 401
    for token in ("invalid", jwt.encode({"sub": str(user.id), "type": "access", "exp": datetime.now(timezone.utc) - timedelta(seconds=60)}, settings.jwt_secret_key, algorithm=settings.jwt_algorithm), create_refresh_token(str(user.id))):
        assert (await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})).status_code == 401
    response = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {create_access_token(str(user.id))}"})
    assert response.status_code == 200
    assert response.json() == {"id": str(user.id), "email": user.email, "name": user.name}


@pytest.mark.asyncio
async def test_refresh_returns_a_valid_access_session(auth_client):
    client, _, user, _ = auth_client
    response = await client.post("/api/auth/refresh", json={"refresh_token": create_refresh_token(str(user.id))})
    assert response.status_code == 200
    assert (await client.get("/api/auth/me", headers={"Authorization": f"Bearer {response.json()['access_token']}"})).status_code == 200


@pytest.mark.asyncio
async def test_auth_disabled_keeps_original_single_user_mode(auth_client, monkeypatch):
    client, _, user, _ = auth_client
    monkeypatch.setattr(settings, "auth_enabled", False)
    response = await client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json()["id"] == str(user.id)


@pytest.mark.asyncio
async def test_login_me_refresh_lifecycle_with_isolated_sqlite(monkeypatch):
    from services.auth.password import hash_password
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "deployment_mode", "single_user")
    monkeypatch.setattr(settings, "jwt_secret_key", "test-lifecycle-secret-key")
    monkeypatch.setattr(settings, "auth_allow_registration", False)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    app = FastAPI()
    app.include_router(router, prefix="/api/auth")

    async def database_override():
        async with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = database_override
    try:
        async with engine.begin() as connection:
            await connection.run_sync(User.__table__.create)
        user_id = uuid.uuid4()
        async with sessions() as db:
            db.add(User(
                id=user_id,
                email="student@example.com",
                name="Student",
                hashed_password=hash_password("password123"),
                is_active=True,
            ))
            await db.commit()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            bad_login = await client.post("/api/auth/login", json={
                "email": "student@example.com", "password": "wrong-password",
            })
            assert bad_login.status_code == 401
            login = await client.post("/api/auth/login", json={
                "email": "student@example.com", "password": "password123",
            })
            assert login.status_code == 200
            tokens = login.json()
            me = await client.get("/api/auth/me", headers={
                "Authorization": f"Bearer {tokens['access_token']}",
            })
            assert me.status_code == 200
            assert me.json()["id"] == str(user_id)
            refreshed = await client.post("/api/auth/refresh", json={
                "refresh_token": tokens["refresh_token"],
            })
            assert refreshed.status_code == 200
            me_again = await client.get("/api/auth/me", headers={
                "Authorization": f"Bearer {refreshed.json()['access_token']}",
            })
            assert me_again.status_code == 200
            assert me_again.json() == me.json()
    finally:
        await engine.dispose()
