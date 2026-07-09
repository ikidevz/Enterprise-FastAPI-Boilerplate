import uuid
import time

from fastapi import Depends, Request, WebSocket
from fastapi.responses import JSONResponse, Response

from backend.app.factory import create_app
from backend.observability.audit import audit_logger
from backend.web.request_size_middleware import RequestSizeLimitMiddleware
from backend.observability.logging import bind_request_context, logger, reset_request_context
from backend.observability.metrics import (
    get_metrics_snapshot,
    get_prometheus_metrics,
    record_request_metrics,
)
from backend.observability.tracing import trace_span
from backend.core.security.rbac import require_role
from backend.resilience.rate_limit import RedisRateLimiter, shared_rate_limiter
from backend.contracts.health_contracts import HealthResponse, MetricsResponse
from backend.core.config import settings
from backend.infrastructure.runtime import platform_runtime
from backend.utils.redis_client import redis_client


rate_limiter = (
    RedisRateLimiter(redis_client)
    if settings.environment != "dev"
    else shared_rate_limiter
)
app = create_app(rate_limiter)

app.add_middleware(
    RequestSizeLimitMiddleware,
    max_body_size=settings.max_request_size_bytes,
)


@app.middleware("http")
async def add_request_context(request: Request, call_next):
    request_id = (
        request.headers.get(settings.request_id_header)
        or str(uuid.uuid4())
    )

    trace_id = request.headers.get("x-trace-id") or request_id

    request.state.request_id = request_id
    request.state.trace_id = trace_id

    token = bind_request_context(
        request_id=request_id,
        trace_id=trace_id,
    )

    def apply_security_headers(response):
        response.headers[settings.request_id_header] = request_id
        response.headers["x-trace-id"] = trace_id
        response.headers["x-content-type-options"] = "nosniff"
        response.headers["x-frame-options"] = "DENY"
        response.headers["referrer-policy"] = (
            "strict-origin-when-cross-origin"
        )
        response.headers["content-security-policy"] = (
            "default-src 'self'; frame-ancestors 'none'; base-uri 'self'"
        )
        response.headers["permissions-policy"] = "geolocation=(), microphone=(), camera=()"

        if settings.require_https:
            response.headers[
                "strict-transport-security"
            ] = "max-age=31536000; includeSubDomains"

        return response

    def build_error_response(status_code: int, detail: str):
        response = JSONResponse(
            status_code=status_code,
            content={"detail": detail},
        )

        apply_security_headers(response)

        audit_logger.log(
            getattr(request.state, "user", None),
            "http.request_rejected",
            request.url.path,
            {"reason": detail},
            request=request,
            status_code=status_code,
            success=False,
        )

        return response

    # ------------------------------------------------------------------
    # Default values (used if an exception occurs)
    # ------------------------------------------------------------------
    response = None
    status_code = 500
    start = time.perf_counter()

    try:
        # ------------------------------------------------------------------
        # Rate Limiting
        # ------------------------------------------------------------------
        peer_ip = request.client.host if request.client else "unknown"
        client_ip = peer_ip

        if settings.trust_proxy_headers and peer_ip in settings.trusted_proxy_ips:
            forwarded_for = request.headers.get("x-forwarded-for", "")
            if forwarded_for:
                client_ip = forwarded_for.split(",")[0].strip()
        elif settings.trust_proxy_headers and not settings.trusted_proxy_ips:
            logger.warning(
                "trust_proxy_headers_enabled_without_allowlist",
                extra={"peer_ip": peer_ip},
            )

        if (
            settings.enable_rate_limiting
            and not await rate_limiter.allow_request(
                client_ip,
                request.url.path,
                limit=settings.rate_limit_requests_per_minute,
            )
        ):
            status_code = 429
            return build_error_response(
                429,
                "Too many requests",
            )

        # ------------------------------------------------------------------
        # Process Request
        # ------------------------------------------------------------------
        with trace_span(
            "http.request",
            method=request.method,
            path=request.url.path,
        ):
            response = await call_next(request)

        status_code = response.status_code

        # ------------------------------------------------------------------
        # Security Headers
        # ------------------------------------------------------------------
        apply_security_headers(response)

        # ------------------------------------------------------------------
        # Logging
        # ------------------------------------------------------------------
        duration_ms = (
            time.perf_counter() - start
        ) * 1000

        logger.info(
            "request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "duration_ms": round(duration_ms, 2),
            },
        )

        # ------------------------------------------------------------------
        # Audit Logging
        # ------------------------------------------------------------------
        audit_logger.log(
            getattr(request.state, "user", None),
            "http.request",
            request.url.path,
            {"method": request.method},
            request=request,
            status_code=status_code,
            success=status_code < 400,
        )

        return response

    except Exception as exc:
        audit_logger.log(
            getattr(request.state, "user", None),
            "http.request",
            request.url.path,
            {"method": request.method},
            request=request,
            status_code=500,
            success=False,
            error=str(exc),
        )
        raise

    finally:
        # ------------------------------------------------------------------
        # Metrics (always recorded)
        # ------------------------------------------------------------------
        route = request.scope.get("route")
        path_template = (
            route.path
            if route is not None
            else "unmatched"
        )

        record_request_metrics(
            request.method,
            status_code,
            path_template,
        )

        reset_request_context(token)


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse(
        status="ok",
        environment=settings.environment,
        version=app.version,
    )


@app.websocket("/ws/health")
async def websocket_health(websocket: WebSocket) -> None:
    await websocket.accept()
    await websocket.send_json({"status": "connected"})
    await websocket.close()


@app.get("/metrics", response_model=None)
async def metrics(
    request: Request,
    current_user=Depends(require_role("admin")),
) -> MetricsResponse | Response:
    accept_header = request.headers.get("accept", "")
    if "text/plain" in accept_header:
        payload, content_type = get_prometheus_metrics()
        return Response(content=payload, media_type=content_type)

    snapshot = get_metrics_snapshot()
    return MetricsResponse(
        status="ok",
        request_count=snapshot.get("request_count", 0),
        status_codes=snapshot.get("status_codes", {}),
        methods=snapshot.get("methods", {}),
        paths=snapshot.get("paths", {}),
    )


@app.get("/runtime")
async def runtime_snapshot(current_user=Depends(require_role("admin"))) -> dict[str, object]:
    return platform_runtime.build_runtime_snapshot(environment=settings.environment)
