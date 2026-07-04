from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

from backend.core.config import settings


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

    def send(self, *, to: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self.from_email
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)

        if self.use_ssl:
            with smtplib.SMTP_SSL(self.host, self.port) as server:
                if self.username and self.password:
                    server.login(self.username, self.password)
                server.sendmail(self.from_email, [to], message.as_string())
            return

        with smtplib.SMTP(self.host, self.port) as server:
            if self.use_tls:
                server.starttls()
            if self.username and self.password:
                server.login(self.username, self.password)
            server.sendmail(self.from_email, [to], message.as_string())


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


email_delivery_service = EmailDeliveryService()
