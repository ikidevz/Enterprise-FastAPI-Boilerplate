import asyncio
from pathlib import Path

from backend.core.config import get_settings


def test_background_job_manager_runs_enqueued_job() -> None:
    async def run_test() -> None:
        from backend.common.background_jobs import BackgroundJobManager

        manager = BackgroundJobManager()
        await manager.start()
        try:
            completed = {"value": False}

            def job() -> None:
                completed["value"] = True

            manager.enqueue(job)
            await asyncio.sleep(0.1)
            assert completed["value"] is True
        finally:
            await manager.stop()

    asyncio.run(run_test())


def test_settings_resolve_secret_files_and_profiles(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env.staging"
    env_file.write_text("SECRET_KEY=from-profile\n", encoding="utf-8")

    db_secret = tmp_path / "database_url.txt"
    db_secret.write_text(
        "postgresql+asyncpg://staging:secret@localhost:5432/app\n", encoding="utf-8")

    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("ENV_FILE", str(env_file))
    monkeypatch.setenv("SECRETS_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL_FILE", "database_url.txt")
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test,http://b.test")

    get_settings.cache_clear()
    settings = get_settings()

    assert settings.database_url == "postgresql+asyncpg://staging:secret@localhost:5432/app"
    assert settings.secret_key == "from-profile"
    assert settings.cors_origins == ["http://a.test", "http://b.test"]
