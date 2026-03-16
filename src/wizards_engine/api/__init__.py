"""API package — FastAPI routers for all /api/v1/ endpoints."""

from fastapi.routing import APIRouter

from wizards_engine.api.routes.auth import router as auth_router
from wizards_engine.api.routes.me import router as me_router
from wizards_engine.api.routes.setup import router as setup_router

router = APIRouter()

router.include_router(setup_router)
router.include_router(me_router)
router.include_router(auth_router)
