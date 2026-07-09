from __future__ import annotations

from backend.core.config import settings
from conftest import login_user, register_user


def test_plan_feature_mapping_and_entitlement_check(client):
    admin = register_user(client, email="billing-admin@example.com",
                          username="billing-admin", role="admin")
    user = register_user(client, email="member@example.com", username="member")

    admin_headers = {
        "Authorization": f"Bearer {login_user(client, email='billing-admin@example.com')}"}
    member_headers = {
        "Authorization": f"Bearer {login_user(client, email='member@example.com')}"}

    plan_response = client.post(
        "/api/v1/billing/admin/plans",
        json={"key": "pro", "name": "Pro",
              "price_cents": 999, "billing_interval": "month"},
        headers=admin_headers,
    )
    assert plan_response.status_code == 201
    plan_id = plan_response.json()["id"]

    feature_response = client.post(
        "/api/v1/billing/admin/features",
        json={"key": "reports.export", "name": "Export Reports"},
        headers=admin_headers,
    )
    assert feature_response.status_code == 201
    feature_key = feature_response.json()["key"]

    mapping_response = client.post(
        f"/api/v1/billing/admin/plans/{plan_id}/features",
        json={"feature_keys": [feature_key]},
        headers=admin_headers,
    )
    assert mapping_response.status_code == 200

    subscription_response = client.post(
        "/api/v1/billing/subscriptions/assign",
        json={"user_id": user["id"], "plan_id": plan_id, "provider": "manual"},
        headers=admin_headers,
    )
    assert subscription_response.status_code == 201

    original_value = settings.subscriptions_enabled
    settings.subscriptions_enabled = True
    try:
        feature_gate_response = client.get(
            "/api/v1/billing/feature-check?feature=reports.export",
            headers=member_headers,
        )
        assert feature_gate_response.status_code == 200, feature_gate_response.text
        assert feature_gate_response.json()["allowed"] is True
    finally:
        settings.subscriptions_enabled = original_value


def test_webhook_is_idempotent_and_persists_event(client):
    admin = register_user(client, email="webhook-admin@example.com",
                          username="webhook-admin", role="admin")
    user = register_user(
        client, email="webhook-user@example.com", username="webhook-user")

    admin_headers = {
        "Authorization": f"Bearer {login_user(client, email='webhook-admin@example.com')}"}

    plan_response = client.post(
        "/api/v1/billing/admin/plans",
        json={"key": "pro", "name": "Pro",
              "price_cents": 999, "billing_interval": "month"},
        headers=admin_headers,
    )
    plan_id = plan_response.json()["id"]

    payload = {
        "provider": "stripe",
        "event_id": "evt_test_001",
        "event_type": "checkout.session.completed",
        "user_id": user["id"],
        "plan_id": plan_id,
    }

    first_response = client.post(
        "/api/v1/billing/webhooks/stripe", json=payload)
    assert first_response.status_code == 200, first_response.text
    assert first_response.json()["processed"] is True

    second_response = client.post(
        "/api/v1/billing/webhooks/stripe", json=payload)
    assert second_response.status_code == 200, second_response.text
    assert second_response.json()["duplicate"] is True
