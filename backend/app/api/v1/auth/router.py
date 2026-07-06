from fastapi import APIRouter, Depends, Request, status
from fastapi.security import OAuth2PasswordRequestForm, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from backend.application.auth import (
    ConfirmEmailVerificationUseCase,
    ConfirmPasswordResetUseCase,
    LoginUseCase,
    RefreshTokenUseCase,
    RequestEmailVerificationUseCase,
    RequestPasswordResetUseCase,
)
from backend.core.config import settings
from backend.common.audit import audit_logger
from backend.common.dependencies import get_current_active_user, security, revocation_store, get_current_active_user
from backend.common.exceptions import DomainError, UnauthorizedError, to_http_exception
from backend.common.schema import (
    EmailVerificationConfirm,
    EmailVerificationRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    UserOut,
    RefreshTokenRequest
)
from backend.common.opentelemetry import trace_span
from backend.database.session import get_db
from backend.domain.users.repository import UserRepository
from backend.domain.users.service import UserService
from backend.domain.users.model import User

from jose import jwt as jose_jwt


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", summary="Sign in", response_description="Access and refresh tokens")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    with trace_span("auth.login"):
        try:
            repository = UserRepository(db)
            service = UserService(repository)
            use_case = LoginUseCase(service, repository)
            result = await use_case.execute(username=form_data.username, password=form_data.password)
            audit_logger.log(
                None,
                "auth.login",
                "session",
                {"username": form_data.username},
                request=request,
                status_code=status.HTTP_200_OK,
                success=True,
            )
            return result
        except DomainError as exc:
            audit_logger.log(
                None,
                "auth.login_failed",
                "session",
                {"reason": str(exc)},
                request=request,
                status_code=status.HTTP_401_UNAUTHORIZED if "Incorrect" in str(
                    exc) else status.HTTP_403_FORBIDDEN,
                success=False,
            )
            raise to_http_exception(exc) from exc


@router.post("/refresh")
async def refresh_token(
    request: Request,
    payload: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    if not payload.refresh_token:
        raise to_http_exception(UnauthorizedError("Invalid refresh token"))
    try:
        repository = UserRepository(db)
        service = UserService(repository)
        use_case = RefreshTokenUseCase(service, repository)
        result = await use_case.execute(refresh_token=payload.refresh_token)
        audit_logger.log(
            None,
            "auth.refresh",
            "session",
            {"refresh_token_present": True},
            request=request,
            status_code=status.HTTP_200_OK,
            success=True,
        )
        return result
    except DomainError as exc:
        audit_logger.log(
            None,
            "auth.refresh_failed",
            "session",
            {"reason": str(exc)},
            request=request,
            status_code=status.HTTP_401_UNAUTHORIZED,
            success=False,
        )
        raise to_http_exception(exc) from exc


@router.post("/logout")
async def logout(
    request: Request,
    payload: RefreshTokenRequest,
    current_user: User = Depends(get_current_active_user),
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict[str, str]:
    from backend.application.auth import token_store
    await token_store.revoke(payload.refresh_token)
    access_payload = jose_jwt.decode(
        credentials.credentials, settings.secret_key, algorithms=[settings.algorithm])
    jti = access_payload.get("jti")
    if jti:
        await revocation_store.revoke_jti(jti)

    audit_logger.log(current_user, "auth.logout", "session", {},
                     request=request, status_code=status.HTTP_200_OK, success=True)
    return {"detail": "Logged out"}


@router.post("/email-verification/request", summary="Request email verification")
async def request_email_verification(payload: EmailVerificationRequest, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    repository = UserRepository(db)
    use_case = RequestEmailVerificationUseCase(repository)
    return await use_case.execute(payload=payload)


@router.post("/email-verification/confirm", summary="Confirm email verification")
async def confirm_email_verification(payload: EmailVerificationConfirm, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    repository = UserRepository(db)
    try:
        use_case = ConfirmEmailVerificationUseCase(repository, db)
        return await use_case.execute(payload=payload)
    except DomainError as exc:
        raise to_http_exception(exc) from exc


@router.post("/password-reset/request", summary="Request password reset")
async def request_password_reset(payload: PasswordResetRequest, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    repository = UserRepository(db)
    use_case = RequestPasswordResetUseCase(repository)
    return await use_case.execute(payload=payload)


@router.post("/password-reset/confirm")
async def confirm_password_reset(payload: PasswordResetConfirm, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    repository = UserRepository(db)
    try:
        use_case = ConfirmPasswordResetUseCase(repository, db)
        return await use_case.execute(payload=payload)
    except DomainError as exc:
        raise to_http_exception(exc) from exc


@router.get("/me", response_model=UserOut)
async def read_me(current_user=Depends(get_current_active_user)):
    return current_user
