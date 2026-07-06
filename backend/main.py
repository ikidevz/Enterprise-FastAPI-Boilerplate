import uuid
import time

from fastapi import Request, WebSocket
from fastapi.responses import JSONResponse

from backend.app.factory import create_app
from backend.common.audit import audit_logger
from backend.common.request_size import RequestSizeLimitMiddleware
from backend.common.log import bind_request_context, logger, reset_request_context
from backend.common.observability import get_metrics_snapshot, record_request_metrics
from backend.common.opentelemetry import trace_span
from backend.common.rate_limit import shared_rate_limiter
from backend.contracts.api_contracts import HealthResponse, MetricsResponse
from backend.core.config import settings
from backend.platform.runtime import PlatformRuntime


rate_limiter = shared_rate_limiter
app = create_app()

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
        return apply_security_headers(response)

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
        client_ip = (
            request.headers.get("x-forwarded-for", "")
            .split(",")[0]
            .strip()
        )

        if not client_ip:
            client_ip = (
                request.client.host
                if request.client
                else "unknown"
            )

        if (
            settings.enable_rate_limiting
            and not rate_limiter.allow_request(
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
        record_request_metrics(
            request.method,
            status_code,
            request.url.path,
        )

        reset_request_context(token)


platform_runtime = PlatformRuntime()


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


@app.get("/metrics", response_model=MetricsResponse)
async def metrics() -> MetricsResponse:
    snapshot = get_metrics_snapshot()
    return MetricsResponse(
        status="ok",
        request_count=snapshot.get("request_count", 0),
        status_codes=snapshot.get("status_codes", {}),
        methods=snapshot.get("methods", {}),
        paths=snapshot.get("paths", {}),
    )


@app.get("/runtime")
async def runtime_snapshot() -> dict[str, object]:
    return platform_runtime.build_runtime_snapshot(environment=settings.environment)
