from __future__ import annotations

from typing import Protocol


class NotificationPort(Protocol):
    def send(self, *, to: str, subject: str, body: str) -> None:
        ...
