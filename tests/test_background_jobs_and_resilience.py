import asyncio
import sys
import types
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from backend.common.background_jobs import BackgroundJobManager
from backend.core.config import settings
from backend.common.exporters import export_metrics
from backend.observability.tracing import trace_span
from backend.resilience.retry import CircuitBreaker, CircuitBreakerOpenError, retry_async


def test_background_job_manager_runs_an_enqueued_job() -> None:
    """Ensures background job manager runs an enqueued job."""
    async def run_test() -> None:
        """Supports the test suite by run test."""
        manager = BackgroundJobManager()
        await manager.start()
        try:
            completed = {"value": False}

            def job() -> None:
                """Supports the test suite by job."""
                completed["value"] = True

            manager.enqueue(job)
            await asyncio.sleep(0.1)
            assert completed["value"] is True
        finally:
            await manager.stop()

    asyncio.run(run_test())


def test_cleanup_stale_uploads_removes_old_local_files_and_records(client: pytest.FixtureRequest, tmp_path: pytest.TempPathFactory) -> None:
    """The cleanup job should remove stale local uploads and their DB records."""
    async def run_test() -> None:
        from backend.common.background_jobs import cleanup_stale_uploads
        from backend.database import session as db_session
        from backend.domain.uploads.model import UploadRecord

        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        stale_file = upload_dir / "stale.txt"
        stale_file.write_text("stale", encoding="utf-8")

        register_result = client.post(
            "/api/v1/users/",
            json={"email": "cleanup@example.com",
                  "username": "cleanup", "password": "StrongPass123!"},
        )
        assert register_result.status_code == 201
        owner_id = register_result.json()["id"]

        original_upload_dir = settings.upload_dir
        settings.upload_dir = str(upload_dir)
        try:
            async with db_session.SessionLocal() as db:
                db.add(UploadRecord(stored_name="stale.txt",
                       original_filename="stale.txt", owner_id=owner_id))
                await db.commit()

            await cleanup_stale_uploads(older_than_days=0)

            async with db_session.SessionLocal() as db:
                record = await db.scalar(select(UploadRecord).where(UploadRecord.stored_name == "stale.txt"))
                assert record is None

            assert not stale_file.exists()
        finally:
            settings.upload_dir = original_upload_dir

    asyncio.run(run_test())


def test_trial_expiry_job_marks_expired_subscriptions(client: pytest.FixtureRequest) -> None:
    """Trial-expiry processing should transition subscriptions past their trial end to expired."""
    async def run_test() -> None:
        from backend.common.background_jobs import expire_trial_subscriptions
        from backend.database import session as db_session
        from backend.domain.billing.models import Plan, Subscription

        register_result = client.post(
            "/api/v1/users/",
            json={"email": "trial@example.com",
                  "username": "trial", "password": "StrongPass123!"},
        )
        assert register_result.status_code == 201
        user_id = register_result.json()["id"]

        async with db_session.SessionLocal() as db:
            plan = Plan(key="trial-plan", name="Trial Plan",
                        price_cents=0, billing_interval="month")
            db.add(plan)
            await db.flush()
            trial_sub = Subscription(user_id=user_id, plan_id=plan.id, status="trialing",
                                     provider="manual", trial_ends_at=datetime.now(timezone.utc) - timedelta(days=1))
            db.add(trial_sub)
            await db.commit()
            trial_sub_id = trial_sub.id

        updated_count = await expire_trial_subscriptions()

        async with db_session.SessionLocal() as db:
            refreshed = await db.get(Subscription, trial_sub_id)
            assert refreshed is not None
            assert refreshed.status == "expired"

        assert updated_count == 1

    asyncio.run(run_test())


def test_periodic_lifecycle_job_runs_cleanup_and_trial_expiry(client: pytest.FixtureRequest, tmp_path: pytest.TempPathFactory) -> None:
    """The periodic lifecycle job should clean up stale uploads and expire old trials in one pass."""
    async def run_test() -> None:
        from backend.common.background_jobs import run_periodic_lifecycle_jobs
        from backend.core.config import settings
        from backend.database import session as db_session
        from backend.domain.billing.models import Plan, Subscription
        from backend.domain.uploads.model import UploadRecord

        register_result = client.post(
            "/api/v1/users/",
            json={"email": "lifecycle@example.com",
                  "username": "lifecycle", "password": "StrongPass123!"},
        )
        assert register_result.status_code == 201
        user_id = register_result.json()["id"]

        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        stale_file = upload_dir / "stale-lifecycle.txt"
        stale_file.write_text("stale", encoding="utf-8")

        original_upload_dir = settings.upload_dir
        settings.upload_dir = str(upload_dir)
        try:
            async with db_session.SessionLocal() as db:
                db.add(UploadRecord(stored_name="stale-lifecycle.txt",
                       original_filename="stale-lifecycle.txt", owner_id=user_id))
                plan = Plan(key="trial-plan-2", name="Trial Plan 2",
                            price_cents=0, billing_interval="month")
                db.add(plan)
                await db.flush()
                db.add(Subscription(user_id=user_id, plan_id=plan.id, status="trialing", provider="manual",
                                    trial_ends_at=datetime.now(timezone.utc) - timedelta(days=1)))
                await db.commit()

            result = await run_periodic_lifecycle_jobs(older_than_days=0)
            assert result["cleaned_uploads"] == 1
            assert result["expired_subscriptions"] == 1
        finally:
            settings.upload_dir = original_upload_dir

    asyncio.run(run_test())


def test_background_job_manager_runs_an_async_job_too() -> None:
    """Ensures background job manager runs an async job too."""
    async def run_test() -> None:
        """Supports the test suite by run test."""
        manager = BackgroundJobManager()
        await manager.start()
        try:
            completed = {"value": False}

            async def async_job() -> None:
                """Supports the test suite by async job."""
                completed["value"] = True

            manager.enqueue(async_job)
            await asyncio.sleep(0.1)
            assert completed["value"] is True
        finally:
            await manager.stop()

    asyncio.run(run_test())


def test_background_job_manager_accepts_jobs_before_start() -> None:
    """Ensures jobs queued before startup are executed once the manager starts."""
    async def run_test() -> None:
        manager = BackgroundJobManager()
        completed = {"value": False}

        def sync_job() -> None:
            completed["value"] = True

        manager.enqueue(sync_job)
        await manager.start()
        try:
            await asyncio.sleep(0.1)
            assert completed["value"] is True
        finally:
            await manager.stop()

    asyncio.run(run_test())


def test_retry_async_retries_on_failure_and_eventually_succeeds() -> None:
    """Ensures retry async retries on failure and eventually succeeds."""
    async def run_test() -> None:
        """Supports the test suite by run test."""
        attempts = {"count": 0}

        async def flaky() -> str:
            """Supports the test suite by flaky."""
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise RuntimeError("temporary failure")
            return "ok"

        result = await retry_async(flaky, retries=3, delay=0.01)
        assert result == "ok"
        assert attempts["count"] == 3

    asyncio.run(run_test())


def test_retry_async_gives_up_after_exhausting_retries() -> None:
    """Ensures retry async gives up after exhausting retries."""
    async def run_test() -> None:
        """Supports the test suite by run test."""
        async def always_fails() -> str:
            """Supports the test suite by always fails."""
            raise RuntimeError("permanent failure")

        with pytest.raises(RuntimeError):
            await retry_async(always_fails, retries=2, delay=0.01)

    asyncio.run(run_test())


def test_circuit_breaker_opens_after_the_failure_threshold_and_blocks_further_calls() -> None:
    """Ensures circuit breaker opens after the failure threshold and blocks further calls."""
    breaker = CircuitBreaker(failure_threshold=2, reset_timeout=1.0)

    breaker.record_failure()
    breaker.record_failure()

    with pytest.raises(CircuitBreakerOpenError):
        breaker.before_call()


def test_circuit_breaker_stays_closed_below_the_failure_threshold() -> None:
    """Ensures circuit breaker stays closed below the failure threshold."""
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
    """Ensures tracing configuration reads environment variables."""
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


def test_tracing_uses_otlp_exporter_in_otlp_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """OTLP mode should instantiate the OTLP exporter when an endpoint is configured."""
    import backend.observability.tracing as tracing

    created: dict[str, object] = {}

    class FakeExporter:
        def __init__(self, endpoint: str) -> None:
            created["endpoint"] = endpoint

        def export(self, spans: object) -> None:
            return None

        def shutdown(self) -> None:
            return None

    fake_module = types.SimpleNamespace(OTLPSpanExporter=FakeExporter)
    monkeypatch.setitem(
        sys.modules, "opentelemetry.exporter.otlp.proto.http.trace_exporter", fake_module)
    monkeypatch.setenv("OTEL_MODE", "otlp")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4318")
    monkeypatch.setattr(tracing, "_tracer", None)

    tracer = tracing._get_tracer()

    assert tracer is not None
    assert created.get("endpoint") == "http://collector:4318"
