from __future__ import annotations

import json
import logging
import logging.handlers
import asyncio
import hmac
import hashlib
from datetime import datetime, timezone
from typing import Any
from pathlib import Path
from fastapi import Request

from backend.domain.users.model import User
from backend.infrastructure.queue import job_queue
from backend.infrastructure.queue.registry import register_job_handler
from backend.observability.logging import get_request_id


class AuditLogger:
    def __init__(
        self,
        *,
        persist_path: str | None = None,
    ) -> None:
        self.logger = logging.getLogger("tier4.audit")

        self._persist_path = Path(persist_path or "logs/audit.jsonl")
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)

        self._file_logger = logging.getLogger("tier4.audit.file")
        self._file_logger.propagate = False
        self._file_logger.setLevel(logging.INFO)
        if not self._file_logger.handlers:
            handler = logging.handlers.RotatingFileHandler(
                self._persist_path,
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            handler.setFormatter(logging.Formatter("%(message)s"))
            self._file_logger.addHandler(handler)

    def _persist(self, entry: dict[str, Any]) -> None:
        try:
            self._file_logger.info(json.dumps(entry, default=str))
        except OSError as exc:
            self.logger.error(
                "audit_persist_failed",
                extra={"error": str(exc)},
            )

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
        actor_id = (
            getattr(actor, "id", None)
            if actor is not None and not isinstance(actor, str)
            else None
        )

        actor_username = (
            getattr(actor, "username", None)
            if actor is not None and not isinstance(actor, str)
            else actor
        )

        request_id = (
            request.state.request_id
            if request is not None and hasattr(request.state, "request_id")
            else get_request_id()
        )
        trace_id = (
            request.state.trace_id
            if request is not None and hasattr(request.state, "trace_id")
            else request_id
        )

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actor_id": actor_id,
            "actor_username": actor_username,
            "action": action,
            "resource": resource,
            "details": details or {},
            "request_id": request_id,
            "trace_id": trace_id,
            "method": request.method if request is not None else None,
            "path": request.url.path if request is not None else None,
            "status_code": status_code,
            "success": success,
            "error": error,
        }

        self.logger.info(
            "audit_event action=%s resource=%s success=%s",
            action,
            resource,
            success,
            extra={
                "request_id": entry["request_id"],
                "trace_id": entry.get("trace_id") or entry.get("request_id") or "-",
            },
        )

        try:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, self._persist, entry)
        except RuntimeError:
            # No running event loop (e.g. tests or CLI scripts).
            self._persist(entry)

        try:
            job_queue.enqueue("persist_audit_log_entry", entry)
        except Exception:
            self.logger.exception("audit_queue_enqueue_failed")
        return entry


@register_job_handler("persist_audit_log_entry")
async def persist_audit_log_entry(payload: dict[str, Any]) -> None:
    from backend.database import session as db_session
    from backend.domain.audit_log.model import AuditLogEntry

    entry = AuditLogEntry(
        actor_id=payload.get("actor_id"),
        actor_username=payload.get("actor_username"),
        action=payload.get("action", ""),
        resource=payload.get("resource", ""),
        details=payload.get("details") or {},
        request_id=payload.get("request_id"),
        trace_id=payload.get("trace_id"),
        method=payload.get("method"),
        path=payload.get("path"),
        status_code=payload.get("status_code"),
        success=payload.get("success", True),
        error=payload.get("error"),
    )
    async with db_session.SessionLocal() as db:
        db.add(entry)
        await db.flush()
        await db.commit()


audit_logger = AuditLogger()
