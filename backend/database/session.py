from collections.abc import AsyncGenerator
from contextvars import ContextVar

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.core.config import settings

engine = create_async_engine(
    settings.database_url, echo=settings.environment == "dev", future=True)
SessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False)

_current_db_session: ContextVar[AsyncSession | None] = ContextVar(
    "current_db_session", default=None)


def get_current_db_session() -> AsyncSession | None:
    return _current_db_session.get()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        token = _current_db_session.set(session)
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            _current_db_session.reset(token)
            await session.close()
