from fastapi.testclient import TestClient

from backend.main import app


def test_metrics_endpoint_exposes_request_metrics() -> None:
    with TestClient(app) as client:
        client.get("/health")
        response = client.get("/metrics")

    assert response.status_code == 200
    body = response.json()
    assert body["request_count"] >= 1
    assert body["status_codes"]["200"] >= 1
