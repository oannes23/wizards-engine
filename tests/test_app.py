"""Smoke tests for the FastAPI application skeleton (Story 1.1.1)."""

import pytest
from httpx import ASGITransport, AsyncClient

from wizards_engine.app import app, create_app


@pytest.fixture
def anyio_backend():
    """Use asyncio backend for async tests."""
    return "asyncio"


@pytest.fixture
async def client():
    """Async HTTP test client bound to the FastAPI app."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_create_app_returns_fastapi_instance():
    """create_app() must return a FastAPI application."""
    from fastapi import FastAPI

    instance = create_app()
    assert isinstance(instance, FastAPI)


@pytest.mark.asyncio
async def test_openapi_json(client: AsyncClient):
    """GET /openapi.json returns a valid OpenAPI spec with 200."""
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    body = response.json()
    assert "openapi" in body
    assert "info" in body
    assert body["info"]["title"] == "Wizards Engine"


@pytest.mark.asyncio
async def test_docs_endpoint(client: AsyncClient):
    """GET /docs returns the Swagger UI (200 HTML)."""
    response = await client.get("/docs")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_redoc_endpoint(client: AsyncClient):
    """GET /redoc returns the ReDoc UI (200 HTML)."""
    response = await client.get("/redoc")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_module_level_app_is_fastapi():
    """The module-level `app` variable must be a FastAPI instance (for uvicorn)."""
    from fastapi import FastAPI

    assert isinstance(app, FastAPI)
