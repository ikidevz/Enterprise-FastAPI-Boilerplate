import asyncio

from fastapi import FastAPI

from backend.app.factory import create_app as create_app_from_factory
from backend.app.infrastructure import build_infrastructure_registry
from backend.common.bootstrap import BootstrapRegistry
from backend.infrastructure.runtime import build_infrastructure_registry as build_enterprise_infrastructure_registry
from backend.common.context import clear_context, get_context_value, set_context_value
from backend.common.lifespan import build_lifespan
from backend.main import create_app


def test_create_app_exposes_health_and_api_routes() -> None:
    app = create_app()
    routes = {route.path for route in app.routes}
    assert "/health/ready" in routes
    assert "/api/v1/auth/login" in routes


def test_request_context_helpers_store_and_clear_values() -> None:
    clear_context()
    set_context_value("request_id", "req-123")
    set_context_value("trace_id", "trace-123")

    assert get_context_value("request_id") == "req-123"
    assert get_context_value("trace_id") == "trace-123"

    clear_context()

    assert get_context_value("request_id") is None
    assert get_context_value("trace_id") is None


def test_app_factory_module_exposes_create_app() -> None:
    app = create_app_from_factory()
    assert app is not None


def test_bootstrap_registry_runs_startup_and_shutdown_hooks() -> None:
    class DummyRateLimiter:
        def reset(self) -> None:
            return None

    events: list[str] = []
    registry = BootstrapRegistry()

    async def startup(_: object) -> None:
        events.append("startup")

    async def shutdown(_: object) -> None:
        events.append("shutdown")

    registry.register_startup_hook(startup)
    registry.register_shutdown_hook(shutdown)

    async def run() -> None:
        lifespan = build_lifespan(DummyRateLimiter(), registry=registry)
        async with lifespan(object()):
            pass

    asyncio.run(run())
    assert events == ["startup", "shutdown"]


def test_infrastructure_registry_registers_runtime_state() -> None:
    class DummyRateLimiter:
        def reset(self) -> None:
            return None

    async def run() -> None:
        app = FastAPI()
        registry = build_infrastructure_registry(DummyRateLimiter())
        lifespan = build_lifespan(DummyRateLimiter(), registry=registry)
        async with lifespan(app):
            assert app.state.runtime is not None
            assert app.state.runtime["rate_limiter"] is not None
            assert app.state.services["logger"] is not None
            assert app.state.services["cache"] is not None
            assert app.state.services["background_jobs"] is not None
            assert app.state.services["email"] is not None

    asyncio.run(run())


def test_enterprise_infrastructure_package_exposes_runtime_registry() -> None:
    class DummyRateLimiter:
        def reset(self) -> None:
            return None

    registry = build_enterprise_infrastructure_registry(DummyRateLimiter())
    assert registry is not None
