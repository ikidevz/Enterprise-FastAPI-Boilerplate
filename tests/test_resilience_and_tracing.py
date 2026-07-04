import asyncio
import importlib

import pytest

from backend.common.exporters import export_metrics
from backend.common.opentelemetry import trace_span
from backend.common.resilience import CircuitBreaker, CircuitBreakerOpenError, retry_async


@pytest.mark.asyncio
async def test_retry_async_retries_and_succeeds() -> None:
    attempts = {"count": 0}

    async def flaky() -> str:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("temporary")
        return "ok"

    result = await retry_async(flaky, retries=3, delay=0.01)
    assert result == "ok"
    assert attempts["count"] == 3


def test_circuit_breaker_opens_and_blocks_calls() -> None:
    breaker = CircuitBreaker(failure_threshold=2, reset_timeout=1.0)
    breaker.record_failure()
    breaker.record_failure()

    with pytest.raises(CircuitBreakerOpenError):
        breaker.before_call()


def test_trace_span_and_export_metrics() -> None:
    with trace_span("test-span", component="tests"):
        pass
    export_metrics()


def test_tracing_configuration_honors_production_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_TRACING", "true")
    monkeypatch.setenv("OTEL_MODE", "production")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4318")

    from backend.common import opentelemetry as opentelemetry_module

    importlib.reload(opentelemetry_module)
    config = opentelemetry_module.get_tracing_configuration()

    assert config["enabled"] is True
    assert config["mode"] == "production"
    assert config["endpoint"] == "http://collector:4318"
