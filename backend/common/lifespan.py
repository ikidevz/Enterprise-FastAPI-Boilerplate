from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from backend.common.background_jobs import background_job_manager
from backend.common.bootstrap import BootstrapRegistry
from backend.common.exporters import export_metrics
from backend.common.log import logger
from backend.database import session as db_session
from backend.database.base import Base


def build_lifespan(rate_limiter, *, registry: BootstrapRegistry | None = None):
    @asynccontextmanager
    async def lifespan(app) -> AsyncIterator[None]:
        logger.info("Starting application")
        rate_limiter.reset()
        await background_job_manager.start()
        try:
            async with db_session.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        except Exception as exc:
            logger.warning("Database initialization skipped: %s", exc)

        if registry is not None:
            await registry.run_startup_hooks(app)
        export_metrics()
        yield
        if registry is not None:
            await registry.run_shutdown_hooks(app)
        export_metrics()
        await background_job_manager.stop()

    return lifespan
