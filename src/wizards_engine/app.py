"""FastAPI application factory for Wizards Engine."""

import pathlib

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from wizards_engine.api import router as api_router

_STATIC_DIR = pathlib.Path(__file__).parent / "static"
_INDEX_HTML = _STATIC_DIR / "index.html"


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

    @app.get("/", include_in_schema=False)
    async def spa_root() -> FileResponse:
        """Serve the SPA shell for the root path."""
        return FileResponse(_INDEX_HTML)

    @app.get("/login/{code}", include_in_schema=False)
    async def spa_login(code: str) -> FileResponse:
        """Serve the SPA shell for magic-link deep links."""
        return FileResponse(_INDEX_HTML)

    @app.get("/setup", include_in_schema=False)
    async def spa_setup() -> FileResponse:
        """Serve the SPA shell for the first-run setup page."""
        return FileResponse(_INDEX_HTML)

    # Static mount must come after explicit routes and the API router so it
    # does not shadow /docs, /redoc, /openapi.json, or /api/v1/*.
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    return app


app = create_app()
