from collections import defaultdict
from threading import Lock
from time import time

from backend.observability.logging import logger


class RateLimiter:
    def __init__(self) -> None:
        self._requests: dict[tuple[str, str], list[float]] = defaultdict(list)
        self._lock = Lock()
        self._configured_limit: int | None = None

    async def allow_request(self, client_id: str, path: str, *, limit: int) -> bool:
        now = time()
        key = (client_id, path)
        with self._lock:
            if self._configured_limit != limit:
                self._requests.clear()
                self._configured_limit = limit
            requests = self._requests[key]
            cutoff = now - 60
            requests[:] = [ts for ts in requests if ts > cutoff]
            if len(requests) >= limit:
                return False
            requests.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._requests.clear()
            self._configured_limit = None


shared_rate_limiter = RateLimiter()


class RedisRateLimiter:
    def __init__(self, redis_client) -> None:
        self.redis = redis_client

    async def allow_request(self, client_id: str, path: str, *, limit: int, window_seconds: int = 60) -> bool:
        key = f"ratelimit:{client_id}:{path}"
        now = time()
        try:
            pipe = self.redis.pipeline()
            pipe.zremrangebyscore(key, 0, now - window_seconds)
            pipe.zadd(key, {str(now): now})
            pipe.zcard(key)
            pipe.expire(key, window_seconds)
            _, _, count, _ = await pipe.execute()
            return count <= limit
        except Exception as exc:

            logger.error(
                "rate_limiter_bypassed_due_to_backend_outage",
                extra={"operation": "allow_request", "error": str(exc)},
            )
            return True
