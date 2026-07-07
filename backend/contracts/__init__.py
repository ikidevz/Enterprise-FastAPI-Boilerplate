"""Shared API contracts and schema boundaries for enterprise-style services."""

from backend.contracts.auth_contracts import (
    DetailResponse,
    EmailVerificationConfirm,
    EmailVerificationRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshTokenRequest,
    TokenResponse,
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
    "EmailVerificationConfirm",
    "EmailVerificationRequest",
    "HealthResponse",
    "MetricsResponse",
    "PasswordResetConfirm",
    "PasswordResetRequest",
    "ProductCreate",
    "ProductOut",
    "ProductUpdate",
    "RefreshTokenRequest",
    "TokenResponse",
    "UploadResponse",
    "UserCreate",
    "UserOut",
    "UserUpdate",
]
