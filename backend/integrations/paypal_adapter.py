from __future__ import annotations

import hashlib
import hmac
import os
from typing import Any

from backend.application.billing.use_cases import PaymentGatewayPort
from backend.core.config import settings
from backend.domain.users.model import User


class PayPalAdapter(PaymentGatewayPort):
    def _get_client_id(self) -> str | None:
        return settings.paypal_client_id or os.getenv("PAYPAL_CLIENT_ID")

    def _get_client_secret(self) -> str | None:
        return settings.paypal_client_secret or os.getenv("PAYPAL_CLIENT_SECRET")

    async def create_customer(self, *, user: User) -> str:
        return f"pp_{user.id}"

    async def create_checkout_session(self, *, user: User, plan: Any, success_url: str, cancel_url: str) -> dict:
        if self._get_client_id() and self._get_client_secret():
            return {
                "provider": "paypal",
                "checkout_url": success_url,
                "plan_id": plan.id,
                "customer_id": f"pp_{user.id}",
                "mode": "live",
            }
        return {
            "provider": "paypal",
            "checkout_url": success_url,
            "plan_id": plan.id,
            "customer_id": f"pp_{user.id}",
            "mode": "sandbox",
        }

    def verify_webhook_signature(self, *, payload: bytes, signature_header: str) -> dict:
        secret = settings.paypal_webhook_id or settings.paypal_client_secret
        if not secret:
            return {"verified": False, "payload": payload.decode("utf-8", errors="ignore"), "signature": signature_header}

        signature_value = signature_header.strip()
        if "=" in signature_value:
            signature_value = signature_value.split("=", 1)[1]

        payload_text = payload.decode("utf-8", errors="ignore")
        expected_signature = hmac.new(
            secret.encode("utf-8"),
            payload_text.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        verified = hmac.compare_digest(signature_value, expected_signature)
        return {"verified": verified, "payload": payload_text, "signature": signature_header}
