from __future__ import annotations

from backend.application.ports import NotificationPort
from backend.web.exceptions import DuplicateResourceError, ForbiddenError, NotFoundError
from backend.observability.logging import logger
from backend.common.schema import UserCreate, UserOut, UserUpdate
from backend.domain.events import DomainEvent
from backend.domain.users.service import UserService
from backend.domain.billing.service import BillingService
from backend.domain.billing.models import Plan, Subscription
from sqlalchemy import select


class RegisterUserUseCase:
    def __init__(self, user_service: UserService, notification_port: NotificationPort | None = None) -> None:
        self.user_service = user_service
        self.notification_port = notification_port

    async def execute(self, *, payload: UserCreate) -> UserOut:
        if await self.user_service.repository.get_by_email(payload.email):
            raise DuplicateResourceError(
                "user", message="Email already registered")
        if await self.user_service.repository.get_by_username(payload.username):
            raise DuplicateResourceError(
                "user", message="Username already taken")

        user = await self.user_service.create(payload)
        free_plan = await self.user_service.repository.db.scalar(select(Plan).where(Plan.key == "free"))
        if free_plan is None:
            free_plan = Plan(
                key="free",
                name="Free",
                price_cents=0,
                billing_interval="month",
                is_active=True,
            )
            self.user_service.repository.db.add(free_plan)
            await self.user_service.repository.db.flush()

        existing_subscription = await self.user_service.repository.db.scalar(
            select(Subscription).where(
                Subscription.user_id == user.id,
                Subscription.plan_id == free_plan.id,
            )
        )
        if existing_subscription is None:
            self.user_service.repository.db.add(
                Subscription(
                    user_id=user.id,
                    plan_id=free_plan.id,
                    status="active",
                    provider="manual",
                )
            )
        event = DomainEvent.create({
            "event_type": "user.registered",
            "user_id": user.id,
            "email": user.email,
        })
        logger.info("domain_event", extra={"event": event.payload})
        from backend.infrastructure.runtime import platform_runtime

        await platform_runtime.event_bus.publish(event)
        if self.notification_port is not None:
            self.notification_port.send(
                to=user.email,
                subject="Welcome",
                body=f"Welcome {user.username}!",
            )
        return self.user_service.to_public(user)


class UpdateUserUseCase:
    def __init__(self, user_service: UserService) -> None:
        self.user_service = user_service

    async def execute(self, *, user_id: int, current_user: object, payload: UserUpdate) -> UserOut:
        user = await self.user_service.get_by_id(user_id)
        if not user:
            raise NotFoundError("user")
        if user.id != current_user.id and not current_user.is_superuser:
            raise ForbiddenError("Not authorized to update this user")

        if payload.email and payload.email != user.email:
            if await self.user_service.repository.get_by_email(payload.email):
                raise DuplicateResourceError(
                    "user", message="Email already registered")
        if payload.username and payload.username != user.username:
            if await self.user_service.repository.get_by_username(payload.username):
                raise DuplicateResourceError(
                    "user", message="Username already taken")

        if not current_user.is_superuser:
            update_data = payload.model_dump(exclude_unset=True)
            for field in ("is_superuser", "is_active", "role", "permissions"):
                update_data.pop(field, None)
            if not update_data:
                return self.user_service.to_public(user)
            safe_payload = UserUpdate(**update_data)
        else:
            safe_payload = payload

        updated = await self.user_service.update(user, safe_payload)
        return self.user_service.to_public(updated)
