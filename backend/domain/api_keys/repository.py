from __future__ import annotations

from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.base_repository import BaseRepository
from backend.domain.api_keys.model import ApiKey


class ApiKeyRepository(BaseRepository[ApiKey, object, object]):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, ApiKey)

    async def get_by_prefix(self, prefix: str) -> ApiKey | None:
        result = await self.db.execute(select(ApiKey).where(ApiKey.key_prefix == prefix))
        return result.scalar_one_or_none()

    async def list_for_owner(self, owner_id: int, *, skip: int = 0, limit: int = 100) -> list[ApiKey]:
        result = await self.db.execute(
            select(ApiKey)
            .where(ApiKey.owner_id == owner_id)
            .where(ApiKey.revoked_at.is_(None))
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def revoke(self, api_key: ApiKey) -> None:
        api_key.revoked_at = datetime.now()
        self.db.add(api_key)
        await self.db.flush()

    async def touch_last_used(self, api_key: ApiKey) -> None:
        api_key.last_used_at = datetime.now()
        self.db.add(api_key)
        await self.db.flush()
