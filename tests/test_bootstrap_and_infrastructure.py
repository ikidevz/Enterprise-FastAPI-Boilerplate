"""App factory, lifespan startup/shutdown hooks, and the infrastructure registry
that wires logging/Redis/background-jobs/email onto app.state.

Note on checking "does this route exist": the older version of this file
used `{route.path for route in app.routes}`, which broke against a newer
FastAPI/Starlette release that wraps included routers in an internal
object with no `.path` attribute (see
IMPROVEMENT_SUGGESTIONS_MERGED.md section 1.12). Reading `app.openapi()`
instead is the version-tolerant way to check "does this route exist" -
it's FastAPI's own public, documented interface for describing its routes,
rather than reaching into routing internals that are free to change
between versions.
"""
import asyncio

from fastapi import FastAPI

from backend.app.factory import create_app as create_app_from_factory
from backend.infrastructure.runtime import build_infrastructure_registry
from backend.common.bootstrap import BootstrapRegistry
from backend.app.lifespan import build_lifespan
from backend.core.config import settings
from backend.infrastructure.upload_storage import LocalUploadStorage


class _DummyRateLimiter:
    """A rate limiter stand-in for tests that only care about lifespan wiring,
    not actual rate-limiting behavior.
    """

    def reset(self) -> None:
        return None


def _all_route_paths(app: FastAPI) -> set[str]:
    """Return every path FastAPI's own OpenAPI schema knows about."""
    return set(app.openapi()["paths"].keys())


def test_app_factory_builds_a_working_app() -> None:
    app = create_app_from_factory()

    assert app is not None


def test_created_app_exposes_the_expected_health_and_api_routes() -> None:
    """`create_app()` (the factory) only wires up routers and middleware - it does not
    attach /health, /metrics, or /runtime. Those three are added directly onto the
    one real `app` singleton in backend/main.py, *after* calling the factory - so a
    fresh call to `create_app()` on its own won't have them. This test checks what
    the factory itself is actually responsible for; test_health_and_runtime.py
    (via the `client` fixture, which uses the real backend.main.app) is what
    checks /health, /metrics, and /runtime end to end.
    """
    app = create_app_from_factory()

    routes = _all_route_paths(app)

    assert "/health/ready" in routes
    assert "/api/v1/auth/login" in routes
    assert "/api/v1/products/" in routes


def test_bootstrap_registry_runs_startup_then_shutdown_hooks_in_order() -> None:
    events: list[str] = []
    registry = BootstrapRegistry()

    async def startup(_: object) -> None:
        events.append("startup")

    async def shutdown(_: object) -> None:
        events.append("shutdown")

    registry.register_startup_hook(startup)
    registry.register_shutdown_hook(shutdown)

    async def run() -> None:
        lifespan = build_lifespan(_DummyRateLimiter(), registry=registry)
        async with lifespan(object()):
            pass

    asyncio.run(run())

    assert events == ["startup", "shutdown"]


def test_infrastructure_registry_attaches_core_services_to_app_state() -> None:
    async def run() -> None:
        app = FastAPI()
        registry = build_infrastructure_registry(_DummyRateLimiter())
        lifespan = build_lifespan(_DummyRateLimiter(), registry=registry)

        async with lifespan(app):
            assert app.state.runtime is not None
            assert app.state.runtime["rate_limiter"] is not None
            assert app.state.services["logger"] is not None
            assert app.state.services["cache"] is not None
            assert app.state.services["background_jobs"] is not None
            assert app.state.services["email"] is not None
            assert app.state.upload_storage is not None
            assert isinstance(app.state.upload_storage, LocalUploadStorage)

    asyncio.run(run())
