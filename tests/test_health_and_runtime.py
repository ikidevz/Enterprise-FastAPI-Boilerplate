"""Health, readiness, metrics, runtime, and "is every response well-formed" checks.

These are the endpoints an ops team or a load balancer would actually poll,
plus the small pieces of middleware that attach to *every* response
(security headers, request/trace IDs). Nothing here needs a logged-in user.
"""
from fastapi.testclient import TestClient

from backend.infrastructure.runtime import PlatformRuntime


def test_health_endpoint_reports_ok_status(client: TestClient) -> None:
    """/health is the liveness probe: it should always say 'ok' if the process is up."""
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["environment"]
    assert body["version"]


def test_readiness_endpoint_reports_dependency_checks(client: TestClient) -> None:
    """/health/ready additionally pings the DB and Redis and reports on both.

    In this test environment there's no real Redis, so the Redis check is
    expected to report as unhealthy/degraded rather than fully "ready" -
    what matters here is that both dependencies are actually checked and
    reported, not that they're both green.
    """
    response = client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ready", "degraded"}
    assert "database" in body["checks"]
    assert "redis" in body["checks"]


def test_metrics_endpoint_counts_requests(client: TestClient) -> None:
    """/metrics is an in-process counter, not a real Prometheus endpoint.

    See IMPROVEMENT_SUGGESTIONS_MERGED.md section 11 ("Runtime, observability")
    for why this doesn't aggregate across multiple workers/replicas - here we
    just check it counts requests within a single process correctly.
    """
    client.get("/health")
    response = client.get("/metrics")

    assert response.status_code == 200
    body = response.json()
    assert body["request_count"] >= 1
    assert body["status_codes"]["200"] >= 1


def test_runtime_endpoint_reports_environment_and_uptime(client: TestClient) -> None:
    """/runtime is the operational snapshot behind PlatformRuntime - env, uptime, metrics."""
    response = client.get("/runtime")

    assert response.status_code == 200
    body = response.json()
    assert body["environment"]
    assert body["service"] == "tier4"
    assert "uptime_seconds" in body


def test_security_headers_are_present_on_every_response(client: TestClient) -> None:
    """The middleware in backend/main.py should attach these to every response, not just /health."""
    response = client.get("/health")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"


def test_request_id_header_is_generated_and_returned(client: TestClient) -> None:
    """Every response should carry an x-request-id, generated if the caller didn't send one."""
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers.get("x-request-id")


def test_http_middleware_wraps_requests_cleanly_without_errors(client: TestClient) -> None:
    """The middleware in backend/main.py should complete a normal request path without throwing and should propagate correlation headers."""
    response = client.get(
        "/health",
        headers={"x-request-id": "req-123", "x-trace-id": "trace-123"},
    )

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req-123"
    assert response.headers["x-trace-id"] == "trace-123"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"


def test_trace_id_header_is_generated_and_returned(client: TestClient) -> None:
    """Every response should carry an x-trace-id too, for correlating logs across a request."""
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers.get("x-trace-id")


def test_request_id_supplied_by_caller_is_echoed_back(client: TestClient) -> None:
    """If a caller already has a request id (e.g. from an upstream proxy), it should be kept, not replaced."""
    response = client.get(
        "/health", headers={"x-request-id": "caller-supplied-id-123"})

    assert response.headers.get("x-request-id") == "caller-supplied-id-123"


def test_websocket_health_endpoint_accepts_and_replies(client: TestClient) -> None:
    """/ws/health is a bare connectivity check: connect, get one message, done."""
    with client.websocket_connect("/ws/health") as websocket:
        message = websocket.receive_json()
        assert message == {"status": "connected"}


def test_openapi_schema_lists_the_main_api_routes(client: TestClient) -> None:
    """A basic sanity check that the OpenAPI schema is being generated and includes our routes.

    This is also the version-tolerant way to check "does this route exist" -
    the older test suite used `{route.path for route in app.routes}`, which
    broke when a newer FastAPI/Starlette wrapped included routers in an
    internal object with no `.path` attribute. Reading the generated OpenAPI
    schema instead of FastAPI's internal route objects survives that kind of
    internal change.
    """
    schema = client.get("/openapi.json").json()

    assert "/api/v1/auth/login" in schema["paths"]
    assert "/api/v1/users/" in schema["paths"]
    assert "/api/v1/products/" in schema["paths"]
    assert "/health/ready" in schema["paths"]


def test_openapi_schema_includes_worked_examples_for_products(client: TestClient) -> None:
    """The product schemas ship with OpenAPI examples - check they're actually wired up."""
    schema = client.get("/openapi.json").json()
    product_create_schema = schema["components"]["schemas"]["ProductCreate"]

    assert product_create_schema["example"]["name"] == "Sample product"


def test_platform_runtime_builds_a_health_snapshot_directly() -> None:
    """Unit test of PlatformRuntime itself, independent of the HTTP layer."""
    runtime = PlatformRuntime()

    snapshot = runtime.build_runtime_snapshot(environment="dev")

    assert snapshot["environment"] == "dev"
    assert snapshot["service"] == "tier4"
    assert "uptime_seconds" in snapshot
    assert "checks" in snapshot


def test_rate_limiting_blocks_requests_past_the_configured_threshold(
    client: TestClient, monkeypatch
) -> None:
    """Uses monkeypatch (not a direct assignment) specifically so the setting is
    automatically restored after this test, regardless of pass/fail - the older
    version of this test mutated `settings.rate_limit_requests_per_minute`
    directly and never put it back, which is exactly the kind of shared global
    state that made other parts of this suite order-dependent (see
    tests/README.md and conftest.py's reset_shared_singletons fixture).
    """
    from backend.core.config import settings

    monkeypatch.setattr(settings, "rate_limit_requests_per_minute", 2)
    monkeypatch.setattr(settings, "enable_rate_limiting", True)

    assert client.get("/health").status_code == 200
    assert client.get("/health").status_code == 200
    blocked_response = client.get("/health")

    assert blocked_response.status_code == 429


def test_request_size_middleware_rejects_too_large_requests(
    client: TestClient, monkeypatch
) -> None:
    """The middleware should stop requests that declare a body larger than the configured maximum."""
    from backend.core.config import settings

    monkeypatch.setattr(settings, "max_request_size_bytes", 10)

    response = client.get(
        "/health",
        headers={"content-length": "11"},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "Request body too large"
