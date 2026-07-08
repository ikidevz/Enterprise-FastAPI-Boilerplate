from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator

from backend.observability.logging import logger
from backend.core.config import get_settings

_tracer = None


def _get_settings():
    return get_settings()


class _SafeConsoleSpanExporter:
    """A console exporter that tolerates closed streams during shutdown."""

    def __init__(self, stream: Any | None = None) -> None:
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter

        self._exporter = ConsoleSpanExporter(out=stream)
        self._closed = False

    def export(self, spans: Any) -> Any:
        if self._closed:
            return "SUCCESS"
        try:
            return self._exporter.export(spans)
        except (AttributeError, BrokenPipeError, OSError, TypeError, ValueError):
            return "SUCCESS"

    def shutdown(self) -> None:
        self._closed = True
        try:
            self._exporter.shutdown()
        except Exception:
            pass


def _get_tracer():
    global _tracer
    if _tracer is not None:
        return _tracer

    settings = _get_settings()
    if not settings.enable_tracing:
        _tracer = _NullTracer()
        return _tracer

    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create(
        {"service.name": settings.otel_service_name}))

    if settings.otel_mode == "production" and settings.otel_exporter_otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(
                endpoint=settings.otel_exporter_otlp_endpoint))
        )
    else:
        # "basic" mode, or production mode with no endpoint configured yet:
        # still real spans, just exported to the console instead of a collector.
        provider.add_span_processor(
            BatchSpanProcessor(_SafeConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(settings.otel_service_name)
    return _tracer


class _NullTracer:
    """Used when ENABLE_TRACING is false - keeps trace_span a real no-op context
    manager instead of branching on a flag at every call site.
    """

    @contextmanager
    def start_as_current_span(self, name: str, attributes: dict | None = None) -> Iterator[None]:
        yield


@contextmanager
def trace_span(name: str, **attributes: object) -> Iterator[None]:
    tracer = _get_tracer()
    with tracer.start_as_current_span(name, attributes=attributes):
        logger.info("span_started", extra={"span": name, **attributes})
        try:
            yield
        finally:
            logger.info("span_finished", extra={"span": name})


def get_tracing_configuration() -> dict[str, object]:
    """Unchanged public shape - your test suite and anything else introspecting
    tracing config still gets exactly this dict back.
    """
    settings = _get_settings()
    enabled = settings.enable_tracing
    mode = os.getenv("OTEL_MODE") or settings.otel_mode
    endpoint = os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT") or settings.otel_exporter_otlp_endpoint
    if os.getenv("ENABLE_TRACING") is not None:
        enabled = os.getenv("ENABLE_TRACING").lower() in (
            "1", "true", "yes", "on")
    return {
        "enabled": enabled,
        "mode": mode,
        "endpoint": endpoint,
    }
