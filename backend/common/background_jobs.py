from __future__ import annotations

import asyncio
import inspect
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select

from backend.core.config import settings
from backend.observability.logging import logger
from backend.resilience.retry import retry_async


def enqueue_billing_notification(*, user_id: int, kind: str, title: str, body: str) -> None:
    from backend.domain.billing.models import Notification
    from backend.database import session as db_session

    async def _job() -> None:
        async with db_session.SessionLocal() as db:
            db.add(Notification(user_id=user_id, kind=kind,
                   title=title, body=body, channel="in_app"))
            await db.commit()

    background_job_manager.enqueue(_job)


async def cleanup_stale_uploads(*, older_than_days: int = 7) -> int:
    from backend.database import session as db_session
    from backend.domain.uploads.model import UploadRecord

    cutoff = datetime.now(timezone.utc) - \
        timedelta(days=max(0, older_than_days))
    async with db_session.SessionLocal() as db:
        result = await db.execute(select(UploadRecord).where(UploadRecord.created_at <= cutoff))
        records = result.scalars().all()
        for record in records:
            if settings.upload_backend == "local":
                file_path = (Path(settings.upload_dir) /
                             record.stored_name).resolve()
                if file_path.exists():
                    file_path.unlink(missing_ok=True)
            await db.delete(record)
        await db.commit()
        return len(records)


async def expire_trial_subscriptions() -> int:
    from backend.database import session as db_session
    from backend.domain.billing.models import Subscription

    now = datetime.now(timezone.utc)
    async with db_session.SessionLocal() as db:
        result = await db.execute(
            select(Subscription).where(
                Subscription.status == "trialing",
                Subscription.trial_ends_at.is_not(None),
                Subscription.trial_ends_at <= now,
            )
        )
        subscriptions = result.scalars().all()
        for subscription in subscriptions:
            subscription.status = "expired"
        await db.commit()
        return len(subscriptions)


async def process_trial_expiry_jobs() -> int:
    from backend.database import session as db_session
    from backend.domain.billing.models import Subscription

    updated = await expire_trial_subscriptions()
    if updated:
        async with db_session.SessionLocal() as db:
            result = await db.execute(select(Subscription).where(Subscription.status == "expired"))
            subscriptions = result.scalars().all()
            for subscription in subscriptions:
                enqueue_billing_notification(
                    user_id=subscription.user_id,
                    kind="trial_expired",
                    title="Trial ended",
                    body="Your trial has ended. Please review your billing plan.",
                )
    return updated


async def run_periodic_lifecycle_jobs(*, older_than_days: int = 7) -> dict[str, int]:
    cleaned_uploads = await cleanup_stale_uploads(older_than_days=older_than_days)
    expired_subscriptions = await process_trial_expiry_jobs()
    return {"cleaned_uploads": cleaned_uploads, "expired_subscriptions": expired_subscriptions}


class QueueBackend:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[Any] | None = None
        self._pending_jobs: list[Any] = []
        self._loop: asyncio.AbstractEventLoop | None = None

    def _ensure_queue(self, loop: asyncio.AbstractEventLoop) -> asyncio.Queue[Any]:
        if self._queue is None or self._loop is not loop:
            self._queue = asyncio.Queue()
            self._loop = loop
            while self._pending_jobs:
                self._queue.put_nowait(self._pending_jobs.pop(0))
        return self._queue

    def enqueue(self, job: Any) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._pending_jobs.append(job)
            return
        self._ensure_queue(loop).put_nowait(job)

    async def get(self) -> Any:
        loop = asyncio.get_running_loop()
        return await self._ensure_queue(loop).get()

    async def task_done(self) -> None:
        loop = asyncio.get_running_loop()
        self._ensure_queue(loop).task_done()


class BackgroundJobManager:
    def __init__(self) -> None:
        self._queue_backend = QueueBackend()
        self._queue: asyncio.Queue[Any] | None = None
        self._task: asyncio.Task[None] | None = None
        self._dead_letter: list[dict[str, object]] = []
        self._dead_letter_limit = 50
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._task is not None and not self._task.done() and self._loop is loop:
            return
        self._loop = loop
        self._queue = self._queue_backend._ensure_queue(loop)
        self._task = loop.create_task(self._run())

    def enqueue(self, job) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._queue_backend.enqueue(job)
            return
        if self._loop is None or self._loop is not loop:
            self._loop = loop
            self._queue = self._queue_backend._ensure_queue(loop)
            self._task = None
        self._queue_backend.enqueue(job)
        if self._task is None or self._task.done():
            self._task = loop.create_task(self._run())

    async def _execute_job(self, job) -> None:
        result = job()
        if inspect.isawaitable(result):
            await result

    async def _run(self) -> None:
        while True:
            job = await self._queue_backend.get()
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
                await self._queue_backend.task_done()

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)
        self._task = None


background_job_manager = BackgroundJobManager()
