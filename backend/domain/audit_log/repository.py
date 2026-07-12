from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.base_repository import BaseRepository
from backend.domain.audit_log.model import AuditLogEntry


class AuditLogRepository(BaseRepository[AuditLogEntry, object, object]):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, AuditLogEntry)

    async def search(
        self,
        actor_id: int | None = None,
        action: str | None = None,
        resource: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        success: bool | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[AuditLogEntry], int]:
        stmt = select(AuditLogEntry)
        filters: list[Any] = []
        if actor_id is not None:
            filters.append(AuditLogEntry.actor_id == actor_id)
        if action:
            filters.append(AuditLogEntry.action == action)
        if resource:
            filters.append(AuditLogEntry.resource == resource)
        if since is not None:
            filters.append(AuditLogEntry.created_at >= since)
        if until is not None:
            filters.append(AuditLogEntry.created_at <= until)
        if success is not None:
            filters.append(AuditLogEntry.success.is_(success))
        if filters:
            stmt = stmt.where(*filters)

        count_stmt = select(func.count()).select_from(AuditLogEntry)
        if filters:
            count_stmt = count_stmt.where(*filters)

        total = int((await self.db.execute(count_stmt)).scalar_one())
        result = await self.db.execute(
            stmt.order_by(AuditLogEntry.created_at.desc()
                          ).offset(skip).limit(limit)
        )
        return list(result.scalars().all()), total
