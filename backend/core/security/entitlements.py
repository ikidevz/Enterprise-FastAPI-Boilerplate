from __future__ import annotations

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.security.dependencies import get_current_active_user, get_db
from backend.domain.billing.service import BillingService
from backend.domain.users.model import User


def require_feature(feature_key: str):
    async def dependency(
        current_user: User = Depends(get_current_active_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        if feature_key in settings.disabled_features:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"error": "feature_disabled",
                        "required_feature": feature_key},
            )
        if not settings.subscriptions_enabled or current_user.is_superuser:
            return current_user

        service = BillingService(db)
        if not await service.user_has_feature(current_user, feature_key):
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={"error": "feature_not_in_plan",
                        "required_feature": feature_key, "upgrade_url": "/billing/plans"},
            )
        return current_user

    return dependency
