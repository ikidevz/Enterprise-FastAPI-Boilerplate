from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from backend.core.config import settings
from backend.infrastructure.queue.registry import JOB_REGISTRY
from backend.utils.redis_client import redis_client


class RedisJobQueue:
    def __init__(self) -> None:
        self._queue_key = "jobs:pending"
        self._dead_letter_key = "jobs:dead_letter"

    def enqueue(self, job_type: str, payload: dict[str, Any], attempts: int = 0) -> None:
        envelope = {
            "job_type": job_type,
            "payload": payload,
            "attempts": attempts,
            "enqueued_at": datetime.now(timezone.utc).isoformat(),
        }
        redis_client.lpush(self._queue_key, json.dumps(envelope, default=str))

    def dequeue(self, timeout: int = 0) -> dict[str, Any] | None:
        raw = redis_client.brpop(self._queue_key, timeout=timeout)
        if raw is None:
            return None
        _, payload = raw
        return json.loads(payload)

    def dead_letter(self, envelope: dict[str, Any]) -> None:
        redis_client.lpush(self._dead_letter_key,
                           json.dumps(envelope, default=str))

    def get_dead_letter(self, count: int = 100) -> list[dict[str, Any]]:
        items = redis_client.lrange(self._dead_letter_key, 0, count - 1)
        return [json.loads(item) for item in items]

    def purge_dead_letter(self) -> None:
        redis_client.delete(self._dead_letter_key)


job_queue = RedisJobQueue()
