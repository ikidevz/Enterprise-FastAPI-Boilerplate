from __future__ import annotations

import asyncio
import httpx
import os
from typing import Any

from backend.observability.metrics import get_metrics_snapshot
from backend.observability.logging import logger

_background_tasks: set[asyncio.Task] = set()


class Exporter:
    def __init__(self, endpoint: str | None = None) -> None:
        self.endpoint = endpoint or os.getenv("EXPORTER_ENDPOINT")

    async def export(self, payload: dict[str, Any]) -> None:
        if not self.endpoint:
            return
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                await client.post(self.endpoint, json=payload)
        except Exception:
            logger.warning("metrics_export_failed", extra={
                           "endpoint": self.endpoint})


metrics_exporter = Exporter()


def export_metrics() -> None:
    payload = {"metrics": get_metrics_snapshot(), "service": "tier4"}
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(metrics_exporter.export(payload))
    else:
        task = asyncio.get_running_loop().create_task(metrics_exporter.export(payload))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
