from datetime import datetime, timezone
from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from backend.database.base import Base

ModelType = TypeVar("ModelType", bound=Base)
CreateSchemaType = TypeVar("CreateSchemaType")
UpdateSchemaType = TypeVar("UpdateSchemaType")


class BaseRepository(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    def __init__(self, db: AsyncSession, model: type[ModelType]) -> None:
        self.db = db
        self.model = model

    async def get_by_id(self, item_id: int) -> ModelType | None:
        stmt = select(self.model).where(self.model.id == item_id)
        if hasattr(self.model, "deleted_at"):
            stmt = stmt.where(getattr(self.model, "deleted_at").is_(None))
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list(self, *, skip: int = 0, limit: int = 100) -> list[ModelType]:
        stmt = select(self.model)
        if hasattr(self.model, "deleted_at"):
            stmt = stmt.where(getattr(self.model, "deleted_at").is_(None))
        stmt = stmt.offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create(self, obj_in: CreateSchemaType | ModelType) -> ModelType:
        if isinstance(obj_in, self.model):
            db_obj = obj_in

        elif hasattr(obj_in, "model_dump"):
            db_obj = self.model(**obj_in.model_dump())

        else:
            raise TypeError(
                f"Unsupported object type: {type(obj_in)}"
            )

        self.db.add(db_obj)
        await self.db.flush()
        await self.db.refresh(db_obj)

        return db_obj

    async def update(self, db_obj: ModelType, obj_in: UpdateSchemaType) -> ModelType:
        if not hasattr(obj_in, "model_dump"):
            raise TypeError(
                "update() requires a Pydantic schema instance, not a raw dict "
                "— construct a schema first so fields are validated and allow-listed."
            )

        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        self.db.add(db_obj)
        await self.db.flush()
        await self.db.refresh(db_obj)
        return db_obj

    async def delete(self, db_obj: ModelType) -> None:
        if hasattr(db_obj, "deleted_at"):
            db_obj.deleted_at = datetime.now(timezone.utc)
        await self.db.flush()

    async def count(self) -> int:
        stmt = select(func.count()).select_from(self.model)
        if hasattr(self.model, "deleted_at"):
            stmt = stmt.where(getattr(self.model, "deleted_at").is_(None))
        result = await self.db.execute(stmt)
        return int(result.scalar_one())
