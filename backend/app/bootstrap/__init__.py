from .router_registry import register_api_routers
from .static_registry import register_static_assets
from .middleware_registry import register_middlewares

__all__ = [
    "register_api_routers",
    "register_static_assets",
    "register_middlewares",
]
