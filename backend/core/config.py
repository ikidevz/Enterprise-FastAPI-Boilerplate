import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, List, Literal

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ALLOWED_ENVIRONMENTS = {"dev", "staging", "prod"}


def _parse_string_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        if value.startswith("["):
            try:
                import json

                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            except Exception:
                pass
        return [item.strip() for item in value.split(",") if item.strip()]
    return [str(value)]


def _resolve_secret_path(path_value: str | None) -> str | None:
    if not path_value:
        return None
    path = Path(path_value)
    if path.is_absolute():
        return str(path)
    secrets_dir = os.getenv("SECRETS_DIR")
    if secrets_dir:
        candidate = Path(secrets_dir) / path_value
        if candidate.exists():
            return str(candidate)
    return path_value


def _read_secret_value(value: str | None, file_field: str | None) -> str | None:
    if file_field:
        path = Path(_resolve_secret_path(file_field) or file_field)
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    if value:
        return value
    return None


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _normalize_env_list_settings() -> None:
    cors_origins = os.getenv("CORS_ORIGINS")
    if cors_origins and not cors_origins.startswith("["):
        values = [item.strip()
                  for item in cors_origins.split(",") if item.strip()]
        os.environ["CORS_ORIGINS"] = json.dumps(values)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore")

    project_name: str = Field(default="Tier 4 Architecture")
    api_v1_str: str = Field(default="/api/v1")
    environment: str = Field(default="dev")
    app_env: str = Field(
        default="dev", validation_alias=AliasChoices("APP_ENV", "app_env"))
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/tier4",
        validation_alias=AliasChoices("DATABASE_URL", "database_url"),
    )
    database_url_file: str | None = Field(default=None, validation_alias=AliasChoices(
        "DATABASE_URL_FILE", "database_url_file"))
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        validation_alias=AliasChoices("REDIS_URL", "redis_url"),
    )
    redis_url_file: str | None = Field(
        default=None, validation_alias=AliasChoices("REDIS_URL_FILE", "redis_url_file"))
    secret_key: str = Field(
        default="change-me-in-production",
        validation_alias=AliasChoices("SECRET_KEY", "secret_key"),
    )
    secret_key_file: str | None = Field(
        default=None, validation_alias=AliasChoices("SECRET_KEY_FILE", "secret_key_file"))
    algorithm: str = Field(default="HS256")
    access_token_expire_minutes: int = Field(default=60 * 24)
    cors_origins: List[str] = Field(default_factory=lambda: [
                                    "http://localhost:3000", "http://localhost:5173"])
    enable_rate_limiting: bool = Field(default=True)
    rate_limit_requests_per_minute: int = Field(default=120)
    request_id_header: str = Field(default="x-request-id")
    max_request_size_bytes: int = Field(default=2 * 1024 * 1024)
    require_email_verification: bool = Field(default=False)
    upload_dir: str = Field(default="./uploads")
    upload_backend: Literal["local", "s3", "azure"] = Field(
        default="local",
        validation_alias=AliasChoices("UPLOAD_BACKEND", "upload_backend"),
    )
    s3_bucket: str | None = Field(
        default=None,
        validation_alias=AliasChoices("S3_BUCKET", "s3_bucket"),
    )
    s3_region: str | None = Field(
        default=None,
        validation_alias=AliasChoices("S3_REGION", "s3_region"),
    )
    s3_access_key_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("S3_ACCESS_KEY_ID", "s3_access_key_id"),
    )
    s3_secret_access_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "S3_SECRET_ACCESS_KEY", "s3_secret_access_key"),
    )
    s3_endpoint_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("S3_ENDPOINT_URL", "s3_endpoint_url"),
    )
    azure_storage_connection_string: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "AZURE_STORAGE_CONNECTION_STRING", "azure_storage_connection_string"),
    )
    azure_storage_container: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "AZURE_STORAGE_CONTAINER", "azure_storage_container"),
    )
    password_reset_token_ttl_minutes: int = Field(default=15)
    email_backend: str = Field(default="console", validation_alias=AliasChoices(
        "EMAIL_BACKEND", "email_backend"))
    smtp_host: str | None = Field(
        default=None, validation_alias=AliasChoices("SMTP_HOST", "smtp_host"))
    smtp_port: int = Field(
        default=587, validation_alias=AliasChoices("SMTP_PORT", "smtp_port"))
    smtp_username: str | None = Field(
        default=None, validation_alias=AliasChoices("SMTP_USERNAME", "smtp_username"))
    smtp_password: str | None = Field(
        default=None, validation_alias=AliasChoices("SMTP_PASSWORD", "smtp_password"))
    smtp_use_tls: bool = Field(
        default=True, validation_alias=AliasChoices("SMTP_USE_TLS", "smtp_use_tls"))
    smtp_use_ssl: bool = Field(
        default=False, validation_alias=AliasChoices("SMTP_USE_SSL", "smtp_use_ssl"))
    smtp_from_email: str = Field(default="no-reply@example.com",
                                 validation_alias=AliasChoices("SMTP_FROM_EMAIL", "smtp_from_email"))
    default_admin_email: str = Field(default="admin@example.com")
    default_admin_username: str = Field(default="admin")
    default_admin_password: str = Field(default="Admin123!")
    require_https: bool = Field(default=False)
    enable_tracing: bool = Field(default=True)
    trust_proxy_headers: bool = Field(default=False)
    otel_mode: str = Field(
        default="basic", validation_alias=AliasChoices("OTEL_MODE", "otel_mode"))
    otel_exporter_otlp_endpoint: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "OTEL_EXPORTER_OTLP_ENDPOINT", "otel_exporter_otlp_endpoint"),
    )
    otel_service_name: str = Field(default="tier4", validation_alias=AliasChoices(
        "OTEL_SERVICE_NAME", "otel_service_name"))

    refresh_token_expire_days: int = Field(default=7)

    @field_validator("environment", "app_env")
    @classmethod
    def validate_environment(cls, value: str) -> str:
        normalized = value.lower().strip()
        if normalized not in ALLOWED_ENVIRONMENTS:
            raise ValueError(
                f"environment must be one of {sorted(ALLOWED_ENVIRONMENTS)}")
        return normalized

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            if value.startswith("["):
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if str(item).strip()]
                except Exception:
                    pass
            return [item.strip() for item in value.split(",") if item.strip()]
        return [str(value)]

    @model_validator(mode="after")
    def _reject_insecure_prod_defaults(self) -> "Settings":
        if self.environment == "prod":
            if self.secret_key == "change-me-in-production":
                raise ValueError(
                    "SECRET_KEY must be set to a real secret in production")
            if self.default_admin_password == "Admin123!":
                raise ValueError(
                    "DEFAULT_ADMIN_PASSWORD must be changed in production")
        return self

    @model_validator(mode="after")
    def _validate_upload_backend_configuration(self) -> "Settings":
        if self.upload_backend == "s3":
            missing = [
                name for name in (
                    "s3_bucket",
                    "s3_access_key_id",
                    "s3_secret_access_key",
                )
                if not getattr(self, name)
            ]
            if missing:
                raise ValueError(
                    f"S3 upload backend requires {', '.join(missing)}"
                )
        if self.upload_backend == "azure":
            missing = [
                name for name in (
                    "azure_storage_connection_string",
                    "azure_storage_container",
                )
                if not getattr(self, name)
            ]
            if missing:
                raise ValueError(
                    f"Azure upload backend requires {', '.join(missing)}"
                )
        return self

    @model_validator(mode="after")
    def _reject_wildcard_origin_with_credentials(self) -> "Settings":
        if "*" in self.cors_origins:
            raise ValueError(
                "CORS_ORIGINS cannot include '*' while credentials are allowed")
        return self


@lru_cache
def get_settings() -> Settings:
    _normalize_env_list_settings()
    environment = os.getenv("ENVIRONMENT") or os.getenv("APP_ENV") or "dev"
    env_file = os.getenv("ENV_FILE")
    env_paths = []
    if env_file:
        env_paths.append(Path(env_file))
    env_paths.extend([
        Path(".env"),
        Path(f".env.{environment}"),
        Path(f".env.{environment}.local"),
        Path(".env.local"),
    ])
    for env_path in env_paths:
        _load_env_file(env_path)

    settings = Settings()
    if settings.environment != settings.app_env:
        settings.app_env = settings.environment
    settings.database_url = _read_secret_value(
        settings.database_url, settings.database_url_file) or settings.database_url
    settings.redis_url = _read_secret_value(
        settings.redis_url, settings.redis_url_file) or settings.redis_url
    settings.secret_key = _read_secret_value(
        settings.secret_key, settings.secret_key_file) or settings.secret_key
    settings.cors_origins = _parse_string_list(settings.cors_origins)
    return settings


settings = get_settings()
