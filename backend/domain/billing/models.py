from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    price_cents: Mapped[int] = mapped_column(default=0, nullable=False)
    billing_interval: Mapped[str] = mapped_column(
        String(20), default="month", nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(
        timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class Feature(Base):
    __tablename__ = "features"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(
        timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class PlanFeature(Base):
    __tablename__ = "plan_features"

    plan_id: Mapped[int] = mapped_column(
        ForeignKey("plans.id"), primary_key=True)
    feature_id: Mapped[int] = mapped_column(
        ForeignKey("features.id"), primary_key=True)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("plans.id"), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default="active", nullable=False)
    provider: Mapped[str] = mapped_column(
        String(50), default="manual", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(
        timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
