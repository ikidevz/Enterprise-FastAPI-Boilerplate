from fastapi.testclient import TestClient


def test_security_headers_are_present(client: TestClient) -> None:
    response = client.get("/health")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"


def test_rate_limit_blocks_excessive_requests(client: TestClient) -> None:
    from backend.core.config import settings

    settings.rate_limit_requests_per_minute = 1
    assert client.get("/health").status_code == 200
    assert client.get("/health").status_code == 429
