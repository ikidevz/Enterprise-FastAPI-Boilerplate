from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.domain.events import DomainEvent
from backend.domain.webhooks.model import WebhookDelivery, WebhookEndpoint
from backend.domain.webhooks.repository import WebhookDeliveryRepository, WebhookEndpointRepository
from backend.infrastructure.queue import job_queue
from backend.infrastructure.queue.registry import register_job_handler


class WebhookService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.endpoint_repository = WebhookEndpointRepository(db)
        self.delivery_repository = WebhookDeliveryRepository(db)

    async def create_endpoint(self, owner_id: int, payload: dict[str, Any]) -> WebhookEndpoint:
        endpoint = WebhookEndpoint(
            owner_id=owner_id,
            name=str(payload["name"]),
            url=str(payload["url"]),
            subscribed_events=payload.get("subscribed_events", []),
            signing_secret=payload.get(
                "signing_secret") or secrets.token_urlsafe(32),
            is_active=payload.get("is_active", True),
        )
        self.db.add(endpoint)
        await self.db.flush()
        await self.db.refresh(endpoint)
        return endpoint

    async def list_endpoints(self, owner_id: int) -> list[WebhookEndpoint]:
        return await self.endpoint_repository.list_for_owner(owner_id)

    async def revoke_endpoint(self, endpoint_id: int, owner_id: int) -> None:
        endpoint = await self.endpoint_repository.get_by_id(endpoint_id)
        if endpoint is None or endpoint.owner_id != owner_id:
            raise ValueError("endpoint not found")
        endpoint.is_active = False
        self.db.add(endpoint)
        await self.db.flush()

    async def list_deliveries(self, endpoint_id: int, owner_id: int) -> list[WebhookDelivery]:
        deliveries = await self.delivery_repository.list_for_endpoint(endpoint_id)
        endpoint = await self.endpoint_repository.get_by_id(endpoint_id)
        if endpoint is None or endpoint.owner_id != owner_id:
            raise ValueError("endpoint not found")
        return deliveries

    async def create_delivery(self, endpoint_id: int, event_type: str, payload: dict[str, Any]) -> WebhookDelivery:
        delivery = WebhookDelivery(
            endpoint_id=endpoint_id,
            event_type=event_type,
            payload=payload,
            attempt_count=0,
        )
        self.db.add(delivery)
        await self.db.flush()
        await self.db.refresh(delivery)
        return delivery

    async def dispatch(self, event: DomainEvent) -> None:
        active_endpoints = await self.endpoint_repository.get_active_for_event(
            event.payload.get("event_type", "")
        )
        for endpoint in active_endpoints:
            delivery = await self.create_delivery(
                endpoint.id,
                event.payload["event_type"],
                event.payload,
            )
            job_queue.enqueue("deliver_webhook", {"delivery_id": delivery.id})


@register_job_handler("deliver_webhook")
async def deliver_webhook(payload: dict[str, Any]) -> None:
    from backend.domain.webhooks.repository import WebhookDeliveryRepository
    from backend.infrastructure.webhooks.dispatcher import sign_webhook_payload
    from backend.database import session as db_session

    delivery_id = int(payload["delivery_id"])
    async with db_session.SessionLocal() as db:
        result = await db.execute(
            select(WebhookDelivery)
            .options(selectinload(WebhookDelivery.endpoint))
            .where(WebhookDelivery.id == delivery_id)
        )
        delivery = result.scalar_one_or_none()
        if delivery is None:
            return
        endpoint = delivery.endpoint
        if endpoint is None or not endpoint.is_active:
            return

        payload_data = delivery.payload
        headers = {
            "X-Signature": sign_webhook_payload(endpoint.signing_secret, payload_data)
        }
        import httpx

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(endpoint.url, json=payload_data, headers=headers)
            delivery.attempt_count += 1
            delivery.last_attempt_at = datetime.now(timezone.utc)
            delivery.last_status_code = response.status_code
            if 200 <= response.status_code < 300:
                delivery.delivered_at = datetime.now(timezone.utc)
            await db.flush()
            await db.commit()
            if response.status_code >= 300 and delivery.attempt_count < 3:
                job_queue.enqueue("deliver_webhook", {
                                  "delivery_id": delivery.id, "attempts": delivery.attempt_count})
        except Exception:
            delivery.attempt_count += 1
            delivery.last_attempt_at = datetime.now(timezone.utc)
            await db.flush()
            await db.commit()
            if delivery.attempt_count < 3:
                job_queue.enqueue("deliver_webhook", {
                                  "delivery_id": delivery.id, "attempts": delivery.attempt_count})
