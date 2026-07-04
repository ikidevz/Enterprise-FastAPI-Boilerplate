import logging
from contextvars import ContextVar
from typing import Any

_request_id_context: ContextVar[str | None] = ContextVar(
    "request_id", default=None)


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = getattr(
            record, "request_id", None) or get_request_id() or "-"
        return True


def get_request_id() -> str | None:
    return _request_id_context.get()


def bind_request_context(**values: Any) -> Any:
    previous = dict(values)
    for key, value in values.items():
        previous[key] = value
    return _request_id_context.set(values.get("request_id"))


def reset_request_context(token: Any) -> None:
    _request_id_context.reset(token)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s [request_id=%(request_id)s] %(message)s",
)
logger = logging.getLogger("tier4")
logger.setLevel(logging.INFO)
logger.propagate = False
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s [request_id=%(request_id)s] %(message)s"
    ))
    logger.addHandler(handler)
logger.addFilter(RequestIdFilter())

root_logger = logging.getLogger()
for handler in root_logger.handlers:
    if not any(isinstance(existing_filter, RequestIdFilter) for existing_filter in handler.filters):
        handler.addFilter(RequestIdFilter())
