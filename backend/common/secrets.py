from __future__ import annotations

import os
from pathlib import Path
from typing import Any


class SecretResolver:
    def __init__(self, secrets_dir: str | None = None) -> None:
        self.secrets_dir = secrets_dir or os.getenv(
            "SECRETS_DIR", "/run/secrets")

    def resolve(self, value: Any, *, env_name: str | None = None) -> str | None:
        if value in (None, ""):
            return None
        if isinstance(value, Path):
            value = str(value)
        if isinstance(value, str):
            if env_name and os.getenv(env_name):
                return os.getenv(env_name)
            secret_path = Path(self.secrets_dir) / value
            if secret_path.exists():
                return secret_path.read_text(encoding="utf-8").strip()
            if value.startswith("/") and Path(value).exists():
                return Path(value).read_text(encoding="utf-8").strip()
        return str(value)


def get_secret(value: Any, *, env_name: str | None = None) -> str | None:
    return SecretResolver().resolve(value, env_name=env_name)
