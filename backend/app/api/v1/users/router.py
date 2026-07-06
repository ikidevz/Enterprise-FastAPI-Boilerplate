from fastapi import APIRouter, Depends, Request, status

from backend.domain.users.model import User
from backend.domain.users.service import UserService
from backend.application.users import RegisterUserUseCase, UpdateUserUseCase
from backend.common.audit import audit_logger
from backend.common.dependencies import get_current_active_user, get_user_service
from backend.common.exceptions import DomainError, NotFoundError, to_http_exception, ForbiddenError
from backend.common.rbac import require_role
from backend.common.schema import UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])

SENSITIVE_FIELDS = {"password"}


def _safe_changes(payload) -> dict:
    changes = payload.model_dump(exclude_unset=True)
    return {
        key: ("***redacted***" if key in SENSITIVE_FIELDS else value)
        for key, value in changes.items()
    }


@router.get("/", response_model=list[UserOut])
async def list_users(
    request: Request,
    current_user: User = Depends(require_role("admin")),
    service: UserService = Depends(get_user_service),
) -> list[UserOut]:
    users = await service.list()

    audit_logger.log(
        actor=current_user,
        action="user.list_viewed",
        resource="users",
        details={"count": len(users)},
        request=request,
    )

    return [service.to_public(user) for user in users]


@router.get("/{user_id}", response_model=UserOut)
async def read_user(
    user_id: int,
    current_user: User = Depends(get_current_active_user),
    service: UserService = Depends(get_user_service),
) -> UserOut:
    user = await service.get_by_id(user_id)
    if not user:
        raise to_http_exception(NotFoundError("user"))
    if user_id != current_user.id and not current_user.is_superuser:
        raise to_http_exception(ForbiddenError(
            "Not authorized to view this user"))
    return service.to_public(user)


@router.post("/", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(request: Request, payload: UserCreate, service: UserService = Depends(get_user_service)) -> UserOut:
    try:
        use_case = RegisterUserUseCase(service)
        user = await use_case.execute(payload=payload)
        audit_logger.log(
            None,
            "user.created",
            "users",
            {"email": payload.email, "username": payload.username},
            request=request,
            status_code=status.HTTP_201_CREATED,
            success=True,
        )
        return user
    except DomainError as exc:
        raise to_http_exception(exc) from exc


@router.put("/{user_id}", response_model=UserOut)
async def update_user(
    request: Request,
    user_id: int,
    payload: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    service: UserService = Depends(get_user_service),
) -> UserOut:
    try:
        use_case = UpdateUserUseCase(service)
        updated = await use_case.execute(user_id=user_id, current_user=current_user, payload=payload)
        audit_logger.log(
            current_user,
            "user.updated",
            f"users:{user_id}",
            {"changes": _safe_changes(payload)},
            request=request,
            status_code=status.HTTP_200_OK,
            success=True,
        )
        return updated
    except DomainError as exc:
        raise to_http_exception(exc) from exc


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    request: Request,
    user_id: int,
    current_user: User = Depends(get_current_active_user),
    service: UserService = Depends(get_user_service),
) -> None:
    user = await service.get_by_id(user_id)
    if not user:
        raise to_http_exception(NotFoundError("user"))
    if user.id != current_user.id and not current_user.is_superuser:
        raise to_http_exception(ForbiddenError(
            "Not authorized to delete this user"))
    await service.delete(user)
    audit_logger.log(
        None,
        "user.deleted",
        f"users:{user_id}",
        {"email": user.email},
        request=request,
        status_code=status.HTTP_204_NO_CONTENT,
        success=True,
    )
