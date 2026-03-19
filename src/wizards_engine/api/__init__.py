"""API package — FastAPI routers for all /api/v1/ endpoints."""

from fastapi.routing import APIRouter

from wizards_engine.api.routes.auth import router as auth_router
from wizards_engine.api.routes.characters import router as characters_router
from wizards_engine.api.routes.clocks import router as clocks_router
from wizards_engine.api.routes.effects import router as effects_router
from wizards_engine.api.routes.find_time import router as find_time_router
from wizards_engine.api.routes.maintain_bond import router as maintain_bond_router
from wizards_engine.api.routes.recharge_trait import router as recharge_trait_router
from wizards_engine.api.routes.events import router as events_router
from wizards_engine.api.routes.feed import router as feed_router
from wizards_engine.api.routes.game import router as game_router
from wizards_engine.api.routes.gm_actions import router as gm_actions_router
from wizards_engine.api.routes.gm_actions_batch import router as gm_actions_batch_router
from wizards_engine.api.routes.gm_dashboard import router as gm_dashboard_router
from wizards_engine.api.routes.groups import router as groups_router
from wizards_engine.api.routes.invites import router as invites_router
from wizards_engine.api.routes.locations import router as locations_router
from wizards_engine.api.routes.me import router as me_router
from wizards_engine.api.routes.players import router as players_router
from wizards_engine.api.routes.proposals import router as proposals_router
from wizards_engine.api.routes.sessions import router as sessions_router
from wizards_engine.api.routes.setup import router as setup_router
from wizards_engine.api.routes.starred import router as starred_router
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
router.include_router(find_time_router)
router.include_router(maintain_bond_router)
router.include_router(recharge_trait_router)
router.include_router(events_router)
router.include_router(feed_router)
router.include_router(gm_actions_router)
router.include_router(gm_actions_batch_router)
router.include_router(gm_dashboard_router)
router.include_router(groups_router)
router.include_router(invites_router)
router.include_router(locations_router)
router.include_router(players_router)
router.include_router(proposals_router)
router.include_router(sessions_router)
router.include_router(starred_router)
router.include_router(stories_router)
router.include_router(trait_templates_router)
