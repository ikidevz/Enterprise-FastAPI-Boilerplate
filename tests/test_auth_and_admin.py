import re

from fastapi.testclient import TestClient

from backend.common import email as email_module
from backend.common.audit import audit_logger

from conftest import login_user, register_user


class CaptureTransport:
    def __init__(self) -> None:
        self.calls = []

    def send(self, *, to: str, subject: str, body: str) -> None:
        self.calls.append({"to": to, "subject": subject, "body": body})


def test_audit_logging_records_auth_and_user_events(client: TestClient) -> None:
    audit_logger.clear()

    register_user(client, email="audit@example.com", username="audit")
    client.post(
        "/api/v1/auth/login",
        data={"username": "audit@example.com", "password": "StrongPass123!"},
    )

    actions = {entry["action"] for entry in audit_logger.entries}
    assert "user.created" in actions
    assert "auth.login" in actions


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_weak_passwords_are_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/users/",
        json={
            "email": "weak@example.com",
            "username": "weak",
            "password": "weakpass",
        },
    )
    assert response.status_code == 422


def test_duplicate_registration_returns_standardized_error_payload(client: TestClient) -> None:
    payload = {
        "email": "duplicate-standard@example.com",
        "username": "duplicate-standard",
        "password": "StrongPass123!",
    }

    first_response = client.post("/api/v1/users/", json=payload)
    assert first_response.status_code == 201

    duplicate_response = client.post("/api/v1/users/", json=payload)
    assert duplicate_response.status_code == 400
    assert duplicate_response.json()["error_code"] == "duplicate_user"


def test_duplicate_product_registration_returns_standardized_error_payload(client: TestClient) -> None:
    payload = {"name": "Duplicate Product",
               "price": 10.0, "description": "dup"}

    first_response = client.post("/api/v1/products/", json=payload)
    assert first_response.status_code == 201

    duplicate_response = client.post("/api/v1/products/", json=payload)
    assert duplicate_response.status_code == 400
    assert duplicate_response.json()["error_code"] == "duplicate_product"


def test_failed_login_attempts_lock_account(client: TestClient) -> None:
    register_user(client, email="lock@example.com", username="lock")

    for _ in range(5):
        response = client.post(
            "/api/v1/auth/login",
            data={"username": "lock@example.com",
                  "password": "wrong-password"},
        )
        assert response.status_code == 401

    locked_response = client.post(
        "/api/v1/auth/login",
        data={"username": "lock@example.com", "password": "StrongPass123!"},
    )
    assert locked_response.status_code == 403
    assert "locked" in locked_response.json()["detail"].lower()


def test_password_reset_email_contains_real_reset_token(client: TestClient) -> None:
    transport = CaptureTransport()
    original_transport = email_module.email_delivery_service.transport
    email_module.email_delivery_service.transport = transport

    try:
        register_user(client, email="reset@example.com", username="reset")

        response = client.post(
            "/api/v1/auth/password-reset/request",
            json={"email": "reset@example.com"},
        )
        assert response.status_code == 200
        assert transport.calls

        body = transport.calls[-1]["body"]
        token_match = re.search(
            r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})",
            body,
        )
        assert token_match is not None

        confirm_response = client.post(
            "/api/v1/auth/password-reset/confirm",
            json={"token": token_match.group(
                1), "new_password": "ResetPass123!"},
        )
        assert confirm_response.status_code == 200
    finally:
        email_module.email_delivery_service.transport = original_transport


def test_email_verification_flow(client: TestClient) -> None:
    register_response = client.post(
        "/api/v1/users/",
        json={
            "email": "verify@example.com",
            "username": "verify",
            "password": "StrongPass123!",
        },
    )
    assert register_response.status_code == 201

    request_response = client.post(
        "/api/v1/auth/email-verification/request",
        json={"email": "verify@example.com"},
    )
    assert request_response.status_code == 200
    token = request_response.json()["token"]

    confirm_response = client.post(
        "/api/v1/auth/email-verification/confirm",
        json={"token": token},
    )
    assert confirm_response.status_code == 200

    login_response = client.post(
        "/api/v1/auth/login",
        data={"username": "verify@example.com", "password": "StrongPass123!"},
    )
    assert login_response.status_code == 200


def test_user_registration_and_login(client: TestClient) -> None:
    register_user(client, email="demo@example.com", username="demo")
    token = login_user(client, email="demo@example.com")

    me_response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "demo@example.com"


def test_admin_users_endpoint_for_superuser(client: TestClient) -> None:
    register_user(client, email="admin@example.com", username="admin")
    client.put(
        "/api/v1/users/1",
        json={"is_superuser": True},
    )

    login_response = client.post(
        "/api/v1/auth/login",
        data={"username": "admin@example.com", "password": "StrongPass123!"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    response = client.get(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200


def test_regular_user_cannot_change_privileged_fields(client: TestClient) -> None:
    register_user(client, email="normal@example.com", username="normal")
    token = login_user(client, email="normal@example.com")

    response = client.put(
        "/api/v1/users/1",
        headers={"Authorization": f"Bearer {token}"},
        json={"is_superuser": True, "is_active": False},
    )
    assert response.status_code == 200
    assert response.json()["is_superuser"] is False
    assert response.json()["is_active"] is True


def test_user_crud_flow(client: TestClient) -> None:
    create_response = client.post(
        "/api/v1/users/",
        json={
            "email": "crud@example.com",
            "username": "crud",
            "password": "StrongPass123!",
        },
    )
    assert create_response.status_code == 201
    user_id = create_response.json()["id"]

    read_response = client.get(f"/api/v1/users/{user_id}")
    assert read_response.status_code == 200
    assert read_response.json()["email"] == "crud@example.com"

    update_response = client.put(
        f"/api/v1/users/{user_id}",
        json={"username": "crud-updated"},
    )
    assert update_response.status_code == 403

    delete_response = client.delete(f"/api/v1/users/{user_id}")
    assert delete_response.status_code == 204


def test_example_products_module_crud(client: TestClient) -> None:
    create_response = client.post(
        "/api/v1/products/",
        json={"name": "Example Product", "price": 19.99,
              "description": "Demo product"},
    )
    assert create_response.status_code == 201
    product_id = create_response.json()["id"]

    list_response = client.get("/api/v1/products/")
    assert list_response.status_code == 200
    assert len(list_response.json()) >= 1

    read_response = client.get(f"/api/v1/products/{product_id}")
    assert read_response.status_code == 200
    assert read_response.json()["name"] == "Example Product"

    update_response = client.put(
        f"/api/v1/products/{product_id}",
        json={"price": 24.99},
    )
    assert update_response.status_code == 200
    assert update_response.json()["price"] == 24.99

    delete_response = client.delete(f"/api/v1/products/{product_id}")
    assert delete_response.status_code == 204


def test_permissions_permission_check(client: TestClient) -> None:
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

    login_response = client.post(
        "/api/v1/auth/login",
        data={"username": "governance@example.com",
              "password": "StrongPass123!"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    response = client.get(
        "/api/v1/admin/permissions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["role"] == "manager"
