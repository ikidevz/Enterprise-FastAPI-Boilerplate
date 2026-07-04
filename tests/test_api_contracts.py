from fastapi.testclient import TestClient


def test_openapi_schema_exposes_expected_api_surface(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    assert "/api/v1/auth/login" in schema["paths"]
    assert "/api/v1/users/" in schema["paths"]
    assert "/api/v1/products/" in schema["paths"]
