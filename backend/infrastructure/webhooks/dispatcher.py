from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from backend.domain.events import DomainEvent, EventBus
from backend.database import session as db_session
from backend.application.webhooks.service import WebhookService


def sign_webhook_payload(secret: str, payload: dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    signature = hmac.new(secret.encode("utf-8"),
                         body.encode("utf-8"), hashlib.sha256)
    return signature.hexdigest()


def subscribe_webhook_dispatcher(event_bus: EventBus) -> None:
    async def handle_event(event: DomainEvent) -> None:
        current_db = db_session.get_current_db_session()
        if current_db is not None:
            service = WebhookService(current_db)
            await service.dispatch(event)
            return

        async with db_session.SessionLocal() as db:
            service = WebhookService(db)
            await service.dispatch(event)

    event_bus.subscribe("*", handle_event)
