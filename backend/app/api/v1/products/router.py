from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.application.products import CreateProductUseCase, UpdateProductUseCase
from backend.database.session import get_db
from backend.observability.audit import audit_logger
from backend.web.exceptions import DomainError, NotFoundError, to_http_exception
from backend.domain.products.repository import ProductRepository
from backend.domain.products.service import ProductService
from backend.core.security.rbac import require_role
from backend.contracts.products_contracts import ProductCreate, ProductOut, ProductUpdate
from backend.observability.tracing import trace_span
from backend.domain.users.model import User
from backend.app.socketio_app import sio

router = APIRouter(prefix="/products", tags=["products"])


@router.get("/", response_model=list[ProductOut])
async def list_products(
    search: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    sort: str | None = None,
    order: Literal["asc", "desc"] = "asc",
    db: AsyncSession = Depends(get_db),
) -> list[ProductOut]:
    service = ProductService(ProductRepository(db))
    products = await service.list_with_filters(
        search=search,
        skip=skip,
        limit=limit,
        sort=sort,
        order=order,
    )
    return [ProductOut.model_validate(product) for product in products]


@router.get("/{product_id}", response_model=ProductOut)
async def read_product(product_id: int, db: AsyncSession = Depends(get_db)) -> ProductOut:
    service = ProductService(ProductRepository(db))
    product = await service.get_by_id(product_id)
    if not product:
        raise to_http_exception(NotFoundError("product"))
    return ProductOut.model_validate(product)


@router.post("/", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def create_product(
    request: Request,
    payload: ProductCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "staff")),
) -> ProductOut:
    with trace_span("product.create"):
        try:
            service = ProductService(ProductRepository(db))
            use_case = CreateProductUseCase(service)
            product = await use_case.execute(payload=payload)
            await sio.emit(
                "product_created",
                {
                    "message": "product created",
                    "data": {"id": product.id, "name": product.name},
                },
                to="authenticated",
            )
            audit_logger.log(
                current_user,
                "product.created",
                f"products:{product.id}",
                {"name": product.name},
                request=request,
                status_code=status.HTTP_201_CREATED,
                success=True,
            )
            return product
        except DomainError as exc:
            raise to_http_exception(exc) from exc


@router.put("/{product_id}", response_model=ProductOut)
async def update_product(
    request: Request,
    product_id: int,
    payload: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "staff")),
) -> ProductOut:
    try:
        service = ProductService(ProductRepository(db))
        use_case = UpdateProductUseCase(service)
        updated = await use_case.execute(product_id=product_id, payload=payload)
        audit_logger.log(
            current_user,
            "product.updated",
            f"products:{product_id}",
            {"changes": payload.model_dump(exclude_unset=True)},
            request=request,
            status_code=status.HTTP_200_OK,
            success=True,
        )
        return updated
    except DomainError as exc:
        raise to_http_exception(exc) from exc


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    request: Request,
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "staff")),
) -> None:
    service = ProductService(ProductRepository(db))
    product = await service.get_by_id(product_id)
    if not product:
        raise to_http_exception(NotFoundError("product"))
    await service.delete(product)
    audit_logger.log(
        current_user,
        "product.deleted",
        f"products:{product_id}",
        {"name": product.name},
        request=request,
        status_code=status.HTTP_204_NO_CONTENT,
        success=True,
    )
