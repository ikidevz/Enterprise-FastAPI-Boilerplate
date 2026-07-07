from fastapi import APIRouter

from backend.app.api.v1.admin.router import router as admin_router
from backend.app.api.v1.auth.router import router as auth_router
from backend.app.api.v1.products.router import router as products_router
from backend.app.api.v1.uploads.router import router as uploads_router
from backend.app.api.v1.users.router import router as users_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(users_router)
router.include_router(products_router)
router.include_router(uploads_router)
router.include_router(admin_router)
# governance_router removed (audit/demo dead-code)
