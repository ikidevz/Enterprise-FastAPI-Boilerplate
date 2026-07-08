from sqlalchemy import asc, desc, or_, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.products.model import Product
from backend.common.base_repository import BaseRepository


class ProductRepository(BaseRepository[Product, object, object]):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, Product)

    async def get_by_name(self, name: str) -> Product | None:
        result = await self.db.execute(select(Product).where(Product.name == name))
        return result.scalar_one_or_none()

    def _build_filter_query(self, *, search: str | None = None):
        stmt = select(Product).where(Product.deleted_at.is_(None))
        if search:
            term = f"%{search.lower()}%"
            stmt = stmt.where(
                or_(
                    Product.name.ilike(term),
                    Product.description.ilike(term),
                )
            )
        return stmt

    async def list_with_filters(
        self,
        *,
        search: str | None = None,
        skip: int = 0,
        limit: int = 100,
        sort: str | None = None,
        order: str = "asc",
    ) -> list[Product]:
        stmt = self._build_filter_query(search=search)

        sort_column = getattr(Product, sort, None) if sort in {
            "id", "name", "price", "created_at", "updated_at"} else None
        if sort_column is None:
            sort_column = Product.id

        direction = desc(sort_column) if order.lower(
        ) == "desc" else asc(sort_column)
        stmt = stmt.offset(skip).limit(limit).order_by(direction)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_with_filters(self, *, search: str | None = None) -> int:
        stmt = self._build_filter_query(search=search)
        stmt = stmt.with_only_columns(func.count()).order_by(None)
        result = await self.db.execute(stmt)
        return int(result.scalar_one())
