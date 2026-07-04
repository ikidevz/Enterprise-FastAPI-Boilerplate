"""Domain events for enterprise-style cross-cutting behavior."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class DomainEvent:
    """Base type for domain events."""

    event_id: str
    occurred_at: datetime
    payload: dict[str, Any]

    @classmethod
    def create(cls, payload: dict[str, Any]) -> "DomainEvent":
        return cls(
            event_id="evt-" +
            str(abs(hash(payload.get("event_type", "domain-event")))).replace("-", ""),
            occurred_at=datetime.now(timezone.utc),
            payload=payload,
        )
