"""Tests for Story 3.2.1 — Trait Template Catalog.

Covers all acceptance criteria:

POST /api/v1/trait-templates
  - GM creates a core template → 201
  - GM creates a role template → 201
  - All fields present in response (id, name, description, type, is_deleted, timestamps)
  - Validation: empty name → 422
  - Validation: missing description → 422
  - Validation: invalid type → 422
  - Player cannot create → 403
  - Unauthenticated → 401

GET /api/v1/trait-templates
  - Authenticated user can list templates
  - Excludes soft-deleted by default
  - include_deleted=true reveals soft-deleted templates
  - Filter by type=core returns only core templates
  - Filter by type=role returns only role templates
  - Filter by invalid type → 422
  - ULID cursor pagination
  - Player can list (read access for all)
  - Unauthenticated → 401

GET /api/v1/trait-templates/{id}
  - Returns template detail
  - Resolves soft-deleted templates (is_deleted=true visible)
  - Non-existent ID → 404
  - Player can get detail
  - Unauthenticated → 401

PATCH /api/v1/trait-templates/{id}
  - GM updates name → 200, updated
  - GM updates description → 200, other fields unchanged
  - GM updates both name and description → 200
  - Omitted fields unchanged (exclude_unset semantics)
  - Empty body is a no-op (200, no changes)
  - Type is immutable: sending type → 422
  - Empty name → 422
  - Empty description → 422
  - Player cannot update → 403
  - Non-existent template → 404
  - Unauthenticated → 401

DELETE /api/v1/trait-templates/{id}
  - GM soft-deletes a template → 204
  - Deleted template hidden from list by default
  - Deleted template still accessible by direct GET (is_deleted=true)
  - Already-deleted template → 204 (idempotent)
  - Player cannot delete → 403
  - Non-existent template → 404
  - Unauthenticated → 401

Propagation via reference:
  - Editing name/description on a template changes what the character detail
    endpoint surfaces (name is read from template.name at response time).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import auth_as
from wizards_engine.models.slot import Slot, TraitTemplate


# ---------------------------------------------------------------------------
# POST /api/v1/trait-templates
# ---------------------------------------------------------------------------


class TestCreateTraitTemplate:
    def test_gm_creates_core_template(self, client: TestClient, seed_data: dict):
        """GM can create a core trait template; returns 201 with full response."""
        auth_as(client, seed_data["gm"])
        response = client.post(
            "/api/v1/trait-templates",
            json={
                "name": "Brave",
                "description": "Acts in the face of danger without hesitation.",
                "type": "core",
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Brave"
        assert body["description"] == "Acts in the face of danger without hesitation."
        assert body["type"] == "core"
        assert body["is_deleted"] is False
        assert "id" in body
        assert "created_at" in body
        assert "updated_at" in body

    def test_gm_creates_role_template(self, client: TestClient, seed_data: dict):
        """GM can create a role trait template; returns 201."""
        auth_as(client, seed_data["gm"])
        response = client.post(
            "/api/v1/trait-templates",
            json={
                "name": "Expert Swordfighter",
                "description": "Trained extensively in blade combat.",
                "type": "role",
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["type"] == "role"
        assert body["is_deleted"] is False

    def test_create_core_and_role_are_distinct(
        self, client: TestClient, seed_data: dict
    ):
        """Core and role are stored as distinct type values."""
        auth_as(client, seed_data["gm"])

        core = client.post(
            "/api/v1/trait-templates",
            json={"name": "Steadfast", "description": "Unwavering resolve.", "type": "core"},
        ).json()
        role = client.post(
            "/api/v1/trait-templates",
            json={"name": "Healer", "description": "Knows medicine.", "type": "role"},
        ).json()

        assert core["type"] == "core"
        assert role["type"] == "role"
        assert core["id"] != role["id"]

    def test_create_empty_name_returns_422(self, client: TestClient, seed_data: dict):
        """Empty name field returns 422 validation error."""
        auth_as(client, seed_data["gm"])
        response = client.post(
            "/api/v1/trait-templates",
            json={"name": "", "description": "Some description.", "type": "core"},
        )
        assert response.status_code == 422

    def test_create_whitespace_only_name_returns_422(
        self, client: TestClient, seed_data: dict
    ):
        """Whitespace-only name returns 422."""
        auth_as(client, seed_data["gm"])
        response = client.post(
            "/api/v1/trait-templates",
            json={"name": "   ", "description": "Some description.", "type": "core"},
        )
        assert response.status_code == 422

    def test_create_missing_description_returns_422(
        self, client: TestClient, seed_data: dict
    ):
        """Missing description field returns 422."""
        auth_as(client, seed_data["gm"])
        response = client.post(
            "/api/v1/trait-templates",
            json={"name": "Brave", "type": "core"},
        )
        assert response.status_code == 422

    def test_create_invalid_type_returns_422(
        self, client: TestClient, seed_data: dict
    ):
        """Invalid type value returns 422 validation error."""
        auth_as(client, seed_data["gm"])
        response = client.post(
            "/api/v1/trait-templates",
            json={"name": "Brave", "description": "Desc.", "type": "invalid"},
        )
        assert response.status_code == 422

    def test_create_missing_type_returns_422(
        self, client: TestClient, seed_data: dict
    ):
        """Missing type field returns 422 validation error."""
        auth_as(client, seed_data["gm"])
        response = client.post(
            "/api/v1/trait-templates",
            json={"name": "Brave", "description": "Desc."},
        )
        assert response.status_code == 422

    def test_player_cannot_create_template(self, client: TestClient, seed_data: dict):
        """Non-GM player receives 403 when attempting to create a template."""
        auth_as(client, seed_data["player1"])
        response = client.post(
            "/api/v1/trait-templates",
            json={"name": "Brave", "description": "Desc.", "type": "core"},
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "insufficient_role"

    def test_unauthenticated_cannot_create_template(
        self, client: TestClient, seed_data: dict
    ):
        """Unauthenticated request to create template receives 401."""
        response = client.post(
            "/api/v1/trait-templates",
            json={"name": "Brave", "description": "Desc.", "type": "core"},
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/trait-templates
# ---------------------------------------------------------------------------


class TestListTraitTemplates:
    def _create_template(
        self,
        client: TestClient,
        seed_data: dict,
        name: str = "Test Trait",
        description: str = "A test trait.",
        template_type: str = "core",
    ) -> dict:
        """Helper — create a template as GM and return the response body."""
        auth_as(client, seed_data["gm"])
        return client.post(
            "/api/v1/trait-templates",
            json={"name": name, "description": description, "type": template_type},
        ).json()

    def test_list_returns_paginated_structure(
        self, client: TestClient, seed_data: dict
    ):
        """Authenticated user can list templates; response has items/next_cursor/has_more."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/trait-templates")

        assert response.status_code == 200
        body = response.json()
        assert "items" in body
        assert "next_cursor" in body
        assert "has_more" in body
        assert isinstance(body["items"], list)

    def test_list_contains_created_template(
        self, client: TestClient, seed_data: dict
    ):
        """A created template appears in the list."""
        auth_as(client, seed_data["gm"])
        created = self._create_template(client, seed_data, name="Unique Trait Name")

        response = client.get("/api/v1/trait-templates")
        ids = [t["id"] for t in response.json()["items"]]
        assert created["id"] in ids

    def test_list_excludes_deleted_by_default(
        self, client: TestClient, seed_data: dict
    ):
        """Soft-deleted templates are excluded from the list by default."""
        auth_as(client, seed_data["gm"])
        created = self._create_template(client, seed_data, name="Will Be Deleted")
        client.delete(f"/api/v1/trait-templates/{created['id']}")

        list_resp = client.get("/api/v1/trait-templates")
        ids = [t["id"] for t in list_resp.json()["items"]]
        assert created["id"] not in ids

    def test_include_deleted_reveals_soft_deleted(
        self, client: TestClient, seed_data: dict
    ):
        """include_deleted=true includes soft-deleted templates."""
        auth_as(client, seed_data["gm"])
        created = self._create_template(client, seed_data, name="Already Deleted")
        client.delete(f"/api/v1/trait-templates/{created['id']}")

        list_resp = client.get("/api/v1/trait-templates?include_deleted=true")
        ids = [t["id"] for t in list_resp.json()["items"]]
        assert created["id"] in ids

    def test_filter_by_type_core(self, client: TestClient, seed_data: dict):
        """type=core filter returns only core templates."""
        auth_as(client, seed_data["gm"])
        core = self._create_template(client, seed_data, name="Core Trait", template_type="core")
        role = self._create_template(client, seed_data, name="Role Trait", template_type="role")

        response = client.get("/api/v1/trait-templates?type=core")
        assert response.status_code == 200
        items = response.json()["items"]
        ids = [t["id"] for t in items]
        assert core["id"] in ids
        assert role["id"] not in ids
        for item in items:
            assert item["type"] == "core"

    def test_filter_by_type_role(self, client: TestClient, seed_data: dict):
        """type=role filter returns only role templates."""
        auth_as(client, seed_data["gm"])
        core = self._create_template(client, seed_data, name="Core Two", template_type="core")
        role = self._create_template(client, seed_data, name="Role Two", template_type="role")

        response = client.get("/api/v1/trait-templates?type=role")
        assert response.status_code == 200
        items = response.json()["items"]
        ids = [t["id"] for t in items]
        assert role["id"] in ids
        assert core["id"] not in ids
        for item in items:
            assert item["type"] == "role"

    def test_filter_by_invalid_type_returns_422(
        self, client: TestClient, seed_data: dict
    ):
        """Invalid type filter value returns 422."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/trait-templates?type=invalid")
        assert response.status_code == 422

    def test_pagination_limit(self, client: TestClient, seed_data: dict):
        """limit parameter caps the page size."""
        auth_as(client, seed_data["gm"])
        for i in range(4):
            self._create_template(client, seed_data, name=f"Paged Trait {i}")

        response = client.get("/api/v1/trait-templates?limit=2")
        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) <= 2

    def test_pagination_cursor(self, client: TestClient, seed_data: dict):
        """After fetching the first page, the cursor returns the next page."""
        auth_as(client, seed_data["gm"])
        for i in range(4):
            self._create_template(client, seed_data, name=f"Cursor Trait {i}")

        page1 = client.get("/api/v1/trait-templates?limit=2").json()
        assert len(page1["items"]) == 2
        assert page1["has_more"] is True
        assert page1["next_cursor"] is not None

        page2 = client.get(
            f"/api/v1/trait-templates?limit=2&after={page1['next_cursor']}"
        ).json()
        assert len(page2["items"]) >= 1
        page1_ids = {t["id"] for t in page1["items"]}
        page2_ids = {t["id"] for t in page2["items"]}
        assert page1_ids.isdisjoint(page2_ids)

    def test_player_can_list_templates(self, client: TestClient, seed_data: dict):
        """Non-GM players can also list templates (read-only access)."""
        auth_as(client, seed_data["player1"])
        response = client.get("/api/v1/trait-templates")
        assert response.status_code == 200

    def test_unauthenticated_list_returns_401(
        self, client: TestClient, seed_data: dict
    ):
        """Unauthenticated request to list templates receives 401."""
        response = client.get("/api/v1/trait-templates")
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/trait-templates/{id}
# ---------------------------------------------------------------------------


class TestGetTraitTemplate:
    def _create_template(
        self, client: TestClient, seed_data: dict, name: str = "Test Trait", template_type: str = "core"
    ) -> dict:
        auth_as(client, seed_data["gm"])
        return client.post(
            "/api/v1/trait-templates",
            json={"name": name, "description": "A test trait.", "type": template_type},
        ).json()

    def test_get_returns_template_detail(self, client: TestClient, seed_data: dict):
        """GET /trait-templates/{id} returns full template detail."""
        auth_as(client, seed_data["gm"])
        created = self._create_template(client, seed_data, name="Detail Trait")
        template_id = created["id"]

        response = client.get(f"/api/v1/trait-templates/{template_id}")
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == template_id
        assert body["name"] == "Detail Trait"
        assert body["is_deleted"] is False

    def test_get_resolves_soft_deleted_template(
        self, client: TestClient, seed_data: dict
    ):
        """GET /trait-templates/{id} resolves soft-deleted templates with is_deleted=true."""
        auth_as(client, seed_data["gm"])
        created = self._create_template(client, seed_data, name="Will Vanish")
        template_id = created["id"]
        client.delete(f"/api/v1/trait-templates/{template_id}")

        response = client.get(f"/api/v1/trait-templates/{template_id}")
        assert response.status_code == 200
        assert response.json()["is_deleted"] is True

    def test_get_nonexistent_returns_404(self, client: TestClient, seed_data: dict):
        """GET /trait-templates/{id} returns 404 for a non-existent ID."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/trait-templates/01DOESNOTEXIST0000000000000")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_player_can_get_template_detail(self, client: TestClient, seed_data: dict):
        """Non-GM players can retrieve template detail."""
        auth_as(client, seed_data["gm"])
        created = self._create_template(client, seed_data, name="Player Visible")
        template_id = created["id"]

        auth_as(client, seed_data["player1"])
        response = client.get(f"/api/v1/trait-templates/{template_id}")
        assert response.status_code == 200
        assert response.json()["id"] == template_id

    def test_unauthenticated_get_returns_401(
        self, client: TestClient, seed_data: dict
    ):
        """Unauthenticated GET /trait-templates/{id} returns 401."""
        auth_as(client, seed_data["gm"])
        created = self._create_template(client, seed_data)
        template_id = created["id"]

        # Clear auth cookie.
        client.cookies.clear()
        response = client.get(f"/api/v1/trait-templates/{template_id}")
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /api/v1/trait-templates/{id}
# ---------------------------------------------------------------------------


class TestUpdateTraitTemplate:
    def _create_template(
        self,
        client: TestClient,
        seed_data: dict,
        name: str = "Original Name",
        description: str = "Original description.",
        template_type: str = "core",
    ) -> dict:
        auth_as(client, seed_data["gm"])
        return client.post(
            "/api/v1/trait-templates",
            json={"name": name, "description": description, "type": template_type},
        ).json()

    def test_gm_updates_name(self, client: TestClient, seed_data: dict):
        """GM can update a template's name; returns 200 with updated name."""
        auth_as(client, seed_data["gm"])
        created = self._create_template(client, seed_data)
        template_id = created["id"]

        response = client.patch(
            f"/api/v1/trait-templates/{template_id}",
            json={"name": "New Name"},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "New Name"
        # Description and type should be unchanged.
        assert response.json()["description"] == "Original description."
        assert response.json()["type"] == "core"

    def test_gm_updates_description(self, client: TestClient, seed_data: dict):
        """GM can update description; name and type stay unchanged."""
        auth_as(client, seed_data["gm"])
        created = self._create_template(client, seed_data)
        template_id = created["id"]

        response = client.patch(
            f"/api/v1/trait-templates/{template_id}",
            json={"description": "Updated description."},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["description"] == "Updated description."
        assert body["name"] == "Original Name"
        assert body["type"] == "core"

    def test_gm_updates_both_name_and_description(
        self, client: TestClient, seed_data: dict
    ):
        """GM can update both name and description in a single PATCH."""
        auth_as(client, seed_data["gm"])
        created = self._create_template(client, seed_data)
        template_id = created["id"]

        response = client.patch(
            f"/api/v1/trait-templates/{template_id}",
            json={"name": "New Name", "description": "New description."},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "New Name"
        assert body["description"] == "New description."

    def test_omitted_fields_unchanged(self, client: TestClient, seed_data: dict):
        """Omitted fields in PATCH body remain unchanged."""
        auth_as(client, seed_data["gm"])
        created = self._create_template(
            client, seed_data, name="Stable Name", description="Stable desc."
        )
        template_id = created["id"]

        # Only update name; description should be unchanged.
        response = client.patch(
            f"/api/v1/trait-templates/{template_id}",
            json={"name": "Changed Name"},
        )
        assert response.status_code == 200
        assert response.json()["description"] == "Stable desc."

    def test_patch_empty_body_is_noop(self, client: TestClient, seed_data: dict):
        """PATCH with an empty JSON object {} is valid; no fields are changed."""
        auth_as(client, seed_data["gm"])
        created = self._create_template(client, seed_data)
        template_id = created["id"]

        response = client.patch(f"/api/v1/trait-templates/{template_id}", json={})
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "Original Name"
        assert body["description"] == "Original description."

    def test_type_is_immutable_returns_422(self, client: TestClient, seed_data: dict):
        """Attempting to change type via PATCH returns 422."""
        auth_as(client, seed_data["gm"])
        created = self._create_template(client, seed_data, template_type="core")
        template_id = created["id"]

        response = client.patch(
            f"/api/v1/trait-templates/{template_id}",
            json={"type": "role"},
        )
        assert response.status_code == 422

    def test_type_combined_with_valid_fields_still_422(
        self, client: TestClient, seed_data: dict
    ):
        """Sending type alongside valid name change still returns 422."""
        auth_as(client, seed_data["gm"])
        created = self._create_template(client, seed_data)
        template_id = created["id"]

        response = client.patch(
            f"/api/v1/trait-templates/{template_id}",
            json={"name": "New Name", "type": "role"},
        )
        assert response.status_code == 422

    def test_patch_empty_name_returns_422(self, client: TestClient, seed_data: dict):
        """Updating name to an empty string returns 422."""
        auth_as(client, seed_data["gm"])
        created = self._create_template(client, seed_data)
        template_id = created["id"]

        response = client.patch(
            f"/api/v1/trait-templates/{template_id}",
            json={"name": ""},
        )
        assert response.status_code == 422

    def test_patch_empty_description_returns_422(
        self, client: TestClient, seed_data: dict
    ):
        """Updating description to an empty string returns 422."""
        auth_as(client, seed_data["gm"])
        created = self._create_template(client, seed_data)
        template_id = created["id"]

        response = client.patch(
            f"/api/v1/trait-templates/{template_id}",
            json={"description": ""},
        )
        assert response.status_code == 422

    def test_player_cannot_update_template(self, client: TestClient, seed_data: dict):
        """Non-GM player receives 403 when attempting to update a template."""
        auth_as(client, seed_data["gm"])
        created = self._create_template(client, seed_data)
        template_id = created["id"]

        auth_as(client, seed_data["player1"])
        response = client.patch(
            f"/api/v1/trait-templates/{template_id}",
            json={"name": "Should Fail"},
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "insufficient_role"

    def test_patch_nonexistent_template_returns_404(
        self, client: TestClient, seed_data: dict
    ):
        """PATCH /trait-templates/{id} returns 404 for a non-existent ID."""
        auth_as(client, seed_data["gm"])
        response = client.patch(
            "/api/v1/trait-templates/01DOESNOTEXIST0000000000000",
            json={"name": "Ghost"},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_unauthenticated_patch_returns_401(
        self, client: TestClient, seed_data: dict
    ):
        """Unauthenticated PATCH returns 401."""
        auth_as(client, seed_data["gm"])
        created = self._create_template(client, seed_data)
        template_id = created["id"]

        client.cookies.clear()
        response = client.patch(
            f"/api/v1/trait-templates/{template_id}",
            json={"name": "No Auth"},
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/v1/trait-templates/{id}
# ---------------------------------------------------------------------------


class TestDeleteTraitTemplate:
    def _create_template(
        self, client: TestClient, seed_data: dict, name: str = "Deletable"
    ) -> dict:
        auth_as(client, seed_data["gm"])
        return client.post(
            "/api/v1/trait-templates",
            json={"name": name, "description": "Desc.", "type": "core"},
        ).json()

    def test_gm_soft_deletes_template(self, client: TestClient, seed_data: dict):
        """GM can soft-delete a template; returns 204 with no body."""
        auth_as(client, seed_data["gm"])
        created = self._create_template(client, seed_data)
        template_id = created["id"]

        response = client.delete(f"/api/v1/trait-templates/{template_id}")
        assert response.status_code == 204
        assert response.content == b""

    def test_deleted_template_hidden_from_list(
        self, client: TestClient, seed_data: dict
    ):
        """Soft-deleted template no longer appears in the default list."""
        auth_as(client, seed_data["gm"])
        created = self._create_template(client, seed_data, name="Hidden After Delete")
        template_id = created["id"]
        client.delete(f"/api/v1/trait-templates/{template_id}")

        list_resp = client.get("/api/v1/trait-templates")
        ids = [t["id"] for t in list_resp.json()["items"]]
        assert template_id not in ids

    def test_deleted_template_accessible_by_direct_get(
        self, client: TestClient, seed_data: dict
    ):
        """After deletion, direct GET still returns the template with is_deleted=true."""
        auth_as(client, seed_data["gm"])
        created = self._create_template(client, seed_data, name="Still Accessible")
        template_id = created["id"]
        client.delete(f"/api/v1/trait-templates/{template_id}")

        get_resp = client.get(f"/api/v1/trait-templates/{template_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["is_deleted"] is True

    def test_delete_already_deleted_is_idempotent(
        self, client: TestClient, seed_data: dict
    ):
        """Deleting an already-deleted template returns 204 (idempotent)."""
        auth_as(client, seed_data["gm"])
        created = self._create_template(client, seed_data, name="Delete Twice")
        template_id = created["id"]

        first = client.delete(f"/api/v1/trait-templates/{template_id}")
        assert first.status_code == 204

        second = client.delete(f"/api/v1/trait-templates/{template_id}")
        assert second.status_code == 204

    def test_player_cannot_delete_template(self, client: TestClient, seed_data: dict):
        """Non-GM player receives 403 when attempting to delete a template."""
        auth_as(client, seed_data["gm"])
        created = self._create_template(client, seed_data)
        template_id = created["id"]

        auth_as(client, seed_data["player1"])
        response = client.delete(f"/api/v1/trait-templates/{template_id}")
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "insufficient_role"

    def test_delete_nonexistent_template_returns_404(
        self, client: TestClient, seed_data: dict
    ):
        """DELETE /trait-templates/{id} returns 404 for a non-existent ID."""
        auth_as(client, seed_data["gm"])
        response = client.delete("/api/v1/trait-templates/01DOESNOTEXIST0000000000000")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_unauthenticated_delete_returns_401(
        self, client: TestClient, seed_data: dict
    ):
        """Unauthenticated DELETE returns 401."""
        auth_as(client, seed_data["gm"])
        created = self._create_template(client, seed_data)
        template_id = created["id"]

        client.cookies.clear()
        response = client.delete(f"/api/v1/trait-templates/{template_id}")
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Propagation by reference
# ---------------------------------------------------------------------------


class TestTemplatePropagation:
    def test_edit_name_propagates_to_character_trait_instance(
        self, client: TestClient, seed_data: dict, db: Session
    ):
        """Editing a template's name propagates to characters referencing it.

        Trait instances store ``template_id`` and the character detail
        endpoint reads ``template.name`` at response time — so updating the
        template is sufficient to propagate the change.
        """
        auth_as(client, seed_data["gm"])

        # Create the template.
        template_resp = client.post(
            "/api/v1/trait-templates",
            json={
                "name": "Original Trait Name",
                "description": "Original description.",
                "type": "core",
            },
        ).json()
        template_id = template_resp["id"]
        pc1 = seed_data["pc1"]

        # Create a trait instance (slot) on pc1 linking to the template.
        trait_slot = Slot(
            slot_type="core_trait",
            owner_type="character",
            owner_id=pc1.id,
            name="Original Trait Name",  # stored name (snapshot)
            template_id=template_id,
            charge=5,
            is_active=True,
        )
        db.add(trait_slot)
        db.commit()

        # Verify character detail surfaces the original template name.
        char_resp = client.get(f"/api/v1/characters/{pc1.id}").json()
        active_trait_names = [t["name"] for t in char_resp["traits"]["active"]]
        assert "Original Trait Name" in active_trait_names

        # Update the template's name.
        client.patch(
            f"/api/v1/trait-templates/{template_id}",
            json={"name": "Updated Trait Name"},
        )

        # Character detail should now surface the updated template name.
        char_resp_after = client.get(f"/api/v1/characters/{pc1.id}").json()
        active_trait_names_after = [t["name"] for t in char_resp_after["traits"]["active"]]
        assert "Updated Trait Name" in active_trait_names_after
        assert "Original Trait Name" not in active_trait_names_after

    def test_soft_delete_does_not_cascade_to_instances(
        self, client: TestClient, seed_data: dict, db: Session
    ):
        """Soft-deleting a template does NOT cascade to trait instances.

        Existing trait instances keep their template_id and remain functional
        on the character sheet.
        """
        auth_as(client, seed_data["gm"])

        template_resp = client.post(
            "/api/v1/trait-templates",
            json={
                "name": "Ephemeral Template",
                "description": "Will be deleted.",
                "type": "role",
            },
        ).json()
        template_id = template_resp["id"]
        pc1 = seed_data["pc1"]

        # Create a trait instance linking to the template.
        trait_slot = Slot(
            slot_type="role_trait",
            owner_type="character",
            owner_id=pc1.id,
            name="Ephemeral Template",
            template_id=template_id,
            charge=5,
            is_active=True,
        )
        db.add(trait_slot)
        db.commit()

        # Soft-delete the template.
        del_resp = client.delete(f"/api/v1/trait-templates/{template_id}")
        assert del_resp.status_code == 204

        # The trait instance must still be visible on the character sheet.
        char_resp = client.get(f"/api/v1/characters/{pc1.id}").json()
        active_trait_names = [t["name"] for t in char_resp["traits"]["active"]]
        assert "Ephemeral Template" in active_trait_names

        # The slot's template_id is still intact.
        db.refresh(trait_slot)
        assert trait_slot.template_id == template_id
