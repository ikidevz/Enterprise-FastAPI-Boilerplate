from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.rbac.models import Permission, Role, RolePermission, UserRole
from backend.domain.users.model import User


class RbacPermissionError(ValueError):
    pass


class RbacService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def ensure_seed_data(self) -> None:
        roles = [
            {"key": "user", "name": "User",
                "description": "Default user role", "is_system": True},
            {"key": "staff", "name": "Staff",
                "description": "Staff role", "is_system": True},
            {"key": "admin", "name": "Admin",
                "description": "Administrative role", "is_system": True},
        ]
        for payload in roles:
            existing = await self.db.scalar(select(Role).where(Role.key == payload["key"]))
            if existing is None:
                self.db.add(Role(**payload))

        permissions = [
            {"key": "rbac.manage", "name": "Manage RBAC"},
            {"key": "billing.manage", "name": "Manage Billing"},
            {"key": "system.billing_toggle", "name": "Toggle Billing System"},
        ]
        for payload in permissions:
            existing = await self.db.scalar(select(Permission).where(Permission.key == payload["key"]))
            if existing is None:
                self.db.add(Permission(**payload))
        await self.db.commit()

    async def create_role(self, *, key: str, name: str, description: str | None = None) -> Role:
        await self.ensure_seed_data()
        existing = await self.db.scalar(select(Role).where(Role.key == key))
        if existing is not None:
            return existing
        role = Role(key=key, name=name, description=description)
        self.db.add(role)
        await self.db.commit()
        await self.db.refresh(role)
        return role

    async def ensure_permission(self, *, key: str, name: str | None = None) -> Permission:
        await self.ensure_seed_data()
        permission = await self.db.scalar(select(Permission).where(Permission.key == key))
        if permission is None:
            permission = Permission(key=key, name=name or key)
            self.db.add(permission)
            await self.db.commit()
            await self.db.refresh(permission)
        return permission

    async def list_roles(self) -> list[Role]:
        await self.ensure_seed_data()
        result = await self.db.execute(select(Role).order_by(Role.id))
        return list(result.scalars().all())

    async def create_permission(self, *, key: str, name: str, description: str | None = None) -> Permission:
        await self.ensure_seed_data()
        existing = await self.db.scalar(select(Permission).where(Permission.key == key))
        if existing is not None:
            return existing
        permission = Permission(key=key, name=name, description=description)
        self.db.add(permission)
        await self.db.commit()
        await self.db.refresh(permission)
        return permission

    async def list_permissions(self) -> list[Permission]:
        await self.ensure_seed_data()
        result = await self.db.execute(select(Permission).order_by(Permission.id))
        return list(result.scalars().all())

    async def validate_grant_scope(self, acting_user: User, *, permission_ids: list[int]) -> None:
        if acting_user.is_superuser:
            return
        if not permission_ids:
            return
        result = await self.db.execute(select(Permission.key).where(Permission.id.in_(permission_ids)))
        permission_keys = {row[0] for row in result.all()}
        if permission_keys and not await self.user_has_all_permissions(acting_user, list(permission_keys)):
            raise RbacPermissionError(
                "acting user cannot grant the requested permissions")

    async def validate_role_assignment_scope(self, acting_user: User, *, role_ids: list[int]) -> None:
        if acting_user.is_superuser:
            return
        if not role_ids:
            return
        result = await self.db.execute(
            select(Permission.key)
            .join(RolePermission, Permission.id == RolePermission.permission_id)
            .where(RolePermission.role_id.in_(role_ids))
        )
        permission_keys = {row[0] for row in result.all()}
        if permission_keys and not await self.user_has_all_permissions(acting_user, list(permission_keys)):
            raise RbacPermissionError(
                "acting user cannot assign the requested role")

    async def set_role_permissions(self, *, role_id: int, permission_ids: list[int], acting_user: User | None = None) -> None:
        await self.ensure_seed_data()
        if acting_user is not None:
            await self.validate_grant_scope(acting_user, permission_ids=permission_ids)
        await self.db.execute(delete(RolePermission).where(RolePermission.role_id == role_id))
        for permission_id in permission_ids:
            self.db.add(RolePermission(role_id=role_id,
                        permission_id=permission_id))
        await self.db.commit()

    async def assign_roles_to_user(self, *, user_id: int, role_ids: list[int], acting_user: User | None = None) -> None:
        await self.ensure_seed_data()
        if acting_user is not None:
            await self.validate_role_assignment_scope(acting_user, role_ids=role_ids)
        await self.db.execute(delete(UserRole).where(UserRole.user_id == user_id))
        for role_id in role_ids:
            self.db.add(UserRole(user_id=user_id, role_id=role_id))
        await self.db.commit()

    async def can_assign_permission(self, acting_user: User, permission_key: str) -> bool:
        return await self.user_has_permission(acting_user, permission_key)

    async def validate_assignment_scope(self, acting_user: User, *, permission_keys: list[str]) -> None:
        for permission_key in permission_keys:
            if not await self.can_assign_permission(acting_user, permission_key):
                raise RbacPermissionError(
                    f"acting user cannot assign {permission_key}")

    async def ensure_admins_remain(self, *, role_id: int | None = None, user_id: int | None = None) -> None:
        if role_id is None and user_id is None:
            return
        admin_role = await self.db.scalar(select(Role).where(Role.key == "admin"))
        if admin_role is None:
            return
        if role_id is not None and role_id == admin_role.id:
            admin_assignments = await self.db.scalar(select(UserRole.user_id).where(UserRole.role_id == admin_role.id).limit(1))
            if admin_assignments is None:
                raise RbacPermissionError(
                    "cannot remove the last admin role assignment")
        if user_id is not None:
            user_roles = await self.db.execute(select(UserRole.role_id).where(UserRole.user_id == user_id))
            role_ids = {row[0] for row in user_roles.all()}
            if admin_role.id in role_ids and len(role_ids) == 1:
                raise RbacPermissionError(
                    "cannot remove the last admin role from a user")

    async def user_has_permission(self, user: User, permission_key: str) -> bool:
        await self.ensure_seed_data()
        if user.is_superuser:
            return True
        result = await self.db.execute(
            select(RolePermission.permission_id)
            .join(Permission)
            .join(Role)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user.id, Permission.key == permission_key)
        )
        return result.scalar_one_or_none() is not None

    async def user_has_all_permissions(self, user: User, permission_keys: list[str]) -> bool:
        for permission_key in permission_keys:
            if not await self.user_has_permission(user, permission_key):
                return False
        return True
