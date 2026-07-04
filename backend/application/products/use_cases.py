from __future__ import annotations

from backend.common.exceptions import DuplicateResourceError, NotFoundError
from backend.common.schema import ProductCreate, ProductOut, ProductUpdate
from backend.domain.products.service import ProductService


class CreateProductUseCase:
    def __init__(self, product_service: ProductService) -> None:
        self.product_service = product_service

    async def execute(self, *, payload: ProductCreate) -> ProductOut:
        existing = await self.product_service.repository.get_by_name(payload.name)
        if existing:
            raise DuplicateResourceError("product")

        product = await self.product_service.create(payload.name, payload.price, payload.description)
        return ProductOut.model_validate(product)


class UpdateProductUseCase:
    def __init__(self, product_service: ProductService) -> None:
        self.product_service = product_service

    async def execute(self, *, product_id: int, payload: ProductUpdate) -> ProductOut:
        product = await self.product_service.get_by_id(product_id)
        if not product:
            raise NotFoundError("product")

        updated = await self.product_service.update(
            product,
            name=payload.name,
            price=payload.price,
            description=payload.description,
        )
        return ProductOut.model_validate(updated)
