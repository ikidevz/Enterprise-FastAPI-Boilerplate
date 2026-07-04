from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

from backend.common.log import logger

T = TypeVar("T")


class CircuitBreakerOpenError(RuntimeError):
    pass


class CircuitBreaker:
    def __init__(self, *, failure_threshold: int = 3, reset_timeout: float = 30.0) -> None:
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self._failure_count = 0
        self._opened_at: float | None = None

    def _is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if time.monotonic() - self._opened_at >= self.reset_timeout:
            self._failure_count = 0
            self._opened_at = None
            return False
        return True

    def before_call(self) -> None:
        if self._is_open():
            raise CircuitBreakerOpenError("Circuit breaker is open")

    def record_success(self) -> None:
        self._failure_count = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failure_count += 1
        if self._failure_count >= self.failure_threshold:
            self._opened_at = time.monotonic()


async def retry_async(
    func: Callable[[], Coroutine[Any, Any, T]],
    *,
    retries: int = 3,
    delay: float = 0.25,
    backoff: float = 2.0,
    on_error: Callable[[Exception], None] | None = None,
) -> T:
    last_error: Exception | None = None
    attempt_delay = delay
    for attempt in range(retries + 1):
        try:
            return await func()
        except Exception as exc:  # pragma: no cover - exercised via behavior
            last_error = exc
            if on_error is not None:
                on_error(exc)
            if attempt >= retries:
                raise
            logger.warning("retrying operation", extra={
                           "attempt": attempt + 1, "error": str(exc)})
            await asyncio.sleep(attempt_delay)
            attempt_delay *= backoff
    if last_error is not None:
        raise last_error
    raise RuntimeError("retry_async failed without an exception")
