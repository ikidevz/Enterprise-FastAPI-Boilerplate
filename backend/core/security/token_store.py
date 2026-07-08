from __future__ import annotations

import uuid
from typing import Any

from backend.observability.logging import logger
from backend.core.config import settings
from backend.utils.redis_client import redis_client


class TokenStoreUnavailableError(RuntimeError):
    """Raised when Redis is unreachable for security-critical token state."""


class TokenStore:
    USED_TOKEN_PREFIX = "used:"

    def __init__(self, prefix: str = "tier4:tokens") -> None:
        self.prefix = prefix
        self._memory_store: dict[str, Any] = {}

    def _key(self, token: str) -> str:
        return f"{self.prefix}:{token}"

    def _user_index_key(self, user_id: int) -> str:
        return f"{self.prefix}:by-user:{user_id}"

    def _used_token_value(self, user_id: int) -> str:
        return f"{self.USED_TOKEN_PREFIX}{user_id}"

    def _is_used_value(self, value: str | None) -> bool:
        return bool(value and value.startswith(self.USED_TOKEN_PREFIX))

    def _used_token_user_id(self, value: str | None) -> int | None:
        if not self._is_used_value(value):
            return None
        return int(value.split(self.USED_TOKEN_PREFIX, 1)[1])

    async def _track_for_user(self, user_id: int, token: str, ttl_seconds: int) -> None:
        key = self._user_index_key(user_id)
        try:
            await redis_client.sadd(key, token)
            await redis_client.expire(key, ttl_seconds)
        except Exception as exc:
            logger.warning(
                "token_store_redis_unavailable",
                extra={"operation": "track_for_user", "error": str(exc)},
            )
            if settings.environment == "dev":
                self._memory_store.setdefault(key, set()).add(token)
            else:
                raise TokenStoreUnavailableError("Redis unavailable")

    async def _set(self, token: str, value: str, ttl_seconds: int) -> None:
        try:
            await redis_client.set(self._key(token), value, ex=ttl_seconds)
        except Exception as exc:
            logger.warning(
                "token_store_redis_unavailable",
                extra={"operation": "set", "error": str(exc)},
            )
            if settings.environment == "dev":
                self._memory_store[self._key(token)] = value
            else:
                raise TokenStoreUnavailableError("Redis unavailable")

    async def _get(self, token: str) -> str | None:
        try:
            return await redis_client.get(self._key(token))
        except Exception as exc:
            logger.warning(
                "token_store_redis_unavailable",
                extra={"operation": "get", "error": str(exc)},
            )
            if settings.environment == "dev":
                return self._memory_store.get(self._key(token))
            raise TokenStoreUnavailableError("Redis unavailable")

    async def _delete(self, token: str) -> None:
        try:
            await redis_client.delete(self._key(token))
        except Exception as exc:
            logger.warning(
                "token_store_redis_unavailable",
                extra={"operation": "delete", "error": str(exc)},
            )
            if settings.environment == "dev":
                self._memory_store.pop(self._key(token), None)
            else:
                raise TokenStoreUnavailableError("Redis unavailable")

    async def add(self, token: str, value: Any, ttl_seconds: int) -> None:
        await self._set(token, str(value), ttl_seconds)

    async def get(self, token: str) -> str | None:
        return await self._get(token)

    async def delete(self, token: str) -> None:
        await self._delete(token)

    async def add_refresh_token(self, user_id: int, ttl_seconds: int) -> str:
        token = str(uuid.uuid4())
        await self.add(token, user_id, ttl_seconds)
        await self._track_for_user(user_id, token, ttl_seconds)
        return token

    async def rotate_refresh_token(self, old_token: str, user_id: int, ttl_seconds: int) -> str:
        used_ttl = min(60, ttl_seconds)
        await self._set(old_token, self._used_token_value(user_id), used_ttl)
        return await self.add_refresh_token(user_id, ttl_seconds)

    async def add_password_reset_token(self, user_id: int, ttl_seconds: int) -> str:
        token = str(uuid.uuid4())
        await self.add(token, user_id, ttl_seconds)
        return token

    async def consume_password_reset_token(self, token: str) -> int | None:
        value = await self.get(token)
        if value is None or self._is_used_value(value):
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
        key = self._user_index_key(user_id)
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

    async def mark_refresh_token_replayed(self, token: str) -> None:
        value = await self.get(token)
        if value is None or self._is_used_value(value):
            return
        user_id = int(value)
        await self._set(token, self._used_token_value(user_id), 60)

    def _access_index_key(self, user_id: int) -> str:
        return f"{self.prefix}:access-by-user:{user_id}"

    async def track_access_token(self, user_id: int, jti: str, ttl_seconds: int) -> None:
        key = self._access_index_key(user_id)
        try:
            await redis_client.sadd(key, jti)
            await redis_client.expire(key, ttl_seconds)
        except Exception as exc:
            logger.warning("token_store_redis_unavailable",
                           extra={"operation": "track_access_token", "error": str(exc)})
            if settings.environment == "dev":
                self._memory_store.setdefault(key, set()).add(jti)
            else:
                raise TokenStoreUnavailableError("Redis unavailable")

    async def revoke_all_access_tokens_for_user(self, user_id: int) -> None:
        key = self._access_index_key(user_id)
        try:
            jtis = await redis_client.smembers(key)
        except Exception:
            jtis = self._memory_store.get(key, set())
        for jti in jtis:
            await self.revoke_jti(jti)
