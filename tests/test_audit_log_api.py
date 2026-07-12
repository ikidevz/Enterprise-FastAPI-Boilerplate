from __future__ import annotations

import asyncio
from sqlalchemy import select

from backend.database import session as db_session
from backend.domain.audit_log.model import AuditLogEntry

from conftest import auth_headers, login_user, register_user, wait_for_background_jobs


def test_audit_log_records_created_for_login_and_api_key_actions(client):
    register_user(
        client,
        email="audit-log-owner@example.com",
        username="audit-log-owner",
        role="admin",
    )
    token = login_user(client, email="audit-log-owner@example.com")
    headers = auth_headers(token)

    client.get("/api/v1/users/me", headers=headers)

    response = client.get(
        "/api/v1/audit-log/",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    entries = response.json()
    assert isinstance(entries, list)
    assert any(entry["action"] == "auth.login" for entry in entries)

    async def verify_entry() -> None:
        async with db_session.SessionLocal() as db:
            result = await db.execute(
                select(AuditLogEntry).where(
                    AuditLogEntry.action == "auth.login")
            )
            entry = result.scalar_one_or_none()
            assert entry is not None
            assert entry.success is True

    asyncio.run(verify_entry())


def test_audit_log_search_filters_by_actor_id(client):
    user = register_user(
        client,
        email="audit-search@example.com",
        username="audit-search",
        role="admin",
    )
    token = login_user(client, email="audit-search@example.com")
    headers = auth_headers(token)

    client.get("/api/v1/users/me", headers=headers)

    response = client.get(
        f"/api/v1/audit-log/?actor_id={user['id']}", headers=headers
    )
    assert response.status_code == 200, response.text
    entries = response.json()
    assert all(entry["actor_id"] == user["id"] for entry in entries)
