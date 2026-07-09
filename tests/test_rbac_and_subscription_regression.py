from __future__ import annotations

from backend.core.config import settings
from conftest import login_user, register_user


def test_grant_ceiling_rejects_assigning_a_role_with_permissions_the_actor_does_not_hold(client):
    register_user(client, email="rbac-admin@example.com",
                  username="rbacadmin", password="StrongPass123!", role="admin")
    actor = register_user(client, email="rbac-actor@example.com",
                          username="rbacactor", password="StrongPass123!")
    target = register_user(client, email="rbac-target@example.com",
                           username="rbactarget", password="StrongPass123!")

    admin_headers = {
        "Authorization": f"Bearer {login_user(client, email='rbac-admin@example.com')}"}
    actor_headers = {
        "Authorization": f"Bearer {login_user(client, email='rbac-actor@example.com')}"}

    ops_role_response = client.post(
        "/api/v1/admin/roles",
        json={"key": "ops", "name": "Ops"},
        headers=admin_headers,
    )
    assert ops_role_response.status_code == 201, ops_role_response.text
    ops_role_id = ops_role_response.json()["id"]

    rbac_permission_response = client.post(
        "/api/v1/admin/permissions",
        json={"key": "rbac.manage", "name": "Manage RBAC"},
        headers=admin_headers,
    )
    assert rbac_permission_response.status_code == 201, rbac_permission_response.text
    client.put(
        f"/api/v1/admin/roles/{ops_role_id}/permissions",
        json={"permission_ids": [rbac_permission_response.json()["id"]]},
        headers=admin_headers,
    )
    assign_ops_role_response = client.post(
        f"/api/v1/admin/users/{actor['id']}/roles",
        json={"role_ids": [ops_role_id]},
        headers=admin_headers,
    )
    assert assign_ops_role_response.status_code == 200, assign_ops_role_response.text

    finance_role_response = client.post(
        "/api/v1/admin/roles",
        json={"key": "finance", "name": "Finance"},
        headers=admin_headers,
    )
    assert finance_role_response.status_code == 201, finance_role_response.text
    finance_role_id = finance_role_response.json()["id"]

    billing_permission_response = client.post(
        "/api/v1/admin/permissions",
        json={"key": "billing.manage", "name": "Manage Billing"},
        headers=admin_headers,
    )
    assert billing_permission_response.status_code == 201, billing_permission_response.text
    client.put(
        f"/api/v1/admin/roles/{finance_role_id}/permissions",
        json={"permission_ids": [billing_permission_response.json()["id"]]},
        headers=admin_headers,
    )

    response = client.post(
        f"/api/v1/admin/users/{target['id']}/roles",
        json={"role_ids": [finance_role_id]},
        headers=actor_headers,
    )
    assert response.status_code == 403, response.text
    assert response.json()["detail"]["error"] == "insufficient_permission"


def test_disabled_feature_returns_service_unavailable(client):
    user = register_user(
        client, email="disabled-user@example.com", username="disableduser")
    headers = {
        "Authorization": f"Bearer {login_user(client, email='disabled-user@example.com')}"}

    original_value = settings.disabled_features
    settings.disabled_features = ["reports.export"]
    try:
        response = client.get(
            "/api/v1/billing/feature-check?feature=reports.export",
            headers=headers,
        )
        assert response.status_code == 503, response.text
        assert response.json()["error"] == "feature_disabled"
    finally:
        settings.disabled_features = original_value


def test_billing_admin_plan_management(client):
    register_user(client, email="admin@example.com",
                  username="billingadmin", password="StrongPass123!", role="admin")
    admin_headers = {
        "Authorization": f"Bearer {login_user(client, email='admin@example.com')}"
    }

    plan_response = client.post(
        "/api/v1/billing/admin/plans",
        json={"key": "pro", "name": "Pro",
              "price_cents": 999, "billing_interval": "month"},
        headers=admin_headers,
    )
    assert plan_response.status_code == 201, plan_response.text
    assert plan_response.json()["key"] == "pro"

    plans_response = client.get("/api/v1/billing/plans")
    assert plans_response.status_code == 200, plans_response.text
    assert any(plan["key"] == "pro" for plan in plans_response.json())


def test_billing_settings_checkout_and_cancellation_flow(client):
    admin = register_user(client, email="billingops@example.com",
                          username="billingops", password="StrongPass123!", role="admin")
    user = register_user(client, email="subscriber@example.com",
                         username="subscriber", password="StrongPass123!")

    admin_headers = {
        "Authorization": f"Bearer {login_user(client, email='billingops@example.com')}"}
    member_headers = {
        "Authorization": f"Bearer {login_user(client, email='subscriber@example.com')}"}

    plan_response = client.post(
        "/api/v1/billing/admin/plans",
        json={"key": "pro", "name": "Pro",
              "price_cents": 999, "billing_interval": "month"},
        headers=admin_headers,
    )
    assert plan_response.status_code == 201, plan_response.text
    plan_id = plan_response.json()["id"]

    toggle_response = client.patch(
        "/api/v1/billing/admin/settings",
        json={"subscriptions_enabled": True,
              "payment_providers_enabled": ["stripe"]},
        headers=admin_headers,
    )
    assert toggle_response.status_code == 200, toggle_response.text
    assert toggle_response.json()["subscriptions_enabled"] is True

    checkout_response = client.post(
        "/api/v1/billing/checkout",
        json={"plan_id": plan_id, "provider": "stripe"},
        headers=member_headers,
    )
    assert checkout_response.status_code == 200, checkout_response.text
    assert checkout_response.json()["provider"] == "stripe"

    assign_response = client.post(
        "/api/v1/billing/subscriptions/assign",
        json={"user_id": user["id"], "plan_id": plan_id, "provider": "manual"},
        headers=admin_headers,
    )
    assert assign_response.status_code == 201, assign_response.text

    cancel_response = client.post(
        "/api/v1/billing/subscriptions/cancel",
        headers=member_headers,
    )
    assert cancel_response.status_code == 200, cancel_response.text
    assert cancel_response.json()["status"] == "canceled"


def test_dynamic_rbac_and_feature_gate_work_end_to_end(client):
    register_user(client, email="admin@example.com",
                  username="rbacadmin", password="StrongPass123!", role="admin")
    user = register_user(client, email="member@example.com",
                         username="member", password="StrongPass123!")

    admin_headers = {
        "Authorization": f"Bearer {login_user(client, email='admin@example.com')}"}
    member_headers = {
        "Authorization": f"Bearer {login_user(client, email='member@example.com')}"}

    role_response = client.post(
        "/api/v1/admin/roles",
        json={"key": "analyst", "name": "Analyst"},
        headers=admin_headers,
    )
    assert role_response.status_code == 201, role_response.text
    role_id = role_response.json()["id"]

    permission_response = client.post(
        "/api/v1/admin/permissions",
        json={"key": "reports.view", "name": "View Reports"},
        headers=admin_headers,
    )
    assert permission_response.status_code == 201, permission_response.text
    permission_id = permission_response.json()["id"]

    assign_permission_response = client.put(
        f"/api/v1/admin/roles/{role_id}/permissions",
        json={"permission_ids": [permission_id]},
        headers=admin_headers,
    )
    assert assign_permission_response.status_code == 200, assign_permission_response.text

    assign_role_response = client.post(
        f"/api/v1/admin/users/{user['id']}/roles",
        json={"role_ids": [role_id]},
        headers=admin_headers,
    )
    assert assign_role_response.status_code == 200, assign_role_response.text

    permission_check = client.get(
        "/api/v1/rbac/check-permission",
        headers=member_headers,
    )
    assert permission_check.status_code == 200, permission_check.text
    assert permission_check.json()["allowed"] is True

    original_value = settings.subscriptions_enabled
    settings.subscriptions_enabled = True
    try:
        feature_response = client.get(
            "/api/v1/billing/feature-check",
            headers=member_headers,
        )
        assert feature_response.status_code == 402, feature_response.text
        assert feature_response.json()["error"] == "feature_not_in_plan"
    finally:
        settings.subscriptions_enabled = original_value
