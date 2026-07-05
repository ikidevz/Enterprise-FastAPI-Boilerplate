from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from backend.app.bootstrap import (
    register_api_routers,
    register_middlewares,
    register_static_assets,
)
from backend.app.socketio_app import app_socket
from backend.infrastructure.runtime import build_infrastructure_registry
from backend.common.exceptions import DomainHTTPException
from backend.common.lifespan import build_lifespan
from backend.common.rate_limit import shared_rate_limiter
from backend.core.config import settings

from sqlalchemy.exc import IntegrityError

rate_limiter = shared_rate_limiter
infrastructure_registry = build_infrastructure_registry(rate_limiter)
lifespan = build_lifespan(rate_limiter, registry=infrastructure_registry)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.project_name,
        version="0.1.0",
        description="Production-grade FastAPI 4-tier boilerplate with authentication, CRUD, permissions, and real-time support.",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
        openapi_tags=[
            {"name": "auth", "description": "Authentication, token refresh, and password reset."},
            {"name": "users", "description": "User registration, profile access, and account updates."},
            {"name": "products", "description": "Example product CRUD module."},
            {"name": "health", "description": "Readiness and health probes."},
        ],
    )

    @app.exception_handler(DomainHTTPException)
    async def domain_http_exception_handler(_: Request, exc: DomainHTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict):
            payload = dict(exc.detail)
            if "detail" in payload and "message" not in payload:
                payload["message"] = payload["detail"]
            return JSONResponse(status_code=exc.status_code, content=payload)
        return JSONResponse(status_code=exc.status_code, content={"message": str(exc), "error_code": None})

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(_: Request, exc: IntegrityError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"message": "Resource already exists", "error_code": "conflict"})

    register_middlewares(app)
    register_api_routers(app)
    register_static_assets(app)

    if app_socket is not None:
        app.mount("/socket.io", app_socket)

    return app
