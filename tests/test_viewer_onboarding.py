"""Tests for Story 9.1.4 — Viewer Onboarding (Invite + Join Flow).

Covers:

POST /api/v1/game/invites with role body
  - GM creates a viewer invite with {"role": "viewer"} → 201, role="viewer" in response
  - GM creates a player invite explicitly with {"role": "player"} → 201, role="player"
  - POST with no body still creates a player invite (backwards compat)
  - Invalid role value → 422
  - InviteResponse now includes role field

POST /api/v1/game/join for viewer invite
  - Viewer invite + no character_name → 201, role="viewer", character_id=None
  - Viewer invite + character_name provided → 201 (character_name is ignored for viewers)
  - Player invite + no character_name → 422 missing_character_name
  - Player invite + character_name → 201 (existing happy path unchanged)
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as DBSession

from tests.conftest import auth_as
from wizards_engine.models.base import _new_ulid
from wizards_engine.models.character import Character
from wizards_engine.models.user import Invite, User

_INVITES_URL = "/api/v1/game/invites"
_JOIN_URL = "/api/v1/game/join"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_invite(db: DBSession, *, role: str = "player", consumed: bool = False) -> str:
    """Insert an Invite row directly and return its id.

    Args:
        db: Active test database session.
        role: The invite role (``"player"`` or ``"viewer"``).
        consumed: Whether the invite should be pre-consumed.

    Returns:
        The invite id string (ULID).
    """
    invite_id = _new_ulid()
    invite = Invite(id=invite_id, role=role, is_consumed=consumed)
    db.add(invite)
    db.commit()
    return invite_id


# ---------------------------------------------------------------------------
# POST /api/v1/game/invites — role field
# ---------------------------------------------------------------------------


class TestCreateInviteRole:
    def test_create_viewer_invite_returns_role_viewer(
        self, client: TestClient, seed_data: dict
    ):
        """GM creates a viewer invite; response has role='viewer'."""
        auth_as(client, seed_data["gm"])
        response = client.post(_INVITES_URL, json={"role": "viewer"})

        assert response.status_code == 201
        body = response.json()
        assert body["role"] == "viewer"

    def test_create_player_invite_explicit_returns_role_player(
        self, client: TestClient, seed_data: dict
    ):
        """GM creates a player invite explicitly; response has role='player'."""
        auth_as(client, seed_data["gm"])
        response = client.post(_INVITES_URL, json={"role": "player"})

        assert response.status_code == 201
        assert response.json()["role"] == "player"

    def test_create_invite_no_body_defaults_to_player(
        self, client: TestClient, seed_data: dict
    ):
        """POST with no body creates a player invite (backwards compatibility)."""
        auth_as(client, seed_data["gm"])
        response = client.post(_INVITES_URL)

        assert response.status_code == 201
        assert response.json()["role"] == "player"

    def test_create_invite_response_includes_role_field(
        self, client: TestClient, seed_data: dict
    ):
        """InviteResponse now always includes a 'role' field."""
        auth_as(client, seed_data["gm"])
        response = client.post(_INVITES_URL)

        assert response.status_code == 201
        assert "role" in response.json()

    def test_create_invite_invalid_role_returns_422(
        self, client: TestClient, seed_data: dict
    ):
        """An invalid role value ('gm') returns 422 validation error."""
        auth_as(client, seed_data["gm"])
        response = client.post(_INVITES_URL, json={"role": "gm"})

        assert response.status_code == 422

    def test_list_invites_includes_role_field(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """GET /game/invites items include the role field."""
        _seed_invite(db, role="viewer")
        auth_as(client, seed_data["gm"])
        response = client.get(_INVITES_URL)

        assert response.status_code == 200
        item = response.json()["items"][0]
        assert "role" in item
        assert item["role"] == "viewer"


# ---------------------------------------------------------------------------
# POST /api/v1/game/join — viewer invite path
# ---------------------------------------------------------------------------


class TestJoinViewerInvite:
    def test_viewer_join_without_character_name_returns_201(self, client, db):
        """Viewer invite redeemed without character_name succeeds (201)."""
        code = _seed_invite(db, role="viewer")
        response = client.post(
            _JOIN_URL,
            json={"code": code, "display_name": "Spectator Sam"},
        )
        assert response.status_code == 201

    def test_viewer_join_response_has_role_viewer(self, client, db):
        """Viewer join response has role='viewer'."""
        code = _seed_invite(db, role="viewer")
        response = client.post(
            _JOIN_URL,
            json={"code": code, "display_name": "Spectator Sam"},
        )
        assert response.json()["role"] == "viewer"

    def test_viewer_join_response_has_null_character_id(self, client, db):
        """Viewer join response has character_id=None (no character created)."""
        code = _seed_invite(db, role="viewer")
        response = client.post(
            _JOIN_URL,
            json={"code": code, "display_name": "Spectator Sam"},
        )
        body = response.json()
        assert body["character_id"] is None

    def test_viewer_join_creates_no_character_in_db(self, client, db):
        """After viewer join, no Character row is created in the database."""
        code = _seed_invite(db, role="viewer")
        characters_before = db.query(Character).count()
        client.post(
            _JOIN_URL,
            json={"code": code, "display_name": "Spectator Sam"},
        )
        db.expire_all()
        characters_after = db.query(Character).count()
        assert characters_after == characters_before

    def test_viewer_join_creates_user_with_viewer_role(self, client, db):
        """After viewer join, a User with role='viewer' exists in the database."""
        code = _seed_invite(db, role="viewer")
        response = client.post(
            _JOIN_URL,
            json={"code": code, "display_name": "Spectator Sam"},
        )
        user_id = response.json()["id"]
        db.expire_all()
        user = db.get(User, user_id)
        assert user is not None
        assert user.role == "viewer"
        assert user.character_id is None
        assert user.is_active is True
        assert user.login_code == code

    def test_viewer_join_marks_invite_consumed(self, client, db):
        """After viewer join, the invite's is_consumed flag is True."""
        code = _seed_invite(db, role="viewer")
        client.post(
            _JOIN_URL,
            json={"code": code, "display_name": "Spectator Sam"},
        )
        db.expire_all()
        invite = db.get(Invite, code)
        assert invite.is_consumed is True

    def test_viewer_join_sets_auth_cookie(self, client, db):
        """After viewer join, the httpOnly auth cookie is set."""
        from wizards_engine.api.auth import COOKIE_NAME

        code = _seed_invite(db, role="viewer")
        response = client.post(
            _JOIN_URL,
            json={"code": code, "display_name": "Spectator Sam"},
        )
        assert response.status_code == 201
        assert COOKIE_NAME in response.headers.get("set-cookie", "")


# ---------------------------------------------------------------------------
# POST /api/v1/game/join — player invite still requires character_name
# ---------------------------------------------------------------------------


class TestJoinPlayerInviteRequiresCharacterName:
    def test_player_invite_without_character_name_returns_422(self, client, db):
        """Player invite redeemed without character_name returns 422."""
        code = _seed_invite(db, role="player")
        response = client.post(
            _JOIN_URL,
            json={"code": code, "display_name": "Player A"},
        )
        assert response.status_code == 422

    def test_player_invite_without_character_name_error_code(self, client, db):
        """422 response for missing character_name uses missing_character_name code."""
        code = _seed_invite(db, role="player")
        response = client.post(
            _JOIN_URL,
            json={"code": code, "display_name": "Player A"},
        )
        assert response.json()["error"]["code"] == "missing_character_name"

    def test_player_invite_without_character_name_does_not_consume_invite(
        self, client, db
    ):
        """A failed player join (no character_name) should not consume the invite.

        Because the ValueError is raised after the invite is marked consumed
        within the service, the transaction is rolled back by the session
        middleware, leaving the invite unconsumed.
        """
        code = _seed_invite(db, role="player")
        client.post(
            _JOIN_URL,
            json={"code": code, "display_name": "Player A"},
        )
        db.expire_all()
        invite = db.get(Invite, code)
        # The transaction is rolled back on error — invite should still be usable
        assert invite.is_consumed is False

    def test_player_invite_with_character_name_still_works(self, client, db):
        """Existing player join (with character_name) is unaffected."""
        code = _seed_invite(db, role="player")
        response = client.post(
            _JOIN_URL,
            json={"code": code, "character_name": "Lyra", "display_name": "Player A"},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["role"] == "player"
        assert body["character_id"] is not None
