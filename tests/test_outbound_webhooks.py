from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from conftest import auth_headers, login_user, register_user, wait_for_background_jobs


def test_create_list_revoke_webhook_endpoint(client):
    register_user(
        client,
        email="webhook-owner@example.com",
        username="webhook-owner",
        role="admin",
    )
    token = login_user(client, email="webhook-owner@example.com")
    headers = auth_headers(token)

    create_response = client.post(
        "/api/v1/webhooks/endpoints",
        json={"name": "test endpoint", "url": "https://example.com/webhook",
              "subscribed_events": ["user.registered"]},
        headers=headers,
    )
    assert create_response.status_code == 201, create_response.text
    body = create_response.json()
    endpoint_id = body["id"]
    assert body["name"] == "test endpoint"
    assert body["subscribed_events"] == ["user.registered"]

    list_response = client.get("/api/v1/webhooks/endpoints", headers=headers)
    assert list_response.status_code == 200, list_response.text
    endpoints = list_response.json()
    assert any(endpoint["id"] == endpoint_id for endpoint in endpoints)

    delete_response = client.delete(
        f"/api/v1/webhooks/endpoints/{endpoint_id}", headers=headers
    )
    assert delete_response.status_code == 204, delete_response.text

    list_response = client.get("/api/v1/webhooks/endpoints", headers=headers)
    assert list_response.status_code == 200, list_response.text
    endpoints = list_response.json()
    assert not any(endpoint["id"] == endpoint_id for endpoint in endpoints)


def test_webhook_deliveries_created_for_dispatched_event(client):
    register_user(
        client,
        email="webhook-dispatch-owner@example.com",
        username="webhook-dispatch-owner",
        role="admin",
    )
    token = login_user(client, email="webhook-dispatch-owner@example.com")
    headers = auth_headers(token)

    create_response = client.post(
        "/api/v1/webhooks/endpoints",
        json={"name": "delivery endpoint", "url": "https://example.com/webhook",
              "subscribed_events": ["user.registered"]},
        headers=headers,
    )
    assert create_response.status_code == 201, create_response.text
    endpoint_id = create_response.json()["id"]

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = SimpleNamespace(status_code=200)
        register_user(
            client,
            email="webhook-event-user@example.com",
            username="webhook-event-user",
        )
        wait_for_background_jobs()

    list_response = client.get(
        f"/api/v1/webhooks/endpoints/{endpoint_id}/deliveries",
        headers=headers,
    )
    assert list_response.status_code == 200, list_response.text
    deliveries = list_response.json()
    assert isinstance(deliveries, list)
    assert len(deliveries) == 1
    assert deliveries[0]["endpoint_id"] == endpoint_id
    assert deliveries[0]["event_type"] == "user.registered"
    assert mock_post.called
