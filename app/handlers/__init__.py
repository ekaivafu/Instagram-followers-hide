from app.handlers.admin import router as admin_router
from app.handlers.admin_items import router as admin_items_router
from app.handlers.base import router as base_router
from app.handlers.fallback import router as fallback_router
from app.handlers.hide import router as hide_router
from app.handlers.referral import router as referral_router

__all__ = [
    "admin_router",
    "admin_items_router",
    "base_router",
    "fallback_router",
    "hide_router",
    "referral_router",
]
