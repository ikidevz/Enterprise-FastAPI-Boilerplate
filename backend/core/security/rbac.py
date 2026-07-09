from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.security.dependencies import get_current_active_user, get_db
from backend.domain.rbac.service import RbacService
from backend.domain.users.model import User


class AuthorizationPolicy:
    def __init__(self, *, required_roles: tuple[str, ...] = (), required_permissions: tuple[str, ...] = ()) -> None:
        self.required_roles = required_roles
        self.required_permissions = required_permissions

    def allows(self, user: User, db: AsyncSession | None = None) -> bool:
        if user.is_superuser:
            return True
        if self.required_roles and user.role not in self.required_roles:
            return False
        if self.required_permissions:
            permissions = set(user.permissions or [])
            if self.required_permissions and all(permission in permissions for permission in self.required_permissions):
                return True
            return False
        return True


def require_role(*roles: str) -> Callable[..., object]:
    async def dependency(current_user: User = Depends(get_current_active_user)) -> User:
        if not current_user.is_superuser and current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": "insufficient_permission",
                        "required_permission": "role:" + ",".join(roles)},
            )
        return current_user
    return dependency


def require_permission(*permission_keys: str) -> Callable[..., object]:
    async def dependency(
        current_user: User = Depends(get_current_active_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        service = RbacService(db)
        if not await service.user_has_all_permissions(current_user, list(permission_keys)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": "insufficient_permission", "required_permission": permission_keys[0] if len(
                    permission_keys) == 1 else list(permission_keys)},
            )
        return current_user

    return dependency


def require_policy(policy: AuthorizationPolicy) -> Callable[..., object]:
    async def dependency(
        current_user: User = Depends(get_current_active_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        if not await policy.allows(current_user, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": "insufficient_permission", "required_permission":
                        policy.required_permissions[0] if policy.required_permissions else "policy"},
            )
        return current_user

    return dependency
