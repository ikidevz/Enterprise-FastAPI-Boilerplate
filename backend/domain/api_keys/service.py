from __future__ import annotations
from backend.domain.users.model import User
from backend.domain.api_keys.repository import ApiKeyRepository
from backend.domain.api_keys.model import ApiKey

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timezone
from typing import Any

import importlib

bcrypt = None
try:
    bcrypt = importlib.import_module("bcrypt")
except Exception:
    bcrypt = None


class ApiKeyService:
    def __init__(self, repository: ApiKeyRepository):
        self.repository = repository

    async def issue(
        self,
        owner: User,
        name: str,
        scopes: list[str] | None = None,
        expires_at: datetime | None = None,
    ) -> tuple[ApiKey, str]:
        raw_secret = secrets.token_urlsafe(32)
        if bcrypt is not None:
            hashed_secret = bcrypt.hashpw(raw_secret.encode(
                "utf-8"), bcrypt.gensalt()).decode("utf-8")
        else:
            salt = hashlib.sha256(os.urandom(16)).hexdigest().encode("utf-8")
            digest = hashlib.pbkdf2_hmac(
                "sha256", raw_secret.encode("utf-8"), salt, 100_000)
            hashed_secret = "pbkdf2_sha256$100000$" + \
                salt.decode("utf-8") + "$" + digest.hex()
        key_prefix = raw_secret[:8]
        api_key = ApiKey(
            owner_id=owner.id,
            name=name,
            key_prefix=key_prefix,
            hashed_secret=hashed_secret,
            scopes=scopes or [],
            expires_at=expires_at,
        )
        self.repository.db.add(api_key)
        await self.repository.db.flush()
        await self.repository.db.refresh(api_key)
        return api_key, raw_secret

    async def authenticate(self, raw_key: str) -> ApiKey | None:
        prefix = raw_key[:8]
        api_key = await self.repository.get_by_prefix(prefix)
        if api_key is None:
            return None
        if api_key.revoked_at is not None:
            return None
        if api_key.expires_at is not None and api_key.expires_at <= datetime.now(timezone.utc):
            return None
        if bcrypt is not None:
            if not bcrypt.checkpw(raw_key.encode("utf-8"), api_key.hashed_secret.encode("utf-8")):
                return None
        else:
            if not api_key.hashed_secret.startswith("pbkdf2_sha256$"):
                return None
            try:
                _, iterations, salt, expected = api_key.hashed_secret.split(
                    "$", 3)
                iterations = int(iterations)
                derived = hashlib.pbkdf2_hmac(
                    "sha256",
                    raw_key.encode("utf-8"),
                    salt.encode("utf-8"),
                    iterations,
                )
            except Exception:
                return None
            if not hmac.compare_digest(derived.hex(), expected):
                return None
        await self.repository.touch_last_used(api_key)
        return api_key

    async def revoke(self, api_key: ApiKey) -> None:
        await self.repository.revoke(api_key)
