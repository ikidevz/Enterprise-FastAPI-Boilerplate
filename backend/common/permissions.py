from __future__ import annotations

from dataclasses import dataclass, field

from backend.domain.users.model import User


@dataclass(frozen=True)
class PermissionPolicy:
    action: str
    resource: str
    permission: str
    required_groups: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PermissionContext:
    user: User
    resource: str | None = None
    owner_id: int | None = None


def evaluate_permission(user: User, policy: PermissionPolicy, context: PermissionContext | None = None) -> bool:
    if user.is_superuser:
        return True

    if policy.permission in user.permissions:
        return True

    if policy.required_groups and user.role in policy.required_groups:
        return True

    if context and context.resource == policy.resource and context.owner_id == user.id:
        return True

    return False


def get_permission_groups(user: User) -> list[str]:
    return [user.role] if user.role else []


def build_policy(action: str, resource: str, permission: str, required_groups: tuple[str, ...] = ()) -> PermissionPolicy:
    return PermissionPolicy(action=action, resource=resource, permission=permission, required_groups=required_groups)
