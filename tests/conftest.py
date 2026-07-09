"""Shared pytest fixtures and helpers for the whole test suite.

Every other test file in this package gets its database, its FastAPI
TestClient, and its "did anything leak between tests" safety net from here.
If you're new to this codebase, start by reading this file end to end -
everything else builds on top of it.

"""
from __future__ import annotations

import asyncio
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import backend.main as main_module
from backend.observability.audit import audit_logger
from backend.common.background_jobs import background_job_manager
from backend.resilience.rate_limit import shared_rate_limiter
from sqlalchemy import text
from backend.database import session as db_session
from backend.database.base import Base


class CaptureTransport:
    """A fake email transport that just remembers what it was asked to send.

    Used anywhere a test needs to check *what* an email would have said
    (e.g. "does the password reset email contain a real token?") without
    actually sending anything or needing a real SMTP server.
    """

    def __init__(self) -> None:
        """Supports the test suite by   init  ."""
        self.calls: list[dict[str, str]] = []

    def send(self, *, to: str, subject: str, body: str) -> None:
        """Supports the test suite by send."""
        self.calls.append({"to": to, "subject": subject, "body": body})


@pytest.fixture(autouse=True)
def reset_shared_singletons() -> Iterator[None]:
    """Reset every process-wide singleton before and after each test.

    A number of objects in this app are created exactly once, at import
    time, and then reused for the lifetime of the process (the rate
    limiter, the background job queue, the audit log, and the in-memory
    token stores used for refresh/reset/verification tokens). That's a
    reasonable design for a running app, but it's dangerous for tests: if
    test A leaves something in the queue or the log, test B can silently
    see it, and whether a test passes ends up depending on what ran before
    it rather than on whether the code is correct.

    This fixture runs automatically for every single test (autouse=True)
    and makes sure each test starts from a clean slate. If you add a new
    process-wide singleton to the app, add its reset here too.
    """
    shared_rate_limiter.reset()
    _reset_audit_logger()
    _reset_background_job_manager()
    _reset_token_stores()

    yield

    shared_rate_limiter.reset()
    _reset_audit_logger()
    _reset_background_job_manager()
    _reset_token_stores()


def _reset_audit_logger() -> None:
    """Reset the shared audit logger in a way that works with the current implementation."""
    if hasattr(audit_logger, "clear"):
        audit_logger.clear()
    elif hasattr(audit_logger, "_persist_path"):
        audit_logger._persist_path.write_text("", encoding="utf-8")


def _reset_background_job_manager() -> None:
    """Drop any queued-but-not-yet-run background jobs from a previous test."""
    queue = getattr(background_job_manager, "_queue", None)
    if queue is None:
        return
    while True:
        try:
            queue.get_nowait()
            queue.task_done()
        except Exception:
            break


def _reset_token_stores() -> None:
    """Clear the in-memory fallback used by TokenStore when Redis isn't reachable.

    In this test environment there is no real Redis, so every TokenStore
    silently falls back to an in-process dict (see backend/common/token_store.py).
    That dict is keyed by a shared prefix per store instance, and those store
    instances are themselves module-level singletons - so, same problem as
    above, a token created in one test could otherwise still be sitting there
    for the next test.
    """
    from backend.application.auth import use_cases as auth_use_cases
    from backend.core.security.dependencies import revocation_store

    for store in (
        auth_use_cases.token_store,
        auth_use_cases.password_reset_store,
        auth_use_cases.email_verification_store,
        revocation_store,
    ):
        store._memory_store.clear()  # type: ignore[attr-defined]


async def _wait_for_background_jobs(timeout: float = 1.0) -> None:
    """Block until the background job queue is empty (or give up after `timeout`).

    Several endpoints (password reset, email verification) hand work off
    to backend.common.background_jobs.background_job_manager instead of
    doing it inline, so the work may not be finished the instant the HTTP
    response comes back. Tests that need to inspect the *effect* of that
    work (e.g. "was an email captured?") should await this helper first
    instead of asserting immediately - asserting immediately is what made
    part of the old test suite order-dependent (see tests/README.md).
    """
    elapsed = 0.0
    step = 0.01
    # type: ignore[attr-defined]
    while not background_job_manager._queue.empty() and elapsed < timeout:
        await asyncio.sleep(step)
        elapsed += step


def wait_for_background_jobs(timeout: float = 1.0) -> None:
    """Sync wrapper around _wait_for_background_jobs, for use in normal `def` tests."""
    asyncio.run(_wait_for_background_jobs(timeout))


@pytest.fixture()
def client() -> Iterator[TestClient]:
    """The main fixture almost every test uses: a fully working FastAPI TestClient
    wired up to its own private, empty, in-memory SQLite database.

    Nothing about the real deployment database, Redis, or SMTP server is
    needed to use this fixture - everything is faked or swapped out for an
    in-memory equivalent, which is what makes the suite fast (no network
    calls) and safe to run anywhere.
    """
    test_engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", echo=False)
    test_session_factory = async_sessionmaker(
        bind=test_engine, expire_on_commit=False)

    # These are module-level globals that the rest of the app imports and
    # uses directly (see backend/database/session.py), so swapping them here
    # is how every request made through the TestClient below ends up talking
    # to our private in-memory database instead of a real one.
    db_session.engine = test_engine
    db_session.SessionLocal = test_session_factory
    main_module.engine = test_engine

    async def init_db() -> None:
        """Supports the test suite by init db."""
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(init_db())

    with TestClient(main_module.app) as test_client:
        yield test_client

    asyncio.run(test_engine.dispose())


def register_user(
    client: TestClient,
    *,
    email: str,
    username: str,
    password: str = "StrongPass123!",
    role: str | None = None,
    permissions: list[str] | None = None,
) -> dict:
    """Register a new user through the real HTTP endpoint and return the response body.

    Fails the test immediately (via assert) if registration didn't return
    201, so every test that calls this can assume the user really exists
    afterward without re-checking the status code itself.
    """
    # Public registration endpoint no longer accepts `role`/`permissions`.
    # Create the user with the minimal allowed payload and then, if the
    # test requested a privileged role or permissions, apply them
    # directly in the test database so existing tests continue to work.
    payload = {"email": email, "username": username, "password": password}

    response = client.post(
        "/api/v1/users/",
        json=payload,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    user_id = body.get("id")
    # If the test asked for a privileged role or permissions, set them
    # directly in the test database so tests that relied on the old
    # behavior continue to work.
    if user_id is not None:
        # Keep legacy test expectations: if the test created a user with
        # username "admin" but didn't pass an explicit role, treat that
        # as the seeded-style admin and mark the role accordingly so tests
        # relying on that convention continue to work.
        if role is None and username == "admin":
            async def _apply_seed_admin_role() -> None:
                """Supports the test suite by  apply seed admin role."""
                async with db_session.SessionLocal() as s:
                    await s.execute(text("UPDATE users SET role = :role WHERE id = :id"), {"role": "admin", "id": user_id})
                    await s.commit()

            asyncio.run(_apply_seed_admin_role())
        if role is not None and role != "user":
            # Use the async session to update the freshly-created user so
            # the DB work runs in the test process' event loop rather than
            # in the TestClient server thread (avoids greenlet issues).
            if role == "admin":
                sql = text(
                    "UPDATE users SET role = :role, is_superuser = :is_superuser WHERE id = :id")
                params = {"role": role, "is_superuser": True, "id": user_id}
            else:
                sql = text("UPDATE users SET role = :role WHERE id = :id")
                params = {"role": role, "id": user_id}

            async def _apply_role() -> None:
                """Supports the test suite by  apply role."""
                async with db_session.SessionLocal() as s:
                    await s.execute(sql, params)
                    await s.commit()

            asyncio.run(_apply_role())
        if permissions is not None:
            # Store permissions JSON directly on the user row using async session.
            perm_sql = text(
                "UPDATE users SET permissions = :permissions WHERE id = :id")
            import json

            perm_params = {"permissions": json.dumps(
                permissions), "id": user_id}

            async def _apply_permissions() -> None:
                """Supports the test suite by  apply permissions."""
                async with db_session.SessionLocal() as s:
                    await s.execute(perm_sql, perm_params)
                    await s.commit()

            asyncio.run(_apply_permissions())
    return body


def login_user(client: TestClient, *, email: str, password: str = "StrongPass123!") -> str:
    """Log in through the real HTTP endpoint and return just the access token."""
    response = client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth_headers(token: str) -> dict:
    """Small convenience wrapper so tests don't retype this dict everywhere."""
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def registered_user(client: TestClient) -> dict:
    """A ready-made, already-registered user for tests that don't care about the details."""
    return register_user(client, email="fixture-user@example.com", username="fixture-user")


@pytest.fixture()
def auth_token(client: TestClient, registered_user: dict) -> str:
    """An access token for `registered_user`, for tests that just need "a logged-in user"."""
    return login_user(client, email="fixture-user@example.com")
