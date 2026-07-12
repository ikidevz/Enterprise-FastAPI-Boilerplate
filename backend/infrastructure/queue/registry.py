from __future__ import annotations

from typing import Any, Awaitable, Callable

from backend.core.config import settings
from backend.resilience.retry import retry_async

EventHandler = Callable[[dict[str, Any]], Awaitable[None]]

JOB_REGISTRY: dict[str, EventHandler] = {}


def register_job_handler(job_type: str):
    def decorator(fn: EventHandler) -> EventHandler:
        JOB_REGISTRY[job_type] = fn
        return fn
    return decorator


async def execute_job(envelope: dict[str, Any]) -> None:
    job_type = envelope.get("job_type")
    payload = envelope.get("payload", {})
    handler = JOB_REGISTRY.get(job_type)
    if handler is None:
        raise ValueError(f"Unknown job type: {job_type}")

    async def run_handler() -> None:
        await handler(payload)

    await retry_async(
        run_handler,
        retries=max(settings.job_max_attempts - 1, 0),
        delay=0.5,
        backoff=2.0,
    )
