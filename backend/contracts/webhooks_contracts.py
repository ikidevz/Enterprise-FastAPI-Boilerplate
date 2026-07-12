from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel


class WebhookEndpointCreate(BaseModel):
    url: str
    subscribed_events: list[str] = []
    name: str
    is_active: bool = True


class WebhookEndpointOut(BaseModel):
    id: int
    owner_id: int
    name: str
    url: str
    subscribed_events: list[str]
    is_active: bool
    created_at: datetime


class WebhookDeliveryOut(BaseModel):
    id: int
    endpoint_id: int
    event_type: str
    payload: dict[str, object]
    attempt_count: int
    last_attempt_at: datetime | None = None
    last_status_code: int | None = None
    delivered_at: datetime | None = None
    created_at: datetime
