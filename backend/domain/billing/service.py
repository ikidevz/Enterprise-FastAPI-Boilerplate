from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.billing.models import Feature, Plan, PlanFeature, Subscription
from backend.domain.users.model import User


class BillingService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def ensure_seed_data(self) -> None:
        free_plan = await self.db.scalar(select(Plan).where(Plan.key == "free"))
        if free_plan is None:
            self.db.add(
                Plan(
                    key="free",
                    name="Free",
                    price_cents=0,
                    billing_interval="month",
                    is_active=True,
                )
            )
            await self.db.commit()

    async def user_has_feature(self, user: User, feature_key: str) -> bool:
        if user.is_superuser:
            return True

        result = await self.db.execute(
            select(Subscription.plan_id)
            .where(
                Subscription.user_id == user.id,
                Subscription.status.in_({"active", "trialing"}),
            )
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
