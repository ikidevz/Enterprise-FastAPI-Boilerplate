from __future__ import annotations

import asyncio
from typing import Any

from backend.infrastructure.queue.registry import JOB_REGISTRY


class InProcessJobQueue:
    def enqueue(self, job_type: str, payload: dict[str, Any], attempts: int = 0) -> None:
        async def handler() -> None:
            job_handler = JOB_REGISTRY.get(job_type)
            if job_handler is None:
                raise ValueError(f"Unknown job type: {job_type}")
            await job_handler(payload)

        from backend.common.background_jobs import background_job_manager

        background_job_manager.enqueue(handler)
