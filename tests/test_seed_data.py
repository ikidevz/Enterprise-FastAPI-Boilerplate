import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from backend.database.base import Base
from backend.domain.products.model import Product
from backend.domain.users.model import User
from backend.scripts import seed_data


def test_seed_creates_a_default_admin_and_sample_products() -> None:
    """Ensures seed creates a default admin and sample products."""
    async def run_seed() -> None:
        """Supports the test suite by run seed."""
        test_engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:", echo=False)
        try:
            async with test_engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            await seed_data.seed(test_engine)

            from sqlalchemy.ext.asyncio import async_sessionmaker

            session_factory = async_sessionmaker(
                bind=test_engine, expire_on_commit=False)
            async with session_factory() as db:
                admin = (
                    await db.execute(select(User).where(User.username == "admin"))
                ).scalar_one_or_none()
                products = (await db.execute(select(Product))).scalars().all()

            assert admin is not None
            assert admin.role == "admin"
            assert len(products) >= 2
        finally:
            await test_engine.dispose()

    asyncio.run(run_seed())


def test_seeding_twice_does_not_create_duplicates() -> None:
    """The seed script should be safe to run repeatedly (e.g. on every container start)."""
    async def run_seed_twice() -> None:
        """Supports the test suite by run seed twice."""
        test_engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:", echo=False)
        try:
            async with test_engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            await seed_data.seed(test_engine)
            await seed_data.seed(test_engine)

            from sqlalchemy.ext.asyncio import async_sessionmaker

            session_factory = async_sessionmaker(
                bind=test_engine, expire_on_commit=False)
            async with session_factory() as db:
                admins = (
                    await db.execute(select(User).where(User.username == "admin"))
                ).scalars().all()

            assert len(admins) == 1
        finally:
            await test_engine.dispose()

    asyncio.run(run_seed_twice())
