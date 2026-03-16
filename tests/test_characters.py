"""Tests for Story 2.1.1 — NPC Character CRUD.

Covers all acceptance criteria:

POST /api/v1/characters
  - GM creates a character with name only → 201, detail_level=simplified
  - GM creates a character with all optional fields → 201, fields persisted
  - Non-GM player cannot create → 403
  - Unauthenticated cannot create → 401
  - Empty name → 422
  - Missing name → 422

GET /api/v1/characters
  - Returns paginated list of non-deleted characters
  - Soft-deleted characters excluded by default
  - include_deleted=true reveals soft-deleted characters
  - Filter: detail_level=full returns only full characters
  - Filter: detail_level=simplified returns only simplified characters
  - Filter: has_player=true returns only characters with a linked user
  - Filter: has_player=false returns only characters without a linked user
  - Filter: name (partial, case-insensitive match)
  - ULID cursor pagination (after + limit)
  - Unauthenticated → 401

GET /api/v1/characters/{id}
  - Returns character detail for non-deleted character
  - Returns character detail for soft-deleted character (is_deleted=true visible)
  - Non-existent ID → 404
  - Unauthenticated → 401

PATCH /api/v1/characters/{id}
  - GM updates name → 200, updated
  - GM updates description → 200, other fields unchanged
  - GM updates notes → 200
  - GM clears description with null → 200, description=null
  - Owner (player linked to character) updates their own character → 200
  - Player cannot update another player's character → 403
  - Non-existent character → 404
  - Empty name → 422
  - Unauthenticated → 401

DELETE /api/v1/characters/{id}
  - GM soft-deletes a character → 204
  - Character is hidden from list after deletion
  - Character is still accessible by direct GET after deletion
  - Non-GM player cannot delete → 403
  - Non-existent character → 404
  - Unauthenticated → 401
"""

import pytest
from fastapi.testclient import TestClient

from tests.conftest import auth_as


# ---------------------------------------------------------------------------
# POST /api/v1/characters
# ---------------------------------------------------------------------------


class TestCreateCharacter:
    def test_gm_creates_character_with_name_only(self, client: TestClient, seed_data: dict):
        """GM can create a character with just a name; returns 201 with simplified detail."""
        auth_as(client, seed_data["gm"])
        response = client.post("/api/v1/characters", json={"name": "The Merchant"})

        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "The Merchant"
        assert body["detail_level"] == "simplified"
        assert body["description"] is None
        assert body["notes"] is None
        assert body["attributes"] is None
        assert body["is_deleted"] is False
        assert "id" in body
        assert "created_at" in body
        assert "updated_at" in body

    def test_gm_creates_character_with_all_fields(self, client: TestClient, seed_data: dict):
        """GM can create a character with all optional fields populated."""
        auth_as(client, seed_data["gm"])
        response = client.post(
            "/api/v1/characters",
            json={
                "name": "The Alchemist",
                "description": "A reclusive maker of potions.",
                "notes": "Appears in the market district.",
                "attributes": {"tier": 2, "specialty": "transmutation"},
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "The Alchemist"
        assert body["description"] == "A reclusive maker of potions."
        assert body["notes"] == "Appears in the market district."
        assert body["attributes"] == {"tier": 2, "specialty": "transmutation"}
        assert body["detail_level"] == "simplified"

    def test_create_character_detail_level_always_simplified(
        self, client: TestClient, seed_data: dict
    ):
        """GM-created characters always have detail_level=simplified."""
        auth_as(client, seed_data["gm"])
        response = client.post("/api/v1/characters", json={"name": "Test NPC"})
        assert response.status_code == 201
        assert response.json()["detail_level"] == "simplified"

    def test_non_gm_cannot_create_character(self, client: TestClient, seed_data: dict):
        """Non-GM player receives 403 when attempting to create a character."""
        auth_as(client, seed_data["player1"])
        response = client.post("/api/v1/characters", json={"name": "Should Fail"})
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "insufficient_role"

    def test_unauthenticated_cannot_create_character(self, client: TestClient, seed_data: dict):
        """Unauthenticated request to create character receives 401."""
        response = client.post("/api/v1/characters", json={"name": "No Auth"})
        assert response.status_code == 401

    def test_create_character_empty_name_returns_422(
        self, client: TestClient, seed_data: dict
    ):
        """Empty name returns 422 validation error."""
        auth_as(client, seed_data["gm"])
        response = client.post("/api/v1/characters", json={"name": ""})
        assert response.status_code == 422

    def test_create_character_whitespace_only_name_returns_422(
        self, client: TestClient, seed_data: dict
    ):
        """Whitespace-only name (empty after strip) returns 422."""
        auth_as(client, seed_data["gm"])
        response = client.post("/api/v1/characters", json={"name": "   "})
        assert response.status_code == 422

    def test_create_character_missing_name_returns_422(
        self, client: TestClient, seed_data: dict
    ):
        """Missing required name field returns 422."""
        auth_as(client, seed_data["gm"])
        response = client.post("/api/v1/characters", json={"description": "No name"})
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/v1/characters
# ---------------------------------------------------------------------------


class TestListCharacters:
    def test_list_returns_characters(self, client: TestClient, seed_data: dict):
        """Authenticated user can list characters; response has items/next_cursor/has_more."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/characters")

        assert response.status_code == 200
        body = response.json()
        assert "items" in body
        assert "next_cursor" in body
        assert "has_more" in body
        assert isinstance(body["items"], list)

    def test_list_excludes_deleted_by_default(self, client: TestClient, seed_data: dict):
        """Soft-deleted characters are excluded from the list by default."""
        auth_as(client, seed_data["gm"])

        # Create and delete a character.
        create_resp = client.post("/api/v1/characters", json={"name": "Soon Deleted"})
        char_id = create_resp.json()["id"]
        client.delete(f"/api/v1/characters/{char_id}")

        # List should not include the deleted character.
        list_resp = client.get("/api/v1/characters")
        ids = [c["id"] for c in list_resp.json()["items"]]
        assert char_id not in ids

    def test_include_deleted_reveals_soft_deleted(self, client: TestClient, seed_data: dict):
        """include_deleted=true includes soft-deleted characters in the list."""
        auth_as(client, seed_data["gm"])

        create_resp = client.post("/api/v1/characters", json={"name": "Will Be Deleted"})
        char_id = create_resp.json()["id"]
        client.delete(f"/api/v1/characters/{char_id}")

        list_resp = client.get("/api/v1/characters?include_deleted=true")
        ids = [c["id"] for c in list_resp.json()["items"]]
        assert char_id in ids

    def test_filter_detail_level_full(self, client: TestClient, seed_data: dict):
        """detail_level=full returns only full (PC-level) characters."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/characters?detail_level=full")
        assert response.status_code == 200
        items = response.json()["items"]
        assert all(c["detail_level"] == "full" for c in items)
        # Seed data has 3 full characters (pc1, pc2, pc3).
        assert len(items) == 3

    def test_filter_detail_level_simplified(self, client: TestClient, seed_data: dict):
        """detail_level=simplified returns only simplified (NPC-level) characters."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/characters?detail_level=simplified")
        assert response.status_code == 200
        items = response.json()["items"]
        assert all(c["detail_level"] == "simplified" for c in items)
        # Seed data has 2 simplified characters (npc1, npc2).
        assert len(items) == 2

    def test_filter_detail_level_invalid_returns_422(
        self, client: TestClient, seed_data: dict
    ):
        """Invalid detail_level value returns 422."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/characters?detail_level=invalid")
        assert response.status_code == 422

    def test_filter_has_player_true(self, client: TestClient, seed_data: dict):
        """has_player=true returns only characters linked to a user."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/characters?has_player=true")
        assert response.status_code == 200
        items = response.json()["items"]
        # Seed data has 3 players linked to pc1, pc2, pc3.
        assert len(items) == 3
        ids = {c["id"] for c in items}
        assert seed_data["pc1"].id in ids
        assert seed_data["pc2"].id in ids
        assert seed_data["pc3"].id in ids

    def test_filter_has_player_false(self, client: TestClient, seed_data: dict):
        """has_player=false returns only characters without a linked user."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/characters?has_player=false")
        assert response.status_code == 200
        items = response.json()["items"]
        # Seed data has 2 NPCs (npc1, npc2) with no linked user.
        assert len(items) == 2
        ids = {c["id"] for c in items}
        assert seed_data["npc1"].id in ids
        assert seed_data["npc2"].id in ids

    def test_filter_name_partial_case_insensitive(self, client: TestClient, seed_data: dict):
        """name filter does a case-insensitive partial match."""
        auth_as(client, seed_data["gm"])
        # "archivist" matches npc1 "The Archivist" regardless of case.
        response = client.get("/api/v1/characters?name=archivist")
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == seed_data["npc1"].id

    def test_filter_name_no_match_returns_empty(self, client: TestClient, seed_data: dict):
        """name filter that matches nothing returns an empty items list."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/characters?name=zzznomatch")
        assert response.status_code == 200
        assert response.json()["items"] == []

    def test_pagination_limit(self, client: TestClient, seed_data: dict):
        """limit parameter caps the page size."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/characters?limit=2")
        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) <= 2

    def test_pagination_cursor(self, client: TestClient, seed_data: dict):
        """After fetching the first page, the cursor returns the next page."""
        auth_as(client, seed_data["gm"])

        # Seed has 5 characters; fetch 2 at a time.
        page1 = client.get("/api/v1/characters?limit=2").json()
        assert len(page1["items"]) == 2
        assert page1["has_more"] is True
        assert page1["next_cursor"] is not None

        page2 = client.get(
            f"/api/v1/characters?limit=2&after={page1['next_cursor']}"
        ).json()
        assert len(page2["items"]) == 2
        # IDs on page 2 must not appear on page 1.
        page1_ids = {c["id"] for c in page1["items"]}
        page2_ids = {c["id"] for c in page2["items"]}
        assert page1_ids.isdisjoint(page2_ids)

    def test_unauthenticated_list_returns_401(self, client: TestClient, seed_data: dict):
        """Unauthenticated request to list characters receives 401."""
        response = client.get("/api/v1/characters")
        assert response.status_code == 401

    def test_player_can_list_characters(self, client: TestClient, seed_data: dict):
        """Non-GM players can also list characters."""
        auth_as(client, seed_data["player1"])
        response = client.get("/api/v1/characters")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/v1/characters/{id}
# ---------------------------------------------------------------------------


class TestGetCharacter:
    def test_get_returns_character_detail(self, client: TestClient, seed_data: dict):
        """GET /characters/{id} returns full character detail."""
        auth_as(client, seed_data["gm"])
        npc_id = seed_data["npc1"].id
        response = client.get(f"/api/v1/characters/{npc_id}")

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == npc_id
        assert body["name"] == "The Archivist"
        assert body["detail_level"] == "simplified"
        assert body["is_deleted"] is False

    def test_get_returns_soft_deleted_character(self, client: TestClient, seed_data: dict):
        """GET /characters/{id} returns soft-deleted characters with is_deleted=true."""
        auth_as(client, seed_data["gm"])

        # Create and delete a character.
        create_resp = client.post("/api/v1/characters", json={"name": "Deleted NPC"})
        char_id = create_resp.json()["id"]
        client.delete(f"/api/v1/characters/{char_id}")

        # Direct GET should still work.
        get_resp = client.get(f"/api/v1/characters/{char_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["is_deleted"] is True

    def test_get_nonexistent_character_returns_404(
        self, client: TestClient, seed_data: dict
    ):
        """GET /characters/{id} returns 404 for a non-existent ID."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/characters/01DOESNOTEXIST0000000000000")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_unauthenticated_get_returns_401(self, client: TestClient, seed_data: dict):
        """Unauthenticated GET /characters/{id} returns 401."""
        npc_id = seed_data["npc1"].id
        response = client.get(f"/api/v1/characters/{npc_id}")
        assert response.status_code == 401

    def test_player_can_get_character_detail(self, client: TestClient, seed_data: dict):
        """Non-GM players can retrieve character detail."""
        auth_as(client, seed_data["player1"])
        npc_id = seed_data["npc1"].id
        response = client.get(f"/api/v1/characters/{npc_id}")
        assert response.status_code == 200
        assert response.json()["id"] == npc_id


# ---------------------------------------------------------------------------
# PATCH /api/v1/characters/{id}
# ---------------------------------------------------------------------------


class TestUpdateCharacter:
    def test_gm_updates_name(self, client: TestClient, seed_data: dict):
        """GM can update a character's name."""
        auth_as(client, seed_data["gm"])
        npc_id = seed_data["npc1"].id
        response = client.patch(
            f"/api/v1/characters/{npc_id}", json={"name": "The Grand Archivist"}
        )
        assert response.status_code == 200
        assert response.json()["name"] == "The Grand Archivist"

    def test_gm_updates_description(self, client: TestClient, seed_data: dict):
        """GM can update description; other fields stay unchanged."""
        auth_as(client, seed_data["gm"])
        npc_id = seed_data["npc1"].id
        response = client.patch(
            f"/api/v1/characters/{npc_id}", json={"description": "Keeper of ancient lore."}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["description"] == "Keeper of ancient lore."
        # Name should be unchanged.
        assert body["name"] == "The Archivist"

    def test_gm_updates_notes(self, client: TestClient, seed_data: dict):
        """GM can update notes."""
        auth_as(client, seed_data["gm"])
        npc_id = seed_data["npc1"].id
        response = client.patch(
            f"/api/v1/characters/{npc_id}", json={"notes": "Lives near the lighthouse."}
        )
        assert response.status_code == 200
        assert response.json()["notes"] == "Lives near the lighthouse."

    def test_gm_clears_description_with_null(self, client: TestClient, seed_data: dict):
        """Sending description=null clears the field."""
        auth_as(client, seed_data["gm"])
        npc_id = seed_data["npc1"].id

        # First set a description.
        client.patch(
            f"/api/v1/characters/{npc_id}",
            json={"description": "Some description"},
        )
        # Now clear it.
        response = client.patch(
            f"/api/v1/characters/{npc_id}", json={"description": None}
        )
        assert response.status_code == 200
        assert response.json()["description"] is None

    def test_owner_can_update_own_character(self, client: TestClient, seed_data: dict):
        """A player linked to a character can update it."""
        auth_as(client, seed_data["player1"])
        pc_id = seed_data["pc1"].id
        response = client.patch(
            f"/api/v1/characters/{pc_id}", json={"description": "My hero's backstory."}
        )
        assert response.status_code == 200
        assert response.json()["description"] == "My hero's backstory."

    def test_player_cannot_update_another_players_character(
        self, client: TestClient, seed_data: dict
    ):
        """A player cannot update another player's character."""
        auth_as(client, seed_data["player1"])
        # pc2 belongs to player2.
        pc2_id = seed_data["pc2"].id
        response = client.patch(
            f"/api/v1/characters/{pc2_id}", json={"description": "Should not work."}
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"

    def test_player_cannot_update_npc(self, client: TestClient, seed_data: dict):
        """A player cannot update an NPC (no character ownership)."""
        auth_as(client, seed_data["player1"])
        npc_id = seed_data["npc1"].id
        response = client.patch(
            f"/api/v1/characters/{npc_id}", json={"description": "Unauthorized."}
        )
        assert response.status_code == 403

    def test_update_nonexistent_character_returns_404(
        self, client: TestClient, seed_data: dict
    ):
        """PATCH /characters/{id} returns 404 for a non-existent ID."""
        auth_as(client, seed_data["gm"])
        response = client.patch(
            "/api/v1/characters/01DOESNOTEXIST0000000000000",
            json={"name": "Ghost"},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_update_empty_name_returns_422(self, client: TestClient, seed_data: dict):
        """Updating name to an empty string returns 422."""
        auth_as(client, seed_data["gm"])
        npc_id = seed_data["npc1"].id
        response = client.patch(f"/api/v1/characters/{npc_id}", json={"name": ""})
        assert response.status_code == 422

    def test_update_whitespace_only_name_returns_422(
        self, client: TestClient, seed_data: dict
    ):
        """Updating name to whitespace-only returns 422."""
        auth_as(client, seed_data["gm"])
        npc_id = seed_data["npc1"].id
        response = client.patch(f"/api/v1/characters/{npc_id}", json={"name": "   "})
        assert response.status_code == 422

    def test_unauthenticated_update_returns_401(self, client: TestClient, seed_data: dict):
        """Unauthenticated PATCH returns 401."""
        npc_id = seed_data["npc1"].id
        response = client.patch(
            f"/api/v1/characters/{npc_id}", json={"name": "No Auth"}
        )
        assert response.status_code == 401

    def test_omitted_fields_are_unchanged(self, client: TestClient, seed_data: dict):
        """Omitted fields in PATCH body remain unchanged (exclude_unset semantics)."""
        auth_as(client, seed_data["gm"])

        # Set initial state.
        npc_id = seed_data["npc1"].id
        client.patch(
            f"/api/v1/characters/{npc_id}",
            json={"name": "Original Name", "description": "Original Desc"},
        )

        # Update only notes; name and description should be unchanged.
        response = client.patch(
            f"/api/v1/characters/{npc_id}", json={"notes": "New note only"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "Original Name"
        assert body["description"] == "Original Desc"
        assert body["notes"] == "New note only"


# ---------------------------------------------------------------------------
# DELETE /api/v1/characters/{id}
# ---------------------------------------------------------------------------


class TestDeleteCharacter:
    def test_gm_soft_deletes_character(self, client: TestClient, seed_data: dict):
        """GM can soft-delete a character; returns 204."""
        auth_as(client, seed_data["gm"])
        npc_id = seed_data["npc1"].id
        response = client.delete(f"/api/v1/characters/{npc_id}")
        assert response.status_code == 204
        assert response.content == b""

    def test_deleted_character_hidden_from_list(self, client: TestClient, seed_data: dict):
        """Soft-deleted character no longer appears in the default list."""
        auth_as(client, seed_data["gm"])
        npc_id = seed_data["npc1"].id
        client.delete(f"/api/v1/characters/{npc_id}")

        list_resp = client.get("/api/v1/characters")
        ids = [c["id"] for c in list_resp.json()["items"]]
        assert npc_id not in ids

    def test_deleted_character_accessible_by_direct_get(
        self, client: TestClient, seed_data: dict
    ):
        """After deletion, direct GET still returns the character with is_deleted=true."""
        auth_as(client, seed_data["gm"])
        npc_id = seed_data["npc1"].id
        client.delete(f"/api/v1/characters/{npc_id}")

        get_resp = client.get(f"/api/v1/characters/{npc_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["is_deleted"] is True

    def test_non_gm_cannot_delete_character(self, client: TestClient, seed_data: dict):
        """Non-GM player receives 403 when attempting to delete."""
        auth_as(client, seed_data["player1"])
        npc_id = seed_data["npc1"].id
        response = client.delete(f"/api/v1/characters/{npc_id}")
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "insufficient_role"

    def test_delete_nonexistent_character_returns_404(
        self, client: TestClient, seed_data: dict
    ):
        """DELETE /characters/{id} returns 404 for a non-existent ID."""
        auth_as(client, seed_data["gm"])
        response = client.delete("/api/v1/characters/01DOESNOTEXIST0000000000000")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_unauthenticated_delete_returns_401(self, client: TestClient, seed_data: dict):
        """Unauthenticated DELETE returns 401."""
        npc_id = seed_data["npc1"].id
        response = client.delete(f"/api/v1/characters/{npc_id}")
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Edge cases not covered by the primary CRUD tests above
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_get_malformed_id_returns_404(self, client: TestClient, seed_data: dict):
        """GET with a non-ULID path segment treats it as a missing resource (404).

        The route accepts character_id as a plain str and delegates lookup to
        the service.  A string that cannot possibly match any ULID in the DB
        should result in a 404, not a 500 or 422.
        """
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/characters/not-a-valid-ulid")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_patch_malformed_id_returns_404(self, client: TestClient, seed_data: dict):
        """PATCH with a non-ULID path segment returns 404."""
        auth_as(client, seed_data["gm"])
        response = client.patch(
            "/api/v1/characters/not-a-valid-ulid", json={"name": "Ghost"}
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_delete_malformed_id_returns_404(self, client: TestClient, seed_data: dict):
        """DELETE with a non-ULID path segment returns 404."""
        auth_as(client, seed_data["gm"])
        response = client.delete("/api/v1/characters/not-a-valid-ulid")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_patch_empty_body_is_noop(self, client: TestClient, seed_data: dict):
        """PATCH with an empty JSON object {} is valid; no fields are changed.

        exclude_unset semantics mean that an empty body applies zero updates
        and returns the character unchanged with 200.
        """
        auth_as(client, seed_data["gm"])
        npc_id = seed_data["npc1"].id

        original = client.get(f"/api/v1/characters/{npc_id}").json()
        response = client.patch(f"/api/v1/characters/{npc_id}", json={})

        assert response.status_code == 200
        body = response.json()
        assert body["name"] == original["name"]
        assert body["description"] == original["description"]
        assert body["notes"] == original["notes"]

    def test_list_empty_database_returns_empty_items(
        self, client: TestClient, seed_data: dict
    ):
        """When all characters are soft-deleted the default list returns empty items."""
        auth_as(client, seed_data["gm"])

        # Soft-delete every character in seed data.
        list_resp = client.get("/api/v1/characters").json()
        for char in list_resp["items"]:
            client.delete(f"/api/v1/characters/{char['id']}")

        response = client.get("/api/v1/characters")
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []
        assert body["has_more"] is False
        assert body["next_cursor"] is None

    def test_list_exact_limit_has_no_more(self, client: TestClient, seed_data: dict):
        """When items == limit exactly, has_more is False and next_cursor is None.

        Seed data has 5 characters.  Requesting limit=5 should return all five
        with has_more=False.
        """
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/characters?limit=5")
        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) == 5
        assert body["has_more"] is False
        assert body["next_cursor"] is None

    def test_list_last_page_has_no_cursor(self, client: TestClient, seed_data: dict):
        """The final page of a multi-page traversal has has_more=False and no cursor."""
        auth_as(client, seed_data["gm"])

        # Seed has 5 characters; 2 pages of 3 and 2.
        page1 = client.get("/api/v1/characters?limit=3").json()
        assert page1["has_more"] is True

        page2 = client.get(
            f"/api/v1/characters?limit=3&after={page1['next_cursor']}"
        ).json()
        assert page2["has_more"] is False
        assert page2["next_cursor"] is None
        assert len(page2["items"]) == 2
