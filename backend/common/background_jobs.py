from __future__ import annotations

import asyncio
import inspect
from collections import deque
from typing import Awaitable, Callable, Deque


class BackgroundJobManager:
    def __init__(self) -> None:
        self._queue: asyncio.Queue = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None

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

    async def _run(self) -> None:
        while True:
            job = await self._queue.get()
            try:
                result = job()
                if inspect.isawaitable(result):
                    await result
            finally:
                self._queue.task_done()

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)
        self._task = None


background_job_manager = BackgroundJobManager()
