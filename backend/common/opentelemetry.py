from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator

from backend.common.log import logger


def get_tracing_configuration() -> dict[str, Any]:
    mode = os.getenv("OTEL_MODE", "basic").strip().lower()
    endpoint = os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT") or os.getenv("OTEL_ENDPOINT")
    enabled = os.getenv("ENABLE_TRACING", "true").lower() in {
        "1", "true", "yes", "on"}
    return {
        "enabled": enabled,
        "mode": mode,
        "endpoint": endpoint,
        "service_name": os.getenv("OTEL_SERVICE_NAME", "tier4"),
    }


class OpenTelemetryBridge:
    def __init__(self) -> None:
        self.configuration = get_tracing_configuration()
        self.enabled = self.configuration["enabled"]

    @contextmanager
    def span(self, name: str, **attributes: Any) -> Iterator[None]:
        if not self.enabled:
            yield
            return

        logger.info(
            "span_started",
            extra={
                "span_name": name,
                "attributes": attributes,
                "otel_mode": self.configuration["mode"],
                "otel_endpoint": self.configuration["endpoint"],
            },
        )
        try:
            yield
        finally:
            logger.info(
                "span_finished",
                extra={
                    "span_name": name,
                    "attributes": attributes,
                    "otel_mode": self.configuration["mode"],
                    "otel_endpoint": self.configuration["endpoint"],
                },
            )


opentelemetry_bridge = OpenTelemetryBridge()


def trace_span(name: str, **attributes: Any) -> Iterator[None]:
    return opentelemetry_bridge.span(name, **attributes)
