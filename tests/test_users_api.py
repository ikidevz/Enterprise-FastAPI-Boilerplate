"""User CRUD endpoints: create, read, list, update, delete.

Several of the xfail tests below document endpoints that currently have
*no* authentication requirement at all - see
IMPROVEMENT_SUGGESTIONS_MERGED.md section 1.3. Each xfail test asserts the
status code the endpoint *should* return to an anonymous caller (401), and
is written so it will flip to a hard failure (not silently pass) the
moment someone adds the missing `Depends(get_current_active_user)` -
forcing a deliberate removal of the marker instead of the fix going
unnoticed.
"""
import pytest
from fastapi.testclient import TestClient

from conftest import auth_headers, login_user, register_user


def test_get_own_profile_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401


def test_get_own_profile_returns_the_logged_in_users_data(client: TestClient) -> None:
    register_user(client, email="profile@example.com", username="profile")
    token = login_user(client, email="profile@example.com")

    response = client.get("/api/v1/auth/me", headers=auth_headers(token))

    assert response.status_code == 200
    assert response.json()["email"] == "profile@example.com"


def test_full_authenticated_crud_flow(client: TestClient) -> None:
    """Create -> read -> list -> update -> delete -> confirm it's gone, all as the owner."""
    created = register_user(
        client, email="crud-user@example.com", username="crud-user")
    token = login_user(client, email="crud-user@example.com")

    read_response = client.get(
        f"/api/v1/users/{created['id']}", headers=auth_headers(token))
    assert read_response.status_code == 200
    assert read_response.json()["email"] == "crud-user@example.com"

    list_response = client.get("/api/v1/users/", headers=auth_headers(token))
    assert list_response.status_code == 200
    assert any(user["id"] == created["id"] for user in list_response.json())

    update_response = client.put(
        f"/api/v1/users/{created['id']}",
        headers=auth_headers(token),
        json={"username": "crud-user-renamed"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["username"] == "crud-user-renamed"

    delete_response = client.delete(
        f"/api/v1/users/{created['id']}", headers=auth_headers(token))
    assert delete_response.status_code == 204

    read_after_delete = client.get(
        f"/api/v1/users/{created['id']}", headers=auth_headers(token)
    )
    assert read_after_delete.status_code == 404


def test_updating_another_users_profile_without_permission_is_forbidden(client: TestClient) -> None:
    owner = register_user(client, email="owner@example.com", username="owner")
    register_user(client, email="other@example.com", username="other")
    other_users_token = login_user(client, email="other@example.com")

    response = client.put(
        f"/api/v1/users/{owner['id']}",
        headers=auth_headers(other_users_token),
        json={"username": "hijacked"},
    )

    assert response.status_code == 403


def test_reading_a_nonexistent_user_returns_404(client: TestClient) -> None:
    register_user(client, email="someone@example.com", username="someone")
    token = login_user(client, email="someone@example.com")

    response = client.get("/api/v1/users/999999", headers=auth_headers(token))

    assert response.status_code == 404


def test_invalid_registration_payload_is_rejected_with_422(client: TestClient) -> None:
    response = client.post(
        "/api/v1/users/",
        json={"email": "not-an-email", "username": "", "password": "short"},
    )

    assert response.status_code == 422


def test_listing_all_users_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/users/")

    assert response.status_code == 401


def test_reading_a_specific_user_requires_authentication(client: TestClient) -> None:
    created = register_user(
        client, email="target@example.com", username="target")

    response = client.get(f"/api/v1/users/{created['id']}")

    assert response.status_code == 401


def test_deleting_a_user_requires_authentication(client: TestClient) -> None:
    created = register_user(
        client, email="deletable@example.com", username="deletable")

    response = client.delete(f"/api/v1/users/{created['id']}")

    assert response.status_code == 401


def test_registration_cannot_self_assign_a_privileged_role(client: TestClient) -> None:
    response = client.post(
        "/api/v1/users/",
        json={
            "email": "hacker@example.com",
            "username": "hacker",
            "password": "StrongPass123!",
            "role": "admin",
            "permissions": ["manage:users"],
        },
    )

    assert response.status_code in (201, 422)
    if response.status_code == 201:
        assert response.json()["role"] == "user"
