from __future__ import annotations

from backend.application.ports import NotificationPort
from backend.common.exceptions import DuplicateResourceError, ForbiddenError, NotFoundError
from backend.common.log import logger
from backend.common.schema import UserCreate, UserOut, UserUpdate
from backend.domain.events import DomainEvent
from backend.domain.users.service import UserService


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
        event = DomainEvent.create({
            "event_type": "user.registered",
            "user_id": user.id,
            "email": user.email,
        })
        logger.info("domain_event", extra={"event": event.payload})
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
