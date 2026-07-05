"""Email transport selection and message formatting.

This doesn't send any real email - CaptureTransport (see conftest.py)
just records what would have been sent so we can check the content.
"""
from conftest import CaptureTransport
from backend.common import email as email_module
from backend.common.email import EmailDeliveryService


def test_password_reset_and_verification_emails_contain_the_right_tokens() -> None:
    transport = CaptureTransport()
    service = EmailDeliveryService(transport=transport)

    service.send_password_reset_email("user@example.com", "reset-token-123")
    service.send_verification_email("user@example.com", "verify-token-456")

    assert len(transport.calls) == 2
    assert transport.calls[0]["to"] == "user@example.com"
    assert "reset-token-123" in transport.calls[0]["body"]
    assert "verify-token-456" in transport.calls[1]["body"]


def test_console_backend_is_the_default() -> None:
    """Local dev should never accidentally try to send real email."""
    from backend.common.email import ConsoleEmailTransport

    service = EmailDeliveryService()

    assert isinstance(service.transport, ConsoleEmailTransport)


def test_smtp_backend_is_used_when_explicitly_configured(monkeypatch) -> None:
    monkeypatch.setattr(email_module.settings, "email_backend", "smtp")

    service = EmailDeliveryService()

    assert isinstance(service.transport, email_module.SMTPEmailTransport)
