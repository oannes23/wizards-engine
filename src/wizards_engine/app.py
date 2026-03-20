"""FastAPI application factory for Wizards Engine."""

import logging
import os
import pathlib
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response as StarletteResponse

from wizards_engine.api import router as api_router
from wizards_engine.services.exceptions import (
    BusinessRuleViolation,
    ForbiddenError,
    InsufficientResources,
    NotFoundError,
    ProposalNotPending,
)

logger = logging.getLogger("wizards_engine")

_STATIC_DIR = pathlib.Path(__file__).parent / "static"
_INDEX_HTML = _STATIC_DIR / "index.html"


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log each request's method, path, status code, and duration."""

    async def dispatch(self, request: StarletteRequest, call_next: RequestResponseEndpoint) -> StarletteResponse:
        """Dispatch the request and log the result.

        Args:
            request: The incoming Starlette request.
            call_next: The next middleware or route handler.

        Returns:
            The response from downstream.
        """
        start = time.monotonic()
        response = await call_next(request)
        duration_ms = (time.monotonic() - start) * 1000
        logger.info(
            "%s %s %d %.1fms",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response


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

    # -- Domain exception handlers -----------------------------------------

    @app.exception_handler(NotFoundError)
    async def _not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": exc.code, "message": str(exc)}},
        )

    @app.exception_handler(ForbiddenError)
    async def _forbidden_handler(request: Request, exc: ForbiddenError) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(BusinessRuleViolation)
    async def _business_rule_handler(request: Request, exc: BusinessRuleViolation) -> JSONResponse:
        body: dict = {"error": {"code": exc.code, "message": exc.message}}
        if exc.details is not None:
            body["error"]["details"] = exc.details
        return JSONResponse(status_code=422, content=body)

    @app.exception_handler(ProposalNotPending)
    async def _proposal_not_pending_handler(request: Request, exc: ProposalNotPending) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"error": {"code": "proposal_not_pending", "message": str(exc)}},
        )

    @app.exception_handler(InsufficientResources)
    async def _insufficient_resources_handler(request: Request, exc: InsufficientResources) -> JSONResponse:
        body: dict = {"error": {"code": exc.code, "message": exc.message}}
        if exc.details is not None:
            body["error"]["details"] = exc.details
        return JSONResponse(status_code=409, content=body)


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

    app.add_middleware(RequestLoggingMiddleware)

    cors_origins = os.environ.get("CORS_ORIGINS", "")
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[o.strip() for o in cors_origins.split(",")],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

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
