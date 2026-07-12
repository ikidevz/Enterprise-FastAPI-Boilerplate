from datetime import datetime

from fastapi import APIRouter, Depends, status

from backend.contracts.audit_contracts import AuditLogEntryOut
from backend.core.security.dependencies import get_db
from backend.core.security.rbac import require_permission
from backend.domain.users.model import User
from backend.domain.audit_log.repository import AuditLogRepository

router = APIRouter(prefix="/audit-log", tags=["audit_log"])


@router.get("/", response_model=list[AuditLogEntryOut])
async def list_audit_entries(
    actor_id: int | None = None,
    action: str | None = None,
    resource: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    success: bool | None = None,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(require_permission("audit.view")),
    db=Depends(get_db),
) -> list[AuditLogEntryOut]:
    repository = AuditLogRepository(db)
    entries, _ = await repository.search(
        actor_id=actor_id,
        action=action,
        resource=resource,
        since=since,
        until=until,
        success=success,
        skip=skip,
        limit=limit,
    )
    return [
        AuditLogEntryOut(
            id=entry.id,
            actor_id=entry.actor_id,
            actor_username=entry.actor_username,
            action=entry.action,
            resource=entry.resource,
            details=entry.details,
            request_id=entry.request_id,
            trace_id=entry.trace_id,
            method=entry.method,
            path=entry.path,
            status_code=entry.status_code,
            success=entry.success,
            error=entry.error,
            created_at=entry.created_at,
        )
        for entry in entries
    ]
