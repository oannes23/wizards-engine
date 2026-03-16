"""API package — FastAPI routers for all /api/v1/ endpoints."""

from fastapi.routing import APIRouter

from wizards_engine.api.routes.auth import router as auth_router
from wizards_engine.api.routes.characters import router as characters_router
from wizards_engine.api.routes.clocks import router as clocks_router
from wizards_engine.api.routes.effects import router as effects_router
from wizards_engine.api.routes.game import router as game_router
from wizards_engine.api.routes.groups import router as groups_router
from wizards_engine.api.routes.invites import router as invites_router
from wizards_engine.api.routes.locations import router as locations_router
from wizards_engine.api.routes.me import router as me_router
from wizards_engine.api.routes.players import router as players_router
from wizards_engine.api.routes.sessions import router as sessions_router
from wizards_engine.api.routes.setup import router as setup_router
from wizards_engine.api.routes.stories import router as stories_router
from wizards_engine.api.routes.trait_templates import router as trait_templates_router

router = APIRouter()

router.include_router(setup_router)
router.include_router(me_router)
router.include_router(auth_router)
router.include_router(game_router)
router.include_router(characters_router)
router.include_router(clocks_router)
router.include_router(effects_router)
router.include_router(groups_router)
router.include_router(invites_router)
router.include_router(locations_router)
router.include_router(players_router)
router.include_router(sessions_router)
router.include_router(stories_router)
router.include_router(trait_templates_router)
