import asyncio

import pytest

from backend.common.background_jobs import BackgroundJobManager
from backend.common.exporters import export_metrics
from backend.observability.tracing import trace_span
from backend.resilience.retry import CircuitBreaker, CircuitBreakerOpenError, retry_async


def test_background_job_manager_runs_an_enqueued_job() -> None:
    async def run_test() -> None:
        manager = BackgroundJobManager()
        await manager.start()
        try:
            completed = {"value": False}

            def job() -> None:
                completed["value"] = True

            manager.enqueue(job)
            await asyncio.sleep(0.1)
            assert completed["value"] is True
        finally:
            await manager.stop()

    asyncio.run(run_test())


def test_background_job_manager_runs_an_async_job_too() -> None:
    async def run_test() -> None:
        manager = BackgroundJobManager()
        await manager.start()
        try:
            completed = {"value": False}

            async def async_job() -> None:
                completed["value"] = True

            manager.enqueue(async_job)
            await asyncio.sleep(0.1)
            assert completed["value"] is True
        finally:
            await manager.stop()

    asyncio.run(run_test())


def test_retry_async_retries_on_failure_and_eventually_succeeds() -> None:
    async def run_test() -> None:
        attempts = {"count": 0}

        async def flaky() -> str:
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise RuntimeError("temporary failure")
            return "ok"

        result = await retry_async(flaky, retries=3, delay=0.01)
        assert result == "ok"
        assert attempts["count"] == 3

    asyncio.run(run_test())


def test_retry_async_gives_up_after_exhausting_retries() -> None:
    async def run_test() -> None:
        async def always_fails() -> str:
            raise RuntimeError("permanent failure")

        with pytest.raises(RuntimeError):
            await retry_async(always_fails, retries=2, delay=0.01)

    asyncio.run(run_test())


def test_circuit_breaker_opens_after_the_failure_threshold_and_blocks_further_calls() -> None:
    breaker = CircuitBreaker(failure_threshold=2, reset_timeout=1.0)

    breaker.record_failure()
    breaker.record_failure()

    with pytest.raises(CircuitBreakerOpenError):
        breaker.before_call()


def test_circuit_breaker_stays_closed_below_the_failure_threshold() -> None:
    breaker = CircuitBreaker(failure_threshold=3, reset_timeout=1.0)

    breaker.record_failure()
    breaker.record_failure()

    breaker.before_call()


def test_trace_span_context_manager_does_not_raise() -> None:
    """trace_span should be safe to use even when tracing is a no-op (see section 2.3)."""
    with trace_span("test-span", component="tests"):
        pass


def test_export_metrics_does_not_raise_with_no_endpoint_configured() -> None:
    """With no EXPORTER_ENDPOINT set, export_metrics() should be a harmless no-op."""
    export_metrics()


def test_tracing_configuration_reads_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_TRACING", "true")
    monkeypatch.setenv("OTEL_MODE", "production")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4318")

    from backend.observability.tracing import get_tracing_configuration

    try:
        config = get_tracing_configuration()

        assert config["enabled"] is True
        assert config["mode"] == "production"
        assert config["endpoint"] == "http://collector:4318"
    finally:
        monkeypatch.undo()
