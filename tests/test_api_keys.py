from __future__ import annotations

import asyncio

from backend.domain.api_keys.model import ApiKey
from backend.database import session as db_session

from conftest import auth_headers, login_user, register_user


def test_create_list_revoke_api_key(client):
    user = register_user(
        client,
        email="api-key-owner@example.com",
        username="api-key-owner",
        role="admin",
    )
    token = login_user(client, email="api-key-owner@example.com")
    headers = auth_headers(token)

    create_response = client.post(
        "/api/v1/api-keys/",
        json={"name": "test key", "scopes": ["audit.view"]},
        headers=headers,
    )
    assert create_response.status_code == 201, create_response.text
    body = create_response.json()
    assert body["name"] == "test key"
    assert body["scopes"] == ["audit.view"]
    assert body["raw_secret"]
    api_key_id = body["id"]
    raw_secret = body["raw_secret"]

    list_response = client.get("/api/v1/api-keys/", headers=headers)
    assert list_response.status_code == 200, list_response.text
    keys = list_response.json()
    assert any(key["id"] == api_key_id for key in keys)

    auth_response = client.get(
        "/api/v1/users/me",
        headers={"X-API-Key": raw_secret},
    )
    assert auth_response.status_code == 200, auth_response.text
    assert auth_response.json()["email"] == "api-key-owner@example.com"

    revoke_response = client.delete(
        f"/api/v1/api-keys/{api_key_id}", headers=headers
    )
    assert revoke_response.status_code == 204, revoke_response.text

    list_response = client.get("/api/v1/api-keys/", headers=headers)
    assert list_response.status_code == 200, list_response.text
    keys = list_response.json()
    assert all(key["id"] != api_key_id for key in keys)


def test_api_key_last_used_is_recorded(client):
    register_user(
        client,
        email="api-key-last-used@example.com",
        username="api-key-last-used",
        role="admin",
    )
    token = login_user(client, email="api-key-last-used@example.com")
    headers = auth_headers(token)

    create_response = client.post(
        "/api/v1/api-keys/",
        json={"name": "use-test", "scopes": []},
        headers=headers,
    )
    assert create_response.status_code == 201, create_response.text
    api_key_id = create_response.json()["id"]
    raw_secret = create_response.json()["raw_secret"]

    auth_response = client.get(
        "/api/v1/users/me",
        headers={"X-API-Key": raw_secret},
    )
    assert auth_response.status_code == 200, auth_response.text

    async def verify_entry() -> None:
        async with db_session.SessionLocal() as db:
            api_key = await db.get(ApiKey, api_key_id)
            assert api_key is not None
            assert api_key.last_used_at is not None

    asyncio.run(verify_entry())
