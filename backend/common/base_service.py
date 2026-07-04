from typing import Generic, TypeVar

from backend.common.base_repository import BaseRepository

ModelType = TypeVar("ModelType")
CreateSchemaType = TypeVar("CreateSchemaType")
UpdateSchemaType = TypeVar("UpdateSchemaType")


class BaseService(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    def __init__(self, repository: BaseRepository[ModelType, CreateSchemaType, UpdateSchemaType]) -> None:
        self.repository = repository

    async def get_by_id(self, item_id: int) -> ModelType | None:
        return await self.repository.get_by_id(item_id)

    async def list(self, *, skip: int = 0, limit: int = 100) -> list[ModelType]:
        return await self.repository.list(skip=skip, limit=limit)

    async def create(self, obj_in: CreateSchemaType) -> ModelType:
        return await self.repository.create(obj_in)

    async def update(self, db_obj: ModelType, obj_in: UpdateSchemaType) -> ModelType:
        return await self.repository.update(db_obj, obj_in)

    async def delete(self, db_obj: ModelType) -> None:
        await self.repository.delete(db_obj)
