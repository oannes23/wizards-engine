"""FastAPI application factory for Wizards Engine."""

from fastapi import FastAPI
from fastapi.routing import APIRouter

from wizards_engine.api import router as api_router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance.

    Returns the configured FastAPI app with:
    - All API routes mounted under /api/v1/
    - Auto-generated OpenAPI docs at /docs, /redoc, /openapi.json
    """
    app = FastAPI(
        title="Wizards Engine",
        description=(
            "Backend state tracker for a narrative TTRPG campaign. "
            "Tracks character sheets, game world state, and provides a "
            "proposal workflow for player actions."
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.include_router(api_router, prefix="/api/v1")

    return app


app = create_app()
