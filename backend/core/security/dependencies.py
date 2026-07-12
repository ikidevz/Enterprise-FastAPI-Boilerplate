from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.database.session import get_db
from backend.domain.api_keys.repository import ApiKeyRepository
from backend.domain.api_keys.service import ApiKeyService
from backend.domain.users.repository import UserRepository
from backend.domain.users.service import UserService
from backend.core.security.token_store import TokenStore

security = HTTPBearer(auto_error=False)
revocation_store = TokenStore(prefix="tier4:revocations")


async def get_current_user(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
):
    if x_api_key is not None:
        api_key_repository = ApiKeyRepository(db)
        api_key_service = ApiKeyService(api_key_repository)
        api_key = await api_key_service.authenticate(x_api_key)
        if api_key is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
            )
        user = await UserRepository(db).get_by_id(int(api_key.owner_id))
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
            )
        user.api_key_scopes = api_key.scopes or []
        user.api_key_id = api_key.id
        return user

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.secret_key,
                             algorithms=[settings.algorithm])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    user_id = payload.get("sub")
    jti = payload.get("jti")
    if not user_id or not jti:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    if await revocation_store.is_revoked(str(jti)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revoked")

    repository = UserRepository(db)
    user = await repository.get_by_id(int(user_id))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )
    return user


async def get_current_active_user(current_user=Depends(get_current_user)):
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
    return current_user


async def get_optional_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
):
    if credentials is None:
        return None

    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.secret_key,
                             algorithms=[settings.algorithm])
    except JWTError:
        return None

    user_id = payload.get("sub")
    jti = payload.get("jti")
    if not user_id or not jti:
        return None

    if await revocation_store.is_revoked(str(jti)):
        return None

    repository = UserRepository(db)
    user = await repository.get_by_id(int(user_id))
    if not user:
        return None
    return user


def get_user_service(db: AsyncSession = Depends(get_db)) -> UserService:
    return UserService(UserRepository(db))
