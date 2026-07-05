from __future__ import annotations

from typing import Any

from backend.common.background_jobs import background_job_manager
from backend.common.bootstrap import BootstrapRegistry
from backend.common.email import email_delivery_service
from backend.common.log import logger
from backend.database import session as db_session
from backend.infrastructure.upload_storage import (
    AzureBlobUploadStorage,
    LocalUploadStorage,
    S3UploadStorage,
)
from backend.utils.redis_client import redis_client
from backend.core.config import settings


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
