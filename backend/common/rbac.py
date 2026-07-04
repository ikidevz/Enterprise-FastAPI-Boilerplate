from collections.abc import Callable

from fastapi import Depends, HTTPException, status

from backend.common.dependencies import get_current_active_user
from backend.domain.users.model import User


class AuthorizationPolicy:
    def __init__(self, *, required_roles: tuple[str, ...] = (), required_permissions: tuple[str, ...] = ()) -> None:
        self.required_roles = required_roles
        self.required_permissions = required_permissions

    def allows(self, user: User) -> bool:
        if user.is_superuser:
            return True
        if self.required_roles and user.username not in self.required_roles:
            return False
        if self.required_permissions and not set(self.required_permissions).issubset(set(user.permissions or [])):
            return False
        return True


def require_role(*roles: str) -> Callable[..., object]:
    async def dependency(current_user: User = Depends(get_current_active_user)) -> User:
        if not current_user.is_superuser and current_user.username not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return current_user

    return dependency


def require_policy(policy: AuthorizationPolicy) -> Callable[..., object]:
    async def dependency(current_user: User = Depends(get_current_active_user)) -> User:
        if not policy.allows(current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return current_user

    return dependency
