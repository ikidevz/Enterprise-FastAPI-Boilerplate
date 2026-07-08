from __future__ import annotations

from collections import Counter
from threading import Lock
from typing import Any

from prometheus_client import CollectorRegistry, CONTENT_TYPE_LATEST, Counter as PromCounter, generate_latest


class MetricsCollector:
    def __init__(self) -> None:
        self._lock = Lock()
        self.request_count = 0
        self.status_codes: Counter[str] = Counter()
        self.methods: Counter[str] = Counter()
        self.paths: Counter[str] = Counter()
        self._registry = CollectorRegistry(auto_describe=True)
        self._http_requests_total = PromCounter(
            "http_requests_total",
            "Total HTTP requests handled by the service",
            labelnames=("method", "status_code", "path"),
            registry=self._registry,
        )

    def record(self, method: str, status_code: int, path: str) -> None:
        with self._lock:
            self.request_count += 1
            self.status_codes[str(status_code)] += 1
            self.methods[method.upper()] += 1
            self.paths[path] += 1
            self._http_requests_total.labels(
                method=method.upper(),
                status_code=str(status_code),
                path=path,
            ).inc()

    def record_rate_limiter_fallback(self) -> None:
        with self._lock:
            self.rate_limiter_fallbacks += 1

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


def record_rate_limiter_fallback() -> None:
    metrics_collector.record_rate_limiter_fallback()


def get_metrics_snapshot() -> dict[str, Any]:
    return metrics_collector.snapshot()


def get_prometheus_metrics() -> tuple[bytes, str]:
    payload = generate_latest(registry=metrics_collector._registry)
    return payload, CONTENT_TYPE_LATEST
