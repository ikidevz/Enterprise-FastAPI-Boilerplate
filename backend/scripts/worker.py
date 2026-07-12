from __future__ import annotations

import asyncio
from typing import Any

from backend.common.background_jobs import background_job_manager
from backend.infrastructure.queue import job_queue
from backend.infrastructure.queue.registry import execute_job
from backend.observability.logging import logger


async def _run_redis_worker() -> None:
    while True:
        envelope = await asyncio.to_thread(job_queue.dequeue, timeout=5)
        if envelope is None:
            await asyncio.sleep(0.1)
            continue

        try:
            await execute_job(envelope)
        except Exception as exc:
            logger.error("redis_job_failed", extra={
                         "error": str(exc), "job": envelope})
            if hasattr(job_queue, "dead_letter"):
                await asyncio.to_thread(job_queue.dead_letter, envelope)


async def main() -> None:
    if hasattr(job_queue, "dequeue"):
        await _run_redis_worker()
        return

    await background_job_manager.start()
    try:
        while True:
            await asyncio.sleep(60)
    finally:
        await background_job_manager.stop()


if __name__ == "__main__":
    asyncio.run(main())
