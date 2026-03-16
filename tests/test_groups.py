"""Tests for Story 2.1.2 — Group CRUD.

Covers all acceptance criteria:

POST /api/v1/groups
  - GM creates a group with name and tier → 201
  - GM creates a group with all optional fields → 201, fields persisted
  - Non-GM player cannot create → 403
  - Unauthenticated cannot create → 401
  - Missing name → 422
  - Empty name → 422
  - Whitespace-only name → 422
  - Missing tier → 422
  - Negative tier → 422

GET /api/v1/groups
  - Returns paginated list of non-deleted groups
  - Soft-deleted groups excluded by default
  - include_deleted=true reveals soft-deleted groups
  - ULID cursor pagination (after + limit)
  - Unauthenticated → 401
  - Non-GM player can list

GET /api/v1/groups/{id}
  - Returns group detail for non-deleted group
  - Returns group detail for soft-deleted group (is_deleted=true visible)
  - Non-existent ID → 404
  - Unauthenticated → 401

PATCH /api/v1/groups/{id}
  - GM updates name → 200, updated
  - GM updates description → 200, other fields unchanged
  - GM updates notes → 200
  - GM clears description with null → 200, description=null
  - tier is NOT updatable via PATCH (field ignored / not in schema)
  - Non-GM player cannot update → 403
  - Non-existent group → 404
  - Empty name → 422
  - Unauthenticated → 401

DELETE /api/v1/groups/{id}
  - GM soft-deletes a group → 204
  - Group is hidden from list after deletion
  - Group is still accessible by direct GET after deletion
  - Non-GM player cannot delete → 403
  - Non-existent group → 404
  - Unauthenticated → 401
"""

import pytest
from fastapi.testclient import TestClient

from tests.conftest import auth_as


# ---------------------------------------------------------------------------
# POST /api/v1/groups
# ---------------------------------------------------------------------------


class TestCreateGroup:
    def test_gm_creates_group_with_required_fields(
        self, client: TestClient, seed_data: dict
    ):
        """GM can create a group with name and tier; returns 201."""
        auth_as(client, seed_data["gm"])
        response = client.post(
            "/api/v1/groups", json={"name": "The Merchant Guild", "tier": 1}
        )

        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "The Merchant Guild"
        assert body["tier"] == 1
        assert body["description"] is None
        assert body["notes"] is None
        assert body["is_deleted"] is False
        assert "id" in body
        assert "created_at" in body
        assert "updated_at" in body

    def test_gm_creates_group_with_all_fields(
        self, client: TestClient, seed_data: dict
    ):
        """GM can create a group with all optional fields populated."""
        auth_as(client, seed_data["gm"])
        response = client.post(
            "/api/v1/groups",
            json={
                "name": "The Alchemists Circle",
                "description": "A secretive order of potion-makers.",
                "tier": 3,
                "notes": "Operates out of the university district.",
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "The Alchemists Circle"
        assert body["description"] == "A secretive order of potion-makers."
        assert body["tier"] == 3
        assert body["notes"] == "Operates out of the university district."

    def test_gm_creates_group_with_tier_zero(
        self, client: TestClient, seed_data: dict
    ):
        """GM can create a group with tier=0 (minimum allowed value)."""
        auth_as(client, seed_data["gm"])
        response = client.post(
            "/api/v1/groups", json={"name": "New Faction", "tier": 0}
        )

        assert response.status_code == 201
        assert response.json()["tier"] == 0

    def test_non_gm_cannot_create_group(self, client: TestClient, seed_data: dict):
        """Non-GM player receives 403 when attempting to create a group."""
        auth_as(client, seed_data["player1"])
        response = client.post(
            "/api/v1/groups", json={"name": "Should Fail", "tier": 1}
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "insufficient_role"

    def test_unauthenticated_cannot_create_group(
        self, client: TestClient, seed_data: dict
    ):
        """Unauthenticated request to create group receives 401."""
        response = client.post(
            "/api/v1/groups", json={"name": "No Auth", "tier": 1}
        )
        assert response.status_code == 401

    def test_create_group_missing_name_returns_422(
        self, client: TestClient, seed_data: dict
    ):
        """Missing required name field returns 422."""
        auth_as(client, seed_data["gm"])
        response = client.post("/api/v1/groups", json={"tier": 1})
        assert response.status_code == 422

    def test_create_group_empty_name_returns_422(
        self, client: TestClient, seed_data: dict
    ):
        """Empty name returns 422 validation error."""
        auth_as(client, seed_data["gm"])
        response = client.post("/api/v1/groups", json={"name": "", "tier": 1})
        assert response.status_code == 422

    def test_create_group_whitespace_only_name_returns_422(
        self, client: TestClient, seed_data: dict
    ):
        """Whitespace-only name (empty after strip) returns 422."""
        auth_as(client, seed_data["gm"])
        response = client.post("/api/v1/groups", json={"name": "   ", "tier": 1})
        assert response.status_code == 422

    def test_create_group_missing_tier_returns_422(
        self, client: TestClient, seed_data: dict
    ):
        """Missing required tier field returns 422."""
        auth_as(client, seed_data["gm"])
        response = client.post("/api/v1/groups", json={"name": "No Tier"})
        assert response.status_code == 422

    def test_create_group_negative_tier_returns_422(
        self, client: TestClient, seed_data: dict
    ):
        """Negative tier returns 422 validation error."""
        auth_as(client, seed_data["gm"])
        response = client.post(
            "/api/v1/groups", json={"name": "Bad Tier", "tier": -1}
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/v1/groups
# ---------------------------------------------------------------------------


class TestListGroups:
    def test_list_returns_groups(self, client: TestClient, seed_data: dict):
        """Authenticated user can list groups; response has items/next_cursor/has_more."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/groups")

        assert response.status_code == 200
        body = response.json()
        assert "items" in body
        assert "next_cursor" in body
        assert "has_more" in body
        assert isinstance(body["items"], list)

    def test_list_contains_seed_group(self, client: TestClient, seed_data: dict):
        """The seed group ('The Syndicate') appears in the list."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/groups")

        assert response.status_code == 200
        ids = [g["id"] for g in response.json()["items"]]
        assert seed_data["group"].id in ids

    def test_list_excludes_deleted_by_default(self, client: TestClient, seed_data: dict):
        """Soft-deleted groups are excluded from the list by default."""
        auth_as(client, seed_data["gm"])

        # Create and delete a group.
        create_resp = client.post(
            "/api/v1/groups", json={"name": "Soon Deleted", "tier": 1}
        )
        group_id = create_resp.json()["id"]
        client.delete(f"/api/v1/groups/{group_id}")

        # List should not include the deleted group.
        list_resp = client.get("/api/v1/groups")
        ids = [g["id"] for g in list_resp.json()["items"]]
        assert group_id not in ids

    def test_include_deleted_reveals_soft_deleted(
        self, client: TestClient, seed_data: dict
    ):
        """include_deleted=true includes soft-deleted groups in the list."""
        auth_as(client, seed_data["gm"])

        create_resp = client.post(
            "/api/v1/groups", json={"name": "Will Be Deleted", "tier": 1}
        )
        group_id = create_resp.json()["id"]
        client.delete(f"/api/v1/groups/{group_id}")

        list_resp = client.get("/api/v1/groups?include_deleted=true")
        ids = [g["id"] for g in list_resp.json()["items"]]
        assert group_id in ids

    def test_pagination_limit(self, client: TestClient, seed_data: dict):
        """limit parameter caps the page size."""
        auth_as(client, seed_data["gm"])

        # Create 3 more groups so we have at least 4 total (1 from seed + 3).
        for i in range(3):
            client.post(
                "/api/v1/groups", json={"name": f"Extra Group {i}", "tier": 0}
            )

        response = client.get("/api/v1/groups?limit=2")
        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) <= 2

    def test_pagination_cursor(self, client: TestClient, seed_data: dict):
        """After fetching the first page, the cursor returns the next page."""
        auth_as(client, seed_data["gm"])

        # Create 3 more groups so we have 4 total.
        for i in range(3):
            client.post(
                "/api/v1/groups", json={"name": f"Page Group {i}", "tier": 0}
            )

        page1 = client.get("/api/v1/groups?limit=2").json()
        assert len(page1["items"]) == 2
        assert page1["has_more"] is True
        assert page1["next_cursor"] is not None

        page2 = client.get(
            f"/api/v1/groups?limit=2&after={page1['next_cursor']}"
        ).json()
        assert len(page2["items"]) >= 1
        # IDs on page 2 must not appear on page 1.
        page1_ids = {g["id"] for g in page1["items"]}
        page2_ids = {g["id"] for g in page2["items"]}
        assert page1_ids.isdisjoint(page2_ids)

    def test_unauthenticated_list_returns_401(
        self, client: TestClient, seed_data: dict
    ):
        """Unauthenticated request to list groups receives 401."""
        response = client.get("/api/v1/groups")
        assert response.status_code == 401

    def test_player_can_list_groups(self, client: TestClient, seed_data: dict):
        """Non-GM players can also list groups."""
        auth_as(client, seed_data["player1"])
        response = client.get("/api/v1/groups")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/v1/groups/{id}
# ---------------------------------------------------------------------------


class TestGetGroup:
    def test_get_returns_group_detail(self, client: TestClient, seed_data: dict):
        """GET /groups/{id} returns full group detail."""
        auth_as(client, seed_data["gm"])
        group_id = seed_data["group"].id
        response = client.get(f"/api/v1/groups/{group_id}")

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == group_id
        assert body["name"] == "The Syndicate"
        assert body["tier"] == 2
        assert body["is_deleted"] is False

    def test_get_returns_soft_deleted_group(self, client: TestClient, seed_data: dict):
        """GET /groups/{id} returns soft-deleted groups with is_deleted=true."""
        auth_as(client, seed_data["gm"])

        # Create and delete a group.
        create_resp = client.post(
            "/api/v1/groups", json={"name": "Deleted Group", "tier": 1}
        )
        group_id = create_resp.json()["id"]
        client.delete(f"/api/v1/groups/{group_id}")

        # Direct GET should still work.
        get_resp = client.get(f"/api/v1/groups/{group_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["is_deleted"] is True

    def test_get_nonexistent_group_returns_404(
        self, client: TestClient, seed_data: dict
    ):
        """GET /groups/{id} returns 404 for a non-existent ID."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/groups/01DOESNOTEXIST0000000000000")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_unauthenticated_get_returns_401(self, client: TestClient, seed_data: dict):
        """Unauthenticated GET /groups/{id} returns 401."""
        group_id = seed_data["group"].id
        response = client.get(f"/api/v1/groups/{group_id}")
        assert response.status_code == 401

    def test_player_can_get_group_detail(self, client: TestClient, seed_data: dict):
        """Non-GM players can retrieve group detail."""
        auth_as(client, seed_data["player1"])
        group_id = seed_data["group"].id
        response = client.get(f"/api/v1/groups/{group_id}")
        assert response.status_code == 200
        assert response.json()["id"] == group_id


# ---------------------------------------------------------------------------
# PATCH /api/v1/groups/{id}
# ---------------------------------------------------------------------------


class TestUpdateGroup:
    def test_gm_updates_name(self, client: TestClient, seed_data: dict):
        """GM can update a group's name."""
        auth_as(client, seed_data["gm"])
        group_id = seed_data["group"].id
        response = client.patch(
            f"/api/v1/groups/{group_id}", json={"name": "The Grand Syndicate"}
        )
        assert response.status_code == 200
        assert response.json()["name"] == "The Grand Syndicate"

    def test_gm_updates_description(self, client: TestClient, seed_data: dict):
        """GM can update description; other fields stay unchanged."""
        auth_as(client, seed_data["gm"])
        group_id = seed_data["group"].id
        response = client.patch(
            f"/api/v1/groups/{group_id}",
            json={"description": "An influential criminal network."},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["description"] == "An influential criminal network."
        # Name and tier should be unchanged.
        assert body["name"] == "The Syndicate"
        assert body["tier"] == 2

    def test_gm_updates_notes(self, client: TestClient, seed_data: dict):
        """GM can update notes."""
        auth_as(client, seed_data["gm"])
        group_id = seed_data["group"].id
        response = client.patch(
            f"/api/v1/groups/{group_id}",
            json={"notes": "Has contacts in every district."},
        )
        assert response.status_code == 200
        assert response.json()["notes"] == "Has contacts in every district."

    def test_gm_clears_description_with_null(
        self, client: TestClient, seed_data: dict
    ):
        """Sending description=null clears the field."""
        auth_as(client, seed_data["gm"])
        group_id = seed_data["group"].id

        # First set a description.
        client.patch(
            f"/api/v1/groups/{group_id}",
            json={"description": "Some description"},
        )
        # Now clear it.
        response = client.patch(
            f"/api/v1/groups/{group_id}", json={"description": None}
        )
        assert response.status_code == 200
        assert response.json()["description"] is None

    def test_tier_not_updatable_via_patch(self, client: TestClient, seed_data: dict):
        """tier field sent in PATCH body is silently ignored (not in schema)."""
        auth_as(client, seed_data["gm"])
        group_id = seed_data["group"].id
        original_tier = seed_data["group"].tier

        # Attempt to change tier via PATCH — it should not be accepted.
        response = client.patch(
            f"/api/v1/groups/{group_id}", json={"name": "Renamed", "tier": 99}
        )
        # Request succeeds (name update goes through).
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "Renamed"
        # Tier is unchanged because it's not in the update schema.
        assert body["tier"] == original_tier

    def test_non_gm_cannot_update_group(self, client: TestClient, seed_data: dict):
        """Non-GM player receives 403 when attempting to update a group."""
        auth_as(client, seed_data["player1"])
        group_id = seed_data["group"].id
        response = client.patch(
            f"/api/v1/groups/{group_id}", json={"name": "Should Fail"}
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "insufficient_role"

    def test_update_nonexistent_group_returns_404(
        self, client: TestClient, seed_data: dict
    ):
        """PATCH /groups/{id} returns 404 for a non-existent ID."""
        auth_as(client, seed_data["gm"])
        response = client.patch(
            "/api/v1/groups/01DOESNOTEXIST0000000000000",
            json={"name": "Ghost"},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_update_empty_name_returns_422(self, client: TestClient, seed_data: dict):
        """Updating name to an empty string returns 422."""
        auth_as(client, seed_data["gm"])
        group_id = seed_data["group"].id
        response = client.patch(f"/api/v1/groups/{group_id}", json={"name": ""})
        assert response.status_code == 422

    def test_update_whitespace_only_name_returns_422(
        self, client: TestClient, seed_data: dict
    ):
        """Updating name to whitespace-only returns 422."""
        auth_as(client, seed_data["gm"])
        group_id = seed_data["group"].id
        response = client.patch(
            f"/api/v1/groups/{group_id}", json={"name": "   "}
        )
        assert response.status_code == 422

    def test_unauthenticated_update_returns_401(
        self, client: TestClient, seed_data: dict
    ):
        """Unauthenticated PATCH returns 401."""
        group_id = seed_data["group"].id
        response = client.patch(
            f"/api/v1/groups/{group_id}", json={"name": "No Auth"}
        )
        assert response.status_code == 401

    def test_omitted_fields_are_unchanged(self, client: TestClient, seed_data: dict):
        """Omitted fields in PATCH body remain unchanged (exclude_unset semantics)."""
        auth_as(client, seed_data["gm"])
        group_id = seed_data["group"].id

        # Set initial state.
        client.patch(
            f"/api/v1/groups/{group_id}",
            json={"name": "Original Name", "description": "Original Desc"},
        )

        # Update only notes; name and description should be unchanged.
        response = client.patch(
            f"/api/v1/groups/{group_id}", json={"notes": "New note only"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "Original Name"
        assert body["description"] == "Original Desc"
        assert body["notes"] == "New note only"

    def test_patch_empty_body_is_noop(self, client: TestClient, seed_data: dict):
        """PATCH with an empty JSON object {} is valid; no fields are changed."""
        auth_as(client, seed_data["gm"])
        group_id = seed_data["group"].id

        original = client.get(f"/api/v1/groups/{group_id}").json()
        response = client.patch(f"/api/v1/groups/{group_id}", json={})

        assert response.status_code == 200
        body = response.json()
        assert body["name"] == original["name"]
        assert body["description"] == original["description"]
        assert body["notes"] == original["notes"]
        assert body["tier"] == original["tier"]


# ---------------------------------------------------------------------------
# DELETE /api/v1/groups/{id}
# ---------------------------------------------------------------------------


class TestDeleteGroup:
    def test_gm_soft_deletes_group(self, client: TestClient, seed_data: dict):
        """GM can soft-delete a group; returns 204."""
        auth_as(client, seed_data["gm"])
        group_id = seed_data["group"].id
        response = client.delete(f"/api/v1/groups/{group_id}")
        assert response.status_code == 204
        assert response.content == b""

    def test_deleted_group_hidden_from_list(self, client: TestClient, seed_data: dict):
        """Soft-deleted group no longer appears in the default list."""
        auth_as(client, seed_data["gm"])
        group_id = seed_data["group"].id
        client.delete(f"/api/v1/groups/{group_id}")

        list_resp = client.get("/api/v1/groups")
        ids = [g["id"] for g in list_resp.json()["items"]]
        assert group_id not in ids

    def test_deleted_group_accessible_by_direct_get(
        self, client: TestClient, seed_data: dict
    ):
        """After deletion, direct GET still returns the group with is_deleted=true."""
        auth_as(client, seed_data["gm"])
        group_id = seed_data["group"].id
        client.delete(f"/api/v1/groups/{group_id}")

        get_resp = client.get(f"/api/v1/groups/{group_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["is_deleted"] is True

    def test_non_gm_cannot_delete_group(self, client: TestClient, seed_data: dict):
        """Non-GM player receives 403 when attempting to delete."""
        auth_as(client, seed_data["player1"])
        group_id = seed_data["group"].id
        response = client.delete(f"/api/v1/groups/{group_id}")
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "insufficient_role"

    def test_delete_nonexistent_group_returns_404(
        self, client: TestClient, seed_data: dict
    ):
        """DELETE /groups/{id} returns 404 for a non-existent ID."""
        auth_as(client, seed_data["gm"])
        response = client.delete("/api/v1/groups/01DOESNOTEXIST0000000000000")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_unauthenticated_delete_returns_401(
        self, client: TestClient, seed_data: dict
    ):
        """Unauthenticated DELETE returns 401."""
        group_id = seed_data["group"].id
        response = client.delete(f"/api/v1/groups/{group_id}")
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_get_malformed_id_returns_404(self, client: TestClient, seed_data: dict):
        """GET with a non-ULID path segment treats it as a missing resource (404)."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/groups/not-a-valid-ulid")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_patch_malformed_id_returns_404(self, client: TestClient, seed_data: dict):
        """PATCH with a non-ULID path segment returns 404."""
        auth_as(client, seed_data["gm"])
        response = client.patch(
            "/api/v1/groups/not-a-valid-ulid", json={"name": "Ghost"}
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_delete_malformed_id_returns_404(
        self, client: TestClient, seed_data: dict
    ):
        """DELETE with a non-ULID path segment returns 404."""
        auth_as(client, seed_data["gm"])
        response = client.delete("/api/v1/groups/not-a-valid-ulid")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_list_empty_returns_empty_items(
        self, client: TestClient, seed_data: dict
    ):
        """When all groups are soft-deleted the default list returns empty items."""
        auth_as(client, seed_data["gm"])

        # Soft-delete every group in seed data.
        list_resp = client.get("/api/v1/groups").json()
        for group in list_resp["items"]:
            client.delete(f"/api/v1/groups/{group['id']}")

        response = client.get("/api/v1/groups")
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []
        assert body["has_more"] is False
        assert body["next_cursor"] is None

    def test_response_includes_tier_field(self, client: TestClient, seed_data: dict):
        """Group response always includes the tier field."""
        auth_as(client, seed_data["gm"])
        group_id = seed_data["group"].id
        response = client.get(f"/api/v1/groups/{group_id}")

        assert response.status_code == 200
        body = response.json()
        assert "tier" in body
        assert isinstance(body["tier"], int)
