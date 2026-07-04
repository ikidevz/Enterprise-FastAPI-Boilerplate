from fastapi.testclient import TestClient

from backend.common.rbac import AuthorizationPolicy
from backend.domain.users.model import User
from backend.main import app


def test_policy_allows_superuser_and_denies_insufficient_permissions() -> None:
    policy = AuthorizationPolicy(required_permissions=("read:admin",))
    superuser = User(id=1, username="admin", email="admin@example.com",
                     hashed_password="x", is_superuser=True, permissions=["read:admin"])
    regular = User(id=2, username="user", email="user@example.com",
                   hashed_password="x", is_superuser=False, permissions=[])

    assert policy.allows(superuser) is True
    assert policy.allows(regular) is False


def test_health_endpoint_still_works_with_environment_config() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
