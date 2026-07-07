from __future__ import annotations

import collections
import json
import logging
from datetime import datetime, timezone
from typing import Any
from pathlib import Path
from fastapi import Request

from backend.domain.users.model import User
from backend.observability.logging import get_request_id


class AuditLogger:
    def __init__(self, *, max_entries: int = 10_000, persist_path: str | None = None) -> None:
        self.entries: collections.deque = collections.deque(maxlen=max_entries)
        self.logger = logging.getLogger("tier4.audit")

        self._persist_path = Path(persist_path or "logs/audit.jsonl")
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)

    def clear(self) -> None:
        self.entries.clear()

    def log(
        self,
        actor: User | str | None,
        action: str,
        resource: str,
        details: dict[str, Any] | None = None,
        *,
        request: Request | None = None,
        status_code: int | None = None,
        success: bool = True,
        error: str | None = None,
    ) -> dict[str, Any]:
        actor_id = getattr(actor, "id", None) if actor is not None and not isinstance(
            actor, str) else None
        actor_username = getattr(
            actor, "username", None) if actor is not None and not isinstance(actor, str) else actor

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actor_id": actor_id,
            "actor_username": actor_username,
            "action": action,
            "resource": resource,
            "details": details or {},
            "request_id": request.state.request_id if request is not None and hasattr(request.state, "request_id") else get_request_id(),
            "method": request.method if request is not None else None,
            "path": request.url.path if request is not None else None,
            "status_code": status_code,
            "success": success,
            "error": error,
        }
        self.entries.append(entry)
        self.logger.info(
            "audit_event action=%s resource=%s success=%s",
            action,
            resource,
            success,
            extra={
                "request_id": entry["request_id"],
                "trace_id": entry.get("request_id") if entry.get("request_id") else "-",
            },
        )
        try:
            with self._persist_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, default=str) + "\n")
        except OSError as exc:
            self.logger.error("audit_persist_failed",
                              extra={"error": str(exc)})

        return entry


audit_logger = AuditLogger()
