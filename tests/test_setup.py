"""Tests for Story 1.2.2 — Setup Endpoint.

Covers:
- POST /api/v1/setup happy path: creates GM, sets cookie, returns 201
- POST /api/v1/setup 409 Conflict when a GM already exists
- Validation: display_name missing → 422
- Validation: display_name empty string → 422
- Validation: display_name whitespace only → 422
- Validation: display_name > 50 chars → 422
- Validation: display_name is trimmed before storage
- Response shape: id, display_name, role, login_url fields present
- login_url format: /login/<code>
- Auth cookie is set: httpOnly, Secure, SameSite=Lax

Test strategy:
- Use an in-memory SQLite database to exercise the real DB layer.
- Override the get_db dependency using the real app factory so the custom
  HTTPException handler and route registration are both active.
- All fixtures are function-scoped to guarantee test isolation.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from wizards_engine.api.auth import COOKIE_NAME
from wizards_engine.db import get_db
from wizards_engine.models.base import Base, _new_ulid
from wizards_engine.models.user import User


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_client(engine) -> TestClient:
    """Build a TestClient wired to the given SQLite engine.

    Creates a fresh sessionmaker and overrides get_db so all routes use the
    isolated test database.  Uses the real app factory so that the custom
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


@pytest.fixture
def empty_client():
    """TestClient backed by a fresh empty in-memory DB (no GM yet)."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    client = _make_client(engine)
    yield client

    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def seeded_client():
    """TestClient backed by an in-memory DB that already has a GM user."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    # Seed a GM directly so we can test the 409 path.
    seed_session = sessionmaker(bind=engine)()
    gm = User(
        id=_new_ulid(),
        display_name="Existing GM",
        role="gm",
        login_code="existing-code",
        is_active=True,
    )
    seed_session.add(gm)
    seed_session.commit()
    seed_session.close()

    client = _make_client(engine)
    yield client

    Base.metadata.drop_all(engine)
    engine.dispose()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_setup_creates_gm_and_returns_201(empty_client: TestClient):
    """Successful setup returns HTTP 201 with user data."""
    response = empty_client.post(
        "/api/v1/setup", json={"display_name": "Dungeon Master"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["display_name"] == "Dungeon Master"
    assert body["role"] == "gm"
    assert "id" in body
    assert len(body["id"]) == 26  # ULID is 26 chars
    assert body["login_url"].startswith("/login/")


def test_setup_response_login_url_contains_code(empty_client: TestClient):
    """login_url must be /login/<code> where code is the 43-char urlsafe token."""
    response = empty_client.post(
        "/api/v1/setup", json={"display_name": "GM"}
    )
    assert response.status_code == 201
    login_url = response.json()["login_url"]
    # /login/<token_urlsafe(32) produces a 43-char base64url string>
    assert login_url.startswith("/login/")
    code = login_url[len("/login/"):]
    assert len(code) == 43


def test_setup_sets_httponly_auth_cookie(empty_client: TestClient):
    """Successful setup must set the auth cookie with httpOnly, Secure, and SameSite=lax."""
    response = empty_client.post(
        "/api/v1/setup", json={"display_name": "GM"}
    )
    assert response.status_code == 201
    set_cookie = response.headers.get("set-cookie", "")
    assert COOKIE_NAME in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    # SameSite header value is case-insensitive in practice; check lowercase
    assert "samesite=lax" in set_cookie.lower()


def test_setup_cookie_value_matches_login_url_code(empty_client: TestClient):
    """The cookie value must be the same code embedded in login_url."""
    response = empty_client.post(
        "/api/v1/setup", json={"display_name": "GM"}
    )
    assert response.status_code == 201
    login_url = response.json()["login_url"]
    code_from_url = login_url[len("/login/"):]

    # httpx TestClient stores cookies in response.cookies
    cookie_value = response.cookies.get(COOKIE_NAME)
    assert cookie_value == code_from_url


# ---------------------------------------------------------------------------
# 409 — GM already exists
# ---------------------------------------------------------------------------


def test_setup_returns_409_when_gm_already_exists(seeded_client: TestClient):
    """Second setup call returns 409 Conflict with already_setup error code."""
    response = seeded_client.post(
        "/api/v1/setup", json={"display_name": "Another GM"}
    )
    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "already_setup"


# ---------------------------------------------------------------------------
# Validation — display_name
# ---------------------------------------------------------------------------


def test_setup_rejects_missing_display_name(empty_client: TestClient):
    """Omitting display_name entirely yields 422."""
    response = empty_client.post("/api/v1/setup", json={})
    assert response.status_code == 422


def test_setup_rejects_empty_display_name(empty_client: TestClient):
    """An empty string for display_name yields 422."""
    response = empty_client.post("/api/v1/setup", json={"display_name": ""})
    assert response.status_code == 422


def test_setup_rejects_whitespace_only_display_name(empty_client: TestClient):
    """A whitespace-only display_name yields 422 (empty after strip)."""
    response = empty_client.post("/api/v1/setup", json={"display_name": "   "})
    assert response.status_code == 422


def test_setup_rejects_display_name_over_50_chars(empty_client: TestClient):
    """A display_name longer than 50 characters yields 422."""
    long_name = "A" * 51
    response = empty_client.post("/api/v1/setup", json={"display_name": long_name})
    assert response.status_code == 422


def test_setup_accepts_display_name_exactly_50_chars(empty_client: TestClient):
    """A display_name of exactly 50 characters is valid."""
    name = "A" * 50
    response = empty_client.post("/api/v1/setup", json={"display_name": name})
    assert response.status_code == 201
    assert response.json()["display_name"] == name


def test_setup_trims_display_name_whitespace(empty_client: TestClient):
    """Leading/trailing whitespace is stripped from display_name before storage."""
    response = empty_client.post(
        "/api/v1/setup", json={"display_name": "  GM With Spaces  "}
    )
    assert response.status_code == 201
    assert response.json()["display_name"] == "GM With Spaces"
