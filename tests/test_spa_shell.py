"""Tests for Story 6.1.1 — Static File Serving + SPA Shell.

Covers:
- GET / returns 200 with Content-Type text/html
- GET /login/<code> returns 200 with Content-Type text/html (magic-link deep link)
- GET /setup returns 200 with Content-Type text/html (first-run page)
- GET /docs still returns Swagger UI (not intercepted by SPA routes)
- GET /api/v1/me still works (API routes unaffected)

Uses the shared ``client`` fixture from conftest.py.
"""

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# SPA shell routes
# ---------------------------------------------------------------------------


def test_root_returns_200_html(client: TestClient):
    """GET / returns 200 with Content-Type text/html."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_root_contains_pico_css_link(client: TestClient):
    """GET / response body references the Pico CSS CDN."""
    response = client.get("/")
    assert "picocss/pico" in response.text


def test_root_contains_alpinejs_script(client: TestClient):
    """GET / response body references the Alpine.js CDN."""
    response = client.get("/")
    assert "alpinejs" in response.text


def test_login_deep_link_returns_200_html(client: TestClient):
    """GET /login/<code> returns 200 with Content-Type text/html."""
    response = client.get("/login/abc123")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_setup_returns_200_html(client: TestClient):
    """GET /setup returns 200 with Content-Type text/html."""
    response = client.get("/setup")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


# ---------------------------------------------------------------------------
# Existing routes must not be affected
# ---------------------------------------------------------------------------


def test_docs_still_returns_swagger_ui(client: TestClient):
    """GET /docs still returns the Swagger UI (not caught by SPA routes)."""
    response = client.get("/docs")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_api_me_still_returns_401_without_auth(client: TestClient):
    """GET /api/v1/me returns 401 when unauthenticated (API routes unaffected)."""
    response = client.get("/api/v1/me")
    assert response.status_code == 401
