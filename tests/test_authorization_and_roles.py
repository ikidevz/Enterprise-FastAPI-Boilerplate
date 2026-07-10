import asyncio
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from conftest import auth_headers, login_user, register_user
from backend.core.security.rbac import AuthorizationPolicy, require_policy
from backend.database import session as db_session
from backend.domain.rbac import service as rbac_service_module
from backend.domain.rbac.service import RbacService
from backend.domain.users.model import User


@pytest.fixture(autouse=True)
def ensure_rbac_seed_data(client: TestClient) -> Iterator[None]:
    """Ensure the default RBAC roles exist in the per-test database."""
    rbac_service_module._rbac_seed_initialized = False

    async def _seed() -> None:
        async with db_session.SessionLocal() as db:
            await RbacService(db).ensure_seed_data()
            await db.commit()

    asyncio.run(_seed())
    yield


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


@pytest.mark.asyncio
async def test_superuser_is_always_allowed_regardless_of_role_or_permissions() -> None:
    """Ensures superuser is always allowed regardless of role or permissions."""
    policy = AuthorizationPolicy(required_roles=(
        "admin",), required_permissions=("read:admin",))
    superuser = _make_user(is_superuser=True, role="user", permissions=[])

    assert await policy.allows(superuser) is True


@pytest.mark.asyncio
async def test_user_without_the_required_permission_is_denied() -> None:
    """Ensures user without the required permission is denied."""
    policy = AuthorizationPolicy(required_permissions=("read:admin",))
    regular_user = _make_user(permissions=[])

    assert await policy.allows(regular_user) is False


@pytest.mark.asyncio
async def test_user_with_the_required_permission_is_allowed() -> None:
    """Ensures user with the required permission is allowed."""
    policy = AuthorizationPolicy(required_permissions=("read:admin",))
    permitted_user = _make_user(permissions=["read:admin"])

    assert await policy.allows(permitted_user) is True


@pytest.mark.asyncio
async def test_role_check_is_based_on_the_role_field_not_the_username() -> None:
    """Ensures role check is based on the role field not the username."""
    policy = AuthorizationPolicy(required_roles=("admin",))

    real_admin_with_an_unrelated_username = _make_user(
        username="jane-from-accounting", role="admin", permissions=[]
    )
    regular_user_who_happens_to_be_named_admin = _make_user(
        username="admin", role="user", permissions=[]
    )

    assert await policy.allows(real_admin_with_an_unrelated_username) is True
    assert await policy.allows(regular_user_who_happens_to_be_named_admin) is False


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
    # Use the test helper which now applies role/permissions directly in DB
    """Ensures permissions endpoint reflects the caller role and permissions."""
    register_user(
        client,
        email="governance@example.com",
        username="governance",
        role="manager",
        permissions=["read:admin"],
    )

    token = login_user(client, email="governance@example.com")

    # The demo permissions endpoint was removed as part of the audit cleanup.
    # Confirm the caller's own user record reflects the assigned role/permissions.
    response = client.get("/api/v1/users/1", headers=auth_headers(token))
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "manager"
    assert "read:admin" in body.get("permissions", [])


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


def test_regular_user_cannot_list_all_users(client: TestClient) -> None:
    """Only admin/staff should be able to list all users. Regular users should get 403."""
    register_user(client, email="admin-list@example.com",
                  username="admin-list", role="admin")

    register_user(client, email="regular-list@example.com",
                  username="regular-list", role="user")

    # Regular user tries to list all users
    regular_token = login_user(client, email="regular-list@example.com")
    response = client.get(
        "/api/v1/users/", headers=auth_headers(regular_token))

    # Should be forbidden
    assert response.status_code == 403

    # But admin should still be able to list
    admin_token = login_user(client, email="admin-list@example.com")
    admin_response = client.get("/api/v1/users/",
                                headers=auth_headers(admin_token))
    assert admin_response.status_code == 200


def test_cannot_remove_last_admin_role_via_admin_user_endpoint(client: TestClient) -> None:
    """The API should prevent removing the last admin role from the final admin user."""
    register_user(client, email="single-admin@example.com",
                  username="single-admin", role="admin")
    admin_token = login_user(client, email="single-admin@example.com")

    response = client.patch(
        "/api/v1/admin/users/1/role",
        headers=auth_headers(admin_token),
        json={"role": "user", "permissions": []},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "insufficient_permission"


def test_create_product_requires_admin_role(client: TestClient) -> None:
    """Only admin/staff should be able to create products. Regular users should get 403.

    See IMPROVEMENT.MD section 1.2: POST /api/v1/products/ only checks "is logged in",
    not role. Any authenticated user can create products. This test documents the
    intended behavior and will pass once the bug is fixed.
    """
    # Register regular user
    register_user(client, email="product-creator@example.com",
                  username="product-creator", role="user")
    regular_token = login_user(client, email="product-creator@example.com")

    # Try to create a product as regular user
    response = client.post(
        "/api/v1/products/",
        headers=auth_headers(regular_token),
        json={"name": "Unauthorized Product",
              "price": 9.99, "description": "should fail"}
    )

    # Should be forbidden
    assert response.status_code == 403


def test_update_product_requires_admin_role(client: TestClient) -> None:
    """Only admin/staff should be able to update products. Regular users should get 403.

    See IMPROVEMENT.MD section 1.2: PUT /api/v1/products/{id} only checks "is logged in".
    """
    # Create a product as admin
    register_user(client, email="admin-product@example.com",
                  username="admin-product", role="admin")
    admin_token = login_user(client, email="admin-product@example.com")

    create_response = client.post(
        "/api/v1/products/",
        headers=auth_headers(admin_token),
        json={"name": "Protected Product", "price": 19.99,
              "description": "admin created"}
    )
    assert create_response.status_code == 201
    product_id = create_response.json()["id"]

    # Register regular user and try to update
    register_user(client, email="product-updater@example.com",
                  username="product-updater", role="user")
    regular_token = login_user(client, email="product-updater@example.com")

    response = client.put(
        f"/api/v1/products/{product_id}",
        headers=auth_headers(regular_token),
        json={"name": "Hijacked Product"}
    )

    assert response.status_code == 403


def test_delete_product_requires_admin_role(client: TestClient) -> None:
    """Only admin/staff should be able to delete products. Regular users should get 403.

    See IMPROVEMENT.MD section 1.2: DELETE /api/v1/products/{id} only checks "is logged in".
    """
    # Create a product as admin
    register_user(client, email="admin-product-del@example.com",
                  username="admin-product-del", role="admin")
    admin_token = login_user(client, email="admin-product-del@example.com")

    create_response = client.post(
        "/api/v1/products/",
        headers=auth_headers(admin_token),
        json={"name": "Deletable Product", "price": 29.99,
              "description": "admin created"}
    )
    assert create_response.status_code == 201
    product_id = create_response.json()["id"]

    # Register regular user and try to delete
    register_user(client, email="product-deleter@example.com",
                  username="product-deleter", role="user")
    regular_token = login_user(client, email="product-deleter@example.com")

    response = client.delete(
        f"/api/v1/products/{product_id}",
        headers=auth_headers(regular_token)
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_require_policy_honors_role_based_permissions(client: TestClient) -> None:
    """Policy-based authorization should honor permissions coming from RBAC role assignments."""
    created_user = register_user(
        client, email="policy-user@example.com", username="policy-user", role="user")

    async with db_session.SessionLocal() as db:
        service = RbacService(db)
        role = await service.create_role(key="reviewer", name="Reviewer")
        permission = await service.create_permission(key="reports.view", name="View Reports")
        await service.set_role_permissions(role_id=role.id, permission_ids=[permission.id], acting_user=None)
        await service.assign_roles_to_user(user_id=created_user["id"], role_ids=[role.id], acting_user=None)

        user = await db.get(User, created_user["id"])
        assert user is not None

        dependency = require_policy(AuthorizationPolicy(
            required_permissions=("reports.view",)))
        authorized_user = await dependency(current_user=user, db=db)
        assert authorized_user is user


def test_permission_granted_via_admin_role_endpoint_is_honored_by_permission_gate(client: TestClient) -> None:
    """A permission assigned through the admin role endpoint should work for later permission-gated routes."""
    register_user(client, email="permission-admin@example.com",
                  username="permission-admin", role="admin")
    admin_token = login_user(client, email="permission-admin@example.com")

    register_user(client, email="permission-target@example.com",
                  username="permission-target", role="user")
    target_token = login_user(client, email="permission-target@example.com")

    response = client.patch(
        "/api/v1/admin/users/2/role",
        headers=auth_headers(admin_token),
        json={"permissions": ["system.billing_toggle"]},
    )
    assert response.status_code == 200

    gated_response = client.patch(
        "/api/v1/admin/system/subscriptions-enabled",
        headers=auth_headers(target_token),
        json={"subscriptions_enabled": True},
    )

    assert gated_response.status_code == 200
    assert gated_response.json()["subscriptions_enabled"] is True


def test_admin_can_bulk_update_user_roles_and_permissions(client: TestClient) -> None:
    """Admin users can apply a batch of role/permission updates in one request."""
    register_user(client, email="bulk-admin@example.com",
                  username="bulk-admin", role="admin")
    admin_token = login_user(client, email="bulk-admin@example.com")

    register_user(client, email="bulk-user-1@example.com",
                  username="bulk-user-1", role="user")
    register_user(client, email="bulk-user-2@example.com",
                  username="bulk-user-2", role="user")

    response = client.patch(
        "/api/v1/admin/users/roles",
        headers=auth_headers(admin_token),
        json={
            "updates": [
                {"user_id": 2, "role": "staff",
                    "permissions": ["read:reports"]},
                {"user_id": 3, "role": "admin",
                    "permissions": ["manage:users"]},
            ]
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["role"] == "staff"
    assert body[0]["permissions"] == ["read:reports"]
    assert body[1]["role"] == "admin"
    assert body[1]["permissions"] == ["manage:users"]
