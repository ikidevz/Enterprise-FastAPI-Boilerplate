import re
from datetime import datetime
from typing import Generic, TypeVar, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

T = TypeVar("T")
PASSWORD_PATTERN = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,}$")

UserRole = Literal["user", "staff", "admin"]


def _validate_password_strength(password: str) -> str:
    if not PASSWORD_PATTERN.match(password):
        raise ValueError(
            "Password must be at least 8 characters and include uppercase, lowercase, number, and special character"
        )
    return password


class TimestampedModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    created_at: datetime | None = None
    updated_at: datetime | None = None


class PaginationMeta(BaseModel):
    page: int
    size: int
    total: int
    pages: int


class PaginatedResponse(TimestampedModel, Generic[T]):
    data: list[T]
    meta: PaginationMeta


class UserCreate(BaseModel):
    """Public self-registration payload."""
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    username: str = Field(min_length=3)
    password: str = Field(min_length=8)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return _validate_password_strength(value)


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    username: str | None = Field(default=None, min_length=3)
    password: str | None = Field(default=None, min_length=8)
    is_superuser: bool | None = None
    is_active: bool | None = None
    role: UserRole | None = None
    permissions: list[str] | None = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_password_strength(value)


class UserOut(TimestampedModel):
    id: int
    email: EmailStr
    username: str
    is_active: bool
    is_verified: bool
    is_superuser: bool
    role: str
    permissions: list[str]


class EmailVerificationRequest(BaseModel):
    email: EmailStr


class EmailVerificationConfirm(BaseModel):
    token: str = Field(min_length=1)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=1)
    new_password: str = Field(min_length=8)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        return _validate_password_strength(value)


class ProductCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Sample product",
                "description": "Example description",
                "price": 19.99,
            }
        }
    )

    name: str = Field(min_length=1)
    description: str | None = None
    price: float = Field(gt=0)


class ProductUpdate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Updated product",
                "price": 29.99,
            }
        }
    )

    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    price: float | None = Field(default=None, gt=0)


class ProductOut(TimestampedModel):
    id: int
    name: str
    description: str | None = None
    price: float


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class AdminUserRoleUpdate(BaseModel):
    role: UserRole | None = None
    permissions: list[str] | None = None
