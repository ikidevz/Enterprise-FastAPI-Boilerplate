"""Domain events for enterprise-style cross-cutting behavior."""

import uuid
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
            event_id=f"evt-{uuid.uuid4()}",
            occurred_at=datetime.now(timezone.utc),
            payload=payload,
        )
