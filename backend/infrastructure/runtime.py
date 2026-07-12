from __future__ import annotations

from typing import Any
from time import time

from backend.common.exporters import export_metrics
from backend.observability.metrics import metrics_collector
from backend.common.background_jobs import background_job_manager
from backend.common.bootstrap import BootstrapRegistry
from backend.infrastructure.email.transport import email_delivery_service
from backend.observability.logging import logger
from backend.database import session as db_session
from backend.infrastructure.upload_storage import (
    AzureBlobUploadStorage,
    LocalUploadStorage,
    S3UploadStorage,
)
from backend.utils.redis_client import redis_client
from backend.core.config import settings
from backend.domain.events import DomainEvent, EventBus


class PlatformRuntime:
    """Thin runtime facade for platform-level observability and health signals."""

    def __init__(self) -> None:
        self.metrics_collector = metrics_collector
        self.started_at = time()
        self.event_bus = EventBus()
        self._register_default_handlers()

    def _register_default_handlers(self) -> None:
        async def log_domain_event(event: DomainEvent) -> None:
            logger.info("domain_event_published",
                        extra={"event": event.payload})

        self.event_bus.subscribe("user.registered", log_domain_event)

    def reset_event_bus(self) -> None:
        self.event_bus = EventBus()
        self._register_default_handlers()

    def build_runtime_snapshot(self, *, environment: str) -> dict[str, object]:
        export_metrics()
        metrics_snapshot = self.metrics_collector.snapshot()
        return {
            "service": "tier4",
            "environment": environment,
            "uptime_seconds": int(time() - self.started_at),
            "checks": {
                "metrics": True,
                "observability": True,
            },
            "metrics": metrics_snapshot,
        }


platform_runtime = PlatformRuntime()


def build_infrastructure_registry(rate_limiter: Any) -> BootstrapRegistry:
    """Enterprise-style infrastructure registry for runtime and persistence wiring."""
    registry = BootstrapRegistry()

    async def register_runtime_state(app: Any) -> None:
        if settings.upload_backend == "s3":
            upload_storage = S3UploadStorage(
                bucket=settings.s3_bucket or "",
                region=settings.s3_region,
                access_key_id=settings.s3_access_key_id,
                secret_access_key=settings.s3_secret_access_key,
                endpoint_url=settings.s3_endpoint_url,
            )
        elif settings.upload_backend == "azure":
            upload_storage = AzureBlobUploadStorage(
                connection_string=settings.azure_storage_connection_string or "",
                container=settings.azure_storage_container or "",
            )
        else:
            upload_storage = LocalUploadStorage(settings.upload_dir)

        app.state.runtime = {
            "rate_limiter": rate_limiter,
            "database_engine": db_session.engine,
            "session_factory": db_session.SessionLocal,
        }
        app.state.persistence = {
            "engine": db_session.engine,
            "session_factory": db_session.SessionLocal,
        }
        app.state.services = {
            "logger": logger,
            "cache": redis_client,
            "background_jobs": background_job_manager,
            "email": email_delivery_service,
            "rate_limiter": rate_limiter,
            "upload_storage": upload_storage,
        }
        app.state.logger = logger
        app.state.cache = redis_client
        app.state.background_jobs = background_job_manager
        app.state.email_service = email_delivery_service
        app.state.rate_limiter = rate_limiter
        app.state.upload_storage = upload_storage

        from backend.infrastructure.webhooks.dispatcher import subscribe_webhook_dispatcher

        platform_runtime.reset_event_bus()
        subscribe_webhook_dispatcher(platform_runtime.event_bus)

    async def clear_runtime_state(app: Any) -> None:
        app.state.runtime = {}
        app.state.persistence = {}
        app.state.services = {}
        app.state.logger = None
        app.state.cache = None
        app.state.background_jobs = None
        app.state.email_service = None
        app.state.rate_limiter = None
        app.state.upload_storage = None

    registry.register_startup_hook(register_runtime_state)
    registry.register_shutdown_hook(clear_runtime_state)
    return registry
