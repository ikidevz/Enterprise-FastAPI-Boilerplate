from __future__ import annotations

from backend.common.email import email_delivery_service


class EmailIntegrationAdapter:
    def __init__(self, service=email_delivery_service) -> None:
        self.service = service

    def send(self, *, to: str, subject: str, body: str) -> None:
        self.service.transport.send(to=to, subject=subject, body=body)
