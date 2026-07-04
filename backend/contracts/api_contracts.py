from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    """Contract for the readiness and liveness health payload."""

    model_config = ConfigDict(str_strip_whitespace=True)

    status: str
    environment: str
    version: str


class MetricsResponse(BaseModel):
    """Contract for the application observability metrics payload."""

    status: str
    request_count: int = Field(default=0)
    status_codes: dict[str, int] = Field(default_factory=dict)
    methods: dict[str, int] = Field(default_factory=dict)
    paths: dict[str, int] = Field(default_factory=dict)
