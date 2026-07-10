from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import func, select

from backend.core.config import settings
from backend.domain.rbac.service import RbacService
from backend.domain.users.model import User
from backend.domain.users.service import UserService
from backend.observability.audit import audit_logger
from backend.core.security.dependencies import get_user_service
from backend.web.exceptions import to_http_exception, NotFoundError
from backend.core.security.rbac import require_permission, require_role
from backend.contracts.users_contracts import UserOut, AdminUserRoleUpdate

router = APIRouter(prefix="/admin", tags=["admin"])


class BulkRoleUpdateEntry(BaseModel):
    user_id: int | None = None
    role: str | None = None
    permissions: list[str] | None = None


class BulkRoleUpdatePayload(BaseModel):
    updates: list[BulkRoleUpdateEntry] = []


@router.get("/users", response_model=list[UserOut])
async def list_admin_users(
    request: Request,
    current_user: User = Depends(require_role("admin")),
    service: UserService = Depends(get_user_service),
) -> list[UserOut]:
    if not current_user.is_superuser and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Insufficient permissions")
    users = await service.list()
    audit_logger.log(
        current_user,
        "admin.users.listed",
        "admin/users",
        {"count": len(users)},
        request=request,
        status_code=status.HTTP_200_OK,
        success=True,
    )
    return [service.to_public(user) for user in users]

# app/api/v1/admin/router.py


@router.patch("/users/{user_id}/role", response_model=UserOut)
async def set_user_role(
    user_id: int,
    payload: AdminUserRoleUpdate,
    request: Request,
    current_user: User = Depends(require_role("admin")),
    service: UserService = Depends(get_user_service),
) -> UserOut:
    user = await service.get_by_id(user_id)
    if not user:
        raise to_http_exception(NotFoundError("user"))

    before = {"role": user.role, "permissions": list(user.permissions)}
    if payload.role is not None:
        if not isinstance(payload.role, str) or not payload.role:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid role")
        role_service = RbacService(service.repository.db)
        allowed_roles = {role.key for role in await role_service.list_roles()}
        if payload.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid role")
        if user.role == "admin" and payload.role != "admin":
            total_admins = await service.repository.db.scalar(
                select(func.count()).select_from(User).where(
                    User.role == "admin", User.deleted_at.is_(None)
                )
            )
            if total_admins == 1:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"error": "insufficient_permission",
                            "message": "Cannot remove the last admin role"},
                )
        user.role = payload.role
    if payload.permissions is not None:
        user.permissions = payload.permissions
    await service.repository.db.flush()
    await service.repository.db.refresh(user)

    audit_logger.log(
        actor=current_user,
        action="user.role_changed",
        resource=f"user:{user.id}",
        details={"before": before, "after": {
            "role": user.role, "permissions": list(user.permissions)}},
        request=request,
    )
    return service.to_public(user)


@router.patch("/system/subscriptions-enabled")
async def toggle_subscriptions_enabled(
    request: Request,
    payload: dict[str, bool],
    current_user: User = Depends(require_permission("system.billing_toggle")),
) -> dict[str, object]:
    if "subscriptions_enabled" in payload:
        settings.subscriptions_enabled = bool(payload.get(
            "subscriptions_enabled", settings.subscriptions_enabled))
        audit_logger.log(
            current_user,
            "system.subscriptions_toggled",
            "system",
            {"subscriptions_enabled": settings.subscriptions_enabled},
            request=request,
        )
    response = {"subscriptions_enabled": settings.subscriptions_enabled}
    if settings.environment != "dev":
        response["warning"] = "Billing toggles are process-local and not persisted across restarts or workers."
    return response


@router.patch("/users/roles", response_model=list[UserOut])
async def bulk_set_user_roles(
    request: Request,
    payload: BulkRoleUpdatePayload,
    current_user: User = Depends(require_role("admin")),
    service: UserService = Depends(get_user_service),
) -> list[UserOut]:
    updates = payload.updates

    total_admins = await service.repository.db.scalar(
        select(func.count()).select_from(User).where(
            User.role == "admin", User.deleted_at.is_(None)
        )
    )
    demotions = 0
    promotions = 0
    for entry in updates:
        user_id = entry.user_id
        if user_id is None:
            continue
        user = await service.get_by_id(user_id)
        if not user:
            continue
        if isinstance(entry.role, str) and entry.role != user.role:
            if user.role == "admin" and entry.role != "admin":
                demotions += 1
            if user.role != "admin" and entry.role == "admin":
                promotions += 1

    if total_admins - demotions + promotions < 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "insufficient_permission",
                    "message": "Cannot remove the last admin role"},
        )

    changed: list[UserOut] = []
    for entry in updates:
        user_id = entry.user_id
        if user_id is None:
            continue
        user = await service.get_by_id(user_id)
        if not user:
            continue

        before = {"role": user.role, "permissions": list(user.permissions)}
        if entry.role is not None:
            role_value = entry.role
            role_service = RbacService(service.repository.db)
            allowed_roles = {role.key for role in await role_service.list_roles()}
            if role_value not in allowed_roles:
                if not isinstance(role_value, str) or not role_value:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid role")
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid role")
            await role_service.ensure_admins_remain(user_id=user_id)
            user.role = role_value
        if entry.permissions is not None:
            permissions_value = entry.permissions
            if isinstance(permissions_value, list):
                user.permissions = [str(item) for item in permissions_value]
            else:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid permissions")
        await service.repository.db.flush()
        await service.repository.db.refresh(user)
        changed.append(
            UserOut(
                id=user.id,
                email=user.email,
                username=user.username,
                is_active=user.is_active,
                is_verified=user.is_verified,
                is_superuser=user.is_superuser,
                role=user.role,
                permissions=list(user.permissions or []),
                created_at=user.created_at,
                updated_at=user.updated_at,
            )
        )

        audit_logger.log(
            actor=current_user,
            action="user.role_changed",
            resource=f"user:{user.id}",
            details={"before": before, "after": {
                "role": user.role, "permissions": list(user.permissions)}},
            request=request,
        )

    return changed
