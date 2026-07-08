from __future__ import annotations

import asyncio
import inspect

from backend.observability.logging import logger
from backend.resilience.retry import retry_async


class BackgroundJobManager:
    def __init__(self) -> None:
        self._queue: asyncio.Queue = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None
        self._dead_letter: list[dict[str, object]] = []
        self._dead_letter_limit = 50

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run())

    def enqueue(self, job) -> None:
        self._queue.put_nowait(job)
        if self._task is None or self._task.done():
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return
            self._task = loop.create_task(self._run())

    async def _execute_job(self, job) -> None:
        result = job()
        if inspect.isawaitable(result):
            await result

    async def _run(self) -> None:
        while True:
            job = await self._queue.get()
            try:
                await retry_async(
                    lambda: self._execute_job(job),
                    retries=2,
                    delay=0.05,
                )
            except Exception as exc:
                self._dead_letter.append(
                    {
                        "job": getattr(job, "__qualname__", repr(job)),
                        "error": str(exc),
                    }
                )
                if len(self._dead_letter) > self._dead_letter_limit:
                    self._dead_letter = self._dead_letter[-self._dead_letter_limit:]
                logger.error(
                    "background_job_failed",
                    extra={"job": getattr(
                        job, "__qualname__", repr(job)), "error": str(exc)},
                )
            finally:
                self._queue.task_done()

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)
        self._task = None


background_job_manager = BackgroundJobManager()
