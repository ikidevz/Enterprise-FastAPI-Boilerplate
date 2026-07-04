from backend.common import email as email_module
from backend.common.email import EmailDeliveryService


class CaptureTransport:
    def __init__(self) -> None:
        self.calls = []

    def send(self, *, to: str, subject: str, body: str) -> None:
        self.calls.append({"to": to, "subject": subject, "body": body})


def test_email_delivery_service_formats_password_reset_and_verification_messages() -> None:
    transport = CaptureTransport()
    service = EmailDeliveryService(transport=transport)

    service.send_password_reset_email("user@example.com", "reset-token")
    service.send_verification_email("user@example.com", "verify-token")

    assert len(transport.calls) == 2
    assert transport.calls[0]["to"] == "user@example.com"
    assert "reset-token" in transport.calls[0]["body"]
    assert "verify-token" in transport.calls[1]["body"]


def test_email_delivery_service_uses_smtp_transport_when_configured(monkeypatch) -> None:
    monkeypatch.setattr(email_module.settings, "email_backend", "smtp")
    service = EmailDeliveryService()
    assert isinstance(service.transport, email_module.SMTPEmailTransport)
