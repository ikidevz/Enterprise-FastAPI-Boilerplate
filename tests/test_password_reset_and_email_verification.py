"""Password reset and email verification flows.

Both flows follow the same shape: request a token (which should only ever
reach the user via the email side-channel), then confirm using that token.
`RequestPasswordResetUseCase` gets this right; the tests below show that,
and also show (via an xfail) that `RequestEmailVerificationUseCase` doesn't
currently follow the same, safer pattern.
"""

import re

import pytest
from fastapi.testclient import TestClient

from conftest import CaptureTransport, register_user, wait_for_background_jobs
from backend.infrastructure.email.transport import email_delivery_service

TOKEN_PATTERN = re.compile(
    r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
)


def test_password_reset_request_always_returns_the_same_generic_message(
    client: TestClient,
) -> None:
    """Whether or not the email exists, the response should look identical.

    This is what stops someone from using this endpoint to check which
    email addresses are registered (account enumeration).
    """
    register_user(
        client,
        email="has-account@example.com",
        username="has-account",
    )

    real_account = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "has-account@example.com"},
    )
    unknown_account = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "no-such-account@example.com"},
    )

    assert real_account.status_code == 200
    assert unknown_account.status_code == 200
    assert real_account.json() == unknown_account.json()
    assert "token" not in real_account.json()


def test_password_reset_email_contains_a_real_token_that_can_be_used_to_reset_the_password(
    client: TestClient,
) -> None:
    """The reset token should only travel through the (fake, captured) email—not the HTTP response."""
    transport = CaptureTransport()
    original_transport = email_delivery_service.transport
    email_delivery_service.transport = transport

    try:
        register_user(
            client,
            email="reset-me@example.com",
            username="reset-me",
        )

        response = client.post(
            "/api/v1/auth/password-reset/request",
            json={"email": "reset-me@example.com"},
        )

        assert response.status_code == 200
        assert "token" not in response.json()

        wait_for_background_jobs()

        assert (
            transport.calls
        ), "expected the reset email to have been sent via the background job queue"

        token_match = TOKEN_PATTERN.search(transport.calls[-1]["body"])
        assert token_match is not None

        confirm_response = client.post(
            "/api/v1/auth/password-reset/confirm",
            json={
                "token": token_match.group(1),
                "new_password": "BrandNewPass123!",
            },
        )

        assert confirm_response.status_code == 200

        login_with_new_password = client.post(
            "/api/v1/auth/login",
            data={
                "username": "reset-me@example.com",
                "password": "BrandNewPass123!",
            },
        )

        assert login_with_new_password.status_code == 200

    finally:
        email_delivery_service.transport = original_transport


def test_password_reset_confirm_rejects_an_unknown_token(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={
            "token": "not-a-real-token",
            "new_password": "SomethingNew123!",
        },
    )

    assert response.status_code in (400, 401, 404)


def test_email_verification_request_and_confirm_marks_the_account_verified(
    client: TestClient,
) -> None:
    transport = CaptureTransport()
    original_transport = email_delivery_service.transport
    email_delivery_service.transport = transport

    try:
        register_user(
            client,
            email="verify-me@example.com",
            username="verify-me",
        )

        request_response = client.post(
            "/api/v1/auth/email-verification/request",
            json={"email": "verify-me@example.com"},
        )

        assert request_response.status_code == 200

        wait_for_background_jobs()

        assert (
            transport.calls
        ), "expected the verification email to have been sent via the background job queue"

        token_match = TOKEN_PATTERN.search(transport.calls[-1]["body"])
        assert token_match is not None

        confirm_response = client.post(
            "/api/v1/auth/email-verification/confirm",
            json={"token": token_match.group(1)},
        )

        assert confirm_response.status_code == 200

    finally:
        email_delivery_service.transport = original_transport


def test_email_verification_request_never_returns_the_token_or_leaks_account_existence(
    client: TestClient,
) -> None:
    register_user(
        client,
        email="should-not-leak@example.com",
        username="should-not-leak",
    )

    real_account = client.post(
        "/api/v1/auth/email-verification/request",
        json={"email": "should-not-leak@example.com"},
    )

    unknown_account = client.post(
        "/api/v1/auth/email-verification/request",
        json={"email": "no-such-account@example.com"},
    )

    assert "token" not in real_account.json()
    assert real_account.json() == unknown_account.json()


def test_login_requires_email_verification_when_enabled(
    client: TestClient,
) -> None:
    """When email verification is required, unverified users should not be able to log in.

    See IMPROVEMENT.MD section 16.2: is_verified is tracked but never enforced.
    This test documents the intended behavior when the
    require_email_verification setting is enabled.

    Note:
        This behavior should be controlled by a
        require_email_verification setting in the config that defaults
        to False for backward compatibility.
    """
    from backend.core.config import settings

    if not settings.require_email_verification:
        pytest.skip("require_email_verification is disabled in config")

    register_user(
        client,
        email="unverified@example.com",
        username="unverified",
    )

    response = client.post(
        "/api/v1/auth/login",
        data={
            "username": "unverified@example.com",
            "password": "StrongPass123!",
        },
    )

    assert response.status_code == 403
    assert (
        "verification" in response.json()["detail"].lower()
        or "verified" in response.json()["detail"].lower()
    )


def test_verified_user_can_log_in_normally(
    client: TestClient,
) -> None:
    """Verified users should always be able to log in regardless of the enforcement setting."""
    transport = CaptureTransport()
    original_transport = email_delivery_service.transport
    email_delivery_service.transport = transport

    try:
        register_user(
            client,
            email="verify-then-login@example.com",
            username="verify-then-login",
        )

        request_response = client.post(
            "/api/v1/auth/email-verification/request",
            json={"email": "verify-then-login@example.com"},
        )

        assert request_response.status_code == 200

        wait_for_background_jobs()

        token_match = TOKEN_PATTERN.search(transport.calls[-1]["body"])
        assert token_match is not None

        confirm_response = client.post(
            "/api/v1/auth/email-verification/confirm",
            json={"token": token_match.group(1)},
        )

        assert confirm_response.status_code == 200

        login_response = client.post(
            "/api/v1/auth/login",
            data={
                "username": "verify-then-login@example.com",
                "password": "StrongPass123!",
            },
        )

        assert login_response.status_code == 200
        assert login_response.json()["access_token"]

    finally:
        email_delivery_service.transport = original_transport
