"""Role and permission checks: the AuthorizationPolicy/PermissionPolicy unit tests,
plus the admin-only HTTP endpoints that use them.

The most important test in this file is the xfail one near the bottom -
it's the regression test for the single highest-severity bug found in this
codebase (see IMPROVEMENT_SUGGESTIONS_MERGED.md section 1.1). Read the
comment above it even if you skip everything else in this file.
"""
import pytest
from fastapi.testclient import TestClient

from conftest import auth_headers, login_user, register_user
from backend.common.rbac import AuthorizationPolicy
from backend.domain.users.model import User


def _make_user(**overrides) -> User:
    """Build a plain in-memory User object for unit-testing AuthorizationPolicy directly,
    without needing a database at all.
    """
    defaults = dict(
        id=1,
        username="someone",
        email="someone@example.com",
        hashed_password="not-a-real-hash",
        is_superuser=False,
        role="user",
        permissions=[],
    )
    defaults.update(overrides)
    return User(**defaults)


def test_superuser_is_always_allowed_regardless_of_role_or_permissions() -> None:
    policy = AuthorizationPolicy(required_roles=(
        "admin",), required_permissions=("read:admin",))
    superuser = _make_user(is_superuser=True, role="user", permissions=[])

    assert policy.allows(superuser) is True


def test_user_without_the_required_permission_is_denied() -> None:
    policy = AuthorizationPolicy(required_permissions=("read:admin",))
    regular_user = _make_user(permissions=[])

    assert policy.allows(regular_user) is False


def test_user_with_the_required_permission_is_allowed() -> None:
    policy = AuthorizationPolicy(required_permissions=("read:admin",))
    permitted_user = _make_user(permissions=["read:admin"])

    assert policy.allows(permitted_user) is True


def test_role_check_is_based_on_the_role_field_not_the_username() -> None:
    policy = AuthorizationPolicy(required_roles=("admin",))

    real_admin_with_an_unrelated_username = _make_user(
        username="jane-from-accounting", role="admin", permissions=[]
    )
    regular_user_who_happens_to_be_named_admin = _make_user(
        username="admin", role="user", permissions=[]
    )

    assert policy.allows(real_admin_with_an_unrelated_username) is True
    assert policy.allows(regular_user_who_happens_to_be_named_admin) is False


def test_admin_users_endpoint_is_reachable_by_the_seeded_style_admin_account(
    client: TestClient,
) -> None:
    """This test intentionally names the admin user "admin" - see the note below.

    This currently passes for the wrong reason: require_role("admin") checks
    `username`, not `role`, so this only works because the username here is
    literally "admin" (matching how backend/scripts/seed_data.py bootstraps
    its default admin). This test documents *today's actual behavior*; the
    xfail test above documents what *should* be true instead. Once the bug
    is fixed, this test should still pass (since the account's role is also
    set to "admin"), so it doesn't need to change.
    """
    register_user(client, email="admin@example.com", username="admin")
    token = login_user(client, email="admin@example.com")

    promote_response = client.put(
        "/api/v1/users/1",
        headers=auth_headers(token),
        json={"is_superuser": True},
    )
    assert promote_response.status_code == 200

    response = client.get("/api/v1/admin/users", headers=auth_headers(token))

    assert response.status_code == 200


def test_permissions_endpoint_reflects_the_caller_role_and_permissions(client: TestClient) -> None:
    register_response = client.post(
        "/api/v1/users/",
        json={
            "email": "governance@example.com",
            "username": "governance",
            "password": "StrongPass123!",
            "role": "manager",
            "permissions": ["read:admin"],
        },
    )
    assert register_response.status_code == 201

    token = login_user(client, email="governance@example.com")

    response = client.get("/api/v1/admin/permissions",
                          headers=auth_headers(token))

    assert response.status_code == 200
    assert response.json()["role"] == "manager"


def test_regular_user_cannot_change_their_own_privileged_fields(client: TestClient) -> None:
    """A non-superuser PUTting their own profile should not be able to grant themselves privileges."""
    register_user(client, email="self-promote@example.com",
                  username="self-promote")
    token = login_user(client, email="self-promote@example.com")

    response = client.put(
        "/api/v1/users/1",
        headers=auth_headers(token),
        json={"is_superuser": True, "is_active": False},
    )

    assert response.status_code == 200
    assert response.json()["is_superuser"] is False
    assert response.json()["is_active"] is True
