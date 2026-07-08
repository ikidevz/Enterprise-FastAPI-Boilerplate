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
