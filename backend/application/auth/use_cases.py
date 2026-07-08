from __future__ import annotations

from jose import jwt as jose_jwt

from backend.common.background_jobs import background_job_manager
from backend.infrastructure.email.transport import email_delivery_service
from backend.web.exceptions import ForbiddenError, NotFoundError, UnauthorizedError
from backend.observability.logging import logger
from backend.common.schema import (
    EmailVerificationConfirm,
    EmailVerificationRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
)
from backend.core.config import settings
from backend.core.security.dependencies import revocation_store
from backend.core.security.token_store import TokenStore
from backend.domain.users.service import UserService


token_store = TokenStore()
password_reset_store = TokenStore(prefix="tier4:password-reset")
email_verification_store = TokenStore(prefix="tier4:email-verification")


class LoginUseCase:
    def __init__(self, user_service: UserService, repository: object) -> None:
        self.user_service = user_service
        self.repository = repository

    async def execute(self, *, username: str, password: str) -> dict[str, object]:
        normalized_username = username.strip().lower()

        user = await self.user_service.authenticate(normalized_username, password)
        if not user:
            raise UnauthorizedError("Incorrect email or password")

        if settings.require_email_verification and not user.is_verified:
            raise ForbiddenError("Please verify your email before signing in")

        access_token = self.user_service.create_access_token(user)

        # Track issued access token so it can be revoked later.
        payload = jose_jwt.get_unverified_claims(access_token)
        await revocation_store.track_access_token(
            user.id,
            payload["jti"],
            settings.access_token_expire_minutes * 60,
        )

        ttl = settings.refresh_token_expire_days * 24 * 60 * 60
        refresh_token = await token_store.add_refresh_token(
            user.id,
            ttl_seconds=ttl,
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
        }


class RefreshTokenUseCase:
    def __init__(self, user_service: UserService, repository: object) -> None:
        self.user_service = user_service
        self.repository = repository

    async def execute(self, *, refresh_token: str) -> dict[str, object]:
        stored_value = await token_store.get(refresh_token)

        if not stored_value:
            raise UnauthorizedError("Invalid refresh token")

        # Detect replayed/used markers placed by TokenStore.rotate_refresh_token
        # (values like "used:123") and treat them as invalid.
        if (
            isinstance(stored_value, str)
            and stored_value.startswith(token_store.USED_TOKEN_PREFIX)
        ):
            raise UnauthorizedError("Invalid refresh token")

        user = await self.repository.get_by_id(int(stored_value))
        if not user:
            raise NotFoundError("user")

        access_token = self.user_service.create_access_token(user)

        # Track newly issued access token so it can be revoked later.
        payload = jose_jwt.get_unverified_claims(access_token)
        await revocation_store.track_access_token(
            user.id,
            payload["jti"],
            settings.access_token_expire_minutes * 60,
        )

        ttl = settings.refresh_token_expire_days * 24 * 60 * 60
        rotated_refresh_token = await token_store.rotate_refresh_token(
            refresh_token,
            user.id,
            ttl_seconds=ttl,
        )

        return {
            "access_token": access_token,
            "refresh_token": rotated_refresh_token,
            "token_type": "bearer",
        }


class RequestEmailVerificationUseCase:
    def __init__(self, repository: object) -> None:
        self.repository = repository

    async def execute(
        self,
        *,
        payload: EmailVerificationRequest,
    ) -> dict[str, str]:
        user = await self.repository.get_by_email(payload.email)

        if user:
            token = await email_verification_store.add_password_reset_token(
                user.id,
                ttl_seconds=15 * 60,
            )

            background_job_manager.enqueue(
                lambda: email_delivery_service.send_verification_email(
                    user.email,
                    token,
                )
            )

            background_job_manager.enqueue(
                lambda: logger.info(
                    "email_verification_requested",
                    extra={
                        "email": user.email,
                        "user_id": user.id,
                    },
                )
            )

        return {
            "detail": "If the account exists, a verification link has been sent",
        }


class ConfirmEmailVerificationUseCase:
    def __init__(self, repository: object, db: object) -> None:
        self.repository = repository
        self.db = db

    async def execute(
        self,
        *,
        payload: EmailVerificationConfirm,
    ) -> dict[str, str]:
        user_id = await email_verification_store.consume_password_reset_token(
            payload.token
        )

        if user_id is None:
            raise UnauthorizedError("Invalid or expired verification token")

        user = await self.repository.get_by_id(user_id)
        if not user:
            raise NotFoundError("user")

        service = UserService(self.repository)

        await service.mark_verified(user)
        await self.db.flush()
        await self.db.refresh(user)

        return {"detail": "Email verified successfully"}


class RequestPasswordResetUseCase:
    def __init__(self, repository: object) -> None:
        self.repository = repository

    async def execute(
        self,
        *,
        payload: PasswordResetRequest,
    ) -> dict[str, str]:
        user = await self.repository.get_by_email(payload.email)

        if user:
            reset_token = await password_reset_store.add_password_reset_token(
                user.id,
                ttl_seconds=settings.password_reset_token_ttl_minutes * 60,
            )

            background_job_manager.enqueue(
                lambda: email_delivery_service.send_password_reset_email(
                    user.email,
                    reset_token,
                )
            )

            background_job_manager.enqueue(
                lambda: logger.info(
                    "password_reset_requested",
                    extra={
                        "email": user.email,
                        "user_id": user.id,
                    },
                )
            )

        return {"detail": "If the account exists, a reset link has been sent"}


class ConfirmPasswordResetUseCase:
    def __init__(self, repository: object, db: object) -> None:
        self.repository = repository
        self.db = db

    async def execute(
        self,
        *,
        payload: PasswordResetConfirm,
    ) -> dict[str, str]:
        user_id = await password_reset_store.consume_password_reset_token(
            payload.token
        )

        if user_id is None:
            raise UnauthorizedError("Invalid or expired reset token")

        user = await self.repository.get_by_id(user_id)
        if not user:
            raise NotFoundError("user")

        service = UserService(self.repository)

        user.hashed_password = service.hash_password(payload.new_password)

        await self.db.flush()
        await self.db.refresh(user)

        # Revoke all refresh tokens.
        await token_store.revoke_all_for_user(user.id)

        # Revoke all active access tokens (audit finding fix).
        await revocation_store.revoke_all_access_tokens_for_user(user.id)

        return {"detail": "Password updated successfully"}
