import json
from threading import Lock
from typing import Any

from backend.core.config import settings
from backend.utils.redis_client import redis_client


class InMemoryIdempotencyStore:
    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}
        self._lock = Lock()

    async def get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            return self._store.get(key)

    async def set(self, key: str, payload: dict[str, Any], *, ttl_seconds: int = 86_400) -> None:
        with self._lock:
            self._store[key] = payload


class RedisIdempotencyStore:
    def __init__(self, redis_client_obj: Any) -> None:
        self._redis = redis_client_obj

    async def get(self, key: str) -> dict[str, Any] | None:
        payload = await self._redis.get(key)
        if payload is None:
            return None
        return json.loads(payload)

    async def set(self, key: str, payload: dict[str, Any], *, ttl_seconds: int = 86_400) -> None:
        await self._redis.set(key, json.dumps(payload), ex=ttl_seconds)


def get_idempotency_store() -> InMemoryIdempotencyStore | RedisIdempotencyStore:
    if settings.environment in {"dev", "test"}:
        return InMemoryIdempotencyStore()
    return RedisIdempotencyStore(redis_client)
