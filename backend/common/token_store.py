from __future__ import annotations

import uuid
from typing import Any

from backend.common.log import logger
from backend.utils.redis_client import redis_client


class TokenStore:
    def __init__(self, prefix: str = "tier4:tokens") -> None:
        self.prefix = prefix
        self._memory_store: dict[str, str] = {}

    def _key(self, token: str) -> str:
        return f"{self.prefix}:{token}"

    async def _track_for_user(self, user_id: int, token: str, ttl_seconds: int) -> None:
        key = f"{self.prefix}:by-user:{user_id}"
        try:
            await redis_client.sadd(key, token)
            await redis_client.expire(key, ttl_seconds)
        except Exception as exc:
            logger.warning(
                "token_store_redis_unavailable",
                extra={"operation": "track_for_user", "error": str(exc)},
            )
            self._memory_store.setdefault(key, set()).add(token)

    async def add(self, token: str, value: Any, ttl_seconds: int) -> None:
        try:
            await redis_client.set(self._key(token), str(value), ex=ttl_seconds)
        except Exception as exc:
            logger.warning(
                "token_store_redis_unavailable",
                extra={"operation": "add", "error": str(exc)},
            )
            self._memory_store[self._key(token)] = str(value)

    async def get(self, token: str) -> str | None:
        try:
            return await redis_client.get(self._key(token))
        except Exception as exc:
            logger.warning(
                "token_store_redis_unavailable",
                extra={"operation": "get", "error": str(exc)},
            )
            return self._memory_store.get(self._key(token))

    async def delete(self, token: str) -> None:
        try:
            await redis_client.delete(self._key(token))
        except Exception as exc:
            logger.warning(
                "token_store_redis_unavailable",
                extra={"operation": "delete", "error": str(exc)},
            )
            self._memory_store.pop(self._key(token), None)

    async def add_refresh_token(self, user_id: int, ttl_seconds: int) -> str:
        token = str(uuid.uuid4())
        await self.add(token, user_id, ttl_seconds)
        await self._track_for_user(user_id, token, ttl_seconds)
        return token

    async def rotate_refresh_token(self, old_token: str, user_id: int, ttl_seconds: int) -> str:
        await self.delete(old_token)
        return await self.add_refresh_token(user_id, ttl_seconds)

    async def add_password_reset_token(self, user_id: int, ttl_seconds: int) -> str:
        token = str(uuid.uuid4())
        await self.add(token, user_id, ttl_seconds)
        return token

    async def consume_password_reset_token(self, token: str) -> int | None:
        value = await self.get(token)
        if value is None:
            return None
        await self.delete(token)
        return int(value)

    async def revoke(self, token: str) -> None:
        await self.delete(token)

    async def revoke_jti(self, jti: str, ttl_seconds: int | None = None) -> None:
        await self.add(jti, "revoked", ttl_seconds or 24 * 60 * 60)

    async def is_revoked(self, jti: str) -> bool:
        value = await self.get(jti)
        return value == "revoked"

    async def revoke_all_for_user(self, user_id: int) -> None:
        key = f"{self.prefix}:by-user:{user_id}"
        try:
            tokens = await redis_client.smembers(key)
        except Exception as exc:
            logger.warning(
                "token_store_redis_unavailable",
                extra={"operation": "revoke_all_for_user", "error": str(exc)},
            )
            tokens = self._memory_store.get(key, set())
        for token in tokens:
            await self.delete(token)
