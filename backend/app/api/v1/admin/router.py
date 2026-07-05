from fastapi import APIRouter, Depends, HTTPException, Request, status

from backend.domain.users.model import User
from backend.domain.users.service import UserService
from backend.common.audit import audit_logger
from backend.common.dependencies import get_user_service
from backend.common.exceptions import to_http_exception, NotFoundError
from backend.common.rbac import require_role
from backend.common.schema import UserOut, AdminUserRoleUpdate

router = APIRouter(prefix="/admin", tags=["admin"])


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

    audit_logger.log(
        actor=current_user,
        action="user.role_changed",
        resource=f"user:{user.id}",
        details={"before": before, "after": {
            "role": user.role, "permissions": list(user.permissions)}},
        request=request,
    )
    return service.to_public(user)
