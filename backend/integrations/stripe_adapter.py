from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Any

from backend.application.billing.use_cases import PaymentGatewayPort
from backend.core.config import settings
from backend.domain.users.model import User


class StripeAdapter(PaymentGatewayPort):
    def _get_api_key(self) -> str | None:
        return settings.stripe_secret_key or os.getenv("STRIPE_SECRET_KEY")

    async def create_customer(self, *, user: User) -> str:
        return f"cus_{user.id}"

    async def create_checkout_session(self, *, user: User, plan: Any, success_url: str, cancel_url: str) -> dict:
        api_key = self._get_api_key()
        if api_key:
            return {
                "provider": "stripe",
                "checkout_url": success_url,
                "plan_id": plan.id,
                "customer_id": f"cus_{user.id}",
                "mode": "live",
            }
        return {
            "provider": "stripe",
            "checkout_url": success_url,
            "plan_id": plan.id,
            "customer_id": f"cus_{user.id}",
            "mode": "sandbox",
        }

    def verify_webhook_signature(self, *, payload: bytes, signature_header: str) -> dict:
        secret = settings.stripe_webhook_secret
        if not secret:
            return {"verified": False, "payload": payload.decode("utf-8", errors="ignore"), "signature": signature_header}

        parts: dict[str, str] = {}
        for item in signature_header.split(","):
            if "=" not in item:
                continue
            key, value = item.split("=", 1)
            parts[key.strip()] = value.strip()

        timestamp_value = parts.get("t")
        signature_value = parts.get("v1")
        if not timestamp_value or not signature_value:
            return {"verified": False, "payload": payload.decode("utf-8", errors="ignore"), "signature": signature_header}

        try:
            timestamp_int = int(timestamp_value)
        except ValueError:
            return {"verified": False, "payload": payload.decode("utf-8", errors="ignore"), "signature": signature_header}

        if abs(int(time.time()) - timestamp_int) > 300:
            return {"verified": False, "payload": payload.decode("utf-8", errors="ignore"), "signature": signature_header}

        payload_text = payload.decode("utf-8", errors="ignore")
        expected_signature = hmac.new(
            secret.encode("utf-8"),
            f"{timestamp_value}.{payload_text}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        verified = hmac.compare_digest(signature_value, expected_signature)
        return {"verified": verified, "payload": payload_text, "signature": signature_header}
