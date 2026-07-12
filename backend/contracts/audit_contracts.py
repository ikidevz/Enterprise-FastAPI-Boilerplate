from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel


class AuditLogEntryOut(BaseModel):
    id: int
    actor_id: int | None = None
    actor_username: str | None = None
    action: str
    resource: str
    details: dict[str, object]
    request_id: str | None = None
    trace_id: str | None = None
    method: str | None = None
    path: str | None = None
    status_code: int | None = None
    success: bool
    error: str | None = None
    created_at: datetime
