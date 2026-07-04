from fastapi.testclient import TestClient

from backend.application.users import RegisterUserUseCase
from backend.integrations.email_adapter import EmailIntegrationAdapter


def test_enterprise_use_case_and_adapter_are_importable() -> None:
    assert RegisterUserUseCase is not None
    assert EmailIntegrationAdapter is not None


def test_health_and_metrics_endpoints_remain_available(client: TestClient) -> None:
    health = client.get("/health")
    metrics = client.get("/metrics")

    assert health.status_code == 200
    assert metrics.status_code == 200
