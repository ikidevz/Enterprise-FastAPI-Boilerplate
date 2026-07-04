from __future__ import annotations

from contextvars import ContextVar
from typing import Any

_context_store: ContextVar[dict[str, Any]] = ContextVar(
    "application_context", default={}
)


def set_context_value(key: str, value: Any) -> None:
    state = dict(_context_store.get())
    state[key] = value
    _context_store.set(state)


def get_context_value(key: str, default: Any = None) -> Any:
    return _context_store.get().get(key, default)


def clear_context() -> None:
    _context_store.set({})
