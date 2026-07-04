from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.users.model import User
from backend.common.base_repository import BaseRepository


class UserRepository(BaseRepository[User, object, object]):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, User)

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> User | None:
        result = await self.db.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()
