from pathlib import Path

import pytest

from backend.core.config import get_settings


def test_settings_resolve_secret_from_a_file_and_from_a_profile_env_file(
    tmp_path: Path, monkeypatch
) -> None:
    """This mirrors how a real deployment would supply secrets: a mounted file
    plus a profile-specific .env, rather than plaintext values in the shell.
    """
    profile_env_file = tmp_path / ".env.staging"
    profile_env_file.write_text("SECRET_KEY=from-profile\n", encoding="utf-8")

    database_url_secret_file = tmp_path / "database_url.txt"
    database_url_secret_file.write_text(
        "postgresql+asyncpg://staging:secret@localhost:5432/app\n", encoding="utf-8"
    )

    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("ENV_FILE", str(profile_env_file))
    monkeypatch.setenv("SECRETS_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL_FILE", "database_url.txt")
    monkeypatch.setenv("DEFAULT_ADMIN_PASSWORD", "StrongTestAdminPw123!")
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test,http://b.test")

    get_settings.cache_clear()
    try:
        settings = get_settings()

        assert settings.database_url == "postgresql+asyncpg://staging:secret@localhost:5432/app"
        assert settings.secret_key == "from-profile"
        assert settings.cors_origins == ["http://a.test", "http://b.test"]
    finally:
        get_settings.cache_clear()


def test_staging_profile_can_use_a_non_default_admin_password(monkeypatch) -> None:
    """Staging settings should accept a supplied admin password without tripping the insecure-default guard."""
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("SECRET_KEY", "from-env")
    monkeypatch.setenv("DEFAULT_ADMIN_PASSWORD", "StrongTestAdminPw123!")

    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.environment == "staging"
        assert settings.secret_key == "from-env"
        assert settings.default_admin_password == "StrongTestAdminPw123!"
    finally:
        get_settings.cache_clear()


def test_app_env_only_aliases_environment(monkeypatch) -> None:
    """APP_ENV must drive the effective environment when ENVIRONMENT is unset."""
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("SECRET_KEY", "from-env")
    monkeypatch.setenv("DEFAULT_ADMIN_PASSWORD", "StrongTestAdminPw123!")

    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.environment == "staging"
        assert settings.app_env == "staging"
    finally:
        get_settings.cache_clear()


def test_upload_backend_s3_requires_credentials(monkeypatch) -> None:
    """Ensures upload backend s3 requires credentials."""
    monkeypatch.setenv("UPLOAD_BACKEND", "s3")
    monkeypatch.setenv("S3_BUCKET", "my-bucket")
    monkeypatch.delenv("S3_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("S3_SECRET_ACCESS_KEY", raising=False)

    get_settings.cache_clear()
    with pytest.raises(ValueError, match="S3 upload backend requires"):
        get_settings()


def test_upload_backend_azure_requires_connection_string_and_container(
    monkeypatch,
) -> None:
    """Ensures upload backend azure requires connection string and container."""
    monkeypatch.setenv("UPLOAD_BACKEND", "azure")
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("AZURE_STORAGE_CONTAINER", raising=False)

    get_settings.cache_clear()
    with pytest.raises(ValueError, match="Azure upload backend requires"):
        get_settings()


def test_cors_origins_can_also_be_supplied_as_a_json_array(monkeypatch) -> None:
    """Ensures cors origins can also be supplied as a json array."""
    monkeypatch.setenv(
        "CORS_ORIGINS", '["http://json.test", "http://also-json.test"]')

    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.cors_origins == [
            "http://json.test", "http://also-json.test"]
    finally:
        get_settings.cache_clear()
