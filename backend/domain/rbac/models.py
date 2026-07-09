from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("key", name="uq_roles_key"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_system: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(
        timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    permissions: Mapped[list["RolePermission"]] = relationship(
        back_populates="role", cascade="all, delete-orphan")


class Permission(Base):
    __tablename__ = "permissions"
    __table_args__ = (UniqueConstraint("key", name="uq_permissions_key"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(
        timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    role_links: Mapped[list["RolePermission"]] = relationship(
        back_populates="permission", cascade="all, delete-orphan")


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id"), primary_key=True)
    permission_id: Mapped[int] = mapped_column(
        ForeignKey("permissions.id"), primary_key=True)

    role: Mapped[Role] = relationship(back_populates="permissions")
    permission: Mapped[Permission] = relationship(back_populates="role_links")


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), primary_key=True)
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id"), primary_key=True)
