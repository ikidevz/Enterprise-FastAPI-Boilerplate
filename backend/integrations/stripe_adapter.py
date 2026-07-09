from __future__ import annotations

from typing import Any

from backend.application.billing.use_cases import PaymentGatewayPort
from backend.domain.users.model import User


class StripeAdapter(PaymentGatewayPort):
    async def create_customer(self, *, user: User) -> str:
        return f"cus_{user.id}"

    async def create_checkout_session(self, *, user: User, plan: Any, success_url: str, cancel_url: str) -> dict:
        return {
            "provider": "stripe",
            "checkout_url": success_url,
            "plan_id": plan.id,
            "customer_id": f"cus_{user.id}",
        }

    def verify_webhook_signature(self, *, payload: bytes, signature_header: str) -> dict:
        verified = bool(signature_header and signature_header.strip())
        return {"verified": verified, "payload": payload.decode("utf-8", errors="ignore"), "signature": signature_header}
