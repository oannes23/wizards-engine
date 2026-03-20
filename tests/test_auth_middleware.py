"""Tests for Story 1.2.1 — Auth Middleware.

Covers:
- get_current_user: returns User when valid login_code cookie is present
- get_current_user: raises 401 (cookie_missing) when no cookie present
- get_current_user: raises 401 (cookie_invalid) when cookie does not match any user
- get_current_user: raises 401 (account_inactive) when matched user is inactive
- require_gm: passes through for GM users
- require_gm: raises 403 (insufficient_role) for player users
- set_auth_cookie: sets expected cookie attributes on a Response
- clear_auth_cookie: removes the cookie from a Response

Test strategy:
- Use an in-memory SQLite database to exercise the real DB layer.
- Mount a minimal probe router under a fresh FastAPI app so that the
  dependency injection wiring is exercised end-to-end via a synchronous
  TestClient.
- All fixtures are function-scoped to guarantee test isolation.
"""

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from wizards_engine.api.auth import COOKIE_NAME, set_auth_cookie, clear_auth_cookie
from wizards_engine.api.deps import get_current_user, require_gm
from wizards_engine.db import get_db
from wizards_engine.models.base import Base, _new_ulid
from wizards_engine.models.user import User


# ---------------------------------------------------------------------------
# Per-test isolated DB and probe app
# ---------------------------------------------------------------------------


def _make_probe_client(engine):
    """Build a FastAPI TestClient wired to the given SQLite engine.

    Creates a fresh sessionmaker from the given engine and overrides the
    ``get_db`` dependency so all routes use the isolated test database.
    Uses the real app factory so that the custom HTTPException handler
    (which strips the ``detail`` wrapper) is registered.
    """
    from wizards_engine.app import create_app

    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def _get_test_db():
        db: Session = TestSessionLocal()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    probe_app = create_app()

    @probe_app.get("/probe/me")
    def probe_me(current_user: User = Depends(get_current_user)):
        return {"id": current_user.id, "role": current_user.role}

    @probe_app.get("/probe/gm-only")
    def probe_gm_only(current_user: User = Depends(require_gm)):
        return {"id": current_user.id, "role": current_user.role}

    probe_app.dependency_overrides[get_db] = _get_test_db

    return TestClient(probe_app, raise_server_exceptions=True)


def _make_seed_session(engine):
    """Return a SQLAlchemy session bound to the given engine for seeding data."""
    return sessionmaker(bind=engine)()


@pytest.fixture
def setup():
    """Provide an isolated in-memory DB, seed users, and a TestClient per test.

    Returns a dict with:
    - ``client``: TestClient
    - ``gm_code``: login_code for active GM
    - ``player_code``: login_code for active player
    - ``inactive_code``: login_code for inactive user
    - ``gm_id``, ``player_id``, ``inactive_id``: corresponding user IDs
    """
    # StaticPool + check_same_thread=False ensures all connections (including
    # those from the ASGI worker thread inside TestClient) share the same
    # in-memory SQLite instance created in the main thread.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    db = _make_seed_session(engine)

    gm_code = "gm-" + _new_ulid()
    gm = User(display_name="Test GM", role="gm", login_code=gm_code, is_active=True)
    db.add(gm)

    player_code = "player-" + _new_ulid()
    player = User(display_name="Test Player", role="player", login_code=player_code, is_active=True)
    db.add(player)

    inactive_code = "inactive-" + _new_ulid()
    inactive = User(display_name="Old Player", role="player", login_code=inactive_code, is_active=False)
    db.add(inactive)

    db.commit()
    db.refresh(gm)
    db.refresh(player)
    db.refresh(inactive)

    gm_id = gm.id
    player_id = player.id
    inactive_id = inactive.id
    db.close()

    client = _make_probe_client(engine)

    yield {
        "client": client,
        "gm_code": gm_code,
        "player_code": player_code,
        "inactive_code": inactive_code,
        "gm_id": gm_id,
        "player_id": player_id,
        "inactive_id": inactive_id,
    }

    Base.metadata.drop_all(engine)
    engine.dispose()


# ---------------------------------------------------------------------------
# get_current_user — happy path
# ---------------------------------------------------------------------------


def test_get_current_user_returns_user_for_valid_gm_cookie(setup):
    """Valid GM login_code cookie returns the matching user."""
    client = setup["client"]
    client.cookies.set(COOKIE_NAME, setup["gm_code"])
    response = client.get("/probe/me")
    client.cookies.clear()
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == setup["gm_id"]
    assert body["role"] == "gm"


def test_get_current_user_returns_user_for_valid_player_cookie(setup):
    """Valid player cookie is also accepted."""
    client = setup["client"]
    client.cookies.set(COOKIE_NAME, setup["player_code"])
    response = client.get("/probe/me")
    client.cookies.clear()
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == setup["player_id"]
    assert body["role"] == "player"


# ---------------------------------------------------------------------------
# get_current_user — error paths
# ---------------------------------------------------------------------------


def test_get_current_user_returns_401_when_no_cookie(setup):
    """Missing cookie yields 401 with cookie_missing error code."""
    response = setup["client"].get("/probe/me")
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "cookie_missing"


def test_get_current_user_returns_401_for_unknown_code(setup):
    """Cookie value that does not match any user yields 401 with cookie_invalid."""
    client = setup["client"]
    client.cookies.set(COOKIE_NAME, "totally-unknown-code-xyz")
    response = client.get("/probe/me")
    client.cookies.clear()
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "cookie_invalid"


def test_get_current_user_returns_401_for_inactive_user(setup):
    """Cookie belonging to an inactive user yields 401 with account_inactive."""
    client = setup["client"]
    client.cookies.set(COOKIE_NAME, setup["inactive_code"])
    response = client.get("/probe/me")
    client.cookies.clear()
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "account_inactive"


# ---------------------------------------------------------------------------
# require_gm dependency
# ---------------------------------------------------------------------------


def test_require_gm_allows_gm_through(setup):
    """require_gm passes for a GM user."""
    client = setup["client"]
    client.cookies.set(COOKIE_NAME, setup["gm_code"])
    response = client.get("/probe/gm-only")
    client.cookies.clear()
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "gm"


def test_require_gm_rejects_player_with_403(setup):
    """require_gm raises 403 insufficient_role for a player."""
    client = setup["client"]
    client.cookies.set(COOKIE_NAME, setup["player_code"])
    response = client.get("/probe/gm-only")
    client.cookies.clear()
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "insufficient_role"


def test_require_gm_rejects_missing_cookie_with_401(setup):
    """require_gm propagates 401 when no cookie present (auth check comes first)."""
    response = setup["client"].get("/probe/gm-only")
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "cookie_missing"


# ---------------------------------------------------------------------------
# auth cookie helpers
# ---------------------------------------------------------------------------


def test_set_auth_cookie_sets_httponly_secure_samesite():
    """set_auth_cookie must produce an httpOnly, Secure, SameSite=Lax cookie."""
    from fastapi.responses import Response as FastAPIResponse

    response = FastAPIResponse()
    set_auth_cookie(response, "test-code-123")

    set_cookie_header = response.headers.get("set-cookie", "")
    assert "test-code-123" in set_cookie_header
    assert "HttpOnly" in set_cookie_header
    assert "Secure" in set_cookie_header
    assert "samesite=lax" in set_cookie_header.lower()


def test_set_auth_cookie_uses_correct_cookie_name():
    """set_auth_cookie must use the COOKIE_NAME constant ('login_code')."""
    assert COOKIE_NAME == "login_code"

    from fastapi.responses import Response as FastAPIResponse

    response = FastAPIResponse()
    set_auth_cookie(response, "xyz")
    set_cookie_header = response.headers.get("set-cookie", "")
    assert "login_code" in set_cookie_header


def test_clear_auth_cookie_emits_delete_directive():
    """clear_auth_cookie must emit a Set-Cookie that expires / zeroes the cookie."""
    from fastapi.responses import Response as FastAPIResponse

    response = FastAPIResponse()
    clear_auth_cookie(response)

    set_cookie_header = response.headers.get("set-cookie", "")
    assert "login_code" in set_cookie_header
    # Must carry an expiry/max-age directive so browsers discard the cookie.
    assert "Max-Age=0" in set_cookie_header or "expires" in set_cookie_header.lower()
