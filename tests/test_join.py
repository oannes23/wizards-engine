"""Tests for Story 3.1.1 — Full Character Creation (Invite Flow).

Covers:
- POST /api/v1/game/join happy path: valid invite → 201, user + character
  created, cookie set
- Invalid invite code → 404 invite_not_found
- Consumed invite code → 404 invite_not_found (same shape — no state leak)
- Missing / unknown code → 404 invite_not_found
- Character fields default correctly (stress=0, skills all 0, magic_stats all
  level=0/xp=0, free_time=0, plot=0, gnosis=0, last_session_time_now=0,
  detail_level="full")
- After join the same invite code works as a login code (via POST /auth/login)
- Validation errors: empty character_name, empty display_name → 422
- Auth cookie is httpOnly, Secure, SameSite=Lax

Test strategy:
- Function-scoped ``client`` + ``db`` from conftest (in-memory SQLite, shared
  engine).  Invites are inserted directly via ``db`` so that we can set up
  specific consumed/unconsumed states without going through a route.
"""

import pytest

from tests.conftest import auth_as
from wizards_engine.api.auth import COOKIE_NAME
from wizards_engine.models.base import _new_ulid
from wizards_engine.models.character import Character
from wizards_engine.models.user import Invite, User

_JOIN_URL = "/api/v1/game/join"
_LOGIN_URL = "/api/v1/auth/login"


# ---------------------------------------------------------------------------
# Helper: seed an unconsumed invite directly into the test DB
# ---------------------------------------------------------------------------


def _seed_invite(db, *, consumed: bool = False) -> str:
    """Insert an Invite row and return its id (= the invite code).

    Args:
        db: Active test session.
        consumed: Whether the invite should be pre-consumed.

    Returns:
        The invite id string (ULID).
    """
    invite_id = _new_ulid()
    invite = Invite(id=invite_id, is_consumed=consumed)
    db.add(invite)
    db.commit()
    return invite_id


# ---------------------------------------------------------------------------
# Happy path — valid invite
# ---------------------------------------------------------------------------


def test_join_valid_invite_returns_201(client, db):
    """POST /game/join with a valid invite returns HTTP 201."""
    code = _seed_invite(db)
    response = client.post(
        _JOIN_URL,
        json={"code": code, "character_name": "Lyra", "display_name": "Player A"},
    )
    assert response.status_code == 201


def test_join_valid_invite_response_shape(client, db):
    """Response contains id, display_name, role='player', and a character_id."""
    code = _seed_invite(db)
    response = client.post(
        _JOIN_URL,
        json={"code": code, "character_name": "Lyra", "display_name": "Player A"},
    )
    body = response.json()
    assert "id" in body
    assert body["display_name"] == "Player A"
    assert body["role"] == "player"
    assert "character_id" in body
    assert body["character_id"] is not None


def test_join_valid_invite_creates_user(client, db):
    """After join, a User with role='player' exists in the database."""
    code = _seed_invite(db)
    response = client.post(
        _JOIN_URL,
        json={"code": code, "character_name": "Lyra", "display_name": "Player A"},
    )
    assert response.status_code == 201
    user_id = response.json()["id"]
    user = db.get(User, user_id)
    assert user is not None
    assert user.role == "player"
    assert user.is_active is True
    assert user.login_code == code


def test_join_valid_invite_creates_character(client, db):
    """After join, a full Character is linked to the new User."""
    code = _seed_invite(db)
    response = client.post(
        _JOIN_URL,
        json={"code": code, "character_name": "Lyra", "display_name": "Player A"},
    )
    char_id = response.json()["character_id"]
    character = db.get(Character, char_id)
    assert character is not None
    assert character.name == "Lyra"
    assert character.detail_level == "full"


def test_join_valid_invite_sets_auth_cookie(client, db):
    """After a successful join the httpOnly login_code cookie is set."""
    code = _seed_invite(db)
    response = client.post(
        _JOIN_URL,
        json={"code": code, "character_name": "Lyra", "display_name": "Player A"},
    )
    assert response.status_code == 201
    set_cookie = response.headers.get("set-cookie", "")
    assert COOKIE_NAME in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "samesite=lax" in set_cookie.lower()


def test_join_valid_invite_cookie_value_equals_code(client, db):
    """The auth cookie value is the invite code (which becomes the login code)."""
    code = _seed_invite(db)
    response = client.post(
        _JOIN_URL,
        json={"code": code, "character_name": "Lyra", "display_name": "Player A"},
    )
    assert response.cookies.get(COOKIE_NAME) == code


def test_join_marks_invite_consumed(client, db):
    """After join, the invite's is_consumed flag is True."""
    code = _seed_invite(db)
    client.post(
        _JOIN_URL,
        json={"code": code, "character_name": "Lyra", "display_name": "Player A"},
    )
    db.expire_all()
    invite = db.get(Invite, code)
    assert invite is not None
    assert invite.is_consumed is True


# ---------------------------------------------------------------------------
# Character field defaults
# ---------------------------------------------------------------------------


def test_join_character_stress_defaults_to_zero(client, db):
    """New full character has stress=0."""
    code = _seed_invite(db)
    r = client.post(
        _JOIN_URL,
        json={"code": code, "character_name": "Lyra", "display_name": "Player A"},
    )
    char = db.get(Character, r.json()["character_id"])
    assert char.stress == 0


def test_join_character_free_time_defaults_to_zero(client, db):
    """New full character has free_time=0."""
    code = _seed_invite(db)
    r = client.post(
        _JOIN_URL,
        json={"code": code, "character_name": "Lyra", "display_name": "Player A"},
    )
    char = db.get(Character, r.json()["character_id"])
    assert char.free_time == 0


def test_join_character_plot_defaults_to_zero(client, db):
    """New full character has plot=0."""
    code = _seed_invite(db)
    r = client.post(
        _JOIN_URL,
        json={"code": code, "character_name": "Lyra", "display_name": "Player A"},
    )
    char = db.get(Character, r.json()["character_id"])
    assert char.plot == 0


def test_join_character_gnosis_defaults_to_zero(client, db):
    """New full character has gnosis=0."""
    code = _seed_invite(db)
    r = client.post(
        _JOIN_URL,
        json={"code": code, "character_name": "Lyra", "display_name": "Player A"},
    )
    char = db.get(Character, r.json()["character_id"])
    assert char.gnosis == 0


def test_join_character_last_session_time_now_defaults_to_zero(client, db):
    """New full character has last_session_time_now=0."""
    code = _seed_invite(db)
    r = client.post(
        _JOIN_URL,
        json={"code": code, "character_name": "Lyra", "display_name": "Player A"},
    )
    char = db.get(Character, r.json()["character_id"])
    assert char.last_session_time_now == 0


def test_join_character_skills_all_zero(client, db):
    """New full character has all 8 skills at level 0."""
    expected_skills = {
        "awareness", "composure", "influence", "finesse",
        "speed", "power", "knowledge", "technology",
    }
    code = _seed_invite(db)
    r = client.post(
        _JOIN_URL,
        json={"code": code, "character_name": "Lyra", "display_name": "Player A"},
    )
    char = db.get(Character, r.json()["character_id"])
    assert char.skills is not None
    assert set(char.skills.keys()) == expected_skills
    for skill, level in char.skills.items():
        assert level == 0, f"skills[{skill}] should be 0, got {level}"


def test_join_character_magic_stats_all_zero(client, db):
    """New full character has all 5 magic stats at level=0 and xp=0."""
    expected_schools = {"being", "wyrding", "summoning", "enchanting", "dreaming"}
    code = _seed_invite(db)
    r = client.post(
        _JOIN_URL,
        json={"code": code, "character_name": "Lyra", "display_name": "Player A"},
    )
    char = db.get(Character, r.json()["character_id"])
    assert char.magic_stats is not None
    assert set(char.magic_stats.keys()) == expected_schools
    for school, stat in char.magic_stats.items():
        assert stat["level"] == 0, f"magic_stats[{school}].level should be 0"
        assert stat["xp"] == 0, f"magic_stats[{school}].xp should be 0"


# ---------------------------------------------------------------------------
# Post-join login — invite code becomes permanent login code
# ---------------------------------------------------------------------------


def test_join_code_works_as_login_afterwards(client, db):
    """After join, the same invite code authenticates via POST /auth/login."""
    code = _seed_invite(db)
    join_resp = client.post(
        _JOIN_URL,
        json={"code": code, "character_name": "Lyra", "display_name": "Player A"},
    )
    assert join_resp.status_code == 201

    # Clear any cookies set during join so this is a fresh login attempt.
    client.cookies.clear()

    login_resp = client.post(_LOGIN_URL, json={"code": code})
    assert login_resp.status_code == 200
    body = login_resp.json()
    assert body["type"] == "user"
    assert body["id"] == join_resp.json()["id"]
    assert body["role"] == "player"


def test_join_code_sets_cookie_on_subsequent_login(client, db):
    """After join, using the code via POST /auth/login sets the auth cookie."""
    code = _seed_invite(db)
    client.post(
        _JOIN_URL,
        json={"code": code, "character_name": "Lyra", "display_name": "Player A"},
    )
    client.cookies.clear()

    login_resp = client.post(_LOGIN_URL, json={"code": code})
    set_cookie = login_resp.headers.get("set-cookie", "")
    assert COOKIE_NAME in set_cookie


# ---------------------------------------------------------------------------
# Error cases — 404 invite_not_found
# ---------------------------------------------------------------------------


def test_join_consumed_invite_returns_404(client, db):
    """A consumed invite code returns 404 with invite_not_found."""
    code = _seed_invite(db, consumed=True)
    response = client.post(
        _JOIN_URL,
        json={"code": code, "character_name": "Lyra", "display_name": "Player A"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "invite_not_found"


def test_join_missing_code_returns_404(client, db):
    """An invite code that does not exist returns 404 with invite_not_found."""
    response = client.post(
        _JOIN_URL,
        json={
            "code": "totally-unknown-code-zzz",
            "character_name": "Lyra",
            "display_name": "Player A",
        },
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "invite_not_found"


def test_join_consumed_and_missing_return_same_shape(client, db):
    """Consumed-invite 404 and missing-code 404 are identical (no state leak)."""
    consumed_code = _seed_invite(db, consumed=True)

    r_consumed = client.post(
        _JOIN_URL,
        json={
            "code": consumed_code,
            "character_name": "Lyra",
            "display_name": "Player A",
        },
    )
    r_missing = client.post(
        _JOIN_URL,
        json={
            "code": "nonexistent-invite-code",
            "character_name": "Lyra",
            "display_name": "Player A",
        },
    )
    assert r_consumed.status_code == r_missing.status_code == 404
    assert (
        r_consumed.json()["error"]["code"] == r_missing.json()["error"]["code"]
        == "invite_not_found"
    )


def test_join_invalid_invite_does_not_set_cookie(client, db):
    """Failed join (invalid code) must not set an auth cookie."""
    response = client.post(
        _JOIN_URL,
        json={
            "code": "nonexistent-code",
            "character_name": "Lyra",
            "display_name": "Player A",
        },
    )
    assert response.status_code == 404
    assert COOKIE_NAME not in response.cookies


# ---------------------------------------------------------------------------
# Validation errors — 422
# ---------------------------------------------------------------------------


def test_join_empty_character_name_returns_422(client, db):
    """An empty character_name after stripping returns 422."""
    code = _seed_invite(db)
    response = client.post(
        _JOIN_URL,
        json={"code": code, "character_name": "   ", "display_name": "Player A"},
    )
    assert response.status_code == 422


def test_join_empty_display_name_returns_422(client, db):
    """An empty display_name after stripping returns 422."""
    code = _seed_invite(db)
    response = client.post(
        _JOIN_URL,
        json={"code": code, "character_name": "Lyra", "display_name": "   "},
    )
    assert response.status_code == 422


def test_join_character_name_too_long_returns_422(client, db):
    """A character_name exceeding 200 characters returns 422."""
    code = _seed_invite(db)
    response = client.post(
        _JOIN_URL,
        json={
            "code": code,
            "character_name": "X" * 201,
            "display_name": "Player A",
        },
    )
    assert response.status_code == 422


def test_join_display_name_too_long_returns_422(client, db):
    """A display_name exceeding 50 characters returns 422."""
    code = _seed_invite(db)
    response = client.post(
        _JOIN_URL,
        json={
            "code": code,
            "character_name": "Lyra",
            "display_name": "Y" * 51,
        },
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Atomicity — second join attempt with the same code fails
# ---------------------------------------------------------------------------


def test_join_same_code_cannot_be_used_twice(client, db):
    """Using the same code a second time returns 404 (invite is now consumed)."""
    code = _seed_invite(db)

    # First join succeeds.
    r1 = client.post(
        _JOIN_URL,
        json={"code": code, "character_name": "Lyra", "display_name": "Player A"},
    )
    assert r1.status_code == 201

    # Second join with the same code must fail.
    r2 = client.post(
        _JOIN_URL,
        json={"code": code, "character_name": "Other", "display_name": "Player B"},
    )
    assert r2.status_code == 404
    assert r2.json()["error"]["code"] == "invite_not_found"
