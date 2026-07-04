from fastapi.testclient import TestClient

from backend.contracts.auth import LoginResponseContract, RefreshTokenResponseContract
from backend.contracts.products import ProductContract
from backend.contracts.users import UserContract
from backend.platform.runtime import PlatformRuntime


def test_platform_runtime_builds_health_snapshot() -> None:
    runtime = PlatformRuntime()
    snapshot = runtime.build_runtime_snapshot(environment="dev")

    assert snapshot["environment"] == "dev"
    assert snapshot["service"] == "tier4"
    assert "uptime_seconds" in snapshot
    assert "checks" in snapshot


def test_feature_contracts_are_available() -> None:
    assert LoginResponseContract is not None
    assert RefreshTokenResponseContract is not None
    assert UserContract is not None
    assert ProductContract is not None


def test_readiness_endpoint_reports_component_checks(client: TestClient) -> None:
    response = client.get("/health/ready")

    assert response.status_code == 200
    payload = response.json()
    assert "status" in payload
    assert "checks" in payload
    assert "database" in payload["checks"]
    assert "redis" in payload["checks"]
