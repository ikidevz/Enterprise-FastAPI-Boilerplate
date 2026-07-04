from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any


class BootstrapRegistry:
    def __init__(self) -> None:
        self._startup_hooks: list[Callable[[Any], Awaitable[None] | None]] = []
        self._shutdown_hooks: list[Callable[[
            Any], Awaitable[None] | None]] = []

    def register_startup_hook(self, hook: Callable[[Any], Awaitable[None] | None]) -> None:
        self._startup_hooks.append(hook)

    def register_shutdown_hook(self, hook: Callable[[Any], Awaitable[None] | None]) -> None:
        self._shutdown_hooks.append(hook)

    async def run_startup_hooks(self, app: Any) -> None:
        for hook in self._startup_hooks:
            result = hook(app)
            if hasattr(result, "__await__"):
                await result

    async def run_shutdown_hooks(self, app: Any) -> None:
        for hook in self._shutdown_hooks:
            result = hook(app)
            if hasattr(result, "__await__"):
                await result
