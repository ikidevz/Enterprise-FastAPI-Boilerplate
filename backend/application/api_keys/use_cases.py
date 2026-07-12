from __future__ import annotations

from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.api_keys.repository import ApiKeyRepository
from backend.domain.api_keys.service import ApiKeyService
from backend.domain.users.model import User
from backend.observability.audit import audit_logger


class ApiKeyUseCases:
    def __init__(self, db: AsyncSession):
        self.repository = ApiKeyRepository(db)
        self.service = ApiKeyService(self.repository)

    async def issue_key(self, owner: User, name: str, scopes: list[str], expires_at: datetime | None = None) -> tuple[object, str]:
        api_key, raw_secret = await self.service.issue(owner, name, scopes=scopes, expires_at=expires_at)
        audit_logger.log(owner, "api_key.created", "api_keys", {
                         "api_key_id": api_key.id}, success=True)
        return api_key, raw_secret

    async def list_keys(self, owner: User) -> list[object]:
        return await self.repository.list_for_owner(owner.id)

    async def revoke_key(self, key_id: int, owner: User) -> None:
        api_key = await self.repository.get_by_id(key_id)
        if api_key is None or api_key.owner_id != owner.id:
            raise ValueError("api key not found")
        await self.service.revoke(api_key)
        audit_logger.log(owner, "api_key.revoked", "api_keys", {
                         "api_key_id": api_key.id}, success=True)
