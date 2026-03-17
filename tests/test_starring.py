"""Tests for Story 4.4.3 — Starring API.

Covers all acceptance criteria:

GET /api/v1/me/starred
  - Returns empty list when user has no starred objects
  - Returns list of starred objects with resolved names
  - Unauthenticated → 401

POST /api/v1/me/starred
  - Star a character → 201 with {type, id, name}
  - Star a group → 201
  - Star a location → 201
  - Star already-starred object → 200 (idempotent)
  - Non-existent character ID → 404
  - Non-existent group ID → 404
  - Non-existent location ID → 404
  - Soft-deleted object → 404
  - Invalid type → 422
  - Missing type field → 422
  - Missing id field → 422
  - Unauthenticated → 401

DELETE /api/v1/me/starred/{type}/{id}
  - Unstar an existing starred object → 204
  - Unstar an object that is not starred → 204 (idempotent)
  - Invalid type in path → 204 (idempotent, not 422)
  - Unauthenticated → 401
"""

import pytest
from fastapi.testclient import TestClient

from tests.conftest import auth_as
from wizards_engine.models.starred import StarredObject


# ---------------------------------------------------------------------------
# GET /api/v1/me/starred
# ---------------------------------------------------------------------------


class TestListStarred:
    def test_empty_list_when_no_stars(self, client: TestClient, seed_data: dict):
        """Returns an empty list when the user has no starred objects."""
        auth_as(client, seed_data["player1"])
        response = client.get("/api/v1/me/starred")

        assert response.status_code == 200
        assert response.json() == []

    def test_returns_starred_objects_with_names(
        self, client: TestClient, seed_data: dict, db
    ):
        """Returns all starred objects with resolved names."""
        player = seed_data["player1"]
        pc2 = seed_data["pc2"]
        group = seed_data["group"]

        # Manually insert starred rows directly via db session.
        db.add(StarredObject(user_id=player.id, object_type="character", object_id=pc2.id))
        db.add(StarredObject(user_id=player.id, object_type="group", object_id=group.id))
        db.commit()

        auth_as(client, player)
        response = client.get("/api/v1/me/starred")

        assert response.status_code == 200
        items = response.json()
        assert len(items) == 2

        types_and_ids = {(item["type"], item["id"]) for item in items}
        assert ("character", pc2.id) in types_and_ids
        assert ("group", group.id) in types_and_ids

        # Names are resolved.
        names = {item["name"] for item in items}
        assert pc2.name in names
        assert group.name in names

    def test_unauthenticated_returns_401(self, client: TestClient):
        """Unauthenticated request returns 401."""
        response = client.get("/api/v1/me/starred")
        assert response.status_code == 401

    def test_starred_objects_isolated_per_user(
        self, client: TestClient, seed_data: dict, db
    ):
        """Each user only sees their own starred objects."""
        player1 = seed_data["player1"]
        player2 = seed_data["player2"]
        group = seed_data["group"]

        db.add(StarredObject(user_id=player1.id, object_type="group", object_id=group.id))
        db.commit()

        auth_as(client, player2)
        response = client.get("/api/v1/me/starred")

        assert response.status_code == 200
        assert response.json() == []


# ---------------------------------------------------------------------------
# POST /api/v1/me/starred
# ---------------------------------------------------------------------------


class TestStarObject:
    def test_star_character_returns_201(self, client: TestClient, seed_data: dict):
        """Starring a character returns 201 with type, id, name."""
        player = seed_data["player1"]
        target = seed_data["pc2"]

        auth_as(client, player)
        response = client.post(
            "/api/v1/me/starred", json={"type": "character", "id": target.id}
        )

        assert response.status_code == 201
        body = response.json()
        assert body["type"] == "character"
        assert body["id"] == target.id
        assert body["name"] == target.name

    def test_star_group_returns_201(self, client: TestClient, seed_data: dict):
        """Starring a group returns 201."""
        player = seed_data["player1"]
        group = seed_data["group"]

        auth_as(client, player)
        response = client.post(
            "/api/v1/me/starred", json={"type": "group", "id": group.id}
        )

        assert response.status_code == 201
        body = response.json()
        assert body["type"] == "group"
        assert body["id"] == group.id
        assert body["name"] == group.name

    def test_star_location_returns_201(self, client: TestClient, seed_data: dict):
        """Starring a location returns 201."""
        player = seed_data["player1"]
        region = seed_data["region"]

        auth_as(client, player)
        response = client.post(
            "/api/v1/me/starred", json={"type": "location", "id": region.id}
        )

        assert response.status_code == 201
        body = response.json()
        assert body["type"] == "location"
        assert body["id"] == region.id
        assert body["name"] == region.name

    def test_star_already_starred_returns_200(
        self, client: TestClient, seed_data: dict
    ):
        """Starring an already-starred object is idempotent — returns 200."""
        player = seed_data["player1"]
        group = seed_data["group"]

        auth_as(client, player)
        # First star.
        r1 = client.post(
            "/api/v1/me/starred", json={"type": "group", "id": group.id}
        )
        assert r1.status_code == 201

        # Second star — same object.
        r2 = client.post(
            "/api/v1/me/starred", json={"type": "group", "id": group.id}
        )
        assert r2.status_code == 200
        body = r2.json()
        assert body["type"] == "group"
        assert body["id"] == group.id
        assert body["name"] == group.name

    def test_star_nonexistent_character_returns_404(
        self, client: TestClient, seed_data: dict
    ):
        """Starring a non-existent character ID returns 404."""
        auth_as(client, seed_data["player1"])
        response = client.post(
            "/api/v1/me/starred",
            json={"type": "character", "id": "01ZZZZZZZZZZZZZZZZZZZZZZZ1"},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_star_nonexistent_group_returns_404(
        self, client: TestClient, seed_data: dict
    ):
        """Starring a non-existent group ID returns 404."""
        auth_as(client, seed_data["player1"])
        response = client.post(
            "/api/v1/me/starred",
            json={"type": "group", "id": "01ZZZZZZZZZZZZZZZZZZZZZZZ2"},
        )
        assert response.status_code == 404

    def test_star_nonexistent_location_returns_404(
        self, client: TestClient, seed_data: dict
    ):
        """Starring a non-existent location ID returns 404."""
        auth_as(client, seed_data["player1"])
        response = client.post(
            "/api/v1/me/starred",
            json={"type": "location", "id": "01ZZZZZZZZZZZZZZZZZZZZZZZ3"},
        )
        assert response.status_code == 404

    def test_star_soft_deleted_character_returns_404(
        self, client: TestClient, seed_data: dict, db
    ):
        """Starring a soft-deleted character returns 404."""
        player = seed_data["player1"]
        pc = seed_data["pc2"]

        # Soft-delete the character.
        pc.is_deleted = True
        db.commit()

        auth_as(client, player)
        response = client.post(
            "/api/v1/me/starred", json={"type": "character", "id": pc.id}
        )
        assert response.status_code == 404

    def test_invalid_type_returns_422(self, client: TestClient, seed_data: dict):
        """An invalid object type returns 422."""
        auth_as(client, seed_data["player1"])
        response = client.post(
            "/api/v1/me/starred", json={"type": "spell", "id": "01ZZZZZZZZZZZZZZZZZZZZZZZ1"}
        )
        assert response.status_code == 422

    def test_missing_type_field_returns_422(self, client: TestClient, seed_data: dict):
        """Missing type field returns 422."""
        auth_as(client, seed_data["player1"])
        response = client.post(
            "/api/v1/me/starred", json={"id": "01ZZZZZZZZZZZZZZZZZZZZZZZ1"}
        )
        assert response.status_code == 422

    def test_missing_id_field_returns_422(self, client: TestClient, seed_data: dict):
        """Missing id field returns 422."""
        auth_as(client, seed_data["player1"])
        response = client.post(
            "/api/v1/me/starred", json={"type": "character"}
        )
        assert response.status_code == 422

    def test_unauthenticated_returns_401(self, client: TestClient, seed_data: dict):
        """Unauthenticated request returns 401."""
        response = client.post(
            "/api/v1/me/starred",
            json={"type": "character", "id": seed_data["pc1"].id},
        )
        assert response.status_code == 401

    def test_star_persisted_in_db(self, client: TestClient, seed_data: dict, db):
        """Starring an object persists a row in starred_objects."""
        player = seed_data["player1"]
        group = seed_data["group"]

        auth_as(client, player)
        client.post("/api/v1/me/starred", json={"type": "group", "id": group.id})

        db.expire_all()
        row = db.get(
            StarredObject,
            {"user_id": player.id, "object_type": "group", "object_id": group.id},
        )
        assert row is not None

    def test_gm_can_star_objects(self, client: TestClient, seed_data: dict):
        """The GM can also star Game Objects."""
        gm = seed_data["gm"]
        group = seed_data["group"]

        auth_as(client, gm)
        response = client.post(
            "/api/v1/me/starred", json={"type": "group", "id": group.id}
        )
        assert response.status_code == 201


# ---------------------------------------------------------------------------
# DELETE /api/v1/me/starred/{type}/{id}
# ---------------------------------------------------------------------------


class TestUnstarObject:
    def test_unstar_existing_star_returns_204(
        self, client: TestClient, seed_data: dict, db
    ):
        """Unstarring an existing starred object returns 204."""
        player = seed_data["player1"]
        group = seed_data["group"]

        db.add(StarredObject(user_id=player.id, object_type="group", object_id=group.id))
        db.commit()

        auth_as(client, player)
        response = client.delete(f"/api/v1/me/starred/group/{group.id}")

        assert response.status_code == 204

    def test_unstar_removes_row_from_db(
        self, client: TestClient, seed_data: dict, db
    ):
        """After unstarring, the row no longer exists in starred_objects."""
        player = seed_data["player1"]
        group = seed_data["group"]

        db.add(StarredObject(user_id=player.id, object_type="group", object_id=group.id))
        db.commit()

        auth_as(client, player)
        client.delete(f"/api/v1/me/starred/group/{group.id}")

        db.expire_all()
        row = db.get(
            StarredObject,
            {"user_id": player.id, "object_type": "group", "object_id": group.id},
        )
        assert row is None

    def test_unstar_not_starred_returns_204(
        self, client: TestClient, seed_data: dict
    ):
        """Unstarring an object that is not starred returns 204 (idempotent)."""
        player = seed_data["player1"]
        group = seed_data["group"]

        auth_as(client, player)
        response = client.delete(f"/api/v1/me/starred/group/{group.id}")

        assert response.status_code == 204

    def test_unstar_invalid_type_returns_204(
        self, client: TestClient, seed_data: dict
    ):
        """Invalid object type in DELETE path returns 204 (idempotent, not 422)."""
        auth_as(client, seed_data["player1"])
        response = client.delete("/api/v1/me/starred/spell/01ZZZZZZZZZZZZZZZZZZZZZZZ1")

        assert response.status_code == 204

    def test_unstar_nonexistent_id_returns_204(
        self, client: TestClient, seed_data: dict
    ):
        """Unstarring a non-existent object ID returns 204 (idempotent)."""
        auth_as(client, seed_data["player1"])
        response = client.delete(
            "/api/v1/me/starred/character/01ZZZZZZZZZZZZZZZZZZZZZZZ9"
        )
        assert response.status_code == 204

    def test_unauthenticated_returns_401(self, client: TestClient, seed_data: dict):
        """Unauthenticated request returns 401."""
        response = client.delete(
            f"/api/v1/me/starred/group/{seed_data['group'].id}"
        )
        assert response.status_code == 401

    def test_unstar_only_affects_current_user(
        self, client: TestClient, seed_data: dict, db
    ):
        """Unstarring does not affect another user's identical starred entry."""
        player1 = seed_data["player1"]
        player2 = seed_data["player2"]
        group = seed_data["group"]

        db.add(StarredObject(user_id=player1.id, object_type="group", object_id=group.id))
        db.add(StarredObject(user_id=player2.id, object_type="group", object_id=group.id))
        db.commit()

        # Player 1 unstars.
        auth_as(client, player1)
        client.delete(f"/api/v1/me/starred/group/{group.id}")

        # Player 2's star should still be there.
        db.expire_all()
        row = db.get(
            StarredObject,
            {"user_id": player2.id, "object_type": "group", "object_id": group.id},
        )
        assert row is not None


# ---------------------------------------------------------------------------
# Round-trip integration tests
# ---------------------------------------------------------------------------


class TestStarringRoundTrip:
    def test_star_then_list_then_unstar(self, client: TestClient, seed_data: dict):
        """Full round-trip: star → appears in list → unstar → gone from list."""
        player = seed_data["player1"]
        region = seed_data["region"]

        auth_as(client, player)

        # Star.
        r1 = client.post(
            "/api/v1/me/starred", json={"type": "location", "id": region.id}
        )
        assert r1.status_code == 201

        # Appears in list.
        r2 = client.get("/api/v1/me/starred")
        assert r2.status_code == 200
        ids_in_list = [item["id"] for item in r2.json()]
        assert region.id in ids_in_list

        # Unstar.
        r3 = client.delete(f"/api/v1/me/starred/location/{region.id}")
        assert r3.status_code == 204

        # Gone from list.
        r4 = client.get("/api/v1/me/starred")
        assert r4.status_code == 200
        ids_in_list = [item["id"] for item in r4.json()]
        assert region.id not in ids_in_list

    def test_multiple_users_star_same_object_independently(
        self, client: TestClient, seed_data: dict
    ):
        """Two players can both star the same object without conflict."""
        player1 = seed_data["player1"]
        player2 = seed_data["player2"]
        group = seed_data["group"]

        auth_as(client, player1)
        r1 = client.post("/api/v1/me/starred", json={"type": "group", "id": group.id})
        assert r1.status_code == 201

        auth_as(client, player2)
        r2 = client.post("/api/v1/me/starred", json={"type": "group", "id": group.id})
        assert r2.status_code == 201
