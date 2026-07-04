from fastapi.testclient import TestClient

from backend.main import app


def test_ready_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get("/health/ready")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] in {"ready", "degraded"}
        assert "checks" in body
        assert "database" in body["checks"]
        assert "redis" in body["checks"]


def test_health_endpoint_reports_environment_and_version() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["environment"]
        assert body["version"]


def test_upload_endpoint_stores_file_and_returns_metadata() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/uploads/",
            files={"file": ("demo.txt", b"hello world", "text/plain")},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["filename"] == "demo.txt"
        assert body["content_type"] == "text/plain"
        assert body["stored_path"].endswith("demo.txt")


def test_refresh_token_endpoint() -> None:
    with TestClient(app) as client:
        response = client.post("/api/v1/auth/refresh",
                               params={"refresh_token": "does-not-exist"})
        assert response.status_code == 401


def test_refresh_token_endpoint_returns_new_access_token() -> None:
    with TestClient(app) as client:
        register_response = client.post(
            "/api/v1/users/",
            json={
                "email": "refresh@example.com",
                "username": "refresh",
                "password": "StrongPass123!",
            },
        )
        assert register_response.status_code == 201

        login_response = client.post(
            "/api/v1/auth/login",
            data={"username": "refresh@example.com",
                  "password": "StrongPass123!"},
        )
        assert login_response.status_code == 200

        refresh_token = login_response.json()["refresh_token"]
        refresh_response = client.post(
            "/api/v1/auth/refresh", params={"refresh_token": refresh_token})
        assert refresh_response.status_code == 200
        assert refresh_response.json()["token_type"] == "bearer"
        assert refresh_response.json()["access_token"]
        assert refresh_response.json()["refresh_token"]

        reuse_response = client.post(
            "/api/v1/auth/refresh", params={"refresh_token": refresh_token})
        assert reuse_response.status_code == 401


def test_logout_revokes_refresh_token() -> None:
    with TestClient(app) as client:
        register_response = client.post(
            "/api/v1/users/",
            json={
                "email": "logout@example.com",
                "username": "logout",
                "password": "StrongPass123!",
            },
        )
        assert register_response.status_code == 201

        login_response = client.post(
            "/api/v1/auth/login",
            data={"username": "logout@example.com",
                  "password": "StrongPass123!"},
        )
        assert login_response.status_code == 200

        refresh_token = login_response.json()["refresh_token"]
        logout_response = client.post(
            "/api/v1/auth/logout",
            params={"refresh_token": refresh_token},
        )
        assert logout_response.status_code == 200

        reuse_response = client.post(
            "/api/v1/auth/refresh", params={"refresh_token": refresh_token})
        assert reuse_response.status_code == 401
