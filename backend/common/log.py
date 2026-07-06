import logging
from contextvars import ContextVar
from typing import Any

_request_context: ContextVar[dict[str, str] | None] = ContextVar(
    "request_context",
    default=None,
)


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = (
            getattr(record, "request_id", None)
            or get_request_id()
            or "-"
        )

        record.trace_id = (
            getattr(record, "trace_id", None)
            or get_trace_id()
            or "-"
        )

        return True


def get_request_id() -> str | None:
    context = _request_context.get()
    if context is None:
        return None
    return context.get("request_id")


def get_trace_id() -> str | None:
    context = _request_context.get()
    if context is None:
        return None
    return context.get("trace_id")


def bind_request_context(
    **values: str,
) -> Any:
    return _request_context.set(values)


def reset_request_context(
    token: Any,
) -> None:
    _request_context.reset(token)


LOG_FORMAT = (
    "%(asctime)s %(levelname)s %(name)s "
    "[request_id=%(request_id)s trace_id=%(trace_id)s] "
    "%(message)s"
)

logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT
)
logger = logging.getLogger("tier4")
logger.setLevel(logging.INFO)
logger.propagate = False
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(LOG_FORMAT)
    )
    logger.addHandler(handler)
logger.addFilter(RequestIdFilter())

root_logger = logging.getLogger()
for handler in root_logger.handlers:
    if not any(isinstance(existing_filter, RequestIdFilter) for existing_filter in handler.filters):
        handler.addFilter(RequestIdFilter())
