from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.security.dependencies import get_current_active_user, get_db
from backend.core.security.rbac import require_permission
from backend.domain.rbac.service import RbacPermissionError, RbacService
from backend.domain.users.model import User
from backend.observability.audit import audit_logger

router = APIRouter(tags=["rbac"])


@router.post("/admin/roles", status_code=status.HTTP_201_CREATED)
async def create_role(
    request: Request,
    payload: dict[str, str],
    current_user: User = Depends(require_permission("rbac.manage")),
    db: AsyncSession = Depends(get_db),
):
    service = RbacService(db)
    role = await service.create_role(key=payload["key"], name=payload.get("name", payload["key"]))
    audit_logger.log(current_user, "rbac.role_created", "rbac", {
                     "role_id": role.id, "key": role.key}, request=request)
    return {"id": role.id, "key": role.key, "name": role.name}


@router.post("/admin/permissions", status_code=status.HTTP_201_CREATED)
async def create_permission(
    request: Request,
    payload: dict[str, str],
    current_user: User = Depends(require_permission("rbac.manage")),
    db: AsyncSession = Depends(get_db),
):
    service = RbacService(db)
    permission = await service.create_permission(key=payload["key"], name=payload.get("name", payload["key"]))
    audit_logger.log(current_user, "rbac.permission_created", "rbac", {
                     "permission_id": permission.id, "key": permission.key}, request=request)
    return {"id": permission.id, "key": permission.key, "name": permission.name}


@router.put("/admin/roles/{role_id}/permissions")
async def set_role_permissions(
    role_id: int,
    payload: dict[str, list[int]],
    current_user: User = Depends(require_permission("rbac.manage")),
    db: AsyncSession = Depends(get_db),
):
    service = RbacService(db)
    try:
        await service.validate_assignment_scope(current_user, permission_keys=["rbac.manage"])
        await service.set_role_permissions(
            role_id=role_id,
            permission_ids=payload.get("permission_ids", []),
            acting_user=current_user,
        )
    except RbacPermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={
                            "error": "insufficient_permission", "required_permission": "rbac.manage"}) from exc
    return {"role_id": role_id, "permission_ids": payload.get("permission_ids", [])}


@router.post("/admin/users/{user_id}/roles")
async def assign_roles_to_user(
    user_id: int,
    payload: dict[str, list[int]],
    current_user: User = Depends(require_permission("rbac.manage")),
    db: AsyncSession = Depends(get_db),
):
    service = RbacService(db)
    try:
        await service.validate_assignment_scope(current_user, permission_keys=["rbac.manage"])
        await service.ensure_admins_remain(user_id=user_id)
        await service.assign_roles_to_user(
            user_id=user_id,
            role_ids=payload.get("role_ids", []),
            acting_user=current_user,
        )
    except RbacPermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={
                            "error": "insufficient_permission", "required_permission": "rbac.manage"}) from exc
    return {"user_id": user_id, "role_ids": payload.get("role_ids", [])}


@router.get("/rbac/check-permission")
async def check_permission(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    service = RbacService(db)
    allowed = await service.user_has_permission(current_user, "reports.view")
    return {"allowed": allowed}
