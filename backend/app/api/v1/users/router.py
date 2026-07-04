from fastapi import Depends, Request, status

from backend.domain.users.model import User
from backend.domain.users.service import UserService
from backend.application.users import RegisterUserUseCase, UpdateUserUseCase
from backend.common.audit import audit_logger
from backend.common.base_router import BaseRouter
from backend.common.dependencies import get_current_active_user, get_user_service
from backend.common.exceptions import DomainError, NotFoundError, to_http_exception
from backend.common.schema import UserCreate, UserOut, UserUpdate

router = BaseRouter(prefix="/users", tags=["users"])


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


@router.get("/me", response_model=UserOut)
async def read_current_user(current_user: User = Depends(get_current_active_user)) -> UserOut:
    return UserService(None).to_public(current_user)


@router.get("/{user_id}", response_model=UserOut)
async def read_user(user_id: int, service: UserService = Depends(get_user_service)) -> UserOut:
    user = await service.get_by_id(user_id)
    if not user:
        raise to_http_exception(NotFoundError("user"))
    return service.to_public(user)


@router.get("/", response_model=list[UserOut])
async def list_users(service: UserService = Depends(get_user_service)) -> list[UserOut]:
    users = await service.list()
    return [service.to_public(user) for user in users]


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
            {"changes": payload.model_dump(exclude_unset=True)},
            request=request,
            status_code=status.HTTP_200_OK,
            success=True,
        )
        return updated
    except DomainError as exc:
        raise to_http_exception(exc) from exc


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(request: Request, user_id: int, service: UserService = Depends(get_user_service)) -> None:
    user = await service.get_by_id(user_id)
    if not user:
        raise to_http_exception(NotFoundError("user"))
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
