from datetime import datetime, timezone

from backend.domain.products.model import Product
from backend.domain.products.repository import ProductRepository
from backend.common.base_service import BaseService


class ProductService(BaseService[Product, object, object]):
    def __init__(self, repository: ProductRepository) -> None:
        super().__init__(repository)

    async def list_with_filters(
        self,
        *,
        search: str | None = None,
        skip: int = 0,
        limit: int = 100,
        sort: str | None = None,
        order: str = "asc",
    ) -> list[Product]:
        return await self.repository.list_with_filters(
            search=search,
            skip=skip,
            limit=limit,
            sort=sort,
            order=order,
        )

    async def create(self, name: str, price: float, description: str | None = None) -> Product:
        product = Product(
            name=name,
            price=price,
            description=description,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.repository.db.add(product)
        await self.repository.db.flush()
        await self.repository.db.refresh(product)
        return product

    async def update(self, db_obj: Product, *, name: str | None = None, price: float | None = None, description: str | None = None) -> Product:
        if name is not None:
            db_obj.name = name
        if price is not None:
            db_obj.price = price
        if description is not None:
            db_obj.description = description
        db_obj.updated_at = datetime.now(timezone.utc)
        self.repository.db.add(db_obj)
        await self.repository.db.flush()
        await self.repository.db.refresh(db_obj)
        return db_obj

    async def delete(self, db_obj: Product) -> None:
        db_obj.deleted_at = datetime.now(timezone.utc)
        db_obj.updated_at = datetime.now(timezone.utc)
        self.repository.db.add(db_obj)
        await self.repository.db.flush()
        await self.repository.db.refresh(db_obj)
