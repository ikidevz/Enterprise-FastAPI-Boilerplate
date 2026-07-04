import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import backend.main as main_module
from backend.common.rate_limit import shared_rate_limiter
from backend.core.config import settings
from backend.database import session as db_session
from backend.database.base import Base


@pytest.fixture(autouse=True)
def reset_test_state() -> None:
    original_limit = settings.rate_limit_requests_per_minute
    original_enable_rate_limiting = settings.enable_rate_limiting

    shared_rate_limiter.reset()
    yield

    settings.rate_limit_requests_per_minute = original_limit
    settings.enable_rate_limiting = original_enable_rate_limiting
    shared_rate_limiter.reset()


@pytest.fixture()
def client() -> TestClient:
    test_engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", echo=False)
    test_session_factory = async_sessionmaker(
        bind=test_engine, expire_on_commit=False)

    shared_rate_limiter.reset()
    db_session.engine = test_engine
    db_session.SessionLocal = test_session_factory
    main_module.engine = test_engine

    async def init_db() -> None:
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(init_db())

    with TestClient(main_module.app) as test_client:
        yield test_client

    asyncio.run(test_engine.dispose())


def register_user(client: TestClient, *, email: str, username: str, password: str = "StrongPass123!") -> dict:
    response = client.post(
        "/api/v1/users/",
        json={"email": email, "username": username, "password": password},
    )
    assert response.status_code == 201
    return response.json()


def login_user(client: TestClient, *, email: str, password: str = "StrongPass123!") -> str:
    response = client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]
