from __future__ import annotations

import asyncio
import contextlib
import inspect
from collections import deque
from typing import Awaitable, Callable, Deque


class BackgroundJobManager:
    def __init__(self) -> None:
        self._queue: Deque[Callable[[], Awaitable[None] | None]] = deque()
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        with contextlib.suppress(asyncio.CancelledError):
            self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)
        self._task = None
        self._stop_event.clear()

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


background_job_manager = BackgroundJobManager()
