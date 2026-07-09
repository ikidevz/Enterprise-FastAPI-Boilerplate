from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

from backend.core.config import settings
from backend.resilience.retry import CircuitBreaker, CircuitBreakerOpenError
from backend.observability.logging import logger


class EmailTransport(Protocol):
    def send(self, *, to: str, subject: str, body: str) -> None:
        ...


class ConsoleEmailTransport:
    def send(self, *, to: str, subject: str, body: str) -> None:
        print(f"[email] to={to} subject={subject}\n{body}")


class SMTPEmailTransport:
    def __init__(self) -> None:
        self.host = settings.smtp_host or "localhost"
        self.port = settings.smtp_port
        self.username = settings.smtp_username
        self.password = settings.smtp_password
        self.use_tls = settings.smtp_use_tls
        self.use_ssl = settings.smtp_use_ssl
        self.from_email = settings.smtp_from_email
        self._breaker = CircuitBreaker(failure_threshold=3, reset_timeout=60.0)

    def send(self, *, to: str, subject: str, body: str) -> None:
        self._breaker.before_call()
        message = EmailMessage()
        message["From"] = self.from_email
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)

        try:
            if self.use_ssl:
                with smtplib.SMTP_SSL(self.host, self.port) as server:
                    if self.username and self.password:
                        server.login(self.username, self.password)
                    server.sendmail(self.from_email, [to], message.as_string())
            else:
                with smtplib.SMTP(self.host, self.port) as server:
                    if self.use_tls:
                        server.starttls()
                    if self.username and self.password:
                        server.login(self.username, self.password)
                    server.sendmail(self.from_email, [to], message.as_string())
        except CircuitBreakerOpenError:
            logger.error("smtp_circuit_open_skipping_send", extra={"to": to})
            raise
        except Exception as exc:
            self._breaker.record_failure()
            logger.error("smtp_send_failed", extra={
                         "to": to, "error": str(exc)})
            raise
        else:
            self._breaker.record_success()


@dataclass
class EmailDeliveryService:
    transport: EmailTransport | None = None

    def __post_init__(self) -> None:
        if self.transport is None:
            backend = getattr(settings, "email_backend", "console").lower()
            if backend == "smtp":
                self.transport = SMTPEmailTransport()
            else:
                self.transport = ConsoleEmailTransport()

    def send_password_reset_email(self, to: str, token: str) -> None:
        self.transport.send(
            to=to,
            subject="Password reset requested",
            body=(
                "A password reset was requested for your account.\n"
                f"Use this token to complete the reset: {token}"
            ),
        )

    def send_verification_email(self, to: str, token: str) -> None:
        self.transport.send(
            to=to,
            subject="Verify your email address",
            body=(
                "Please verify your email address to activate your account.\n"
                f"Use this token to confirm your email: {token}"
            ),
        )

    def send_billing_event_email(self, *, to: str, event_type: str, plan_name: str | None = None) -> None:
        subject_map = {
            "subscription_assigned": "Your billing plan is now active",
            "plan_changed": "Your billing plan has been updated",
            "payment_failed": "We need to update your billing details",
        }
        body_map = {
            "subscription_assigned": (
                "Your subscription is active and ready to use."
                + (f" Plan: {plan_name}." if plan_name else "")
            ),
            "plan_changed": (
                "Your billing plan has been updated."
                + (f" New plan: {plan_name}." if plan_name else "")
            ),
            "payment_failed": (
                "We could not process your most recent payment."
                + (f" Plan: {plan_name}." if plan_name else "")
            ),
        }
        subject = subject_map.get(event_type, "Billing update")
        body = body_map.get(
            event_type, f"A billing update is available for your account. Plan: {plan_name or 'your current plan'}.")
        self.transport.send(to=to, subject=subject, body=body)


email_delivery_service = EmailDeliveryService()
