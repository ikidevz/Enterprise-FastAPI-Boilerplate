from __future__ import annotations

import hashlib
import hmac
import json
import time

from backend.core.config import settings
from conftest import login_user, register_user, wait_for_background_jobs


def test_plan_feature_mapping_and_entitlement_check(client):
    register_user(client, email="billing-admin@example.com",
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


def test_invoice_history_and_plan_change_proration(client):
    register_user(client, email="billing-history-admin@example.com",
                  username="billing-history-admin", role="admin")
    user = register_user(client, email="member-history@example.com",
                         username="member-history")

    admin_headers = {
        "Authorization": f"Bearer {login_user(client, email='billing-history-admin@example.com')}"}
    member_headers = {
        "Authorization": f"Bearer {login_user(client, email='member-history@example.com')}"}

    basic_plan = client.post(
        "/api/v1/billing/admin/plans",
        json={"key": "basic", "name": "Basic",
              "price_cents": 1000, "billing_interval": "month"},
        headers=admin_headers,
    )
    premium_plan = client.post(
        "/api/v1/billing/admin/plans",
        json={"key": "premium", "name": "Premium",
              "price_cents": 2000, "billing_interval": "month"},
        headers=admin_headers,
    )
    assert basic_plan.status_code == 201
    assert premium_plan.status_code == 201

    assign_response = client.post(
        "/api/v1/billing/subscriptions/assign",
        json={"user_id": user["id"], "plan_id": basic_plan.json()[
            "id"], "provider": "manual"},
        headers=admin_headers,
    )
    assert assign_response.status_code == 201

    invoices_response = client.get(
        "/api/v1/billing/invoices/me",
        headers=member_headers,
    )
    assert invoices_response.status_code == 200
    assert len(invoices_response.json()) >= 1

    change_response = client.post(
        "/api/v1/billing/subscriptions/change-plan",
        json={"plan_id": premium_plan.json()["id"], "proration_days": 15},
        headers=member_headers,
    )
    assert change_response.status_code == 200, change_response.text
    assert change_response.json()["prorated_amount_cents"] == 500

    admin_invoices_response = client.get(
        "/api/v1/billing/admin/invoices",
        headers=admin_headers,
    )
    assert admin_invoices_response.status_code == 200
    assert len(admin_invoices_response.json()) >= 2


def test_billing_metrics_report_price_weighted_mrr(client):
    register_user(client, email="mrr-admin@example.com",
                  username="mrr-admin", role="admin")
    user = register_user(client, email="mrr-user@example.com",
                         username="mrr-user")

    admin_headers = {
        "Authorization": f"Bearer {login_user(client, email='mrr-admin@example.com')}"}

    basic_plan = client.post(
        "/api/v1/billing/admin/plans",
        json={"key": "basic", "name": "Basic",
              "price_cents": 1000, "billing_interval": "month"},
        headers=admin_headers,
    )
    premium_plan = client.post(
        "/api/v1/billing/admin/plans",
        json={"key": "premium", "name": "Premium",
              "price_cents": 2500, "billing_interval": "month"},
        headers=admin_headers,
    )
    assert basic_plan.status_code == 201
    assert premium_plan.status_code == 201

    active_response = client.post(
        "/api/v1/billing/subscriptions/assign",
        json={"user_id": user["id"], "plan_id": basic_plan.json()[
            "id"], "provider": "manual"},
        headers=admin_headers,
    )
    assert active_response.status_code == 201

    trial_response = client.post(
        "/api/v1/billing/subscriptions/assign",
        json={"user_id": user["id"], "plan_id": premium_plan.json(
        )["id"], "provider": "manual", "status": "trialing"},
        headers=admin_headers,
    )
    assert trial_response.status_code == 201

    metrics_response = client.get(
        "/api/v1/billing/admin/billing/metrics",
        headers=admin_headers,
    )
    assert metrics_response.status_code == 200
    assert metrics_response.json()["mrr_cents"] == 3500


def test_failed_payment_webhook_marks_subscription_past_due_and_notifies_user(client):
    register_user(client, email="failed-payment-admin@example.com",
                  username="failed-payment-admin", role="admin")
    user = register_user(client, email="failed-payment-user@example.com",
                         username="failed-payment-user")

    admin_headers = {
        "Authorization": f"Bearer {login_user(client, email='failed-payment-admin@example.com')}"}
    member_headers = {
        "Authorization": f"Bearer {login_user(client, email='failed-payment-user@example.com')}"}

    plan_response = client.post(
        "/api/v1/billing/admin/plans",
        json={"key": "pro", "name": "Pro",
              "price_cents": 999, "billing_interval": "month"},
        headers=admin_headers,
    )
    assert plan_response.status_code == 201

    assign_response = client.post(
        "/api/v1/billing/subscriptions/assign",
        json={"user_id": user["id"], "plan_id": plan_response.json()[
            "id"], "provider": "manual"},
        headers=admin_headers,
    )
    assert assign_response.status_code == 201
    subscription_id = assign_response.json()["id"]

    payload = {
        "provider": "stripe",
        "event_id": "evt_failed_payment_001",
        "event_type": "invoice.payment_failed",
        "user_id": user["id"],
        "plan_id": plan_response.json()["id"],
        "subscription_id": subscription_id,
    }
    payload_bytes = json.dumps(payload, separators=(
        ",", ":"), sort_keys=True).encode("utf-8")
    timestamp = str(int(time.time()))
    signing_secret = settings.stripe_webhook_secret or "dev-stripe-webhook-secret"
    signature = hmac.new(
        signing_secret.encode("utf-8"),
        f"{timestamp}.{payload_bytes.decode('utf-8')}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    headers = {"x-signature": f"t={timestamp},v1={signature}"}

    webhook_response = client.post(
        "/api/v1/billing/webhooks/stripe", json=payload, headers=headers)
    assert webhook_response.status_code == 200, webhook_response.text

    wait_for_background_jobs(timeout=2)

    subscription_response = client.get(
        "/api/v1/billing/subscriptions/me",
        headers=member_headers,
    )
    assert subscription_response.status_code == 200
    assert subscription_response.json()["status"] == "past_due"

    notifications_response = client.get(
        "/api/v1/billing/notifications/me",
        headers=member_headers,
    )
    assert notifications_response.status_code == 200
    assert any(item["kind"] ==
               "payment_failed" for item in notifications_response.json())


def test_notification_feed_and_mark_as_read(client):
    register_user(client, email="notifications-admin@example.com",
                  username="notifications-admin", role="admin")
    user = register_user(client, email="notifications-user@example.com",
                         username="notifications-user")

    admin_headers = {
        "Authorization": f"Bearer {login_user(client, email='notifications-admin@example.com')}"}
    member_headers = {
        "Authorization": f"Bearer {login_user(client, email='notifications-user@example.com')}"}

    plan_response = client.post(
        "/api/v1/billing/admin/plans",
        json={"key": "starter", "name": "Starter",
              "price_cents": 500, "billing_interval": "month"},
        headers=admin_headers,
    )
    assert plan_response.status_code == 201

    assign_response = client.post(
        "/api/v1/billing/subscriptions/assign",
        json={"user_id": user["id"], "plan_id": plan_response.json()[
            "id"], "provider": "manual"},
        headers=admin_headers,
    )
    assert assign_response.status_code == 201

    wait_for_background_jobs(timeout=2)

    list_response = client.get(
        "/api/v1/billing/notifications/me",
        headers=member_headers,
    )
    assert list_response.status_code == 200
    assert len(list_response.json()) >= 1

    notification_id = list_response.json()[0]["id"]
    read_response = client.post(
        f"/api/v1/billing/notifications/me/{notification_id}/read",
        headers=member_headers,
    )
    assert read_response.status_code == 200
    assert read_response.json()["is_read"] is True


def test_webhook_requires_a_signature_header(client):
    register_user(client, email="webhook-admin@example.com",
                  username="webhook-admin", role="admin")
    user = register_user(
        client, email="webhook-user@example.com", username="webhook-user")

    payload = {
        "provider": "stripe",
        "event_id": "evt_test_002",
        "event_type": "checkout.session.completed",
        "user_id": user["id"],
        "plan_id": 1,
    }

    response = client.post("/api/v1/billing/webhooks/stripe", json=payload)
    assert response.status_code == 400, response.text
    assert response.json()["error"] == "invalid_webhook_signature"


def test_webhook_is_idempotent_and_persists_event(client):
    register_user(client, email="webhook-admin@example.com",
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
    payload_bytes = json.dumps(payload, separators=(
        ",", ":"), sort_keys=True).encode("utf-8")
    timestamp = str(int(time.time()))
    signing_secret = settings.stripe_webhook_secret or "dev-stripe-webhook-secret"
    signature = hmac.new(
        signing_secret.encode("utf-8"),
        f"{timestamp}.{payload_bytes.decode('utf-8')}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    headers = {"x-signature": f"t={timestamp},v1={signature}"}

    first_response = client.post(
        "/api/v1/billing/webhooks/stripe", json=payload, headers=headers)
    assert first_response.status_code == 200, first_response.text
    assert first_response.json()["processed"] is True

    second_response = client.post(
        "/api/v1/billing/webhooks/stripe", json=payload, headers=headers)
    assert second_response.status_code == 200, second_response.text
    assert second_response.json()["duplicate"] is True
