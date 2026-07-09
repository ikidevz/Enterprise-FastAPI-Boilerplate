from __future__ import annotations

from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.billing.models import Feature, Plan, PlanFeature, Subscription
from backend.domain.users.model import User


class PaymentGatewayPort(Protocol):
    async def create_customer(self, *, user: User) -> str:
        ...

    async def create_checkout_session(self, *, user: User, plan: Plan, success_url: str, cancel_url: str) -> dict:
        ...

    def verify_webhook_signature(self, *, payload: bytes, signature_header: str) -> dict:
        ...


class BillingUseCases:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_plan(self, *, key: str, name: str, price_cents: int, billing_interval: str, is_active: bool = True) -> Plan:
        plan = Plan(key=key, name=name, price_cents=price_cents,
                    billing_interval=billing_interval, is_active=is_active)
        self.db.add(plan)
        await self.db.commit()
        await self.db.refresh(plan)
        return plan

    async def create_feature(self, *, key: str, name: str, description: str | None = None) -> Feature:
        feature = Feature(key=key, name=name, description=description)
        self.db.add(feature)
        await self.db.commit()
        await self.db.refresh(feature)
        return feature

    async def map_feature_to_plan(self, *, plan_id: int, feature_key: str) -> PlanFeature:
        plan = await self.db.get(Plan, plan_id)
        if plan is None:
            raise ValueError("plan not found")
        feature = await self.db.scalar(select(Feature).where(Feature.key == feature_key))
        if feature is None:
            feature = Feature(key=feature_key, name=feature_key)
            self.db.add(feature)
            await self.db.flush()
            await self.db.refresh(feature)
        mapping = PlanFeature(plan_id=plan.id, feature_id=feature.id)
        self.db.add(mapping)
        await self.db.commit()
        await self.db.refresh(mapping)
        return mapping

    async def assign_subscription(self, *, user_id: int, plan_id: int, provider: str = "manual") -> Subscription:
        subscription = Subscription(
            user_id=user_id, plan_id=plan_id, status="active", provider=provider)
        self.db.add(subscription)
        await self.db.commit()
        await self.db.refresh(subscription)
        return subscription

    async def user_has_feature(self, *, user_id: int, feature_key: str) -> bool:
        result = await self.db.execute(
            select(Subscription.plan_id)
            .join(Plan, Subscription.plan_id == Plan.id)
            .where(Subscription.user_id == user_id, Subscription.status.in_({"active", "trialing"}))
        )
        plan_ids = {row[0] for row in result.all()}
        if not plan_ids:
            return False
        feature_result = await self.db.execute(
            select(PlanFeature.feature_id)
            .join(Feature, PlanFeature.feature_id == Feature.id)
            .where(PlanFeature.plan_id.in_(plan_ids), Feature.key == feature_key)
        )
        return feature_result.scalar_one_or_none() is not None
