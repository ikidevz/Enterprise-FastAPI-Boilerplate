from backend.main import app


def test_enterprise_contracts_and_routes_are_available() -> None:
    routes = {route.path for route in app.routes}
    assert "/health" in routes
    assert "/metrics" in routes
