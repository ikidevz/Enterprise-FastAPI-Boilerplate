from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.core.config import settings
from backend.database.base import Base
from backend.domain.billing.service import BillingService
from backend.domain.products.model import Product
from backend.domain.users.model import User
from backend.domain.users.repository import UserRepository
from backend.domain.users.service import UserService


async def seed(engine=None) -> None:
    created_engine = False
    if engine is None:
        engine = create_async_engine(
            settings.database_url, echo=False, future=True)
        created_engine = True

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        async with session.begin():
            if await session.get(User, 1) is None:
                repo = UserRepository(session)
                service = UserService(repo)
                admin = User(
                    email=settings.default_admin_email,
                    username=settings.default_admin_username,
                    hashed_password=service.hash_password(
                        settings.default_admin_password),
                    is_active=True,
                    is_verified=True,
                    is_superuser=True,
                    role="admin",
                    permissions=["manage:users", "manage:products"],
                )
                session.add(admin)

            billing_service = BillingService(session)
            await billing_service.ensure_seed_data()

            if not await session.scalar(select(Product).limit(1)):
                session.add_all(
                    [
                        Product(name="Seed Product One", price=9.99,
                                description="Seeded product"),
                        Product(name="Seed Product Two", price=19.99,
                                description="Seeded product"),
                    ]
                )

    if created_engine:
        await engine.dispose()
