"""Tests for Story 3.1.2 — Invite Management.

Covers all acceptance criteria:

POST /api/v1/game/invites
  - GM can create an invite → 201 with id, is_consumed=False, login_url
  - login_url is /login/<id>
  - Player cannot create invite → 403
  - Unauthenticated cannot create invite → 401

GET /api/v1/game/invites
  - GM can list invites → 200 with items/next_cursor/has_more
  - Empty list returns empty items
  - Pagination limit works
  - Pagination cursor works
  - Player cannot list invites → 403
  - Unauthenticated cannot list invites → 401

DELETE /api/v1/game/invites/{id}
  - GM can delete an unconsumed invite → 204
  - Deleted invite no longer retrievable (not in list)
  - Deleting a consumed invite → 409 (invite_consumed)
  - Deleting a non-existent invite → 404 (not_found)
  - Player cannot delete invite → 403
  - Unauthenticated cannot delete invite → 401
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as DBSession

from tests.conftest import auth_as
from wizards_engine.models.user import Invite


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_invite(db: DBSession, *, is_consumed: bool = False) -> Invite:
    """Insert an Invite row directly into the DB.

    Used to set up test state without going through the API.

    Args:
        db: Active test database session.
        is_consumed: Whether the invite should already be marked consumed.

    Returns:
        The created and refreshed Invite instance.
    """
    invite = Invite(is_consumed=is_consumed)
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return invite


# ---------------------------------------------------------------------------
# POST /api/v1/game/invites
# ---------------------------------------------------------------------------


class TestCreateInvite:
    def test_gm_can_create_invite(
        self, client: TestClient, seed_data: dict
    ):
        """GM creates an invite; returns 201 with id, is_consumed=False, login_url."""
        auth_as(client, seed_data["gm"])
        response = client.post("/api/v1/game/invites")

        assert response.status_code == 201
        body = response.json()
        assert "id" in body
        assert body["is_consumed"] is False
        assert "login_url" in body
        assert "created_at" in body

    def test_create_invite_login_url_format(
        self, client: TestClient, seed_data: dict
    ):
        """The login_url is /login/<id>."""
        auth_as(client, seed_data["gm"])
        response = client.post("/api/v1/game/invites")

        assert response.status_code == 201
        body = response.json()
        assert body["login_url"] == f"/login/{body['id']}"

    def test_create_invite_returns_unique_ids(
        self, client: TestClient, seed_data: dict
    ):
        """Each POST generates a distinct invite with a unique ID."""
        auth_as(client, seed_data["gm"])
        r1 = client.post("/api/v1/game/invites")
        r2 = client.post("/api/v1/game/invites")

        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r1.json()["id"] != r2.json()["id"]

    def test_player_cannot_create_invite(
        self, client: TestClient, seed_data: dict
    ):
        """Non-GM player receives 403 when attempting to create an invite."""
        auth_as(client, seed_data["player1"])
        response = client.post("/api/v1/game/invites")

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "insufficient_role"

    def test_unauthenticated_cannot_create_invite(
        self, client: TestClient, seed_data: dict
    ):
        """Unauthenticated request to create invite receives 401."""
        response = client.post("/api/v1/game/invites")
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/game/invites
# ---------------------------------------------------------------------------


class TestListInvites:
    def test_gm_can_list_invites(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """GM can list invites; response has items/next_cursor/has_more."""
        _make_invite(db)
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/game/invites")

        assert response.status_code == 200
        body = response.json()
        assert "items" in body
        assert "next_cursor" in body
        assert "has_more" in body
        assert isinstance(body["items"], list)
        assert len(body["items"]) >= 1

    def test_list_empty_returns_empty_items(
        self, client: TestClient, seed_data: dict
    ):
        """Empty DB returns an empty items list."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/game/invites")

        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []
        assert body["has_more"] is False
        assert body["next_cursor"] is None

    def test_list_includes_consumed_and_unconsumed(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """List includes both consumed and unconsumed invites."""
        _make_invite(db, is_consumed=False)
        _make_invite(db, is_consumed=True)
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/game/invites")

        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 2
        consumed_flags = {item["is_consumed"] for item in items}
        assert True in consumed_flags
        assert False in consumed_flags

    def test_list_item_has_login_url(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Each item in the list has a login_url field."""
        _make_invite(db)
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/game/invites")

        assert response.status_code == 200
        item = response.json()["items"][0]
        assert "login_url" in item
        assert item["login_url"] == f"/login/{item['id']}"

    def test_list_pagination_limit(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """limit parameter caps the page size."""
        for _ in range(5):
            _make_invite(db)

        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/game/invites?limit=2")

        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) <= 2

    def test_list_pagination_cursor(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """After fetching the first page, the cursor returns the next page."""
        for _ in range(4):
            _make_invite(db)

        auth_as(client, seed_data["gm"])
        page1 = client.get("/api/v1/game/invites?limit=2").json()
        assert len(page1["items"]) == 2
        assert page1["has_more"] is True
        assert page1["next_cursor"] is not None

        page2 = client.get(
            f"/api/v1/game/invites?limit=2&after={page1['next_cursor']}"
        ).json()
        page1_ids = {inv["id"] for inv in page1["items"]}
        page2_ids = {inv["id"] for inv in page2["items"]}
        assert page1_ids.isdisjoint(page2_ids)

    def test_player_cannot_list_invites(
        self, client: TestClient, seed_data: dict
    ):
        """Non-GM player receives 403 when attempting to list invites."""
        auth_as(client, seed_data["player1"])
        response = client.get("/api/v1/game/invites")

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "insufficient_role"

    def test_unauthenticated_cannot_list_invites(
        self, client: TestClient, seed_data: dict
    ):
        """Unauthenticated request to list invites receives 401."""
        response = client.get("/api/v1/game/invites")
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/v1/game/invites/{id}
# ---------------------------------------------------------------------------


class TestDeleteInvite:
    def test_gm_can_delete_unconsumed_invite(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """GM can hard-delete an unconsumed invite; returns 204."""
        invite = _make_invite(db)
        auth_as(client, seed_data["gm"])
        response = client.delete(f"/api/v1/game/invites/{invite.id}")

        assert response.status_code == 204
        assert response.content == b""

    def test_deleted_invite_not_in_list(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """After hard delete, the invite no longer appears in the list."""
        invite = _make_invite(db)
        invite_id = invite.id
        auth_as(client, seed_data["gm"])
        client.delete(f"/api/v1/game/invites/{invite_id}")

        list_resp = client.get("/api/v1/game/invites")
        ids = [inv["id"] for inv in list_resp.json()["items"]]
        assert invite_id not in ids

    def test_delete_consumed_invite_returns_409(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Attempting to delete a consumed invite returns 409 (invite_consumed)."""
        invite = _make_invite(db, is_consumed=True)
        auth_as(client, seed_data["gm"])
        response = client.delete(f"/api/v1/game/invites/{invite.id}")

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "invite_consumed"

    def test_delete_nonexistent_invite_returns_404(
        self, client: TestClient, seed_data: dict
    ):
        """Attempting to delete a non-existent invite returns 404 (not_found)."""
        auth_as(client, seed_data["gm"])
        response = client.delete("/api/v1/game/invites/01DOESNOTEXIST0000000000000")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_player_cannot_delete_invite(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Non-GM player receives 403 when attempting to delete an invite."""
        invite = _make_invite(db)
        auth_as(client, seed_data["player1"])
        response = client.delete(f"/api/v1/game/invites/{invite.id}")

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "insufficient_role"

    def test_unauthenticated_cannot_delete_invite(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Unauthenticated DELETE returns 401."""
        invite = _make_invite(db)
        response = client.delete(f"/api/v1/game/invites/{invite.id}")

        assert response.status_code == 401

    def test_delete_malformed_id_returns_404(
        self, client: TestClient, seed_data: dict
    ):
        """DELETE with a non-ULID path segment returns 404."""
        auth_as(client, seed_data["gm"])
        response = client.delete("/api/v1/game/invites/not-a-valid-ulid")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"
