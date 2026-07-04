from __future__ import annotations

from time import time

from backend.common.exporters import export_metrics
from backend.common.observability import metrics_collector


class PlatformRuntime:
    """Thin runtime facade for platform-level observability and health signals."""

    def __init__(self) -> None:
        self.metrics_collector = metrics_collector
        self.started_at = time()

    def build_runtime_snapshot(self, *, environment: str) -> dict[str, object]:
        export_metrics()
        metrics_snapshot = self.metrics_collector.snapshot()
        return {
            "service": "tier4",
            "environment": environment,
            "uptime_seconds": int(time() - self.started_at),
            "checks": {
                "metrics": True,
                "observability": True,
            },
            "metrics": metrics_snapshot,
        }

    def emit_runtime_snapshot(self) -> dict[str, object]:
        return self.build_runtime_snapshot(environment="development")
