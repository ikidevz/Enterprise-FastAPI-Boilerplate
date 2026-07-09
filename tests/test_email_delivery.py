from conftest import CaptureTransport
from backend.core.config import settings
from backend.infrastructure.email.transport import EmailDeliveryService


def test_password_reset_and_verification_emails_contain_the_right_tokens() -> None:
    """Ensures password reset and verification emails contain the right tokens."""
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
    from backend.infrastructure.email.transport import ConsoleEmailTransport

    service = EmailDeliveryService()

    assert isinstance(service.transport, ConsoleEmailTransport)


def test_smtp_backend_is_used_when_explicitly_configured(monkeypatch) -> None:
    """Ensures smtp backend is used when explicitly configured."""
    from backend.infrastructure.email.transport import SMTPEmailTransport
    monkeypatch.setattr(settings, "email_backend", "smtp")

    service = EmailDeliveryService()

    assert isinstance(service.transport, SMTPEmailTransport)


def test_billing_event_email_uses_a_templated_subject_and_body() -> None:
    """Billing emails should include a clear subject and the relevant plan context."""
    transport = CaptureTransport()
    service = EmailDeliveryService(transport=transport)

    service.send_billing_event_email(
        to="billing@example.com",
        event_type="subscription_assigned",
        plan_name="Pro",
    )

    assert len(transport.calls) == 1
    assert transport.calls[0]["subject"] == "Your billing plan is now active"
    assert "Pro" in transport.calls[0]["body"]
