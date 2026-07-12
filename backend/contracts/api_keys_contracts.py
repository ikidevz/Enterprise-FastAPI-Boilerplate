from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class ApiKeyCreate(BaseModel):
    name: str
    scopes: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None


class ApiKeyCreated(BaseModel):
    id: int
    owner_id: int
    name: str
    key_prefix: str
    raw_secret: str
    scopes: list[str]
    expires_at: datetime | None = None
    created_at: datetime


class ApiKeyOut(BaseModel):
    id: int
    owner_id: int
    name: str
    key_prefix: str
    scopes: list[str]
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime
