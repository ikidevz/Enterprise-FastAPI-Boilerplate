from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class UserContract(BaseModel):
    """Contract for the public user representation exposed by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    username: str
    is_active: bool
    is_verified: bool
    is_superuser: bool
    role: str
    permissions: list[str]
