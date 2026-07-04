from __future__ import annotations

import json
import os
from typing import Any

from backend.common.observability import get_metrics_snapshot
from backend.common.log import logger


class Exporter:
    def __init__(self, endpoint: str | None = None) -> None:
        self.endpoint = endpoint or os.getenv("EXPORTER_ENDPOINT")

    def export(self, payload: dict[str, Any]) -> None:
        if not self.endpoint:
            return
        try:
            logger.info("exporting_observability_payload", extra={
                        "endpoint": self.endpoint, "payload": payload})
        except Exception:
            return


metrics_exporter = Exporter()


def export_metrics() -> None:
    payload = {"metrics": get_metrics_snapshot(), "service": "tier4"}
    metrics_exporter.export(payload)
