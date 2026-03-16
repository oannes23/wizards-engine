"""Tests for Story 2.1.4 — Player Roster.

Covers all acceptance criteria:

GET /api/v1/players
  - Authenticated user receives a flat list of all users
  - Response includes: id, display_name, role, character_id, is_active
  - Non-GM caller does NOT receive login_url
  - GM caller receives login_url per player in /login/<code> format
  - Returns all users (GM + players) — not filtered
  - Not paginated — flat list (no items/next_cursor/has_more wrapper)
  - Unauthenticated caller receives 401
  - Inactive users are included in the roster
"""

import pytest
from fastapi.testclient import TestClient

from tests.conftest import auth_as


# ---------------------------------------------------------------------------
# GET /api/v1/players — general shape
# ---------------------------------------------------------------------------


class TestListPlayers:
    def test_returns_all_users(self, client: TestClient, seed_data: dict):
        """All users (GM + 3 players) are returned in the roster."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/players")

        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)
        # Seed data has 1 GM + 3 players = 4 users total.
        assert len(body) == 4

    def test_response_includes_required_fields(self, client: TestClient, seed_data: dict):
        """Each entry contains id, display_name, role, character_id, is_active."""
        auth_as(client, seed_data["player1"])
        response = client.get("/api/v1/players")

        assert response.status_code == 200
        for entry in response.json():
            assert "id" in entry
            assert "display_name" in entry
            assert "role" in entry
            assert "character_id" in entry
            assert "is_active" in entry

    def test_gm_user_is_in_roster(self, client: TestClient, seed_data: dict):
        """The GM account is included in the returned roster."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/players")

        ids = {entry["id"] for entry in response.json()}
        assert seed_data["gm"].id in ids

    def test_all_players_are_in_roster(self, client: TestClient, seed_data: dict):
        """All three player accounts appear in the roster."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/players")

        ids = {entry["id"] for entry in response.json()}
        assert seed_data["player1"].id in ids
        assert seed_data["player2"].id in ids
        assert seed_data["player3"].id in ids

    def test_character_id_populated_for_players(self, client: TestClient, seed_data: dict):
        """Player entries have their character_id set correctly."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/players")

        by_id = {entry["id"]: entry for entry in response.json()}

        assert by_id[seed_data["player1"].id]["character_id"] == seed_data["pc1"].id
        assert by_id[seed_data["player2"].id]["character_id"] == seed_data["pc2"].id
        assert by_id[seed_data["player3"].id]["character_id"] == seed_data["pc3"].id

    def test_gm_character_id_is_none(self, client: TestClient, seed_data: dict):
        """The GM entry has character_id=None (no character linked by default)."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/players")

        by_id = {entry["id"]: entry for entry in response.json()}
        assert by_id[seed_data["gm"].id]["character_id"] is None

    def test_roles_are_correct(self, client: TestClient, seed_data: dict):
        """Role field reflects the actual user role."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/players")

        by_id = {entry["id"]: entry for entry in response.json()}
        assert by_id[seed_data["gm"].id]["role"] == "gm"
        assert by_id[seed_data["player1"].id]["role"] == "player"

    def test_is_active_is_true_for_active_users(self, client: TestClient, seed_data: dict):
        """Active accounts have is_active=True."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/players")

        for entry in response.json():
            assert entry["is_active"] is True

    def test_unauthenticated_returns_401(self, client: TestClient, seed_data: dict):
        """Unauthenticated request receives 401."""
        response = client.get("/api/v1/players")
        assert response.status_code == 401

    def test_not_paginated_returns_flat_list(self, client: TestClient, seed_data: dict):
        """Response is a flat JSON array, not a paginated envelope."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/players")

        # A flat list — not a dict with items/next_cursor/has_more.
        assert isinstance(response.json(), list)
        assert "items" not in response.json()


# ---------------------------------------------------------------------------
# Role-conditional login_url visibility
# ---------------------------------------------------------------------------


class TestLoginUrlVisibility:
    def test_gm_caller_receives_login_url(self, client: TestClient, seed_data: dict):
        """GM caller receives login_url for every entry in the roster."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/players")

        assert response.status_code == 200
        for entry in response.json():
            assert "login_url" in entry
            assert entry["login_url"] is not None

    def test_gm_login_url_format(self, client: TestClient, seed_data: dict):
        """login_url is formatted as /login/<login_code>."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/players")

        by_id = {entry["id"]: entry for entry in response.json()}

        # Verify the GM's own login_url points to their login code.
        gm = seed_data["gm"]
        assert by_id[gm.id]["login_url"] == f"/login/{gm.login_code}"

        # Verify a player's login_url as well.
        player1 = seed_data["player1"]
        assert by_id[player1.id]["login_url"] == f"/login/{player1.login_code}"

    def test_player_caller_does_not_receive_login_url(
        self, client: TestClient, seed_data: dict
    ):
        """Non-GM caller does not receive login_url in any entry."""
        auth_as(client, seed_data["player1"])
        response = client.get("/api/v1/players")

        assert response.status_code == 200
        for entry in response.json():
            assert "login_url" not in entry

    def test_player_can_access_roster(self, client: TestClient, seed_data: dict):
        """Non-GM player receives 200 and all four users."""
        auth_as(client, seed_data["player2"])
        response = client.get("/api/v1/players")

        assert response.status_code == 200
        assert len(response.json()) == 4

    def test_player_roster_contains_expected_fields_only(
        self, client: TestClient, seed_data: dict
    ):
        """Non-GM response contains exactly: id, display_name, role, character_id, is_active."""
        auth_as(client, seed_data["player1"])
        response = client.get("/api/v1/players")

        expected_keys = {"id", "display_name", "role", "character_id", "is_active"}
        for entry in response.json():
            assert set(entry.keys()) == expected_keys
