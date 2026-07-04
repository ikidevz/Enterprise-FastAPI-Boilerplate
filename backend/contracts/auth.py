from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class LoginResponseContract(BaseModel):
    """Contract for authentication responses returned by the login flow."""

    model_config = ConfigDict(from_attributes=True)

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int | None = None


class RefreshTokenResponseContract(BaseModel):
    """Contract for auth refresh responses."""

    model_config = ConfigDict(from_attributes=True)

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int | None = None
