"""Tests for Story 2.2.2 — Story CRUD + Owners.

Covers all acceptance criteria:

POST /api/v1/stories
  - GM creates a story with name only → 201, status=active
  - GM creates a story with all optional fields → 201, fields persisted
  - Non-GM player cannot create → 403
  - Unauthenticated cannot create → 401
  - Empty name → 422
  - Missing name → 422
  - Invalid status → 422
  - parent_id references non-existent story → 404

GET /api/v1/stories
  - Returns paginated list of non-deleted stories
  - Soft-deleted stories excluded by default
  - include_deleted=true reveals soft-deleted stories
  - Filter: ?status=active returns only active stories
  - Filter: ?status=completed returns only completed stories
  - Filter: ?tag=<string> returns only stories with that tag
  - Filter: ?owner=<type>:<id> returns only stories with that owner
  - Invalid status filter → 422
  - Invalid owner format → 422
  - Invalid owner type → 422
  - ULID cursor pagination (after + limit)
  - Unauthenticated → 401

GET /api/v1/stories/{id}
  - Returns story detail with owners and entries
  - Soft-deleted entries excluded from detail
  - Returns soft-deleted story with is_deleted=true
  - Non-existent ID → 404
  - Unauthenticated → 401

PATCH /api/v1/stories/{id}
  - GM updates name → 200, updated
  - GM updates status → 200
  - GM updates tags → 200
  - GM updates visibility_level → 200
  - GM updates visibility_overrides → 200
  - GM clears summary with null → 200, summary=null
  - Omitted fields are unchanged
  - Non-GM player cannot update → 403
  - Non-existent story → 404
  - Empty name → 422
  - Unauthenticated → 401

DELETE /api/v1/stories/{id}
  - GM soft-deletes a story → 204
  - Story hidden from list after deletion
  - Story still accessible by direct GET after deletion
  - Non-GM player cannot delete → 403
  - Non-existent story → 404
  - Unauthenticated → 401

POST /api/v1/stories/{id}/owners
  - GM adds a character as owner → 201
  - GM adds a group as owner → 201
  - GM adds a location as owner → 201
  - Mixed owner types on same story → both visible in detail
  - Referenced game object not found → 404
  - Story not found → 404
  - Duplicate owner → 409
  - Non-GM cannot add owner → 403
  - Unauthenticated → 401

DELETE /api/v1/stories/{id}/owners/{type}/{owner_id}
  - GM removes an owner → 204
  - Owner not on story → 404
  - Story not found → 404
  - Invalid owner type → 422
  - Non-GM cannot remove owner → 403
  - Unauthenticated → 401
"""

import pytest
from fastapi.testclient import TestClient

from tests.conftest import auth_as


# ---------------------------------------------------------------------------
# POST /api/v1/stories
# ---------------------------------------------------------------------------


class TestCreateStory:
    def test_gm_creates_story_with_name_only(self, client: TestClient, seed_data: dict):
        """GM can create a story with just a name; returns 201 with status=active."""
        auth_as(client, seed_data["gm"])
        response = client.post("/api/v1/stories", json={"name": "The Syndicate Plot"})

        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "The Syndicate Plot"
        assert body["status"] == "active"
        assert body["summary"] is None
        assert body["parent_id"] is None
        assert body["tags"] is None
        assert body["visibility_level"] is None
        assert body["visibility_overrides"] is None
        assert body["is_deleted"] is False
        assert "id" in body
        assert "created_at" in body
        assert "updated_at" in body

    def test_gm_creates_story_with_all_fields(self, client: TestClient, seed_data: dict):
        """GM can create a story with all optional fields populated."""
        auth_as(client, seed_data["gm"])
        response = client.post(
            "/api/v1/stories",
            json={
                "name": "The Harbour Conspiracy",
                "summary": "A web of smugglers operating out of Old Quarter.",
                "status": "completed",
                "tags": ["crime", "harbour", "mystery"],
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "The Harbour Conspiracy"
        assert body["summary"] == "A web of smugglers operating out of Old Quarter."
        assert body["status"] == "completed"
        assert body["tags"] == ["crime", "harbour", "mystery"]

    def test_gm_creates_story_with_parent(self, client: TestClient, seed_data: dict):
        """GM can create a sub-arc story referencing a parent story."""
        auth_as(client, seed_data["gm"])
        parent_resp = client.post("/api/v1/stories", json={"name": "Main Arc"})
        parent_id = parent_resp.json()["id"]

        response = client.post(
            "/api/v1/stories",
            json={"name": "Sub Arc", "parent_id": parent_id},
        )
        assert response.status_code == 201
        assert response.json()["parent_id"] == parent_id

    def test_create_story_invalid_parent_returns_422(
        self, client: TestClient, seed_data: dict
    ):
        """parent_id referencing a non-existent story returns 422."""
        auth_as(client, seed_data["gm"])
        response = client.post(
            "/api/v1/stories",
            json={"name": "Orphan", "parent_id": "01DOESNOTEXIST0000000000000"},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    def test_non_gm_cannot_create_story(self, client: TestClient, seed_data: dict):
        """Non-GM player receives 403 when attempting to create a story."""
        auth_as(client, seed_data["player1"])
        response = client.post("/api/v1/stories", json={"name": "Should Fail"})
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "insufficient_role"

    def test_unauthenticated_cannot_create_story(self, client: TestClient, seed_data: dict):
        """Unauthenticated request to create story receives 401."""
        response = client.post("/api/v1/stories", json={"name": "No Auth"})
        assert response.status_code == 401

    def test_create_story_empty_name_returns_422(
        self, client: TestClient, seed_data: dict
    ):
        """Empty name returns 422 validation error."""
        auth_as(client, seed_data["gm"])
        response = client.post("/api/v1/stories", json={"name": ""})
        assert response.status_code == 422

    def test_create_story_whitespace_only_name_returns_422(
        self, client: TestClient, seed_data: dict
    ):
        """Whitespace-only name returns 422."""
        auth_as(client, seed_data["gm"])
        response = client.post("/api/v1/stories", json={"name": "   "})
        assert response.status_code == 422

    def test_create_story_missing_name_returns_422(
        self, client: TestClient, seed_data: dict
    ):
        """Missing required name field returns 422."""
        auth_as(client, seed_data["gm"])
        response = client.post("/api/v1/stories", json={"summary": "No name"})
        assert response.status_code == 422

    def test_create_story_invalid_status_returns_422(
        self, client: TestClient, seed_data: dict
    ):
        """Invalid status value returns 422."""
        auth_as(client, seed_data["gm"])
        response = client.post(
            "/api/v1/stories", json={"name": "Bad Status", "status": "deleted"}
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/v1/stories
# ---------------------------------------------------------------------------


class TestListStories:
    def test_list_returns_stories(self, client: TestClient, seed_data: dict):
        """Authenticated user can list stories; response has items/next_cursor/has_more."""
        auth_as(client, seed_data["gm"])
        client.post("/api/v1/stories", json={"name": "Story A"})
        response = client.get("/api/v1/stories")

        assert response.status_code == 200
        body = response.json()
        assert "items" in body
        assert "next_cursor" in body
        assert "has_more" in body
        assert isinstance(body["items"], list)

    def test_list_excludes_deleted_by_default(self, client: TestClient, seed_data: dict):
        """Soft-deleted stories are excluded from the list by default."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post("/api/v1/stories", json={"name": "Will Be Deleted"})
        story_id = create_resp.json()["id"]
        client.delete(f"/api/v1/stories/{story_id}")

        list_resp = client.get("/api/v1/stories")
        ids = [s["id"] for s in list_resp.json()["items"]]
        assert story_id not in ids

    def test_include_deleted_reveals_soft_deleted(self, client: TestClient, seed_data: dict):
        """include_deleted=true includes soft-deleted stories in the list."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post("/api/v1/stories", json={"name": "Deleted Story"})
        story_id = create_resp.json()["id"]
        client.delete(f"/api/v1/stories/{story_id}")

        list_resp = client.get("/api/v1/stories?include_deleted=true")
        ids = [s["id"] for s in list_resp.json()["items"]]
        assert story_id in ids

    def test_filter_status_active(self, client: TestClient, seed_data: dict):
        """?status=active returns only active stories."""
        auth_as(client, seed_data["gm"])
        client.post("/api/v1/stories", json={"name": "Active Arc", "status": "active"})
        client.post(
            "/api/v1/stories", json={"name": "Completed Arc", "status": "completed"}
        )

        response = client.get("/api/v1/stories?status=active")
        assert response.status_code == 200
        items = response.json()["items"]
        assert all(s["status"] == "active" for s in items)

    def test_filter_status_completed(self, client: TestClient, seed_data: dict):
        """?status=completed returns only completed stories."""
        auth_as(client, seed_data["gm"])
        client.post("/api/v1/stories", json={"name": "Active Arc", "status": "active"})
        client.post(
            "/api/v1/stories", json={"name": "Completed Arc", "status": "completed"}
        )

        response = client.get("/api/v1/stories?status=completed")
        assert response.status_code == 200
        items = response.json()["items"]
        assert all(s["status"] == "completed" for s in items)
        assert len(items) == 1
        assert items[0]["name"] == "Completed Arc"

    def test_filter_status_invalid_returns_422(self, client: TestClient, seed_data: dict):
        """Invalid status filter value returns 422."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/stories?status=invalid")
        assert response.status_code == 422

    def test_filter_tag(self, client: TestClient, seed_data: dict):
        """?tag=<string> returns only stories that contain that tag."""
        auth_as(client, seed_data["gm"])
        client.post(
            "/api/v1/stories",
            json={"name": "Tagged Story", "tags": ["political", "intrigue"]},
        )
        client.post(
            "/api/v1/stories",
            json={"name": "Untagged Story", "tags": ["combat"]},
        )
        client.post("/api/v1/stories", json={"name": "No Tags Story"})

        response = client.get("/api/v1/stories?tag=political")
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["name"] == "Tagged Story"

    def test_filter_tag_no_match(self, client: TestClient, seed_data: dict):
        """?tag filter with no match returns empty list."""
        auth_as(client, seed_data["gm"])
        client.post("/api/v1/stories", json={"name": "Story", "tags": ["combat"]})

        response = client.get("/api/v1/stories?tag=zzznomatch")
        assert response.status_code == 200
        assert response.json()["items"] == []

    def test_filter_owner_character(self, client: TestClient, seed_data: dict):
        """?owner=character:<id> returns only stories owned by that character."""
        auth_as(client, seed_data["gm"])
        pc_id = seed_data["pc1"].id

        # Create two stories; add owner to only the first.
        story1_resp = client.post("/api/v1/stories", json={"name": "PC1 Story"})
        story1_id = story1_resp.json()["id"]
        client.post(
            f"/api/v1/stories/{story1_id}/owners",
            json={"type": "character", "id": pc_id},
        )
        client.post("/api/v1/stories", json={"name": "Unowned Story"})

        response = client.get(f"/api/v1/stories?owner=character:{pc_id}")
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == story1_id

    def test_filter_owner_group(self, client: TestClient, seed_data: dict):
        """?owner=group:<id> returns only stories owned by that group."""
        auth_as(client, seed_data["gm"])
        group_id = seed_data["group"].id

        story_resp = client.post("/api/v1/stories", json={"name": "Group Story"})
        story_id = story_resp.json()["id"]
        client.post(
            f"/api/v1/stories/{story_id}/owners",
            json={"type": "group", "id": group_id},
        )
        client.post("/api/v1/stories", json={"name": "Unowned Story"})

        response = client.get(f"/api/v1/stories?owner=group:{group_id}")
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == story_id

    def test_filter_owner_invalid_format_returns_422(
        self, client: TestClient, seed_data: dict
    ):
        """?owner with no colon separator returns 422."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/stories?owner=characternocolon")
        assert response.status_code == 422

    def test_filter_owner_invalid_type_returns_422(
        self, client: TestClient, seed_data: dict
    ):
        """?owner with unknown type returns 422."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/stories?owner=unknown:01HXYZ")
        assert response.status_code == 422

    def test_pagination_limit(self, client: TestClient, seed_data: dict):
        """limit parameter caps the page size."""
        auth_as(client, seed_data["gm"])
        for i in range(5):
            client.post("/api/v1/stories", json={"name": f"Story {i}"})

        response = client.get("/api/v1/stories?limit=2")
        assert response.status_code == 200
        assert len(response.json()["items"]) <= 2

    def test_pagination_cursor(self, client: TestClient, seed_data: dict):
        """After fetching the first page, the cursor returns the next page."""
        auth_as(client, seed_data["gm"])
        for i in range(5):
            client.post("/api/v1/stories", json={"name": f"Arc {i}"})

        page1 = client.get("/api/v1/stories?limit=2").json()
        assert len(page1["items"]) == 2
        assert page1["has_more"] is True
        assert page1["next_cursor"] is not None

        page2 = client.get(
            f"/api/v1/stories?limit=2&after={page1['next_cursor']}"
        ).json()
        page1_ids = {s["id"] for s in page1["items"]}
        page2_ids = {s["id"] for s in page2["items"]}
        assert page1_ids.isdisjoint(page2_ids)

    def test_unauthenticated_list_returns_401(self, client: TestClient, seed_data: dict):
        """Unauthenticated request to list stories receives 401."""
        response = client.get("/api/v1/stories")
        assert response.status_code == 401

    def test_player_can_list_stories(self, client: TestClient, seed_data: dict):
        """Non-GM players can list stories; stories they can see appear in the list."""
        auth_as(client, seed_data["gm"])
        # Create a global story so player1 can see at least one item.
        resp = client.post("/api/v1/stories", json={"name": "Global Story"})
        story_id = resp.json()["id"]
        client.patch(f"/api/v1/stories/{story_id}", json={"visibility_level": "global"})

        auth_as(client, seed_data["player1"])
        response = client.get("/api/v1/stories")
        assert response.status_code == 200
        ids = [s["id"] for s in response.json()["items"]]
        assert story_id in ids


# ---------------------------------------------------------------------------
# GET /api/v1/stories/{id}
# ---------------------------------------------------------------------------


class TestGetStory:
    def test_get_returns_story_detail_with_owners_and_entries(
        self, client: TestClient, seed_data: dict
    ):
        """GET /stories/{id} returns full detail including owners list and entries."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post(
            "/api/v1/stories",
            json={"name": "Full Detail Story", "summary": "A tale."},
        )
        story_id = create_resp.json()["id"]

        response = client.get(f"/api/v1/stories/{story_id}")
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == story_id
        assert body["name"] == "Full Detail Story"
        assert body["summary"] == "A tale."
        assert "owners" in body
        assert "entries" in body
        assert isinstance(body["owners"], list)
        assert isinstance(body["entries"], list)
        assert body["owners"] == []
        assert body["entries"] == []

    def test_get_detail_shows_owners(self, client: TestClient, seed_data: dict):
        """Detail endpoint shows owners added to the story."""
        auth_as(client, seed_data["gm"])
        story_resp = client.post("/api/v1/stories", json={"name": "Owned Story"})
        story_id = story_resp.json()["id"]
        pc_id = seed_data["pc1"].id

        client.post(
            f"/api/v1/stories/{story_id}/owners",
            json={"type": "character", "id": pc_id},
        )

        detail = client.get(f"/api/v1/stories/{story_id}").json()
        assert len(detail["owners"]) == 1
        assert detail["owners"][0]["type"] == "character"
        assert detail["owners"][0]["id"] == pc_id

    def test_get_returns_soft_deleted_story(self, client: TestClient, seed_data: dict):
        """GET /stories/{id} returns soft-deleted stories with is_deleted=true."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post("/api/v1/stories", json={"name": "Will Be Deleted"})
        story_id = create_resp.json()["id"]
        client.delete(f"/api/v1/stories/{story_id}")

        get_resp = client.get(f"/api/v1/stories/{story_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["is_deleted"] is True

    def test_get_nonexistent_story_returns_404(
        self, client: TestClient, seed_data: dict
    ):
        """GET /stories/{id} returns 404 for a non-existent ID."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/stories/01DOESNOTEXIST0000000000000")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_unauthenticated_get_returns_401(self, client: TestClient, seed_data: dict):
        """Unauthenticated GET /stories/{id} returns 401."""
        auth_as(client, seed_data["gm"])
        story_resp = client.post("/api/v1/stories", json={"name": "Test"})
        story_id = story_resp.json()["id"]
        # Clear auth cookie.
        client.cookies.clear()
        response = client.get(f"/api/v1/stories/{story_id}")
        assert response.status_code == 401

    def test_player_can_get_story_detail(self, client: TestClient, seed_data: dict):
        """Non-GM players can retrieve story detail when they have visibility."""
        auth_as(client, seed_data["gm"])
        story_resp = client.post("/api/v1/stories", json={"name": "Global Story"})
        story_id = story_resp.json()["id"]
        # Set global visibility so all players can see this story.
        client.patch(f"/api/v1/stories/{story_id}", json={"visibility_level": "global"})

        auth_as(client, seed_data["player1"])
        response = client.get(f"/api/v1/stories/{story_id}")
        assert response.status_code == 200
        assert response.json()["id"] == story_id


# ---------------------------------------------------------------------------
# PATCH /api/v1/stories/{id}
# ---------------------------------------------------------------------------


class TestUpdateStory:
    def test_gm_updates_name(self, client: TestClient, seed_data: dict):
        """GM can update a story's name."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post("/api/v1/stories", json={"name": "Old Name"})
        story_id = create_resp.json()["id"]

        response = client.patch(
            f"/api/v1/stories/{story_id}", json={"name": "New Name"}
        )
        assert response.status_code == 200
        assert response.json()["name"] == "New Name"

    def test_gm_updates_status(self, client: TestClient, seed_data: dict):
        """GM can update status to any valid value."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post("/api/v1/stories", json={"name": "Status Test"})
        story_id = create_resp.json()["id"]

        response = client.patch(
            f"/api/v1/stories/{story_id}", json={"status": "completed"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "completed"

        response = client.patch(
            f"/api/v1/stories/{story_id}", json={"status": "abandoned"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "abandoned"

        # Can set back to active freely.
        response = client.patch(
            f"/api/v1/stories/{story_id}", json={"status": "active"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "active"

    def test_gm_updates_tags(self, client: TestClient, seed_data: dict):
        """GM can update the tags list."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post(
            "/api/v1/stories", json={"name": "Tagged", "tags": ["old"]}
        )
        story_id = create_resp.json()["id"]

        response = client.patch(
            f"/api/v1/stories/{story_id}", json={"tags": ["new", "updated"]}
        )
        assert response.status_code == 200
        assert response.json()["tags"] == ["new", "updated"]

    def test_gm_updates_visibility_level(self, client: TestClient, seed_data: dict):
        """GM can update visibility_level."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post("/api/v1/stories", json={"name": "Visibility Test"})
        story_id = create_resp.json()["id"]

        response = client.patch(
            f"/api/v1/stories/{story_id}", json={"visibility_level": "gm_only"}
        )
        assert response.status_code == 200
        assert response.json()["visibility_level"] == "gm_only"

    def test_gm_updates_visibility_overrides(self, client: TestClient, seed_data: dict):
        """GM can update visibility_overrides."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post("/api/v1/stories", json={"name": "Override Test"})
        story_id = create_resp.json()["id"]
        player_id = seed_data["player1"].id

        response = client.patch(
            f"/api/v1/stories/{story_id}",
            json={"visibility_overrides": [player_id]},
        )
        assert response.status_code == 200
        assert response.json()["visibility_overrides"] == [player_id]

    def test_gm_clears_summary_with_null(self, client: TestClient, seed_data: dict):
        """Sending summary=null clears the field."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post(
            "/api/v1/stories",
            json={"name": "With Summary", "summary": "Some summary"},
        )
        story_id = create_resp.json()["id"]

        response = client.patch(
            f"/api/v1/stories/{story_id}", json={"summary": None}
        )
        assert response.status_code == 200
        assert response.json()["summary"] is None

    def test_omitted_fields_are_unchanged(self, client: TestClient, seed_data: dict):
        """Omitted fields in PATCH body remain unchanged."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post(
            "/api/v1/stories",
            json={"name": "Original Name", "summary": "Original Summary"},
        )
        story_id = create_resp.json()["id"]

        response = client.patch(
            f"/api/v1/stories/{story_id}", json={"status": "completed"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "Original Name"
        assert body["summary"] == "Original Summary"
        assert body["status"] == "completed"

    def test_patch_empty_body_is_noop(self, client: TestClient, seed_data: dict):
        """PATCH with empty body {} returns 200 with no changes."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post("/api/v1/stories", json={"name": "Noop Story"})
        story_id = create_resp.json()["id"]

        original = client.get(f"/api/v1/stories/{story_id}").json()
        response = client.patch(f"/api/v1/stories/{story_id}", json={})
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == original["name"]
        assert body["status"] == original["status"]

    def test_non_gm_cannot_update_story(self, client: TestClient, seed_data: dict):
        """Non-GM player receives 403 when attempting to update a story."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post("/api/v1/stories", json={"name": "GM Story"})
        story_id = create_resp.json()["id"]

        auth_as(client, seed_data["player1"])
        response = client.patch(
            f"/api/v1/stories/{story_id}", json={"name": "Unauthorized"}
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "insufficient_role"

    def test_update_nonexistent_story_returns_404(
        self, client: TestClient, seed_data: dict
    ):
        """PATCH /stories/{id} returns 404 for a non-existent ID."""
        auth_as(client, seed_data["gm"])
        response = client.patch(
            "/api/v1/stories/01DOESNOTEXIST0000000000000",
            json={"name": "Ghost"},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_update_empty_name_returns_422(self, client: TestClient, seed_data: dict):
        """Updating name to an empty string returns 422."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post("/api/v1/stories", json={"name": "Valid Name"})
        story_id = create_resp.json()["id"]

        response = client.patch(f"/api/v1/stories/{story_id}", json={"name": ""})
        assert response.status_code == 422

    def test_unauthenticated_update_returns_401(
        self, client: TestClient, seed_data: dict
    ):
        """Unauthenticated PATCH returns 401."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post("/api/v1/stories", json={"name": "Story"})
        story_id = create_resp.json()["id"]
        client.cookies.clear()

        response = client.patch(f"/api/v1/stories/{story_id}", json={"name": "No Auth"})
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/v1/stories/{id}
# ---------------------------------------------------------------------------


class TestDeleteStory:
    def test_gm_soft_deletes_story(self, client: TestClient, seed_data: dict):
        """GM can soft-delete a story; returns 204."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post("/api/v1/stories", json={"name": "To Delete"})
        story_id = create_resp.json()["id"]

        response = client.delete(f"/api/v1/stories/{story_id}")
        assert response.status_code == 204
        assert response.content == b""

    def test_deleted_story_hidden_from_list(self, client: TestClient, seed_data: dict):
        """Soft-deleted story no longer appears in the default list."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post("/api/v1/stories", json={"name": "Going Away"})
        story_id = create_resp.json()["id"]
        client.delete(f"/api/v1/stories/{story_id}")

        list_resp = client.get("/api/v1/stories")
        ids = [s["id"] for s in list_resp.json()["items"]]
        assert story_id not in ids

    def test_deleted_story_accessible_by_direct_get(
        self, client: TestClient, seed_data: dict
    ):
        """After deletion, direct GET still returns the story with is_deleted=true."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post("/api/v1/stories", json={"name": "Archived Arc"})
        story_id = create_resp.json()["id"]
        client.delete(f"/api/v1/stories/{story_id}")

        get_resp = client.get(f"/api/v1/stories/{story_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["is_deleted"] is True

    def test_non_gm_cannot_delete_story(self, client: TestClient, seed_data: dict):
        """Non-GM player receives 403 when attempting to delete."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post("/api/v1/stories", json={"name": "Protected Story"})
        story_id = create_resp.json()["id"]

        auth_as(client, seed_data["player1"])
        response = client.delete(f"/api/v1/stories/{story_id}")
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "insufficient_role"

    def test_delete_nonexistent_story_returns_404(
        self, client: TestClient, seed_data: dict
    ):
        """DELETE /stories/{id} returns 404 for a non-existent ID."""
        auth_as(client, seed_data["gm"])
        response = client.delete("/api/v1/stories/01DOESNOTEXIST0000000000000")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_unauthenticated_delete_returns_401(
        self, client: TestClient, seed_data: dict
    ):
        """Unauthenticated DELETE returns 401."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post("/api/v1/stories", json={"name": "Story"})
        story_id = create_resp.json()["id"]
        client.cookies.clear()

        response = client.delete(f"/api/v1/stories/{story_id}")
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/v1/stories/{id}/owners
# ---------------------------------------------------------------------------


class TestAddOwner:
    def test_gm_adds_character_as_owner(self, client: TestClient, seed_data: dict):
        """GM can add a character as owner; returns 201 with type and id."""
        auth_as(client, seed_data["gm"])
        story_resp = client.post("/api/v1/stories", json={"name": "Character Story"})
        story_id = story_resp.json()["id"]
        pc_id = seed_data["pc1"].id

        response = client.post(
            f"/api/v1/stories/{story_id}/owners",
            json={"type": "character", "id": pc_id},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["type"] == "character"
        assert body["id"] == pc_id

    def test_gm_adds_group_as_owner(self, client: TestClient, seed_data: dict):
        """GM can add a group as owner."""
        auth_as(client, seed_data["gm"])
        story_resp = client.post("/api/v1/stories", json={"name": "Group Story"})
        story_id = story_resp.json()["id"]
        group_id = seed_data["group"].id

        response = client.post(
            f"/api/v1/stories/{story_id}/owners",
            json={"type": "group", "id": group_id},
        )
        assert response.status_code == 201
        assert response.json()["type"] == "group"
        assert response.json()["id"] == group_id

    def test_gm_adds_location_as_owner(self, client: TestClient, seed_data: dict):
        """GM can add a location as owner."""
        auth_as(client, seed_data["gm"])
        story_resp = client.post("/api/v1/stories", json={"name": "Location Story"})
        story_id = story_resp.json()["id"]
        region_id = seed_data["region"].id

        response = client.post(
            f"/api/v1/stories/{story_id}/owners",
            json={"type": "location", "id": region_id},
        )
        assert response.status_code == 201
        assert response.json()["type"] == "location"
        assert response.json()["id"] == region_id

    def test_mixed_owner_types_on_same_story(self, client: TestClient, seed_data: dict):
        """Multiple owners of different types can be added to the same story."""
        auth_as(client, seed_data["gm"])
        story_resp = client.post("/api/v1/stories", json={"name": "Multi-Owner Story"})
        story_id = story_resp.json()["id"]
        pc_id = seed_data["pc1"].id
        group_id = seed_data["group"].id
        region_id = seed_data["region"].id

        client.post(
            f"/api/v1/stories/{story_id}/owners",
            json={"type": "character", "id": pc_id},
        )
        client.post(
            f"/api/v1/stories/{story_id}/owners",
            json={"type": "group", "id": group_id},
        )
        client.post(
            f"/api/v1/stories/{story_id}/owners",
            json={"type": "location", "id": region_id},
        )

        detail = client.get(f"/api/v1/stories/{story_id}").json()
        owner_entries = {(o["type"], o["id"]) for o in detail["owners"]}
        assert ("character", pc_id) in owner_entries
        assert ("group", group_id) in owner_entries
        assert ("location", region_id) in owner_entries

    def test_add_owner_story_not_found_returns_404(
        self, client: TestClient, seed_data: dict
    ):
        """Returns 404 if the story does not exist."""
        auth_as(client, seed_data["gm"])
        response = client.post(
            "/api/v1/stories/01DOESNOTEXIST0000000000000/owners",
            json={"type": "character", "id": seed_data["pc1"].id},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_add_owner_game_object_not_found_returns_404(
        self, client: TestClient, seed_data: dict
    ):
        """Returns 404 if the referenced game object does not exist."""
        auth_as(client, seed_data["gm"])
        story_resp = client.post("/api/v1/stories", json={"name": "Story"})
        story_id = story_resp.json()["id"]

        response = client.post(
            f"/api/v1/stories/{story_id}/owners",
            json={"type": "character", "id": "01DOESNOTEXIST0000000000000"},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_add_duplicate_owner_returns_409(
        self, client: TestClient, seed_data: dict
    ):
        """Adding the same owner twice returns 409 Conflict."""
        auth_as(client, seed_data["gm"])
        story_resp = client.post("/api/v1/stories", json={"name": "Story"})
        story_id = story_resp.json()["id"]
        pc_id = seed_data["pc1"].id

        client.post(
            f"/api/v1/stories/{story_id}/owners",
            json={"type": "character", "id": pc_id},
        )
        response = client.post(
            f"/api/v1/stories/{story_id}/owners",
            json={"type": "character", "id": pc_id},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "conflict"

    def test_non_gm_cannot_add_owner(self, client: TestClient, seed_data: dict):
        """Non-GM player cannot add owners."""
        auth_as(client, seed_data["gm"])
        story_resp = client.post("/api/v1/stories", json={"name": "Story"})
        story_id = story_resp.json()["id"]

        auth_as(client, seed_data["player1"])
        response = client.post(
            f"/api/v1/stories/{story_id}/owners",
            json={"type": "character", "id": seed_data["pc1"].id},
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "insufficient_role"

    def test_unauthenticated_add_owner_returns_401(
        self, client: TestClient, seed_data: dict
    ):
        """Unauthenticated request to add owner returns 401."""
        auth_as(client, seed_data["gm"])
        story_resp = client.post("/api/v1/stories", json={"name": "Story"})
        story_id = story_resp.json()["id"]
        client.cookies.clear()

        response = client.post(
            f"/api/v1/stories/{story_id}/owners",
            json={"type": "character", "id": seed_data["pc1"].id},
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/v1/stories/{id}/owners/{type}/{owner_id}
# ---------------------------------------------------------------------------


class TestRemoveOwner:
    def test_gm_removes_owner(self, client: TestClient, seed_data: dict):
        """GM can remove an owner; returns 204."""
        auth_as(client, seed_data["gm"])
        story_resp = client.post("/api/v1/stories", json={"name": "Story"})
        story_id = story_resp.json()["id"]
        pc_id = seed_data["pc1"].id

        client.post(
            f"/api/v1/stories/{story_id}/owners",
            json={"type": "character", "id": pc_id},
        )

        response = client.delete(
            f"/api/v1/stories/{story_id}/owners/character/{pc_id}"
        )
        assert response.status_code == 204
        assert response.content == b""

        # Owner should no longer appear in detail.
        detail = client.get(f"/api/v1/stories/{story_id}").json()
        owner_ids = [o["id"] for o in detail["owners"]]
        assert pc_id not in owner_ids

    def test_remove_owner_not_on_story_returns_404(
        self, client: TestClient, seed_data: dict
    ):
        """Returns 404 if the owner is not on the story."""
        auth_as(client, seed_data["gm"])
        story_resp = client.post("/api/v1/stories", json={"name": "Story"})
        story_id = story_resp.json()["id"]
        pc_id = seed_data["pc1"].id

        response = client.delete(
            f"/api/v1/stories/{story_id}/owners/character/{pc_id}"
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_remove_owner_story_not_found_returns_404(
        self, client: TestClient, seed_data: dict
    ):
        """Returns 404 if the story does not exist."""
        auth_as(client, seed_data["gm"])
        response = client.delete(
            f"/api/v1/stories/01DOESNOTEXIST0000000000000/owners/character/{seed_data['pc1'].id}"
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_remove_owner_invalid_type_returns_422(
        self, client: TestClient, seed_data: dict
    ):
        """Returns 422 if the owner_type path segment is not valid."""
        auth_as(client, seed_data["gm"])
        story_resp = client.post("/api/v1/stories", json={"name": "Story"})
        story_id = story_resp.json()["id"]

        response = client.delete(
            f"/api/v1/stories/{story_id}/owners/invalid_type/01HXYZ"
        )
        assert response.status_code == 422

    def test_non_gm_cannot_remove_owner(self, client: TestClient, seed_data: dict):
        """Non-GM player cannot remove owners."""
        auth_as(client, seed_data["gm"])
        story_resp = client.post("/api/v1/stories", json={"name": "Story"})
        story_id = story_resp.json()["id"]
        pc_id = seed_data["pc1"].id
        client.post(
            f"/api/v1/stories/{story_id}/owners",
            json={"type": "character", "id": pc_id},
        )

        auth_as(client, seed_data["player1"])
        response = client.delete(
            f"/api/v1/stories/{story_id}/owners/character/{pc_id}"
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "insufficient_role"

    def test_unauthenticated_remove_owner_returns_401(
        self, client: TestClient, seed_data: dict
    ):
        """Unauthenticated request to remove owner returns 401."""
        auth_as(client, seed_data["gm"])
        story_resp = client.post("/api/v1/stories", json={"name": "Story"})
        story_id = story_resp.json()["id"]
        pc_id = seed_data["pc1"].id
        client.post(
            f"/api/v1/stories/{story_id}/owners",
            json={"type": "character", "id": pc_id},
        )
        client.cookies.clear()

        response = client.delete(
            f"/api/v1/stories/{story_id}/owners/character/{pc_id}"
        )
        assert response.status_code == 401
