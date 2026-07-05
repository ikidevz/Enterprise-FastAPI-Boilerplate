from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.core.config import settings


def register_static_assets(app: FastAPI) -> None:
    if settings.upload_backend == "local":
        upload_dir = Path(settings.upload_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)
        app.mount("/static/uploads",
                  StaticFiles(directory=upload_dir), name="uploads")
