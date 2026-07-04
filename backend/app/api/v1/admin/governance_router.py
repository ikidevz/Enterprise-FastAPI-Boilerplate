from fastapi import APIRouter, Depends, HTTPException, status

from backend.domain.users.model import User
from backend.common.audit import audit_logger
from backend.common.dependencies import get_current_active_user
from backend.common.permissions import PermissionPolicy, evaluate_permission

router = APIRouter(prefix="/admin", tags=["permissions"])


@router.get("/permissions")
async def permissions_example(current_user: User = Depends(get_current_active_user)) -> dict[str, object]:
    policy = PermissionPolicy(
        action="read", resource="admin", permission="read:admin")
    if not evaluate_permission(current_user, policy):
        audit_logger.log(current_user, "deny:permissions",
                         "admin", {"permission": policy.permission})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Missing required permission")
    audit_logger.log(current_user, "allow:permissions",
                     "admin", {"permission": policy.permission})
    return {"role": current_user.role, "permissions": current_user.permissions}
