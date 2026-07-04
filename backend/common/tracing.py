from __future__ import annotations

import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Iterator

from backend.common.log import logger

_span_context: ContextVar[dict[str, Any]] = ContextVar(
    "trace_span_context", default={}
)


@contextmanager
def trace_span(name: str, **attributes: Any) -> Iterator[None]:
    span_id = str(uuid.uuid4())[:8]
    parent = _span_context.get()
    span_context = {
        "name": name,
        "span_id": span_id,
        "parent_span_id": parent.get("span_id"),
        "attributes": dict(attributes),
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    token = _span_context.set(span_context)
    logger.info(
        "span_started",
        extra={"span_name": name, "span_id": span_id, "attributes": attributes},
    )
    try:
        yield
    finally:
        logger.info(
            "span_finished",
            extra={"span_name": name, "span_id": span_id,
                   "attributes": attributes},
        )
        _span_context.reset(token)
