"""Tests for Story 1.2.3 — Login Endpoint.

Covers:
- POST /api/v1/auth/login with a valid active-user code: set cookie, return user info, type="user"
- POST /api/v1/auth/login with an inactive user's code: 404, no cookie
- POST /api/v1/auth/login with an unconsumed invite id: return {"type": "invite"}, no cookie
- POST /api/v1/auth/login with a consumed invite id: 404 (same as unknown code)
- POST /api/v1/auth/login with an unknown code: 404 with code_not_found
- Response shape: id, display_name, role, character_id, type fields present for user match
- Auth cookie set on user match: httpOnly, Secure, SameSite=Lax
- No cookie set on invite match

Test strategy:
- In-memory SQLite database, seeded per-test via a direct session.
- Override get_db dependency using the real app factory so the custom
  HTTPException handler and route registration are both active.
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
from wizards_engine.models.user import Invite, User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LOGIN_URL = "/api/v1/auth/login"


def _make_client(engine) -> TestClient:
    """Build a TestClient wired to the given SQLite engine.

    Creates a fresh sessionmaker and overrides get_db so all routes use the
    isolated test database.  Uses the real app factory so the custom
    HTTPException handler and route registrations are both exercised.
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

    test_app = create_app()
    test_app.dependency_overrides[get_db] = _get_test_db

    return TestClient(test_app, raise_server_exceptions=True)


def _fresh_engine():
    """Return a new in-memory SQLite engine with all tables created."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


def _seed_session(engine):
    """Return a direct (non-dependency-override) session for seeding."""
    return sessionmaker(bind=engine)()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def active_user_client():
    """Client backed by a DB seeded with one active GM user."""
    engine = _fresh_engine()

    user_id = _new_ulid()
    seed = _seed_session(engine)
    user = User(
        id=user_id,
        display_name="Test GM",
        role="gm",
        login_code="valid-user-code-abc123",
        is_active=True,
    )
    seed.add(user)
    seed.commit()
    seed.close()

    client = _make_client(engine)
    yield client, "valid-user-code-abc123", user_id, "Test GM", "gm"

    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def inactive_user_client():
    """Client backed by a DB seeded with one inactive user."""
    engine = _fresh_engine()

    seed = _seed_session(engine)
    user = User(
        id=_new_ulid(),
        display_name="Inactive Player",
        role="player",
        login_code="inactive-user-code-xyz",
        is_active=False,
    )
    seed.add(user)
    seed.commit()
    seed.close()

    client = _make_client(engine)
    yield client, "inactive-user-code-xyz"

    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def unconsumed_invite_client():
    """Client backed by a DB seeded with one unconsumed invite."""
    engine = _fresh_engine()

    seed = _seed_session(engine)
    invite_id = _new_ulid()
    invite = Invite(id=invite_id, is_consumed=False)
    seed.add(invite)
    seed.commit()
    seed.close()

    client = _make_client(engine)
    yield client, invite_id

    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def consumed_invite_client():
    """Client backed by a DB seeded with one consumed invite."""
    engine = _fresh_engine()

    seed = _seed_session(engine)
    invite_id = _new_ulid()
    invite = Invite(id=invite_id, is_consumed=True)
    seed.add(invite)
    seed.commit()
    seed.close()

    client = _make_client(engine)
    yield client, invite_id

    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def empty_client():
    """Client backed by a fresh empty DB (no users or invites)."""
    engine = _fresh_engine()
    client = _make_client(engine)
    yield client
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def active_player_client():
    """Client backed by a DB seeded with one active player user with no linked character."""
    engine = _fresh_engine()

    user_id = _new_ulid()
    seed = _seed_session(engine)
    user = User(
        id=user_id,
        display_name="Player One",
        role="player",
        login_code="player-code-abc456",
        is_active=True,
    )
    seed.add(user)
    seed.commit()
    seed.close()

    client = _make_client(engine)
    yield client, "player-code-abc456", user_id, "Player One", "player"

    Base.metadata.drop_all(engine)
    engine.dispose()


# ---------------------------------------------------------------------------
# Happy path — active user
# ---------------------------------------------------------------------------


def test_login_active_user_returns_200(active_user_client):
    """Login with a valid active-user code returns HTTP 200."""
    client, code, *_ = active_user_client
    response = client.post(_LOGIN_URL, json={"code": code})
    assert response.status_code == 200


def test_login_active_user_returns_user_info(active_user_client):
    """Login with a valid code returns the user's id, display_name, role, and character_id."""
    client, code, user_id, display_name, role = active_user_client
    response = client.post(_LOGIN_URL, json={"code": code})
    body = response.json()
    assert body["type"] == "user"
    assert body["id"] == user_id
    assert body["display_name"] == display_name
    assert body["role"] == role
    assert "character_id" in body
    assert body["character_id"] is None  # GM has no character


def test_login_active_user_sets_auth_cookie(active_user_client):
    """Login with a valid user code sets the httpOnly, Secure, SameSite=Lax cookie."""
    client, code, *_ = active_user_client
    response = client.post(_LOGIN_URL, json={"code": code})
    assert response.status_code == 200
    set_cookie = response.headers.get("set-cookie", "")
    assert COOKIE_NAME in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "samesite=lax" in set_cookie.lower()


def test_login_active_user_cookie_value_matches_code(active_user_client):
    """The cookie value stored equals the code the caller submitted."""
    client, code, *_ = active_user_client
    response = client.post(_LOGIN_URL, json={"code": code})
    assert response.cookies.get(COOKIE_NAME) == code


# ---------------------------------------------------------------------------
# Happy path — unconsumed invite
# ---------------------------------------------------------------------------


def test_login_unconsumed_invite_returns_200(unconsumed_invite_client):
    """Login with an unconsumed invite id returns HTTP 200."""
    client, invite_id = unconsumed_invite_client
    response = client.post(_LOGIN_URL, json={"code": invite_id})
    assert response.status_code == 200


def test_login_unconsumed_invite_returns_invite_type(unconsumed_invite_client):
    """Login with an unconsumed invite id returns {"type": "invite"}."""
    client, invite_id = unconsumed_invite_client
    response = client.post(_LOGIN_URL, json={"code": invite_id})
    body = response.json()
    assert body == {"type": "invite"}


def test_login_unconsumed_invite_does_not_set_cookie(unconsumed_invite_client):
    """Login with an unconsumed invite does NOT set the auth cookie."""
    client, invite_id = unconsumed_invite_client
    response = client.post(_LOGIN_URL, json={"code": invite_id})
    assert COOKIE_NAME not in response.cookies


# ---------------------------------------------------------------------------
# Error cases — 404
# ---------------------------------------------------------------------------


def test_login_unknown_code_returns_404(empty_client):
    """An unrecognised code returns 404 with code_not_found."""
    response = empty_client.post(_LOGIN_URL, json={"code": "totally-unknown-code"})
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "code_not_found"


def test_login_inactive_user_returns_404(inactive_user_client):
    """A code belonging to an inactive user returns 404 (does not reveal account state)."""
    client, code = inactive_user_client
    response = client.post(_LOGIN_URL, json={"code": code})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "code_not_found"


def test_login_inactive_user_does_not_set_cookie(inactive_user_client):
    """An inactive-user 404 must not set any auth cookie."""
    client, code = inactive_user_client
    response = client.post(_LOGIN_URL, json={"code": code})
    assert COOKIE_NAME not in response.cookies


def test_login_consumed_invite_returns_404(consumed_invite_client):
    """A consumed invite's id returns 404 — same response as an unknown code."""
    client, invite_id = consumed_invite_client
    response = client.post(_LOGIN_URL, json={"code": invite_id})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "code_not_found"


def test_login_consumed_invite_does_not_set_cookie(consumed_invite_client):
    """A consumed-invite 404 must not set any auth cookie."""
    client, invite_id = consumed_invite_client
    response = client.post(_LOGIN_URL, json={"code": invite_id})
    assert COOKIE_NAME not in response.cookies


def test_login_consumed_invite_and_unknown_return_identical_shape(
    consumed_invite_client, empty_client
):
    """Consumed-invite 404 and unknown-code 404 share the exact same response shape."""
    client_consumed, invite_id = consumed_invite_client
    resp_consumed = client_consumed.post(_LOGIN_URL, json={"code": invite_id})
    resp_unknown = empty_client.post(_LOGIN_URL, json={"code": "does-not-exist"})

    assert resp_consumed.status_code == resp_unknown.status_code == 404
    assert resp_consumed.json()["error"]["code"] == resp_unknown.json()["error"]["code"]


# ---------------------------------------------------------------------------
# Happy path — active player (role="player")
# ---------------------------------------------------------------------------


def test_login_active_player_returns_200(active_player_client):
    """Login with a valid active-player code returns HTTP 200."""
    client, code, *_ = active_player_client
    response = client.post(_LOGIN_URL, json={"code": code})
    assert response.status_code == 200


def test_login_active_player_returns_user_info(active_player_client):
    """Login with a player code returns correct id, display_name, role='player', and type='user'."""
    client, code, user_id, display_name, role = active_player_client
    response = client.post(_LOGIN_URL, json={"code": code})
    body = response.json()
    assert body["type"] == "user"
    assert body["id"] == user_id
    assert body["display_name"] == display_name
    assert body["role"] == "player"
    assert "character_id" in body


def test_login_active_player_sets_auth_cookie(active_player_client):
    """Login with a valid player code sets the auth cookie."""
    client, code, *_ = active_player_client
    response = client.post(_LOGIN_URL, json={"code": code})
    set_cookie = response.headers.get("set-cookie", "")
    assert COOKIE_NAME in set_cookie
    assert "HttpOnly" in set_cookie
