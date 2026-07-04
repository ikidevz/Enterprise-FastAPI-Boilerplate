from __future__ import annotations

from collections import Counter
from threading import Lock
from typing import Any


class MetricsCollector:
    def __init__(self) -> None:
        self._lock = Lock()
        self.request_count = 0
        self.status_codes: Counter[str] = Counter()
        self.methods: Counter[str] = Counter()
        self.paths: Counter[str] = Counter()

    def record(self, method: str, status_code: int, path: str) -> None:
        with self._lock:
            self.request_count += 1
            self.status_codes[str(status_code)] += 1
            self.methods[method.upper()] += 1
            self.paths[path] += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "request_count": self.request_count,
                "status_codes": dict(self.status_codes),
                "methods": dict(self.methods),
                "paths": dict(self.paths),
            }

    def reset(self) -> None:
        with self._lock:
            self.request_count = 0
            self.status_codes.clear()
            self.methods.clear()
            self.paths.clear()


metrics_collector = MetricsCollector()


def record_request_metrics(method: str, status_code: int, path: str) -> None:
    metrics_collector.record(method, status_code, path)


def get_metrics_snapshot() -> dict[str, Any]:
    return metrics_collector.snapshot()
