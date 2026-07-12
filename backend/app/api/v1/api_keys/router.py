from fastapi import APIRouter, Depends, HTTPException, Request, status

from backend.application.api_keys.use_cases import ApiKeyUseCases
from backend.contracts.api_keys_contracts import ApiKeyCreate, ApiKeyCreated, ApiKeyOut
from backend.core.security.dependencies import get_current_active_user, get_db
from backend.domain.users.model import User
from backend.web.exceptions import DomainError, NotFoundError, to_http_exception

router = APIRouter(prefix="/api-keys", tags=["api_keys"])


@router.post("/", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    request: Request,
    payload: ApiKeyCreate,
    current_user: User = Depends(get_current_active_user),
    db=Depends(get_db),
) -> ApiKeyCreated:
    try:
        use_case = ApiKeyUseCases(db)
        api_key, raw_secret = await use_case.issue_key(
            current_user,
            payload.name,
            payload.scopes,
            expires_at=payload.expires_at,
        )
        return ApiKeyCreated(
            id=api_key.id,
            owner_id=api_key.owner_id,
            name=api_key.name,
            key_prefix=api_key.key_prefix,
            raw_secret=raw_secret,
            scopes=api_key.scopes,
            expires_at=api_key.expires_at,
            created_at=api_key.created_at,
        )
    except DomainError as exc:
        raise to_http_exception(exc) from exc


@router.get("/", response_model=list[ApiKeyOut])
async def list_api_keys(
    current_user: User = Depends(get_current_active_user),
    db=Depends(get_db),
) -> list[ApiKeyOut]:
    use_case = ApiKeyUseCases(db)
    keys = await use_case.list_keys(current_user)
    return [
        ApiKeyOut(
            id=key.id,
            owner_id=key.owner_id,
            name=key.name,
            key_prefix=key.key_prefix,
            scopes=key.scopes,
            expires_at=key.expires_at,
            last_used_at=key.last_used_at,
            revoked_at=key.revoked_at,
            created_at=key.created_at,
        )
        for key in keys
    ]


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: int,
    current_user: User = Depends(get_current_active_user),
    db=Depends(get_db),
) -> None:
    try:
        use_case = ApiKeyUseCases(db)
        await use_case.revoke_key(key_id, current_user)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DomainError as exc:
        raise to_http_exception(exc) from exc
