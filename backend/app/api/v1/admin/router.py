from fastapi import APIRouter, Depends, HTTPException, Request, status

from backend.domain.users.model import User
from backend.domain.users.service import UserService
from backend.common.audit import audit_logger
from backend.common.dependencies import get_user_service
from backend.common.rbac import require_role
from backend.common.schema import UserOut

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=list[UserOut])
async def list_admin_users(
    request: Request,
    current_user: User = Depends(require_role("admin")),
    service: UserService = Depends(get_user_service),
) -> list[UserOut]:
    if not current_user.is_superuser and current_user.username != "admin":
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
