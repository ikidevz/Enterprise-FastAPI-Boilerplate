from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.background_jobs import enqueue_billing_notification
from backend.core.config import settings
from backend.core.security.dependencies import get_current_active_user, get_db
from backend.core.security.rbac import require_permission
from backend.domain.billing.models import Feature, Invoice, Notification, Plan, PlanFeature, Subscription
from backend.domain.billing.service import BillingService
from backend.domain.billing.webhook_models import PaymentEvent
from backend.domain.users.model import User
from backend.integrations.paypal_adapter import PayPalAdapter
from backend.integrations.stripe_adapter import StripeAdapter
from backend.observability.audit import audit_logger
from backend.resilience.idempotency import get_idempotency_store

router = APIRouter(prefix="/billing", tags=["billing"])


@router.post("/admin/plans", status_code=status.HTTP_201_CREATED)
async def create_plan(
    request: Request,
    payload: dict[str, object],
    current_user: User = Depends(require_permission("billing.manage")),
    db: AsyncSession = Depends(get_db),
):
    plan = Plan(
        key=str(payload.get("key", "")),
        name=str(payload.get("name", str(payload.get("key", "")))),
        price_cents=int(payload.get("price_cents", 0)),
        billing_interval=str(payload.get("billing_interval", "month")),
        is_active=bool(payload.get("is_active", True)),
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    audit_logger.log(current_user, "billing.plan_created", "billing", {
                     "plan_id": plan.id, "key": plan.key}, request=request)
    return {"id": plan.id, "key": plan.key, "name": plan.name, "price_cents": plan.price_cents, "billing_interval": plan.billing_interval}


@router.post("/admin/features", status_code=status.HTTP_201_CREATED)
async def create_feature(
    payload: dict[str, object],
    current_user: User = Depends(require_permission("billing.manage")),
    db: AsyncSession = Depends(get_db),
):
    feature = Feature(
        key=str(payload.get("key", "")),
        name=str(payload.get("name", str(payload.get("key", "")))),
        description=str(payload.get("description", "")) if payload.get(
            "description") is not None else None,
    )
    db.add(feature)
    await db.commit()
    await db.refresh(feature)
    audit_logger.log(current_user, "billing.feature_created", "billing", {
                     "feature_id": feature.id, "key": feature.key})
    return {"id": feature.id, "key": feature.key, "name": feature.name, "description": feature.description}


@router.post("/admin/plans/{plan_id}/features")
async def map_plan_features(
    plan_id: int,
    payload: dict[str, object],
    current_user: User = Depends(require_permission("billing.manage")),
    db: AsyncSession = Depends(get_db),
):
    plan = await db.get(Plan, plan_id)
    if plan is None:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"error": "plan_not_found"})

    feature_keys = payload.get("feature_keys", [])
    if not isinstance(feature_keys, list):
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"error": "feature_keys_must_be_a_list"})

    for feature_key in feature_keys:
        feature_key_name = str(feature_key)
        feature = await db.scalar(select(Feature).where(Feature.key == feature_key_name))
        if feature is None:
            feature = Feature(key=feature_key_name, name=feature_key_name)
            db.add(feature)
            await db.flush()
            await db.refresh(feature)

        existing = await db.scalar(
            select(PlanFeature).where(PlanFeature.plan_id ==
                                      plan.id, PlanFeature.feature_id == feature.id)
        )
        if existing is None:
            db.add(PlanFeature(plan_id=plan.id, feature_id=feature.id))

    await db.commit()
    audit_logger.log(current_user, "billing.plan_features_mapped", "billing", {
                     "plan_id": plan.id, "feature_keys": feature_keys})
    return {"plan_id": plan.id, "feature_keys": feature_keys}


@router.patch("/admin/settings")
async def update_billing_settings(
    payload: dict[str, object],
    current_user: User = Depends(require_permission("billing.manage")),
):
    if "subscriptions_enabled" in payload:
        settings.subscriptions_enabled = bool(payload.get(
            "subscriptions_enabled", settings.subscriptions_enabled))
    if "payment_providers_enabled" in payload:
        values = payload.get("payment_providers_enabled", [])
        if isinstance(values, list):
            settings.payment_providers_enabled = [
                str(item).strip().lower() for item in values if str(item).strip()]
        else:
            settings.payment_providers_enabled = [str(values).strip().lower()]
    audit_logger.log(current_user, "billing.settings_updated", "billing", {
        "subscriptions_enabled": settings.subscriptions_enabled,
        "payment_providers_enabled": settings.payment_providers_enabled,
    })
    return {
        "subscriptions_enabled": settings.subscriptions_enabled,
        "payment_providers_enabled": settings.payment_providers_enabled,
    }


@router.get("/admin/billing/metrics")
async def get_billing_metrics(
    current_user: User = Depends(require_permission("billing.manage")),
    db: AsyncSession = Depends(get_db),
):
    subscriptions_result = await db.execute(
        select(Subscription, Plan.price_cents)
        .join(Plan, Subscription.plan_id == Plan.id)
        .where(Subscription.status.in_({"active", "trialing"}))
    )
    subscription_rows = subscriptions_result.all()
    active_count = len(subscription_rows)
    mrr_cents = sum(price_cents for _,
                    price_cents in subscription_rows if price_cents is not None)
    return {
        "active_subscribers": active_count,
        "mrr_cents": mrr_cents,
        "churned_this_month": 0,
        "trial_conversion_rate": 0.0,
    }


@router.post("/subscriptions/assign", status_code=status.HTTP_201_CREATED)
async def assign_subscription(
    payload: dict[str, object],
    current_user: User = Depends(require_permission("billing.manage")),
    db: AsyncSession = Depends(get_db),
):
    subscription = Subscription(
        user_id=int(payload.get("user_id", 0)),
        plan_id=int(payload.get("plan_id", 0)),
        status=str(payload.get("status", "active")),
        provider=str(payload.get("provider", "manual")),
    )
    db.add(subscription)
    await db.flush()

    plan = await db.get(Plan, subscription.plan_id)
    invoice = Invoice(
        subscription_id=subscription.id,
        user_id=subscription.user_id,
        plan_id=subscription.plan_id,
        amount_cents=plan.price_cents if plan is not None else 0,
        description=f"Initial subscription for plan {plan.key if plan is not None else 'unknown'}",
        status="issued",
    )
    db.add(invoice)
    await db.commit()
    await db.refresh(subscription)
    await db.refresh(invoice)
    enqueue_billing_notification(
        user_id=subscription.user_id,
        kind="subscription_assigned",
        title="Subscription activated",
        body=f"Your subscription to plan {plan.key if plan is not None else 'your selected plan'} is now active.",
    )
    audit_logger.log(current_user, "billing.subscription_assigned", "billing", {
                     "subscription_id": subscription.id, "user_id": subscription.user_id})
    return {"id": subscription.id, "user_id": subscription.user_id, "plan_id": subscription.plan_id, "provider": subscription.provider, "status": subscription.status}


@router.post("/subscriptions/change-plan")
async def change_plan(
    payload: dict[str, object],
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Subscription).where(Subscription.user_id == current_user.id).order_by(Subscription.id.desc()).limit(1))
    subscription = result.scalar_one_or_none()
    if subscription is None:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"error": "subscription_not_found"})

    plan_id = int(payload.get("plan_id", 0))
    plan = await db.get(Plan, plan_id)
    if plan is None:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"error": "plan_not_found"})

    current_plan = await db.get(Plan, subscription.plan_id)
    proration_days = max(1, int(payload.get("proration_days", 30)))
    delta_cents = plan.price_cents - \
        (current_plan.price_cents if current_plan is not None else 0)
    prorated_amount_cents = int(delta_cents * proration_days / 30)

    subscription.plan_id = plan.id
    subscription.status = "active"

    invoice = Invoice(
        subscription_id=subscription.id,
        user_id=current_user.id,
        plan_id=plan.id,
        amount_cents=abs(prorated_amount_cents),
        description=f"Proration for plan change to {plan.key}",
        status="issued",
    )
    db.add(invoice)
    await db.commit()
    await db.refresh(subscription)
    await db.refresh(invoice)
    enqueue_billing_notification(
        user_id=current_user.id,
        kind="plan_changed",
        title="Plan updated",
        body=f"Your billing plan has been updated to {plan.key}.",
    )
    return {
        "id": subscription.id,
        "plan_id": subscription.plan_id,
        "status": subscription.status,
        "prorated_amount_cents": prorated_amount_cents,
    }


@router.get("/invoices/me")
async def get_my_invoices(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Invoice).where(Invoice.user_id == current_user.id).order_by(Invoice.id.desc()))
    invoices = result.scalars().all()
    return [{
        "id": invoice.id,
        "plan_id": invoice.plan_id,
        "amount_cents": invoice.amount_cents,
        "status": invoice.status,
        "description": invoice.description,
    } for invoice in invoices]


@router.get("/admin/invoices")
async def list_all_invoices(
    current_user: User = Depends(require_permission("billing.manage")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Invoice).order_by(Invoice.id.desc()))
    invoices = result.scalars().all()
    return [{
        "id": invoice.id,
        "user_id": invoice.user_id,
        "plan_id": invoice.plan_id,
        "amount_cents": invoice.amount_cents,
        "status": invoice.status,
        "description": invoice.description,
    } for invoice in invoices]


@router.get("/notifications/me")
async def list_my_notifications(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Notification).where(Notification.user_id == current_user.id).order_by(Notification.id.desc()))
    notifications = result.scalars().all()
    return [{
        "id": item.id,
        "kind": item.kind,
        "title": item.title,
        "body": item.body,
        "is_read": item.is_read,
    } for item in notifications]


@router.post("/notifications/me/{notification_id}/read")
async def mark_notification_read(
    notification_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    notification = await db.get(Notification, notification_id)
    if notification is None or notification.user_id != current_user.id:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"error": "notification_not_found"})
    notification.is_read = True
    await db.commit()
    return {"id": notification.id, "is_read": notification.is_read}


@router.post("/checkout")
async def create_checkout(
    payload: dict[str, object],
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    provider = str(payload.get("provider", "stripe")).lower()
    if settings.payment_providers_enabled and provider not in settings.payment_providers_enabled:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"error": "provider_not_enabled", "provider": provider})

    plan_id = int(payload.get("plan_id", 0))
    plan = await db.get(Plan, plan_id)
    if plan is None:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"error": "plan_not_found"})

    adapter = StripeAdapter() if provider == "stripe" else PayPalAdapter(
    ) if provider == "paypal" else None
    if adapter is None:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"error": "unsupported_provider"})

    session = await adapter.create_checkout_session(
        user=current_user,
        plan=plan,
        success_url=str(payload.get(
            "success_url", "/billing/subscriptions/me")),
        cancel_url=str(payload.get("cancel_url", "/billing/plans")),
    )
    return {"provider": provider, "plan_id": plan.id, "checkout_url": session.get("checkout_url"), "customer_id": session.get("customer_id")}


@router.post("/subscriptions/cancel")
async def cancel_subscription(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Subscription).where(Subscription.user_id == current_user.id).order_by(Subscription.id.desc()).limit(1))
    subscription = result.scalar_one_or_none()
    if subscription is None:
        return {"status": "none", "plan": None}
    subscription.status = "canceled"
    await db.commit()
    await db.refresh(subscription)
    return {"id": subscription.id, "status": subscription.status}


@router.get("/plans")
async def list_plans(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.id))
    plans = result.scalars().all()
    return [{"id": plan.id, "key": plan.key, "name": plan.name, "price_cents": plan.price_cents, "billing_interval": plan.billing_interval} for plan in plans]


@router.get("/subscriptions/me")
async def get_my_subscription(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Subscription).where(Subscription.user_id == current_user.id).order_by(Subscription.id.desc()).limit(1))
    subscription = result.scalar_one_or_none()
    if subscription is None:
        return {"status": "none", "plan": None}
    return {"status": subscription.status, "plan": {"id": subscription.plan_id, "provider": subscription.provider}}


@router.get("/feature-check")
async def feature_check(
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    feature_key = request.query_params.get("feature", "reports.export")
    if feature_key in settings.disabled_features:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": "feature_disabled",
                     "required_feature": feature_key},
        )
    if settings.subscriptions_enabled and not current_user.is_superuser:
        service = BillingService(db)
        await service.ensure_seed_data()
        if not await service.user_has_feature(current_user, feature_key):
            return JSONResponse(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                content={"error": "feature_not_in_plan",
                         "required_feature": feature_key, "upgrade_url": "/billing/plans"},
            )
    return {"allowed": True, "feature": feature_key}


@router.post("/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    payload: dict[str, object],
    db: AsyncSession = Depends(get_db),
):
    provider = str(payload.get("provider", "stripe")).lower()
    event_id = str(payload.get("event_id", ""))
    event_type = str(payload.get("event_type", ""))
    signature_header = (
        request.headers.get("x-signature")
        or request.headers.get("x-stripe-signature")
        or request.headers.get("x-paypal-transmission-sig")
        or str(payload.get("signature", ""))
    )
    adapter = StripeAdapter() if provider == "stripe" else PayPalAdapter(
    ) if provider == "paypal" else None
    if adapter is None:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"error": "unsupported_provider"})

    payload_bytes = json.dumps(payload, separators=(
        ",", ":"), sort_keys=True).encode("utf-8")
    verification = adapter.verify_webhook_signature(
        payload=payload_bytes, signature_header=signature_header)
    if not verification.get("verified", False):
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"error": "invalid_webhook_signature"})

    store = get_idempotency_store()
    existing_key = await store.get(f"{provider}:{event_id}")
    if existing_key is not None:
        return {"processed": False, "duplicate": True, "event_id": event_id}

    existing = await db.scalar(
        select(PaymentEvent).where(PaymentEvent.provider ==
                                   provider, PaymentEvent.provider_event_id == event_id)
    )
    if existing is not None:
        await store.set(f"{provider}:{event_id}", {"event_id": event_id, "provider": provider})
        return {"processed": False, "duplicate": True, "event_id": event_id}

    event = PaymentEvent(
        provider=provider,
        provider_event_id=event_id,
        event_type=event_type,
        payload=json.dumps(payload),
    )
    db.add(event)
    await db.flush()

    if event_type == "checkout.session.completed":
        subscription = Subscription(
            user_id=int(payload.get("user_id", 0)),
            plan_id=int(payload.get("plan_id", 0)),
            status="active",
            provider=provider,
        )
        db.add(subscription)
    elif event_type == "invoice.payment_failed":
        subscription_id = int(payload.get("subscription_id", 0) or 0)
        subscription: Subscription | None = None
        if subscription_id:
            subscription = await db.get(Subscription, subscription_id)
        if subscription is None:
            subscription = await db.scalar(
                select(Subscription).where(
                    Subscription.user_id == int(payload.get("user_id", 0)),
                    Subscription.plan_id == int(payload.get("plan_id", 0)),
                ).order_by(Subscription.id.desc()).limit(1)
            )
        if subscription is not None:
            subscription.status = "past_due"
            await db.flush()
            enqueue_billing_notification(
                user_id=subscription.user_id,
                kind="payment_failed",
                title="Payment failed",
                body="A recent payment attempt failed. Please update your billing details to restore access.",
            )

    await db.commit()
    await store.set(f"{provider}:{event_id}", {"event_id": event_id, "provider": provider})
    return {"processed": True, "duplicate": False, "event_id": event_id}
