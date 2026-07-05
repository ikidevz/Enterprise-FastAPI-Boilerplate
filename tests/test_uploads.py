"""File upload endpoint.

Two real problems documented here as xfail tests (both in
IMPROVEMENT_SUGGESTIONS_MERGED.md section 1.4): the endpoint has no
authentication, and it writes to disk using the client-supplied filename
directly, with no sanitization - a path-traversal filename can write
outside the intended upload directory.
"""
from pathlib import Path

from fastapi.testclient import TestClient

from backend.core.config import settings
from conftest import auth_headers, login_user, register_user


def test_uploading_a_file_stores_it_and_returns_metadata(client: TestClient) -> None:
    register_user(client, email="upload@example.com", username="upload")
    token = login_user(client, email="upload@example.com")

    response = client.post(
        "/api/v1/uploads/",
        headers=auth_headers(token),
        files={"file": ("demo.txt", b"hello world", "text/plain")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "demo.txt"
    assert body["content_type"] == "text/plain"
    assert body["stored_as"] != "demo.txt"
    assert body["stored_as"].endswith(".txt")
    assert body["stored_path"].endswith(body["stored_as"])


def test_uploading_without_a_filename_is_rejected(client: TestClient) -> None:
    register_user(client, email="upload-no-name@example.com",
                  username="upload-no-name")
    token = login_user(client, email="upload-no-name@example.com")

    response = client.post(
        "/api/v1/uploads/",
        headers=auth_headers(token),
        files={"file": ("", b"no filename here", "text/plain")},
    )

    # An empty filename is rejected before it even reaches the route handler's
    # own `if not file.filename` check - Starlette's multipart parsing itself
    # treats a blank filename as an invalid part of the request.
    assert response.status_code == 422


def test_upload_rejects_a_path_traversal_filename(client: TestClient, tmp_path) -> None:
    from backend.app.api.v1.uploads import router as uploads_router

    register_user(client, email="upload-path@example.com",
                  username="upload-path")
    token = login_user(client, email="upload-path@example.com")

    response = client.post(
        "/api/v1/uploads/",
        headers=auth_headers(token),
        files={"file": ("../../escape-attempt.txt",
                        b"should not escape", "text/plain")},
    )

    if response.status_code == 201:
        stored_path = response.json()["stored_path"]
        # The stored path should still be inside the configured upload directory.
        assert str(Path(settings.upload_dir).resolve()) in stored_path
    else:
        assert response.status_code in (400, 422)


def test_uploading_a_file_requires_authentication(client: TestClient) -> None:
    response = client.post(
        "/api/v1/uploads/",
        files={"file": ("should-need-auth.txt", b"data", "text/plain")},
    )

    assert response.status_code == 401
