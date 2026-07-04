from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ProductContract(BaseModel):
    """Contract for the public product representation exposed by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    price: float
