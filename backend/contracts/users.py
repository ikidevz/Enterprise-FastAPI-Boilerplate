from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class UserContract(BaseModel):
    """Contract for the public user representation exposed by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str | None = None
    is_active: bool = True
