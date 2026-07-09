from fastapi import APIRouter, Depends, HTTPException, Request, status

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


class BulkRoleUpdatePayload(dict):
    pass


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
    return {"subscriptions_enabled": settings.subscriptions_enabled}


@router.patch("/users/roles", response_model=list[UserOut])
async def bulk_set_user_roles(
    request: Request,
    payload: dict[str, list[dict[str, object]]],
    current_user: User = Depends(require_role("admin")),
    service: UserService = Depends(get_user_service),
) -> list[UserOut]:
    updates = payload.get("updates", [])
    if not isinstance(updates, list):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="updates must be a list")

    changed: list[UserOut] = []
    for entry in updates:
        if not isinstance(entry, dict):
            continue
        user_id = entry.get("user_id")
        if not isinstance(user_id, int):
            continue
        user = await service.get_by_id(user_id)
        if not user:
            continue

        before = {"role": user.role, "permissions": list(user.permissions)}
        if entry.get("role") is not None:
            role_value = entry.get("role")
            role_service = RbacService(service.repository.db)
            allowed_roles = {role.key for role in await role_service.list_roles()}
            if role_value not in allowed_roles:
                if not isinstance(role_value, str) or not role_value:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid role")
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid role")
            user.role = role_value
        if entry.get("permissions") is not None:
            permissions_value = entry.get("permissions")
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
