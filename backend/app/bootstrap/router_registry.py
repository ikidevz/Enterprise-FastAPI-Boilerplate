from __future__ import annotations

from fastapi import FastAPI

from backend.app.api.v1.router import router as api_router
from backend.observability.health_checks import router as health_router
from backend.core.config import settings


def register_api_routers(app: FastAPI) -> None:
    app.include_router(api_router, prefix=settings.api_v1_str)
    app.include_router(health_router)
