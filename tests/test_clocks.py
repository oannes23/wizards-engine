"""Tests for Story 2.2.1 — Clock CRUD.

Covers all acceptance criteria:

POST /api/v1/clocks
  - GM creates a clock with name only → 201, segments=5, progress=0, is_completed=False
  - GM creates a clock with all fields → 201, fields persisted
  - GM creates a clock with valid association → 201, association stored
  - Association validation: invalid associated_type → 422
  - Association validation: associated_type without associated_id → 422
  - Association validation: associated_id for non-existent object → 422
  - Association: segments=0 → 422
  - Association: segments negative → 422
  - Empty name → 422
  - Missing name → 422
  - Non-GM player cannot create → 403
  - Unauthenticated → 401

POST /api/v1/groups/{id}/clocks
  - GM creates a group clock → 201, association auto-set to (group, id)
  - Non-existent group → 404
  - Soft-deleted group → 404
  - Segments validation applies → 422
  - Non-GM player cannot create → 403
  - Unauthenticated → 401

GET /api/v1/clocks
  - Returns paginated list of non-deleted clocks
  - Soft-deleted clocks excluded by default
  - include_deleted=true reveals soft-deleted clocks
  - Filter: associated_type returns only matching clocks
  - Filter: associated_id returns only clocks for that object
  - Filter: invalid associated_type → 422
  - ULID cursor pagination (after + limit)
  - Unauthenticated → 401

GET /api/v1/clocks/{id}
  - Returns clock detail with is_completed
  - is_completed=True when progress >= segments
  - is_completed=False when progress < segments
  - Returns soft-deleted clock (is_deleted=true visible)
  - Non-existent ID → 404
  - Unauthenticated → 401

PATCH /api/v1/clocks/{id}
  - GM updates name → 200, updated
  - GM updates notes → 200
  - GM updates segments → 200
  - GM clears notes with null → 200, notes=null
  - Omitted fields are unchanged (exclude_unset)
  - Empty body is a no-op → 200
  - Attempt to change associated_type → 422
  - Attempt to change associated_id → 422
  - Attempt to change progress → 422
  - Empty name → 422
  - Segments=0 → 422
  - Non-existent clock → 404
  - Non-GM player cannot update → 403
  - Unauthenticated → 401

DELETE /api/v1/clocks/{id}
  - GM soft-deletes a clock → 204
  - Clock hidden from list after deletion
  - Clock accessible by direct GET after deletion (is_deleted=true)
  - Non-existent clock → 404
  - Non-GM player cannot delete → 403
  - Unauthenticated → 401
"""

import pytest
from fastapi.testclient import TestClient

from tests.conftest import auth_as


# ---------------------------------------------------------------------------
# POST /api/v1/clocks
# ---------------------------------------------------------------------------


class TestCreateClock:
    def test_gm_creates_clock_with_name_only(self, client: TestClient, seed_data: dict):
        """GM can create a clock with just a name; defaults apply."""
        auth_as(client, seed_data["gm"])
        response = client.post("/api/v1/clocks", json={"name": "Operation Sunrise"})

        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Operation Sunrise"
        assert body["segments"] == 5
        assert body["progress"] == 0
        assert body["is_completed"] is False
        assert body["associated_type"] is None
        assert body["associated_id"] is None
        assert body["notes"] is None
        assert body["is_deleted"] is False
        assert "id" in body
        assert "created_at" in body
        assert "updated_at" in body

    def test_gm_creates_clock_with_all_fields(self, client: TestClient, seed_data: dict):
        """GM can create a clock with all optional fields populated."""
        auth_as(client, seed_data["gm"])
        group_id = seed_data["group"].id
        response = client.post(
            "/api/v1/clocks",
            json={
                "name": "Infiltration",
                "segments": 8,
                "associated_type": "group",
                "associated_id": group_id,
                "notes": "Phase one of the heist.",
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Infiltration"
        assert body["segments"] == 8
        assert body["associated_type"] == "group"
        assert body["associated_id"] == group_id
        assert body["notes"] == "Phase one of the heist."

    def test_gm_creates_clock_associated_with_character(
        self, client: TestClient, seed_data: dict
    ):
        """GM can create a clock associated with a character."""
        auth_as(client, seed_data["gm"])
        char_id = seed_data["npc1"].id
        response = client.post(
            "/api/v1/clocks",
            json={"name": "Personal Goal", "associated_type": "character", "associated_id": char_id},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["associated_type"] == "character"
        assert body["associated_id"] == char_id

    def test_gm_creates_clock_associated_with_location(
        self, client: TestClient, seed_data: dict
    ):
        """GM can create a clock associated with a location."""
        auth_as(client, seed_data["gm"])
        loc_id = seed_data["region"].id
        response = client.post(
            "/api/v1/clocks",
            json={"name": "Siege", "associated_type": "location", "associated_id": loc_id},
        )
        assert response.status_code == 201
        assert response.json()["associated_type"] == "location"

    def test_create_clock_segments_must_be_positive(
        self, client: TestClient, seed_data: dict
    ):
        """Segments=0 returns 422."""
        auth_as(client, seed_data["gm"])
        response = client.post("/api/v1/clocks", json={"name": "Bad Clock", "segments": 0})
        assert response.status_code == 422

    def test_create_clock_negative_segments_returns_422(
        self, client: TestClient, seed_data: dict
    ):
        """Negative segments returns 422."""
        auth_as(client, seed_data["gm"])
        response = client.post("/api/v1/clocks", json={"name": "Bad Clock", "segments": -3})
        assert response.status_code == 422

    def test_create_clock_empty_name_returns_422(self, client: TestClient, seed_data: dict):
        """Empty name returns 422."""
        auth_as(client, seed_data["gm"])
        response = client.post("/api/v1/clocks", json={"name": ""})
        assert response.status_code == 422

    def test_create_clock_whitespace_only_name_returns_422(
        self, client: TestClient, seed_data: dict
    ):
        """Whitespace-only name returns 422."""
        auth_as(client, seed_data["gm"])
        response = client.post("/api/v1/clocks", json={"name": "   "})
        assert response.status_code == 422

    def test_create_clock_missing_name_returns_422(
        self, client: TestClient, seed_data: dict
    ):
        """Missing required name field returns 422."""
        auth_as(client, seed_data["gm"])
        response = client.post("/api/v1/clocks", json={"segments": 5})
        assert response.status_code == 422

    def test_create_clock_associated_type_without_id_returns_422(
        self, client: TestClient, seed_data: dict
    ):
        """associated_type without associated_id returns 422."""
        auth_as(client, seed_data["gm"])
        response = client.post(
            "/api/v1/clocks",
            json={"name": "Orphan", "associated_type": "group"},
        )
        assert response.status_code == 422

    def test_create_clock_associated_id_without_type_returns_422(
        self, client: TestClient, seed_data: dict
    ):
        """associated_id without associated_type returns 422."""
        auth_as(client, seed_data["gm"])
        group_id = seed_data["group"].id
        response = client.post(
            "/api/v1/clocks",
            json={"name": "Orphan", "associated_id": group_id},
        )
        assert response.status_code == 422

    def test_create_clock_nonexistent_associated_object_returns_422(
        self, client: TestClient, seed_data: dict
    ):
        """Reference to a non-existent associated object returns 422."""
        auth_as(client, seed_data["gm"])
        response = client.post(
            "/api/v1/clocks",
            json={
                "name": "Ghost Clock",
                "associated_type": "group",
                "associated_id": "01DOESNOTEXIST0000000000000",
            },
        )
        assert response.status_code == 422

    def test_non_gm_cannot_create_clock(self, client: TestClient, seed_data: dict):
        """Non-GM player receives 403 when attempting to create a clock."""
        auth_as(client, seed_data["player1"])
        response = client.post("/api/v1/clocks", json={"name": "Should Fail"})
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "insufficient_role"

    def test_unauthenticated_cannot_create_clock(self, client: TestClient, seed_data: dict):
        """Unauthenticated request to create clock receives 401."""
        response = client.post("/api/v1/clocks", json={"name": "No Auth"})
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/v1/groups/{id}/clocks
# ---------------------------------------------------------------------------


class TestCreateGroupClock:
    def test_gm_creates_group_clock(self, client: TestClient, seed_data: dict):
        """GM can create a clock via the group sub-resource route."""
        auth_as(client, seed_data["gm"])
        group_id = seed_data["group"].id
        response = client.post(
            f"/api/v1/groups/{group_id}/clocks",
            json={"name": "Project: Expansion", "segments": 6},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Project: Expansion"
        assert body["segments"] == 6
        assert body["associated_type"] == "group"
        assert body["associated_id"] == group_id
        assert body["progress"] == 0
        assert body["is_completed"] is False

    def test_group_clock_with_notes(self, client: TestClient, seed_data: dict):
        """Group clock sub-resource accepts optional notes."""
        auth_as(client, seed_data["gm"])
        group_id = seed_data["group"].id
        response = client.post(
            f"/api/v1/groups/{group_id}/clocks",
            json={"name": "Recon", "notes": "Gather intel on the target."},
        )
        assert response.status_code == 201
        assert response.json()["notes"] == "Gather intel on the target."

    def test_group_clock_defaults_segments_to_5(self, client: TestClient, seed_data: dict):
        """Segments default to 5 when not provided."""
        auth_as(client, seed_data["gm"])
        group_id = seed_data["group"].id
        response = client.post(
            f"/api/v1/groups/{group_id}/clocks",
            json={"name": "Quick Job"},
        )
        assert response.status_code == 201
        assert response.json()["segments"] == 5

    def test_group_clock_nonexistent_group_returns_404(
        self, client: TestClient, seed_data: dict
    ):
        """Non-existent group ID returns 404."""
        auth_as(client, seed_data["gm"])
        response = client.post(
            "/api/v1/groups/01DOESNOTEXIST0000000000000/clocks",
            json={"name": "Ghost Clock"},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_group_clock_soft_deleted_group_returns_404(
        self, client: TestClient, seed_data: dict
    ):
        """Soft-deleted group returns 404 for the sub-resource route."""
        auth_as(client, seed_data["gm"])
        group_id = seed_data["group"].id

        # Soft-delete the group via CRUD endpoint (if available) or direct API.
        client.delete(f"/api/v1/groups/{group_id}")

        response = client.post(
            f"/api/v1/groups/{group_id}/clocks",
            json={"name": "Deleted Group Clock"},
        )
        assert response.status_code == 404

    def test_group_clock_segments_must_be_positive(
        self, client: TestClient, seed_data: dict
    ):
        """Segments=0 returns 422 on the sub-resource route."""
        auth_as(client, seed_data["gm"])
        group_id = seed_data["group"].id
        response = client.post(
            f"/api/v1/groups/{group_id}/clocks",
            json={"name": "Bad Segments", "segments": 0},
        )
        assert response.status_code == 422

    def test_non_gm_cannot_create_group_clock(self, client: TestClient, seed_data: dict):
        """Non-GM player receives 403 on the group sub-resource route."""
        auth_as(client, seed_data["player1"])
        group_id = seed_data["group"].id
        response = client.post(
            f"/api/v1/groups/{group_id}/clocks",
            json={"name": "Should Fail"},
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "insufficient_role"

    def test_unauthenticated_cannot_create_group_clock(
        self, client: TestClient, seed_data: dict
    ):
        """Unauthenticated request to group clock sub-resource receives 401."""
        group_id = seed_data["group"].id
        response = client.post(
            f"/api/v1/groups/{group_id}/clocks",
            json={"name": "No Auth"},
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/clocks
# ---------------------------------------------------------------------------


class TestListClocks:
    def test_list_returns_clocks(self, client: TestClient, seed_data: dict):
        """Authenticated user can list clocks; response has items/next_cursor/has_more."""
        auth_as(client, seed_data["gm"])
        # Create a clock first so the list is non-empty.
        client.post("/api/v1/clocks", json={"name": "Clock A"})

        response = client.get("/api/v1/clocks")
        assert response.status_code == 200
        body = response.json()
        assert "items" in body
        assert "next_cursor" in body
        assert "has_more" in body
        assert isinstance(body["items"], list)
        assert len(body["items"]) >= 1

    def test_list_excludes_deleted_by_default(self, client: TestClient, seed_data: dict):
        """Soft-deleted clocks are excluded from the list by default."""
        auth_as(client, seed_data["gm"])

        create_resp = client.post("/api/v1/clocks", json={"name": "Soon Deleted"})
        clock_id = create_resp.json()["id"]
        client.delete(f"/api/v1/clocks/{clock_id}")

        list_resp = client.get("/api/v1/clocks")
        ids = [c["id"] for c in list_resp.json()["items"]]
        assert clock_id not in ids

    def test_include_deleted_reveals_soft_deleted(self, client: TestClient, seed_data: dict):
        """include_deleted=true includes soft-deleted clocks in the list."""
        auth_as(client, seed_data["gm"])

        create_resp = client.post("/api/v1/clocks", json={"name": "Will Be Deleted"})
        clock_id = create_resp.json()["id"]
        client.delete(f"/api/v1/clocks/{clock_id}")

        list_resp = client.get("/api/v1/clocks?include_deleted=true")
        ids = [c["id"] for c in list_resp.json()["items"]]
        assert clock_id in ids

    def test_filter_associated_type(self, client: TestClient, seed_data: dict):
        """associated_type filter returns only clocks with matching type."""
        auth_as(client, seed_data["gm"])
        group_id = seed_data["group"].id
        char_id = seed_data["npc1"].id

        # Create one group clock and one character clock.
        client.post(
            "/api/v1/clocks",
            json={"name": "Group Task", "associated_type": "group", "associated_id": group_id},
        )
        client.post(
            "/api/v1/clocks",
            json={"name": "Char Task", "associated_type": "character", "associated_id": char_id},
        )

        response = client.get("/api/v1/clocks?associated_type=group")
        assert response.status_code == 200
        items = response.json()["items"]
        assert all(c["associated_type"] == "group" for c in items)
        names = {c["name"] for c in items}
        assert "Group Task" in names
        assert "Char Task" not in names

    def test_filter_associated_id(self, client: TestClient, seed_data: dict):
        """associated_id filter returns only clocks for that specific object."""
        auth_as(client, seed_data["gm"])
        group_id = seed_data["group"].id
        region_id = seed_data["region"].id

        client.post(
            "/api/v1/clocks",
            json={"name": "Task A", "associated_type": "group", "associated_id": group_id},
        )
        client.post(
            "/api/v1/clocks",
            json={"name": "Task B", "associated_type": "location", "associated_id": region_id},
        )

        response = client.get(f"/api/v1/clocks?associated_id={group_id}")
        assert response.status_code == 200
        items = response.json()["items"]
        assert all(c["associated_id"] == group_id for c in items)

    def test_filter_invalid_associated_type_returns_422(
        self, client: TestClient, seed_data: dict
    ):
        """Invalid associated_type value returns 422."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/clocks?associated_type=faction")
        assert response.status_code == 422

    def test_pagination_limit(self, client: TestClient, seed_data: dict):
        """limit parameter caps the page size."""
        auth_as(client, seed_data["gm"])
        for i in range(5):
            client.post("/api/v1/clocks", json={"name": f"Clock {i}"})

        response = client.get("/api/v1/clocks?limit=2")
        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) <= 2

    def test_pagination_cursor(self, client: TestClient, seed_data: dict):
        """After fetching the first page, the cursor returns the next page."""
        auth_as(client, seed_data["gm"])
        for i in range(6):
            client.post("/api/v1/clocks", json={"name": f"Paginated Clock {i}"})

        page1 = client.get("/api/v1/clocks?limit=3").json()
        assert len(page1["items"]) == 3
        assert page1["has_more"] is True
        assert page1["next_cursor"] is not None

        page2 = client.get(f"/api/v1/clocks?limit=3&after={page1['next_cursor']}").json()
        page1_ids = {c["id"] for c in page1["items"]}
        page2_ids = {c["id"] for c in page2["items"]}
        assert page1_ids.isdisjoint(page2_ids)

    def test_unauthenticated_list_returns_401(self, client: TestClient, seed_data: dict):
        """Unauthenticated request to list clocks receives 401."""
        response = client.get("/api/v1/clocks")
        assert response.status_code == 401

    def test_player_can_list_clocks(self, client: TestClient, seed_data: dict):
        """Non-GM players can also list clocks."""
        auth_as(client, seed_data["player1"])
        response = client.get("/api/v1/clocks")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/v1/clocks/{id}
# ---------------------------------------------------------------------------


class TestGetClock:
    def test_get_returns_clock_detail(self, client: TestClient, seed_data: dict):
        """GET /clocks/{id} returns full clock detail."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post(
            "/api/v1/clocks", json={"name": "The Great Heist", "segments": 7}
        )
        clock_id = create_resp.json()["id"]

        response = client.get(f"/api/v1/clocks/{clock_id}")
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == clock_id
        assert body["name"] == "The Great Heist"
        assert body["segments"] == 7
        assert body["progress"] == 0
        assert body["is_completed"] is False
        assert body["is_deleted"] is False

    def test_get_is_completed_false_when_progress_below_segments(
        self, client: TestClient, seed_data: dict
    ):
        """is_completed is False when progress < segments."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post("/api/v1/clocks", json={"name": "In Progress", "segments": 5})
        clock_id = create_resp.json()["id"]

        response = client.get(f"/api/v1/clocks/{clock_id}")
        assert response.json()["is_completed"] is False

    def test_get_is_completed_true_when_progress_equals_segments(
        self, client: TestClient, seed_data: dict, db
    ):
        """is_completed is True when progress >= segments.

        We manipulate the DB record directly via the ``db`` fixture
        (which shares the same in-memory engine as the test client).
        """
        from wizards_engine.models.clock import Clock as ClockModel

        auth_as(client, seed_data["gm"])
        create_resp = client.post("/api/v1/clocks", json={"name": "Done", "segments": 3})
        clock_id = create_resp.json()["id"]

        # Directly update progress in the shared DB session.
        clock_obj = db.get(ClockModel, clock_id)
        clock_obj.progress = 3
        db.commit()

        response = client.get(f"/api/v1/clocks/{clock_id}")
        assert response.json()["is_completed"] is True

    def test_get_is_completed_true_when_progress_exceeds_segments(
        self, client: TestClient, seed_data: dict, db
    ):
        """is_completed is True even when progress > segments (soft cap)."""
        from wizards_engine.models.clock import Clock as ClockModel

        auth_as(client, seed_data["gm"])
        create_resp = client.post("/api/v1/clocks", json={"name": "Over-achieved", "segments": 3})
        clock_id = create_resp.json()["id"]

        # Directly update progress in the shared DB session.
        clock_obj = db.get(ClockModel, clock_id)
        clock_obj.progress = 5  # exceeds segments=3
        db.commit()

        response = client.get(f"/api/v1/clocks/{clock_id}")
        assert response.json()["is_completed"] is True

    def test_get_returns_soft_deleted_clock(self, client: TestClient, seed_data: dict):
        """GET /clocks/{id} returns soft-deleted clocks with is_deleted=true."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post("/api/v1/clocks", json={"name": "Deleted Clock"})
        clock_id = create_resp.json()["id"]
        client.delete(f"/api/v1/clocks/{clock_id}")

        get_resp = client.get(f"/api/v1/clocks/{clock_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["is_deleted"] is True

    def test_get_nonexistent_clock_returns_404(self, client: TestClient, seed_data: dict):
        """GET /clocks/{id} returns 404 for a non-existent ID."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/clocks/01DOESNOTEXIST0000000000000")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_unauthenticated_get_returns_401(self, client: TestClient, seed_data: dict):
        """Unauthenticated GET /clocks/{id} returns 401."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post("/api/v1/clocks", json={"name": "Auth Test"})
        clock_id = create_resp.json()["id"]

        client.cookies.clear()
        response = client.get(f"/api/v1/clocks/{clock_id}")
        assert response.status_code == 401

    def test_player_can_get_clock_detail(self, client: TestClient, seed_data: dict):
        """Non-GM players can retrieve clock detail."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post("/api/v1/clocks", json={"name": "Visible Clock"})
        clock_id = create_resp.json()["id"]

        auth_as(client, seed_data["player1"])
        response = client.get(f"/api/v1/clocks/{clock_id}")
        assert response.status_code == 200
        assert response.json()["id"] == clock_id


# ---------------------------------------------------------------------------
# PATCH /api/v1/clocks/{id}
# ---------------------------------------------------------------------------


class TestUpdateClock:
    def test_gm_updates_name(self, client: TestClient, seed_data: dict):
        """GM can update a clock's name."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post("/api/v1/clocks", json={"name": "Old Name"})
        clock_id = create_resp.json()["id"]

        response = client.patch(f"/api/v1/clocks/{clock_id}", json={"name": "New Name"})
        assert response.status_code == 200
        assert response.json()["name"] == "New Name"

    def test_gm_updates_notes(self, client: TestClient, seed_data: dict):
        """GM can update notes."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post("/api/v1/clocks", json={"name": "Clock"})
        clock_id = create_resp.json()["id"]

        response = client.patch(f"/api/v1/clocks/{clock_id}", json={"notes": "Some notes."})
        assert response.status_code == 200
        assert response.json()["notes"] == "Some notes."

    def test_gm_updates_segments(self, client: TestClient, seed_data: dict):
        """GM can update segments count."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post("/api/v1/clocks", json={"name": "Clock", "segments": 4})
        clock_id = create_resp.json()["id"]

        response = client.patch(f"/api/v1/clocks/{clock_id}", json={"segments": 10})
        assert response.status_code == 200
        assert response.json()["segments"] == 10

    def test_gm_clears_notes_with_null(self, client: TestClient, seed_data: dict):
        """Sending notes=null clears the field."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post(
            "/api/v1/clocks", json={"name": "Clock", "notes": "Initial notes."}
        )
        clock_id = create_resp.json()["id"]

        response = client.patch(f"/api/v1/clocks/{clock_id}", json={"notes": None})
        assert response.status_code == 200
        assert response.json()["notes"] is None

    def test_omitted_fields_are_unchanged(self, client: TestClient, seed_data: dict):
        """Omitted fields in PATCH body remain unchanged."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post(
            "/api/v1/clocks",
            json={"name": "Original Name", "segments": 6, "notes": "Original notes."},
        )
        clock_id = create_resp.json()["id"]

        # Update only name; segments and notes should be unchanged.
        response = client.patch(f"/api/v1/clocks/{clock_id}", json={"name": "Updated Name"})
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "Updated Name"
        assert body["segments"] == 6
        assert body["notes"] == "Original notes."

    def test_patch_empty_body_is_noop(self, client: TestClient, seed_data: dict):
        """PATCH with an empty JSON object {} is a no-op."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post("/api/v1/clocks", json={"name": "Unchanged Clock"})
        clock_id = create_resp.json()["id"]
        original = client.get(f"/api/v1/clocks/{clock_id}").json()

        response = client.patch(f"/api/v1/clocks/{clock_id}", json={})
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == original["name"]
        assert body["segments"] == original["segments"]

    def test_patch_rejects_associated_type(self, client: TestClient, seed_data: dict):
        """PATCH rejects attempts to change associated_type."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post("/api/v1/clocks", json={"name": "Clock"})
        clock_id = create_resp.json()["id"]

        response = client.patch(
            f"/api/v1/clocks/{clock_id}", json={"associated_type": "group"}
        )
        assert response.status_code == 422

    def test_patch_rejects_associated_id(self, client: TestClient, seed_data: dict):
        """PATCH rejects attempts to change associated_id."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post("/api/v1/clocks", json={"name": "Clock"})
        clock_id = create_resp.json()["id"]

        response = client.patch(
            f"/api/v1/clocks/{clock_id}",
            json={"associated_id": "01SOMEIDVALUE00000000000000"},
        )
        assert response.status_code == 422

    def test_patch_rejects_progress(self, client: TestClient, seed_data: dict):
        """PATCH rejects attempts to change progress."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post("/api/v1/clocks", json={"name": "Clock"})
        clock_id = create_resp.json()["id"]

        response = client.patch(f"/api/v1/clocks/{clock_id}", json={"progress": 3})
        assert response.status_code == 422

    def test_patch_empty_name_returns_422(self, client: TestClient, seed_data: dict):
        """Updating name to empty string returns 422."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post("/api/v1/clocks", json={"name": "Clock"})
        clock_id = create_resp.json()["id"]

        response = client.patch(f"/api/v1/clocks/{clock_id}", json={"name": ""})
        assert response.status_code == 422

    def test_patch_segments_zero_returns_422(self, client: TestClient, seed_data: dict):
        """Updating segments to 0 returns 422."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post("/api/v1/clocks", json={"name": "Clock"})
        clock_id = create_resp.json()["id"]

        response = client.patch(f"/api/v1/clocks/{clock_id}", json={"segments": 0})
        assert response.status_code == 422

    def test_update_nonexistent_clock_returns_404(self, client: TestClient, seed_data: dict):
        """PATCH /clocks/{id} returns 404 for a non-existent ID."""
        auth_as(client, seed_data["gm"])
        response = client.patch(
            "/api/v1/clocks/01DOESNOTEXIST0000000000000", json={"name": "Ghost"}
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_non_gm_cannot_update_clock(self, client: TestClient, seed_data: dict):
        """Non-GM player receives 403 when attempting to update a clock."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post("/api/v1/clocks", json={"name": "Protected Clock"})
        clock_id = create_resp.json()["id"]

        auth_as(client, seed_data["player1"])
        response = client.patch(f"/api/v1/clocks/{clock_id}", json={"name": "Hacked"})
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "insufficient_role"

    def test_unauthenticated_update_returns_401(self, client: TestClient, seed_data: dict):
        """Unauthenticated PATCH returns 401."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post("/api/v1/clocks", json={"name": "Clock"})
        clock_id = create_resp.json()["id"]

        client.cookies.clear()
        response = client.patch(f"/api/v1/clocks/{clock_id}", json={"name": "No Auth"})
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/v1/clocks/{id}
# ---------------------------------------------------------------------------


class TestDeleteClock:
    def test_gm_soft_deletes_clock(self, client: TestClient, seed_data: dict):
        """GM can soft-delete a clock; returns 204."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post("/api/v1/clocks", json={"name": "To Be Deleted"})
        clock_id = create_resp.json()["id"]

        response = client.delete(f"/api/v1/clocks/{clock_id}")
        assert response.status_code == 204
        assert response.content == b""

    def test_deleted_clock_hidden_from_list(self, client: TestClient, seed_data: dict):
        """Soft-deleted clock no longer appears in the default list."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post("/api/v1/clocks", json={"name": "Goodbye"})
        clock_id = create_resp.json()["id"]
        client.delete(f"/api/v1/clocks/{clock_id}")

        list_resp = client.get("/api/v1/clocks")
        ids = [c["id"] for c in list_resp.json()["items"]]
        assert clock_id not in ids

    def test_deleted_clock_accessible_by_direct_get(
        self, client: TestClient, seed_data: dict
    ):
        """After deletion, direct GET still returns the clock with is_deleted=true."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post("/api/v1/clocks", json={"name": "Lingering"})
        clock_id = create_resp.json()["id"]
        client.delete(f"/api/v1/clocks/{clock_id}")

        get_resp = client.get(f"/api/v1/clocks/{clock_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["is_deleted"] is True

    def test_delete_nonexistent_clock_returns_404(self, client: TestClient, seed_data: dict):
        """DELETE /clocks/{id} returns 404 for a non-existent ID."""
        auth_as(client, seed_data["gm"])
        response = client.delete("/api/v1/clocks/01DOESNOTEXIST0000000000000")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_non_gm_cannot_delete_clock(self, client: TestClient, seed_data: dict):
        """Non-GM player receives 403 when attempting to delete."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post("/api/v1/clocks", json={"name": "Protected"})
        clock_id = create_resp.json()["id"]

        auth_as(client, seed_data["player1"])
        response = client.delete(f"/api/v1/clocks/{clock_id}")
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "insufficient_role"

    def test_unauthenticated_delete_returns_401(self, client: TestClient, seed_data: dict):
        """Unauthenticated DELETE returns 401."""
        auth_as(client, seed_data["gm"])
        create_resp = client.post("/api/v1/clocks", json={"name": "Clock"})
        clock_id = create_resp.json()["id"]

        client.cookies.clear()
        response = client.delete(f"/api/v1/clocks/{clock_id}")
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_get_malformed_id_returns_404(self, client: TestClient, seed_data: dict):
        """GET with a non-ULID path segment returns 404."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/clocks/not-a-valid-ulid")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_patch_malformed_id_returns_404(self, client: TestClient, seed_data: dict):
        """PATCH with a non-ULID path segment returns 404."""
        auth_as(client, seed_data["gm"])
        response = client.patch(
            "/api/v1/clocks/not-a-valid-ulid", json={"name": "Ghost"}
        )
        assert response.status_code == 404

    def test_delete_malformed_id_returns_404(self, client: TestClient, seed_data: dict):
        """DELETE with a non-ULID path segment returns 404."""
        auth_as(client, seed_data["gm"])
        response = client.delete("/api/v1/clocks/not-a-valid-ulid")
        assert response.status_code == 404

    def test_list_empty_returns_empty_items(self, client: TestClient, seed_data: dict):
        """When there are no clocks the default list returns empty items."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/clocks")
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []
        assert body["has_more"] is False
        assert body["next_cursor"] is None

    def test_standalone_and_group_route_same_underlying_record(
        self, client: TestClient, seed_data: dict
    ):
        """A clock created via the group sub-resource is retrievable via /clocks/{id}."""
        auth_as(client, seed_data["gm"])
        group_id = seed_data["group"].id

        create_resp = client.post(
            f"/api/v1/groups/{group_id}/clocks",
            json={"name": "Dual Access"},
        )
        assert create_resp.status_code == 201
        clock_id = create_resp.json()["id"]

        # Should be accessible via the standalone route.
        get_resp = client.get(f"/api/v1/clocks/{clock_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == clock_id
        assert get_resp.json()["associated_id"] == group_id
