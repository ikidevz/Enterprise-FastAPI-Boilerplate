from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.base_repository import BaseRepository
from backend.domain.webhooks.model import WebhookDelivery, WebhookEndpoint


class WebhookEndpointRepository(BaseRepository[WebhookEndpoint, object, object]):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, WebhookEndpoint)

    async def get_active_for_event(self, event_type: str) -> list[WebhookEndpoint]:
        result = await self.db.execute(
            select(WebhookEndpoint).where(WebhookEndpoint.is_active.is_(True))
        )
        endpoints = result.scalars().all()
        return [endpoint for endpoint in endpoints if event_type in (endpoint.subscribed_events or [])]

    async def list_for_owner(self, owner_id: int, *, skip: int = 0, limit: int = 100) -> list[WebhookEndpoint]:
        result = await self.db.execute(
            select(WebhookEndpoint)
            .where(
                WebhookEndpoint.owner_id == owner_id,
                WebhookEndpoint.is_active.is_(True),
            )
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())


class WebhookDeliveryRepository(BaseRepository[WebhookDelivery, object, object]):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, WebhookDelivery)

    async def list_for_endpoint(self, endpoint_id: int, *, skip: int = 0, limit: int = 100) -> list[WebhookDelivery]:
        result = await self.db.execute(
            select(WebhookDelivery)
            .where(WebhookDelivery.endpoint_id == endpoint_id)
            .order_by(WebhookDelivery.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())
