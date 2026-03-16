"""FastAPI application factory for Wizards Engine."""

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRouter

from wizards_engine.api import router as api_router


def _register_exception_handlers(app: FastAPI) -> None:
    """Register custom exception handlers for spec-compliant error envelopes.

    FastAPI's default HTTPException handler wraps ``detail`` under a
    ``{"detail": ...}`` key.  Our auth middleware and other code pass
    ``detail={"error": {"code": ..., "message": ...}}`` to HTTPException,
    expecting the top-level response to be ``{"error": {...}}`` per the
    API conventions spec.  This handler detects that shape and returns
    the ``detail`` dict directly as the response body.
    """

    @app.exception_handler(HTTPException)
    async def _http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            return JSONResponse(
                status_code=exc.status_code,
                content=exc.detail,
            )
        # Fall back to standard FastAPI shape for plain-string details.
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance.

    Returns the configured FastAPI app with:
    - All API routes mounted under /api/v1/
    - Custom exception handler for spec-compliant error envelopes
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

    _register_exception_handlers(app)
    app.include_router(api_router, prefix="/api/v1")

    return app


app = create_app()
