"""Tests for POST /api/v1/auth/logout.

Covers:
- POST /logout returns 204 with empty body
- POST /logout after login emits a Set-Cookie header that clears login_code
  (Max-Age=0 or expires in the past)
- POST /logout with no auth cookie still returns 204 (not 401)
- GET /logout returns 405

Test strategy:
- Uses the shared ``client`` and ``seed_data`` fixtures from conftest so the
  standard in-memory SQLite engine and canonical seed data are available.
- The ``auth_as`` helper from conftest sets the login_code cookie on the
  TestClient for the cookie-clearing test.
- Logout is intentionally unauthenticated; most tests need no seeded users.
"""

import pytest
from fastapi.testclient import TestClient

from wizards_engine.api.auth import COOKIE_NAME
from tests.conftest import auth_as

_LOGOUT_URL = "/api/v1/auth/logout"


# ---------------------------------------------------------------------------
# 204 — no body
# ---------------------------------------------------------------------------


def test_logout_returns_204(client: TestClient) -> None:
    """POST /logout returns HTTP 204 with an empty body."""
    response = client.post(_LOGOUT_URL)
    assert response.status_code == 204
    assert response.content == b""


# ---------------------------------------------------------------------------
# Cookie-clearing behaviour
# ---------------------------------------------------------------------------


def test_logout_clears_cookie(client: TestClient, seed_data: dict) -> None:
    """After setting the auth cookie via auth_as, POST /logout emits a
    Set-Cookie header that expires (Max-Age=0) the login_code cookie."""
    auth_as(client, seed_data["gm"])

    response = client.post(_LOGOUT_URL)
    client.cookies.clear()

    assert response.status_code == 204

    set_cookie_header = response.headers.get("set-cookie", "")
    assert COOKIE_NAME in set_cookie_header, (
        "Expected Set-Cookie header to reference login_code cookie"
    )
    # FastAPI's delete_cookie sets Max-Age=0; a browser also honours an
    # expires value in the past.  Either directive is acceptable.
    assert "Max-Age=0" in set_cookie_header or "expires" in set_cookie_header.lower(), (
        "Expected Set-Cookie header to carry Max-Age=0 or an expires directive "
        f"to clear the cookie; got: {set_cookie_header!r}"
    )


# ---------------------------------------------------------------------------
# Unauthenticated logout
# ---------------------------------------------------------------------------


def test_logout_works_without_auth(client: TestClient) -> None:
    """POST /logout with no auth cookie present still returns 204 (not 401).

    The endpoint is deliberately unauthenticated: clearing a non-existent
    cookie is harmless and requiring auth creates a catch-22 when the cookie
    is already stale.
    """
    # Ensure no cookies are set before the request.
    client.cookies.clear()
    response = client.post(_LOGOUT_URL)
    assert response.status_code == 204


# ---------------------------------------------------------------------------
# Method not allowed
# ---------------------------------------------------------------------------


def test_logout_get_returns_405(client: TestClient) -> None:
    """GET on /logout returns 405 — only POST is defined."""
    response = client.get(_LOGOUT_URL)
    assert response.status_code == 405
