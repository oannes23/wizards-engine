"""Tests for Story 2.2.3 — Story Entries.

Covers all acceptance criteria:

POST /api/v1/stories/{id}/entries
  - Any authenticated user can create an entry (GM and player)
  - author_id is set from authenticated user, not request body
  - session_id is auto-captured when an active session exists
  - session_id is None when no active session exists
  - character_id and game_object_refs are optional
  - Returns 201 with entry shape
  - Story not found → 404
  - Unauthenticated → 401
  - Empty text → 422
  - Missing text → 422

PATCH /api/v1/stories/{id}/entries/{entry_id}
  - GM can edit any entry → 200, text updated, updated_by set
  - Player can edit their own entry → 200
  - Player cannot edit another player's entry → 403
  - Story not found → 404
  - Entry not found → 404
  - Entry belongs to a different story → 404
  - Unauthenticated → 401
  - Empty text → 422

DELETE /api/v1/stories/{id}/entries/{entry_id}
  - GM can delete any entry → 204
  - Player can delete their own entry → 204
  - Player cannot delete another player's entry → 403
  - Soft-deleted entry is hidden from story detail
  - Story not found → 404
  - Entry not found → 404
  - Entry belongs to a different story → 404
  - Unauthenticated → 401

GET /api/v1/stories/{id} (entry filtering)
  - Detail endpoint excludes soft-deleted entries by default
  - Non-deleted entries appear sorted by created_at
"""

import pytest
from fastapi.testclient import TestClient

from tests.conftest import auth_as


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_story(client: TestClient, name: str = "Test Story") -> str:
    """Create a story as GM and return its ID."""
    resp = client.post("/api/v1/stories", json={"name": name})
    assert resp.status_code == 201
    return resp.json()["id"]


def _create_entry(
    client: TestClient,
    story_id: str,
    text: str = "A narrative entry.",
    **kwargs,
) -> dict:
    """Create an entry on *story_id* and return the response body."""
    payload = {"text": text, **kwargs}
    resp = client.post(f"/api/v1/stories/{story_id}/entries", json=payload)
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# POST /api/v1/stories/{id}/entries
# ---------------------------------------------------------------------------


class TestCreateEntry:
    def test_gm_creates_entry(self, client: TestClient, seed_data: dict):
        """GM can create a narrative entry on any story; returns 201."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client)

        response = client.post(
            f"/api/v1/stories/{story_id}/entries",
            json={"text": "The Syndicate moved against the harbour."},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["text"] == "The Syndicate moved against the harbour."
        assert body["story_id"] == story_id
        assert body["author_id"] == seed_data["gm"].id
        assert body["is_deleted"] is False
        assert body["session_id"] is None
        assert body["character_id"] is None
        assert body["event_id"] is None
        assert "id" in body
        assert "created_at" in body
        assert "updated_at" in body

    def test_player_creates_entry(self, client: TestClient, seed_data: dict):
        """Any authenticated player can create an entry when they can see the story."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client)
        # Make the story globally visible so player1 can see and write to it.
        client.patch(f"/api/v1/stories/{story_id}", json={"visibility_level": "global"})

        auth_as(client, seed_data["player1"])
        response = client.post(
            f"/api/v1/stories/{story_id}/entries",
            json={"text": "Player perspective on events."},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["author_id"] == seed_data["player1"].id
        assert body["story_id"] == story_id

    def test_author_id_from_authenticated_user_not_request_body(
        self, client: TestClient, seed_data: dict
    ):
        """author_id is always set from the current user; request body cannot override it."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client)
        # Make the story globally visible so player1 can write to it.
        client.patch(f"/api/v1/stories/{story_id}", json={"visibility_level": "global"})

        auth_as(client, seed_data["player1"])
        response = client.post(
            f"/api/v1/stories/{story_id}/entries",
            json={"text": "My entry."},
        )
        assert response.status_code == 201
        assert response.json()["author_id"] == seed_data["player1"].id

    def test_entry_with_character_id(self, client: TestClient, seed_data: dict):
        """Entry can include an optional character_id linkage."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client)
        pc_id = seed_data["pc1"].id

        response = client.post(
            f"/api/v1/stories/{story_id}/entries",
            json={"text": "Character-linked entry.", "character_id": pc_id},
        )

        assert response.status_code == 201
        assert response.json()["character_id"] == pc_id

    def test_entry_with_game_object_refs(self, client: TestClient, seed_data: dict):
        """Entry can include optional game_object_refs."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client)
        group_id = seed_data["group"].id

        refs = [{"type": "group", "id": group_id}]
        response = client.post(
            f"/api/v1/stories/{story_id}/entries",
            json={"text": "Group-linked entry.", "game_object_refs": refs},
        )

        assert response.status_code == 201
        assert response.json()["game_object_refs"] == refs

    def test_session_id_none_when_no_active_session(
        self, client: TestClient, seed_data: dict
    ):
        """When no active session exists, session_id on the entry is None."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client)

        response = client.post(
            f"/api/v1/stories/{story_id}/entries",
            json={"text": "No session entry."},
        )

        assert response.status_code == 201
        assert response.json()["session_id"] is None

    def test_session_id_captured_from_active_session(
        self, client: TestClient, seed_data: dict, db
    ):
        """When an active session exists, session_id is auto-populated on the entry."""
        from wizards_engine.models.session import Session as GameSession

        # Create an active session directly in the database.
        active_session = GameSession(status="active")
        db.add(active_session)
        db.commit()
        db.refresh(active_session)
        session_id = active_session.id

        auth_as(client, seed_data["gm"])
        story_id = _create_story(client)

        response = client.post(
            f"/api/v1/stories/{story_id}/entries",
            json={"text": "Session-linked entry."},
        )

        assert response.status_code == 201
        assert response.json()["session_id"] == session_id

    def test_create_entry_story_not_found_returns_404(
        self, client: TestClient, seed_data: dict
    ):
        """Returns 404 when the story does not exist."""
        auth_as(client, seed_data["gm"])
        response = client.post(
            "/api/v1/stories/01DOESNOTEXIST0000000000000/entries",
            json={"text": "Ghost entry."},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_unauthenticated_create_entry_returns_401(
        self, client: TestClient, seed_data: dict
    ):
        """Unauthenticated request returns 401."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client)
        client.cookies.clear()

        response = client.post(
            f"/api/v1/stories/{story_id}/entries",
            json={"text": "No auth."},
        )
        assert response.status_code == 401

    def test_empty_text_returns_422(self, client: TestClient, seed_data: dict):
        """Empty text returns 422 validation error."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client)

        response = client.post(
            f"/api/v1/stories/{story_id}/entries",
            json={"text": ""},
        )
        assert response.status_code == 422

    def test_whitespace_only_text_returns_422(self, client: TestClient, seed_data: dict):
        """Whitespace-only text returns 422 after stripping."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client)

        response = client.post(
            f"/api/v1/stories/{story_id}/entries",
            json={"text": "   "},
        )
        assert response.status_code == 422

    def test_missing_text_returns_422(self, client: TestClient, seed_data: dict):
        """Missing required text field returns 422."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client)

        response = client.post(
            f"/api/v1/stories/{story_id}/entries",
            json={},
        )
        assert response.status_code == 422

    def test_entry_appears_in_story_detail(self, client: TestClient, seed_data: dict):
        """Created entries appear in the story detail response."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client)
        entry = _create_entry(client, story_id, text="Important narrative moment.")

        detail = client.get(f"/api/v1/stories/{story_id}").json()
        entry_ids = [e["id"] for e in detail["entries"]]
        assert entry["id"] in entry_ids


# ---------------------------------------------------------------------------
# PATCH /api/v1/stories/{id}/entries/{entry_id}
# ---------------------------------------------------------------------------


class TestUpdateEntry:
    def test_gm_updates_any_entry(self, client: TestClient, seed_data: dict):
        """GM can update the text of any entry; updated_by is set to GM id."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client)
        # Make globally visible so player1 can create an entry.
        client.patch(f"/api/v1/stories/{story_id}", json={"visibility_level": "global"})

        # Player creates entry.
        auth_as(client, seed_data["player1"])
        entry = _create_entry(client, story_id, text="Original text.")
        entry_id = entry["id"]

        # GM updates it.
        auth_as(client, seed_data["gm"])
        response = client.patch(
            f"/api/v1/stories/{story_id}/entries/{entry_id}",
            json={"text": "GM-edited text."},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["text"] == "GM-edited text."
        assert body["updated_by"] == seed_data["gm"].id
        assert body["author_id"] == seed_data["player1"].id  # author unchanged

    def test_player_updates_own_entry(self, client: TestClient, seed_data: dict):
        """Player can update the text of their own entry; returns 200."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client)
        # Make globally visible so player1 can create and edit an entry.
        client.patch(f"/api/v1/stories/{story_id}", json={"visibility_level": "global"})

        auth_as(client, seed_data["player1"])
        entry = _create_entry(client, story_id, text="My first draft.")
        entry_id = entry["id"]

        response = client.patch(
            f"/api/v1/stories/{story_id}/entries/{entry_id}",
            json={"text": "My revised entry."},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["text"] == "My revised entry."
        assert body["updated_by"] == seed_data["player1"].id

    def test_player_cannot_update_other_players_entry(
        self, client: TestClient, seed_data: dict
    ):
        """Player receives 403 when attempting to edit another player's entry."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client)
        # Make globally visible so both players can see and write to this story.
        client.patch(f"/api/v1/stories/{story_id}", json={"visibility_level": "global"})

        auth_as(client, seed_data["player1"])
        entry = _create_entry(client, story_id, text="Player 1 entry.")
        entry_id = entry["id"]

        auth_as(client, seed_data["player2"])
        response = client.patch(
            f"/api/v1/stories/{story_id}/entries/{entry_id}",
            json={"text": "Player 2 edits player 1."},
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"

    def test_update_entry_story_not_found_returns_404(
        self, client: TestClient, seed_data: dict
    ):
        """Returns 404 when the story does not exist."""
        auth_as(client, seed_data["gm"])
        response = client.patch(
            "/api/v1/stories/01DOESNOTEXIST0000000000000/entries/01DOESNOTEXIST0000000000001",
            json={"text": "Updated."},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_update_entry_not_found_returns_404(
        self, client: TestClient, seed_data: dict
    ):
        """Returns 404 when the entry does not exist."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client)

        response = client.patch(
            f"/api/v1/stories/{story_id}/entries/01DOESNOTEXIST0000000000000",
            json={"text": "Updated."},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_update_entry_wrong_story_returns_404(
        self, client: TestClient, seed_data: dict
    ):
        """Returns 404 when the entry exists but belongs to a different story."""
        auth_as(client, seed_data["gm"])
        story1_id = _create_story(client, "Story One")
        story2_id = _create_story(client, "Story Two")

        entry = _create_entry(client, story1_id, text="Entry in story 1.")
        entry_id = entry["id"]

        # Try to update entry via story 2.
        response = client.patch(
            f"/api/v1/stories/{story2_id}/entries/{entry_id}",
            json={"text": "Wrong story."},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_unauthenticated_update_entry_returns_401(
        self, client: TestClient, seed_data: dict
    ):
        """Unauthenticated PATCH returns 401."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client)
        entry = _create_entry(client, story_id)
        entry_id = entry["id"]
        client.cookies.clear()

        response = client.patch(
            f"/api/v1/stories/{story_id}/entries/{entry_id}",
            json={"text": "No auth."},
        )
        assert response.status_code == 401

    def test_update_entry_empty_text_returns_422(
        self, client: TestClient, seed_data: dict
    ):
        """Empty text returns 422 validation error."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client)
        entry = _create_entry(client, story_id)
        entry_id = entry["id"]

        response = client.patch(
            f"/api/v1/stories/{story_id}/entries/{entry_id}",
            json={"text": ""},
        )
        assert response.status_code == 422

    def test_update_entry_missing_text_returns_422(
        self, client: TestClient, seed_data: dict
    ):
        """Missing text field returns 422."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client)
        entry = _create_entry(client, story_id)
        entry_id = entry["id"]

        response = client.patch(
            f"/api/v1/stories/{story_id}/entries/{entry_id}",
            json={},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /api/v1/stories/{id}/entries/{entry_id}
# ---------------------------------------------------------------------------


class TestDeleteEntry:
    def test_gm_deletes_any_entry(self, client: TestClient, seed_data: dict):
        """GM can soft-delete any entry; returns 204."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client)
        # Make globally visible so player1 can create an entry.
        client.patch(f"/api/v1/stories/{story_id}", json={"visibility_level": "global"})

        auth_as(client, seed_data["player1"])
        entry = _create_entry(client, story_id, text="Player entry.")
        entry_id = entry["id"]

        auth_as(client, seed_data["gm"])
        response = client.delete(f"/api/v1/stories/{story_id}/entries/{entry_id}")

        assert response.status_code == 204
        assert response.content == b""

    def test_player_deletes_own_entry(self, client: TestClient, seed_data: dict):
        """Player can soft-delete their own entry; returns 204."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client)
        # Make globally visible so player1 can create and delete their own entry.
        client.patch(f"/api/v1/stories/{story_id}", json={"visibility_level": "global"})

        auth_as(client, seed_data["player1"])
        entry = _create_entry(client, story_id, text="My entry.")
        entry_id = entry["id"]

        response = client.delete(f"/api/v1/stories/{story_id}/entries/{entry_id}")
        assert response.status_code == 204
        assert response.content == b""

    def test_player_cannot_delete_other_players_entry(
        self, client: TestClient, seed_data: dict
    ):
        """Player receives 403 when attempting to delete another player's entry."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client)
        # Make globally visible so both players can see and write to this story.
        client.patch(f"/api/v1/stories/{story_id}", json={"visibility_level": "global"})

        auth_as(client, seed_data["player1"])
        entry = _create_entry(client, story_id, text="Player 1 entry.")
        entry_id = entry["id"]

        auth_as(client, seed_data["player2"])
        response = client.delete(f"/api/v1/stories/{story_id}/entries/{entry_id}")

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"

    def test_deleted_entry_hidden_from_story_detail(
        self, client: TestClient, seed_data: dict
    ):
        """Soft-deleted entries are excluded from the story detail response."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client)
        entry = _create_entry(client, story_id, text="Will be deleted.")
        entry_id = entry["id"]

        client.delete(f"/api/v1/stories/{story_id}/entries/{entry_id}")

        detail = client.get(f"/api/v1/stories/{story_id}").json()
        entry_ids = [e["id"] for e in detail["entries"]]
        assert entry_id not in entry_ids

    def test_deleted_entry_sets_deleted_by(
        self, client: TestClient, seed_data: dict, db
    ):
        """deleted_by is set to the user who performed the deletion."""
        from wizards_engine.models.story import StoryEntry

        auth_as(client, seed_data["gm"])
        story_id = _create_story(client)
        entry_data = _create_entry(client, story_id, text="To be deleted.")
        entry_id = entry_data["id"]

        client.delete(f"/api/v1/stories/{story_id}/entries/{entry_id}")

        db.expire_all()
        entry = db.get(StoryEntry, entry_id)
        assert entry.is_deleted is True
        assert entry.deleted_by == seed_data["gm"].id

    def test_delete_entry_story_not_found_returns_404(
        self, client: TestClient, seed_data: dict
    ):
        """Returns 404 when the story does not exist."""
        auth_as(client, seed_data["gm"])
        response = client.delete(
            "/api/v1/stories/01DOESNOTEXIST0000000000000/entries/01DOESNOTEXIST0000000000001"
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_delete_entry_not_found_returns_404(
        self, client: TestClient, seed_data: dict
    ):
        """Returns 404 when the entry does not exist."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client)

        response = client.delete(
            f"/api/v1/stories/{story_id}/entries/01DOESNOTEXIST0000000000000"
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_delete_entry_wrong_story_returns_404(
        self, client: TestClient, seed_data: dict
    ):
        """Returns 404 when the entry exists but belongs to a different story."""
        auth_as(client, seed_data["gm"])
        story1_id = _create_story(client, "Story One")
        story2_id = _create_story(client, "Story Two")

        entry = _create_entry(client, story1_id, text="Entry in story 1.")
        entry_id = entry["id"]

        # Try to delete entry via story 2.
        response = client.delete(f"/api/v1/stories/{story2_id}/entries/{entry_id}")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_unauthenticated_delete_entry_returns_401(
        self, client: TestClient, seed_data: dict
    ):
        """Unauthenticated DELETE returns 401."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client)
        entry = _create_entry(client, story_id)
        entry_id = entry["id"]
        client.cookies.clear()

        response = client.delete(f"/api/v1/stories/{story_id}/entries/{entry_id}")
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/stories/{id} — entry ordering and filtering
# ---------------------------------------------------------------------------


class TestStoryDetailEntries:
    def test_entries_sorted_by_created_at_ascending(
        self, client: TestClient, seed_data: dict
    ):
        """Entries in story detail are sorted oldest-first."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client)

        e1 = _create_entry(client, story_id, text="First entry.")
        e2 = _create_entry(client, story_id, text="Second entry.")
        e3 = _create_entry(client, story_id, text="Third entry.")

        detail = client.get(f"/api/v1/stories/{story_id}").json()
        entry_ids = [e["id"] for e in detail["entries"]]

        assert entry_ids.index(e1["id"]) < entry_ids.index(e2["id"])
        assert entry_ids.index(e2["id"]) < entry_ids.index(e3["id"])

    def test_soft_deleted_entries_excluded_from_detail(
        self, client: TestClient, seed_data: dict
    ):
        """Soft-deleted entries do not appear in the story detail entries list."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client)

        kept = _create_entry(client, story_id, text="Keep this.")
        removed = _create_entry(client, story_id, text="Remove this.")

        client.delete(f"/api/v1/stories/{story_id}/entries/{removed['id']}")

        detail = client.get(f"/api/v1/stories/{story_id}").json()
        entry_ids = [e["id"] for e in detail["entries"]]
        assert kept["id"] in entry_ids
        assert removed["id"] not in entry_ids

    def test_mixed_entries_from_different_authors(
        self, client: TestClient, seed_data: dict
    ):
        """Entries from GM and multiple players all appear in detail."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client)
        # Make globally visible so all players can contribute entries.
        client.patch(f"/api/v1/stories/{story_id}", json={"visibility_level": "global"})

        gm_entry = _create_entry(client, story_id, text="GM observation.")

        auth_as(client, seed_data["player1"])
        p1_entry = _create_entry(client, story_id, text="Player 1 note.")

        auth_as(client, seed_data["player2"])
        p2_entry = _create_entry(client, story_id, text="Player 2 note.")

        auth_as(client, seed_data["gm"])
        detail = client.get(f"/api/v1/stories/{story_id}").json()
        entry_ids = [e["id"] for e in detail["entries"]]

        assert gm_entry["id"] in entry_ids
        assert p1_entry["id"] in entry_ids
        assert p2_entry["id"] in entry_ids


# ---------------------------------------------------------------------------
# GET /api/v1/stories/{id}/entries — paginated entries endpoint
# ---------------------------------------------------------------------------


class TestListStoryEntriesPaginated:
    """Tests for the new cursor-paginated entries sub-resource."""

    def test_returns_entries_oldest_first(self, client: TestClient, seed_data: dict):
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client)
        e1 = _create_entry(client, story_id, text="First")
        e2 = _create_entry(client, story_id, text="Second")

        resp = client.get(f"/api/v1/stories/{story_id}/entries")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 2
        assert body["items"][0]["id"] == e1["id"]
        assert body["items"][1]["id"] == e2["id"]
        assert body["has_more"] is False
        assert body["next_cursor"] is None

    def test_pagination_with_cursor(self, client: TestClient, seed_data: dict):
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client)
        entries = [_create_entry(client, story_id, text=f"Entry {i}") for i in range(5)]

        # Request with limit=2
        resp1 = client.get(f"/api/v1/stories/{story_id}/entries?limit=2")
        assert resp1.status_code == 200
        page1 = resp1.json()
        assert len(page1["items"]) == 2
        assert page1["has_more"] is True
        assert page1["next_cursor"] is not None

        # Continue with cursor
        resp2 = client.get(
            f"/api/v1/stories/{story_id}/entries?limit=2&after={page1['next_cursor']}"
        )
        page2 = resp2.json()
        assert len(page2["items"]) == 2
        assert page2["has_more"] is True

        # Third page has the last entry
        resp3 = client.get(
            f"/api/v1/stories/{story_id}/entries?limit=2&after={page2['next_cursor']}"
        )
        page3 = resp3.json()
        assert len(page3["items"]) == 1
        assert page3["has_more"] is False

        # All 5 entries returned across pages, in order
        all_ids = [e["id"] for e in page1["items"] + page2["items"] + page3["items"]]
        assert all_ids == [e["id"] for e in entries]

    def test_soft_deleted_entries_excluded(self, client: TestClient, seed_data: dict):
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client)
        e1 = _create_entry(client, story_id, text="Keep me")
        e2 = _create_entry(client, story_id, text="Delete me")

        # Soft-delete e2
        client.delete(f"/api/v1/stories/{story_id}/entries/{e2['id']}")

        resp = client.get(f"/api/v1/stories/{story_id}/entries")
        body = resp.json()
        assert len(body["items"]) == 1
        assert body["items"][0]["id"] == e1["id"]

    def test_story_not_found_returns_404(self, client: TestClient, seed_data: dict):
        auth_as(client, seed_data["gm"])
        resp = client.get("/api/v1/stories/00000000000000000000000099/entries")
        assert resp.status_code == 404

    def test_empty_story_returns_empty_list(self, client: TestClient, seed_data: dict):
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client)
        resp = client.get(f"/api/v1/stories/{story_id}/entries")
        body = resp.json()
        assert body["items"] == []
        assert body["has_more"] is False

    def test_unauthenticated_returns_401(self, client: TestClient):
        resp = client.get("/api/v1/stories/anything/entries")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/stories/{id} — inline entries capping
# ---------------------------------------------------------------------------


class TestDetailEntriesCapping:
    """Detail endpoint caps inline entries at 20 most recent."""

    def test_detail_caps_at_20_entries(self, client: TestClient, seed_data: dict):
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client)
        entries = [
            _create_entry(client, story_id, text=f"Entry {i}") for i in range(25)
        ]

        detail = client.get(f"/api/v1/stories/{story_id}").json()
        assert len(detail["entries"]) == 20
        assert detail["has_more_entries"] is True
        # Should be the newest 20 entries (entries[5:])
        inline_ids = [e["id"] for e in detail["entries"]]
        expected_ids = [e["id"] for e in entries[5:]]
        assert inline_ids == expected_ids

    def test_detail_under_cap_returns_all(self, client: TestClient, seed_data: dict):
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client)
        entries = [
            _create_entry(client, story_id, text=f"Entry {i}") for i in range(10)
        ]

        detail = client.get(f"/api/v1/stories/{story_id}").json()
        assert len(detail["entries"]) == 10
        assert detail["has_more_entries"] is False
        assert detail["entries_cursor"] is None
