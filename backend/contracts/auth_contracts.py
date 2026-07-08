from __future__ import annotations

from pydantic import BaseModel


class TokenResponse(BaseModel):
    """Contract for auth token responses."""

    access_token: str
    refresh_token: str
    token_type: str


class DetailResponse(BaseModel):
    """Contract for endpoints that return a simple detail message."""

    detail: str


class PasswordPolicyResponse(BaseModel):
    """Contract for password policy metadata exposed to clients."""

    min_length: int
    require_uppercase: bool
    require_lowercase: bool
    require_number: bool
    require_special_character: bool
