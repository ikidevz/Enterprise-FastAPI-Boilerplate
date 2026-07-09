from __future__ import annotations

import types

import pytest

from backend.integrations.paypal_adapter import PayPalAdapter
from backend.integrations.stripe_adapter import StripeAdapter
from backend.core.config import settings


@pytest.mark.asyncio
async def test_stripe_adapter_uses_live_or_sandbox_mode_based_on_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = StripeAdapter()

    monkeypatch.setattr(settings, "stripe_secret_key", "sk_live_123")
    session = await adapter.create_checkout_session(
        user=types.SimpleNamespace(id=7),
        plan=types.SimpleNamespace(id=5),
        success_url="/billing/success",
        cancel_url="/billing/cancel",
    )
    assert session["mode"] == "live"

    monkeypatch.setattr(settings, "stripe_secret_key", None)
    session = await adapter.create_checkout_session(
        user=types.SimpleNamespace(id=7),
        plan=types.SimpleNamespace(id=5),
        success_url="/billing/success",
        cancel_url="/billing/cancel",
    )
    assert session["mode"] == "sandbox"


@pytest.mark.asyncio
async def test_paypal_adapter_uses_sandbox_mode_when_credentials_are_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = PayPalAdapter()

    monkeypatch.setattr(settings, "paypal_client_id", None)
    monkeypatch.setattr(settings, "paypal_client_secret", None)
    session = await adapter.create_checkout_session(
        user=types.SimpleNamespace(id=8),
        plan=types.SimpleNamespace(id=9),
        success_url="/billing/success",
        cancel_url="/billing/cancel",
    )
    assert session["mode"] == "sandbox"
