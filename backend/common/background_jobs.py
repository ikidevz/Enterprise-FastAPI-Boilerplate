from __future__ import annotations

import asyncio
import inspect
from collections import deque
from typing import Awaitable, Callable, Deque


class BackgroundJobManager:
    def __init__(self) -> None:
        self._queue: Deque[Callable[[], Awaitable[None] | None]] = deque()
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())

    def enqueue(self, job: Callable[[], Awaitable[None] | None]) -> None:
        self._queue.append(job)

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            if not self._queue:
                await asyncio.sleep(0.01)
                continue
            job = self._queue.popleft()
            result = job()
            if inspect.isawaitable(result):
                await result

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)
        self._task = None


background_job_manager = BackgroundJobManager()
