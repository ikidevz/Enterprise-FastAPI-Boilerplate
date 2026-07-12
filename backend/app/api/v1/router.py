from fastapi import APIRouter

from backend.app.api.v1.admin.router import router as admin_router
from backend.app.api.v1.api_keys.router import router as api_keys_router
from backend.app.api.v1.auth.router import router as auth_router
from backend.app.api.v1.audit_log.router import router as audit_log_router
from backend.app.api.v1.billing.router import router as billing_router
from backend.app.api.v1.products.router import router as products_router
from backend.app.api.v1.rbac.router import router as rbac_router
from backend.app.api.v1.uploads.router import router as uploads_router
from backend.app.api.v1.users.router import router as users_router
from backend.app.api.v1.webhooks.router import router as webhooks_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(users_router)
router.include_router(products_router)
router.include_router(uploads_router)
router.include_router(admin_router)
router.include_router(rbac_router)
router.include_router(billing_router)
router.include_router(api_keys_router)
router.include_router(webhooks_router)
router.include_router(audit_log_router)
