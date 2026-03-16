"""Tests for Story 1.2.4 — Identity & Profile (/me endpoints).

Covers:
- GET /api/v1/me: returns current user identity for GM
- GET /api/v1/me: returns current user identity for player (with null character_id)
- GET /api/v1/me: returns 401 when no auth cookie is present
- PATCH /api/v1/me: updates display_name and returns updated identity
- PATCH /api/v1/me: strips surrounding whitespace from display_name
- PATCH /api/v1/me: returns 422 when display_name is empty (after trim)
- PATCH /api/v1/me: returns 422 when display_name exceeds 50 characters
- PATCH /api/v1/me: returns 401 when no auth cookie is present

Test strategy:
- In-memory SQLite database with StaticPool for full isolation per test.
- TestClient wraps the real create_app() factory so the custom HTTPException
  handler (which strips the `detail` wrapper) is exercised end-to-end.
- All fixtures are function-scoped to guarantee test isolation.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from wizards_engine.api.auth import COOKIE_NAME
from wizards_engine.db import get_db
from wizards_engine.models.base import Base, _new_ulid
from wizards_engine.models.user import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_test_client(engine) -> TestClient:
    """Build a TestClient wired to the given SQLite engine.

    Uses the real create_app() factory so the custom HTTPException handler is
    registered.  Overrides ``get_db`` to use an isolated in-memory database.
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

    app = create_app()
    app.dependency_overrides[get_db] = _get_test_db
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def setup():
    """Provide an isolated in-memory DB seeded with a GM and a player, plus a TestClient.

    Returns a dict with:
    - ``client``: TestClient
    - ``gm_code``: login_code for the active GM
    - ``player_code``: login_code for the active player
    - ``gm_id``: ULID of the GM user
    - ``player_id``: ULID of the player user
    - ``gm_display_name``: initial display name for the GM
    - ``player_display_name``: initial display name for the player
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    db: Session = sessionmaker(bind=engine)()

    gm_code = "gm-" + _new_ulid()
    gm = User(display_name="Test GM", role="gm", login_code=gm_code, is_active=True)
    db.add(gm)

    player_code = "player-" + _new_ulid()
    player = User(
        display_name="Test Player", role="player", login_code=player_code, is_active=True
    )
    db.add(player)

    db.commit()
    db.refresh(gm)
    db.refresh(player)

    gm_id = gm.id
    player_id = player.id
    db.close()

    client = _make_test_client(engine)

    yield {
        "client": client,
        "gm_code": gm_code,
        "player_code": player_code,
        "gm_id": gm_id,
        "player_id": player_id,
        "gm_display_name": "Test GM",
        "player_display_name": "Test Player",
    }

    Base.metadata.drop_all(engine)
    engine.dispose()


# ---------------------------------------------------------------------------
# GET /api/v1/me — happy paths
# ---------------------------------------------------------------------------


def test_get_me_returns_gm_identity(setup):
    """GET /me returns id, display_name, role='gm', and character_id=null for the GM."""
    response = setup["client"].get(
        "/api/v1/me", cookies={COOKIE_NAME: setup["gm_code"]}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == setup["gm_id"]
    assert body["display_name"] == setup["gm_display_name"]
    assert body["role"] == "gm"
    assert body["character_id"] is None


def test_get_me_returns_player_identity(setup):
    """GET /me returns id, display_name, role='player', and character_id=null for a player."""
    response = setup["client"].get(
        "/api/v1/me", cookies={COOKIE_NAME: setup["player_code"]}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == setup["player_id"]
    assert body["display_name"] == setup["player_display_name"]
    assert body["role"] == "player"
    assert body["character_id"] is None


# ---------------------------------------------------------------------------
# GET /api/v1/me — auth errors
# ---------------------------------------------------------------------------


def test_get_me_returns_401_when_no_cookie(setup):
    """GET /me returns 401 cookie_missing when no auth cookie is present."""
    response = setup["client"].get("/api/v1/me")
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "cookie_missing"


# ---------------------------------------------------------------------------
# PATCH /api/v1/me — happy paths
# ---------------------------------------------------------------------------


def test_patch_me_updates_display_name(setup):
    """PATCH /me with a valid display_name updates and returns the new name."""
    response = setup["client"].patch(
        "/api/v1/me",
        json={"display_name": "New GM Name"},
        cookies={COOKIE_NAME: setup["gm_code"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == setup["gm_id"]
    assert body["display_name"] == "New GM Name"
    assert body["role"] == "gm"
    assert body["character_id"] is None


def test_patch_me_strips_surrounding_whitespace(setup):
    """PATCH /me trims leading/trailing whitespace from display_name."""
    response = setup["client"].patch(
        "/api/v1/me",
        json={"display_name": "  Trimmed Name  "},
        cookies={COOKIE_NAME: setup["player_code"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["display_name"] == "Trimmed Name"


def test_patch_me_accepts_exactly_50_chars(setup):
    """PATCH /me accepts a display_name that is exactly 50 characters long."""
    name_50 = "A" * 50
    response = setup["client"].patch(
        "/api/v1/me",
        json={"display_name": name_50},
        cookies={COOKIE_NAME: setup["gm_code"]},
    )
    assert response.status_code == 200
    assert response.json()["display_name"] == name_50


def test_patch_me_persists_change_across_requests(setup):
    """After PATCH /me, a subsequent GET /me reflects the updated display_name."""
    setup["client"].patch(
        "/api/v1/me",
        json={"display_name": "Persisted Name"},
        cookies={COOKIE_NAME: setup["gm_code"]},
    )
    get_response = setup["client"].get(
        "/api/v1/me", cookies={COOKIE_NAME: setup["gm_code"]}
    )
    assert get_response.status_code == 200
    assert get_response.json()["display_name"] == "Persisted Name"


# ---------------------------------------------------------------------------
# PATCH /api/v1/me — validation errors
# ---------------------------------------------------------------------------


def test_patch_me_returns_422_for_empty_display_name(setup):
    """PATCH /me returns 422 when display_name is an empty string."""
    response = setup["client"].patch(
        "/api/v1/me",
        json={"display_name": ""},
        cookies={COOKIE_NAME: setup["gm_code"]},
    )
    assert response.status_code == 422


def test_patch_me_returns_422_for_whitespace_only_display_name(setup):
    """PATCH /me returns 422 when display_name is whitespace-only (empty after trim)."""
    response = setup["client"].patch(
        "/api/v1/me",
        json={"display_name": "   "},
        cookies={COOKIE_NAME: setup["gm_code"]},
    )
    assert response.status_code == 422


def test_patch_me_returns_422_for_display_name_over_50_chars(setup):
    """PATCH /me returns 422 when display_name exceeds 50 characters."""
    response = setup["client"].patch(
        "/api/v1/me",
        json={"display_name": "A" * 51},
        cookies={COOKIE_NAME: setup["gm_code"]},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /api/v1/me — auth errors
# ---------------------------------------------------------------------------


def test_patch_me_returns_401_when_no_cookie(setup):
    """PATCH /me returns 401 cookie_missing when no auth cookie is present."""
    response = setup["client"].patch(
        "/api/v1/me", json={"display_name": "No Auth"}
    )
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "cookie_missing"


# ---------------------------------------------------------------------------
# Auth errors — invalid (unrecognised) cookie value
# ---------------------------------------------------------------------------


def test_get_me_returns_401_for_invalid_cookie(setup):
    """GET /me returns 401 cookie_invalid when the cookie value is not in the DB."""
    response = setup["client"].get(
        "/api/v1/me", cookies={COOKIE_NAME: "this-code-does-not-exist"}
    )
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "cookie_invalid"


def test_patch_me_returns_401_for_invalid_cookie(setup):
    """PATCH /me returns 401 cookie_invalid when the cookie value is not in the DB."""
    response = setup["client"].patch(
        "/api/v1/me",
        json={"display_name": "Will Not Save"},
        cookies={COOKIE_NAME: "this-code-does-not-exist"},
    )
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "cookie_invalid"
