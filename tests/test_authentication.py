"""Registration, login, account lockout, and refresh/logout token handling.

If you're trying to understand the auth system, this is the file to read
first: it walks through the whole lifecycle a user goes through - sign up,
log in, get locked out after too many bad attempts, refresh a token,
log out - in the order that actually happens.

A couple of tests below are marked `xfail(strict=True)`. That's not a typo
and it's not "this test is broken" - it means: this documents a real,
currently-open bug in the application code (not in the test). The test
asserts what *should* happen; today it fails, on purpose, and pytest
reports it as an expected failure so the overall suite still shows green.
The day someone fixes the underlying bug, this exact test will start
passing - and because it's `strict=True`, pytest will treat that
unexpected pass as a hard failure, forcing whoever fixed it to notice and
delete the xfail marker. See IMPROVEMENT_SUGGESTIONS_MERGED.md for the
full write-up (source code, root cause, suggested fix) behind each one.
"""
import pytest
from fastapi.testclient import TestClient

from conftest import auth_headers, login_user, register_user


def test_registration_creates_a_user_and_returns_its_public_profile(client: TestClient) -> None:
    user = register_user(
        client, email="new-user@example.com", username="new-user")

    assert user["email"] == "new-user@example.com"
    assert user["username"] == "new-user"
    assert "password" not in user
    assert "hashed_password" not in user


def test_weak_passwords_are_rejected_at_the_schema_level(client: TestClient) -> None:
    """Password strength validation happens in the Pydantic schema, before any DB work."""
    response = client.post(
        "/api/v1/users/",
        json={"email": "weak@example.com",
              "username": "weak", "password": "weakpass"},
    )

    assert response.status_code == 422


def test_duplicate_email_registration_is_rejected_cleanly(client: TestClient) -> None:
    payload = {
        "email": "duplicate@example.com",
        "username": "duplicate-one",
        "password": "StrongPass123!",
    }
    first = client.post("/api/v1/users/", json=payload)
    assert first.status_code == 201

    duplicate = client.post(
        "/api/v1/users/",
        json={**payload, "username": "duplicate-two"},
    )
    assert duplicate.status_code == 400
    assert duplicate.json()["error_code"] == "duplicate_user"


def test_duplicate_username_with_a_different_email_is_rejected_cleanly(client: TestClient) -> None:
    register_user(client, email="first-owner@example.com",
                  username="shared-name")

    response = client.post(
        "/api/v1/users/",
        json={
            "email": "second-owner@example.com",
            "username": "shared-name",
            "password": "StrongPass123!",
        },
    )

    assert response.status_code in (400, 409)


def test_login_with_correct_credentials_returns_tokens(client: TestClient) -> None:
    register_user(client, email="login@example.com", username="login")

    response = client.post(
        "/api/v1/auth/login",
        data={"username": "login@example.com", "password": "StrongPass123!"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]


def test_login_with_wrong_password_is_rejected(client: TestClient) -> None:
    register_user(client, email="wrongpass@example.com", username="wrongpass")

    response = client.post(
        "/api/v1/auth/login",
        data={"username": "wrongpass@example.com", "password": "totally-wrong"},
    )

    assert response.status_code == 401


def test_login_with_unknown_email_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "nobody-registered@example.com", "password": "whatever"},
    )

    assert response.status_code == 401


def test_access_token_grants_access_to_the_current_user_profile(client: TestClient) -> None:
    register_user(client, email="me-route@example.com", username="me-route")
    token = login_user(client, email="me-route@example.com")

    response = client.get("/api/v1/auth/me", headers=auth_headers(token))

    assert response.status_code == 200
    assert response.json()["email"] == "me-route@example.com"


def test_access_token_for_deleted_user_is_rejected(client: TestClient) -> None:
    import asyncio

    from sqlalchemy import delete

    from backend.database import session as db_session
    from backend.domain.users.model import User

    register_user(client, email="deleted-user@example.com",
                  username="deleted-user")
    token = login_user(client, email="deleted-user@example.com")

    async def delete_user() -> None:
        async with db_session.SessionLocal() as db:
            await db.execute(delete(User).where(User.email == "deleted-user@example.com"))
            await db.commit()

    asyncio.run(delete_user())

    response = client.get("/api/v1/auth/me", headers=auth_headers(token))

    assert response.status_code == 401


def test_account_locks_after_five_failed_login_attempts(client: TestClient) -> None:
    register_user(client, email="lockout@example.com", username="lockout")

    for _ in range(5):
        response = client.post(
            "/api/v1/auth/login",
            data={"username": "lockout@example.com",
                  "password": "wrong-password"},
        )
        assert response.status_code == 401

    locked_response = client.post(
        "/api/v1/auth/login",
        data={"username": "lockout@example.com", "password": "StrongPass123!"},
    )
    assert locked_response.status_code == 403
    assert "locked" in locked_response.json()["detail"].lower()


def test_account_can_log_in_again_once_the_lockout_window_has_expired(client: TestClient) -> None:
    import asyncio
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from backend.database import session as db_session
    from backend.domain.users.model import User

    register_user(client, email="recovers@example.com", username="recovers")
    for _ in range(5):
        client.post(
            "/api/v1/auth/login",
            data={"username": "recovers@example.com",
                  "password": "wrong-password"},
        )

    async def expire_the_lockout_window() -> None:
        async with db_session.SessionLocal() as db:
            result = await db.execute(select(User).where(User.email == "recovers@example.com"))
            user = result.scalar_one()
            user.locked_until = datetime.now(
                timezone.utc) - timedelta(minutes=1)
            await db.commit()

    asyncio.run(expire_the_lockout_window())

    response = client.post(
        "/api/v1/auth/login",
        data={"username": "recovers@example.com",
              "password": "StrongPass123!"},
    )

    assert response.status_code == 200


def test_refresh_token_issues_a_new_access_and_refresh_token(client: TestClient) -> None:
    register_user(client, email="refresh@example.com", username="refresh")
    login_response = client.post(
        "/api/v1/auth/login",
        data={"username": "refresh@example.com", "password": "StrongPass123!"},
    )
    refresh_token = login_response.json()["refresh_token"]

    response = client.post("/api/v1/auth/refresh",
                           params={"refresh_token": refresh_token})

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert response.json()["access_token"]
    assert response.json()["refresh_token"]


def test_refresh_token_cannot_be_reused_after_rotation(client: TestClient) -> None:
    """Refresh tokens are single-use: once rotated, the old one must stop working."""
    register_user(client, email="rotate@example.com", username="rotate")
    login_response = client.post(
        "/api/v1/auth/login",
        data={"username": "rotate@example.com", "password": "StrongPass123!"},
    )
    old_refresh_token = login_response.json()["refresh_token"]

    first_use = client.post("/api/v1/auth/refresh",
                            params={"refresh_token": old_refresh_token})
    assert first_use.status_code == 200

    reuse_attempt = client.post(
        "/api/v1/auth/refresh", params={"refresh_token": old_refresh_token})
    assert reuse_attempt.status_code == 401


def test_refresh_with_an_unknown_token_is_rejected(client: TestClient) -> None:
    response = client.post("/api/v1/auth/refresh",
                           params={"refresh_token": "not-a-real-token"})

    assert response.status_code == 401


def test_logout_revokes_the_refresh_token(client: TestClient) -> None:
    register_user(client, email="logout@example.com", username="logout")
    login_response = client.post(
        "/api/v1/auth/login",
        data={"username": "logout@example.com", "password": "StrongPass123!"},
    )
    refresh_token = login_response.json()["refresh_token"]

    logout_response = client.post(
        "/api/v1/auth/logout", params={"refresh_token": refresh_token})
    assert logout_response.status_code == 200

    reuse_attempt = client.post(
        "/api/v1/auth/refresh", params={"refresh_token": refresh_token})
    assert reuse_attempt.status_code == 401
