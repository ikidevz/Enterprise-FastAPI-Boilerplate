"""Domain events for enterprise-style cross-cutting behavior."""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable


EventHandler = Callable[["DomainEvent"], Awaitable[None]]


@dataclass(slots=True)
class DomainEvent:
    """Base type for domain events."""

    event_id: str
    occurred_at: datetime
    payload: dict[str, Any]

    @classmethod
    def create(cls, payload: dict[str, Any]) -> "DomainEvent":
        return cls(
            event_id=f"evt-{uuid.uuid4()}",
            occurred_at=datetime.now(timezone.utc),
            payload=payload,
        )


class EventBus:
    """Simple in-process event bus for domain events."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = {}

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    async def publish(self, event: DomainEvent) -> None:
        event_type = event.payload.get("event_type", "")
        for handler in self._handlers.get(event_type, []) + self._handlers.get("*", []):
            await handler(event)
