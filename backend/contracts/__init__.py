"""Shared API contracts and schema boundaries for enterprise-style services."""

from backend.contracts.auth_contracts import (
    DetailResponse,
    TokenResponse
)
from backend.contracts.health_contracts import HealthResponse, MetricsResponse
from backend.contracts.products_contracts import ProductCreate, ProductOut, ProductUpdate
from backend.contracts.uploads_contracts import UploadResponse
from backend.contracts.users_contracts import (
    AdminUserRoleUpdate,
    UserCreate,
    UserOut,
    UserUpdate,
)

__all__ = [
    "AdminUserRoleUpdate",
    "DetailResponse",
    "HealthResponse",
    "MetricsResponse",
    "ProductCreate",
    "ProductOut",
    "ProductUpdate",
    "TokenResponse",
    "UploadResponse",
    "UserCreate",
    "UserOut",
    "UserUpdate",
]
