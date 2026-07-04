from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from backend.database.session import engine
from backend.utils.redis_client import redis_client

router = APIRouter(tags=["health"])


@router.get("/health/ready")
async def readiness_check() -> dict[str, object]:
    db_ok = True
    redis_ok = True

    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    try:
        await redis_client.ping()
    except Exception:
        redis_ok = False

    checks = {"database": db_ok, "redis": redis_ok}
    return {
        "status": "ready" if db_ok and redis_ok else "degraded",
        "checks": checks,
    }
