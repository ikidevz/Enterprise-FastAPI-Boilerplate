from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from backend.core.config import settings
from backend.common.background_jobs import background_job_manager
from backend.common.bootstrap import BootstrapRegistry
from backend.common.exporters import export_metrics
from backend.observability.logging import logger
from backend.database import session as db_session
from backend.database.base import Base
from backend.domain.rbac.service import RbacService
from backend.domain.billing.service import BillingService


def build_lifespan(rate_limiter, *, registry: BootstrapRegistry | None = None):
    @asynccontextmanager
    async def lifespan(app) -> AsyncIterator[None]:
        logger.info("Starting application")
        rate_limiter.reset()
        await background_job_manager.start()
        if settings.environment == "dev":
            try:
                async with db_session.engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
            except Exception as exc:
                logger.warning("Database initialization skipped: %s", exc)

        if registry is not None:
            await registry.run_startup_hooks(app)

        try:
            async with db_session.SessionLocal() as db:
                async with db.begin():
                    rbac_service = RbacService(db)
                    await rbac_service.ensure_seed_data()
                    billing_service = BillingService(db)
                    await billing_service.ensure_seed_data()
        except Exception as exc:
            logger.error("startup_seed_failed", extra={"error": str(exc)})
            raise

        export_metrics()
        yield
        if registry is not None:
            await registry.run_shutdown_hooks(app)
        export_metrics()
        await background_job_manager.stop()

    return lifespan
