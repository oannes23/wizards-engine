"""Tests for Story 5.5.6 — Characters Summary Endpoint.

Covers GET /api/v1/characters/summary:

- Unauthenticated → 401
- Player can access → 200
- GM can access → 200
- Returns only detail_level="full" characters (not simplified/NPCs)
- Does not return deleted characters
- Response shape: {items: [{id, name, stress, free_time, plot, gnosis}]}
- Handles nullable meter columns — returns 0 for null stress/free_time/plot/gnosis
- Returns empty list when no full characters exist (edge case)
"""

import pytest
from fastapi.testclient import TestClient

from tests.conftest import auth_as
from wizards_engine.models.character import Character


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


class TestSummaryAuth:
    def test_unauthenticated_returns_401(self, client: TestClient, seed_data: dict):
        """Unauthenticated request returns 401."""
        response = client.get("/api/v1/characters/summary")
        assert response.status_code == 401

    def test_player_can_access(self, client: TestClient, seed_data: dict):
        """Any authenticated player can access the summary endpoint."""
        auth_as(client, seed_data["player1"])
        response = client.get("/api/v1/characters/summary")
        assert response.status_code == 200

    def test_gm_can_access(self, client: TestClient, seed_data: dict):
        """GM can access the summary endpoint."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/characters/summary")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Filtering — only full, non-deleted characters
# ---------------------------------------------------------------------------


class TestSummaryFiltering:
    def test_returns_only_full_characters(self, client: TestClient, seed_data: dict):
        """Only detail_level='full' characters appear in the summary."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/characters/summary")
        assert response.status_code == 200

        items = response.json()["items"]
        ids = {item["id"] for item in items}

        # Full PCs should be present.
        assert seed_data["pc1"].id in ids
        assert seed_data["pc2"].id in ids
        assert seed_data["pc3"].id in ids

        # Simplified NPCs must be absent.
        assert seed_data["npc1"].id not in ids
        assert seed_data["npc2"].id not in ids

    def test_excludes_deleted_characters(self, client: TestClient, seed_data: dict, db):
        """Soft-deleted full characters are excluded from the summary."""
        auth_as(client, seed_data["gm"])

        # Soft-delete pc1 via the API.
        pc1_id = seed_data["pc1"].id
        client.delete(f"/api/v1/characters/{pc1_id}")

        response = client.get("/api/v1/characters/summary")
        assert response.status_code == 200

        ids = {item["id"] for item in response.json()["items"]}
        assert pc1_id not in ids

    def test_count_matches_seed_full_characters(self, client: TestClient, seed_data: dict):
        """Seed data has exactly 3 full PCs; summary must return 3 items."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/characters/summary")
        assert response.status_code == 200
        assert len(response.json()["items"]) == 3


# ---------------------------------------------------------------------------
# Response shape
# ---------------------------------------------------------------------------


class TestSummaryResponseShape:
    def test_response_has_items_key(self, client: TestClient, seed_data: dict):
        """Response body must have a top-level 'items' list."""
        auth_as(client, seed_data["player1"])
        response = client.get("/api/v1/characters/summary")
        body = response.json()
        assert "items" in body
        assert isinstance(body["items"], list)

    def test_item_shape_has_required_fields(self, client: TestClient, seed_data: dict):
        """Each item must contain exactly id, name, stress, free_time, plot, gnosis."""
        auth_as(client, seed_data["player1"])
        response = client.get("/api/v1/characters/summary")
        items = response.json()["items"]

        assert len(items) > 0
        item = items[0]
        assert "id" in item
        assert "name" in item
        assert "stress" in item
        assert "free_time" in item
        assert "plot" in item
        assert "gnosis" in item

    def test_item_does_not_contain_sensitive_fields(
        self, client: TestClient, seed_data: dict
    ):
        """Summary items must not expose skills, magic_stats, bonds, traits, etc."""
        auth_as(client, seed_data["player1"])
        response = client.get("/api/v1/characters/summary")
        item = response.json()["items"][0]

        excluded = [
            "skills",
            "magic_stats",
            "bonds",
            "traits",
            "magic_effects",
            "description",
            "notes",
            "is_deleted",
            "detail_level",
            "attributes",
            "created_at",
            "updated_at",
        ]
        for field in excluded:
            assert field not in item, f"Field '{field}' should not appear in summary item"

    def test_meter_values_match_seed_data(self, client: TestClient, seed_data: dict):
        """Meter values in the summary match what was seeded into the database."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/characters/summary")
        items = {item["id"]: item for item in response.json()["items"]}

        # Seed data initialises all meters to 0 for full characters.
        for key in ("pc1", "pc2", "pc3"):
            pc_id = seed_data[key].id
            item = items[pc_id]
            assert item["stress"] == 0
            assert item["free_time"] == 0
            assert item["plot"] == 0
            assert item["gnosis"] == 0

    def test_items_sorted_by_name_ascending(self, client: TestClient, seed_data: dict):
        """Items are returned in ascending alphabetical order by name."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/characters/summary")
        names = [item["name"] for item in response.json()["items"]]
        assert names == sorted(names)


# ---------------------------------------------------------------------------
# Nullable meter columns — must coerce to 0
# ---------------------------------------------------------------------------


class TestSummaryNullableMeters:
    def test_null_meters_coerce_to_zero(self, client: TestClient, db, seed_data: dict):
        """If meter columns are NULL in the DB they are returned as 0, not null."""
        auth_as(client, seed_data["gm"])

        # Force pc1's meter columns to None directly in the DB to simulate
        # a character whose meters were never initialised.
        pc1 = seed_data["pc1"]
        pc1.stress = None
        pc1.free_time = None
        pc1.plot = None
        pc1.gnosis = None
        db.commit()

        response = client.get("/api/v1/characters/summary")
        assert response.status_code == 200

        items = {item["id"]: item for item in response.json()["items"]}
        item = items[pc1.id]
        assert item["stress"] == 0
        assert item["free_time"] == 0
        assert item["plot"] == 0
        assert item["gnosis"] == 0


# ---------------------------------------------------------------------------
# Edge case — empty result set
# ---------------------------------------------------------------------------


class TestSummaryEdgeCases:
    def test_empty_list_when_no_full_characters(self, client: TestClient, db, seed_data: dict):
        """Returns an empty items list when no non-deleted full characters exist."""
        auth_as(client, seed_data["gm"])

        # Soft-delete all full PCs via the API.
        for key in ("pc1", "pc2", "pc3"):
            pc_id = seed_data[key].id
            client.delete(f"/api/v1/characters/{pc_id}")

        response = client.get("/api/v1/characters/summary")
        assert response.status_code == 200
        assert response.json()["items"] == []
