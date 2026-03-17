"""Tests for Story 4.4.4 — Story Visibility.

Covers the unified visibility model applied to Story endpoints:

Visibility computation
  - GM always sees all stories
  - Player in visibility_overrides sees the story
  - PC-owner sees their own story (private visibility)
  - familiar (default) — bond-graph 2-hop traversal from owners
  - bonded — 1-hop traversal
  - public — 3-hop traversal
  - global — all players see it
  - gm_only — only GM sees it
  - private — only PC owners (and GM)
  - No owners → only GM sees the story
  - Mixed owners — union of owner rules

GET /api/v1/stories (list)
  - Player only sees stories they have visibility to
  - GM sees all stories
  - Stories outside the player's bond graph are hidden

GET /api/v1/stories/{id} (detail)
  - Player gets 404 for stories they cannot see
  - Player gets 200 for stories they can see
  - GM always gets the story

POST /api/v1/stories/{id}/entries (see=write)
  - Player can create entry when they can see the story
  - Player gets 404 when trying to create entry on invisible story
  - GM can always create entries
"""

import pytest
from fastapi.testclient import TestClient

from tests.conftest import auth_as


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_story(client: TestClient, name: str = "Test Story", **kwargs) -> str:
    """Create a story as the currently authenticated user and return its ID."""
    payload = {"name": name, **kwargs}
    resp = client.post("/api/v1/stories", json=payload)
    assert resp.status_code == 201, resp.json()
    return resp.json()["id"]


def _add_owner(client: TestClient, story_id: str, owner_type: str, owner_id: str) -> None:
    """Add a Game Object owner to a story (as GM)."""
    resp = client.post(
        f"/api/v1/stories/{story_id}/owners",
        json={"type": owner_type, "id": owner_id},
    )
    assert resp.status_code == 201, resp.json()


def _set_visibility(
    client: TestClient,
    story_id: str,
    level: str | None = None,
    overrides: list[str] | None = None,
) -> None:
    """Patch a story's visibility_level and/or visibility_overrides as GM."""
    payload: dict = {}
    if level is not None:
        payload["visibility_level"] = level
    if overrides is not None:
        payload["visibility_overrides"] = overrides
    resp = client.patch(f"/api/v1/stories/{story_id}", json=payload)
    assert resp.status_code == 200, resp.json()


# ---------------------------------------------------------------------------
# GM always sees everything
# ---------------------------------------------------------------------------


class TestGMVisibility:
    def test_gm_sees_story_with_no_owners(self, client: TestClient, seed_data: dict):
        """GM can see a story with no owners (no players can)."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client, "No Owner Story")

        response = client.get(f"/api/v1/stories/{story_id}")
        assert response.status_code == 200
        assert response.json()["id"] == story_id

    def test_gm_sees_gm_only_story(self, client: TestClient, seed_data: dict):
        """GM can see a gm_only story."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client, "GM Only Story")
        _set_visibility(client, story_id, level="gm_only")

        response = client.get(f"/api/v1/stories/{story_id}")
        assert response.status_code == 200

    def test_gm_sees_all_stories_in_list(self, client: TestClient, seed_data: dict):
        """GM list includes stories of all visibility levels."""
        auth_as(client, seed_data["gm"])
        story_a = _create_story(client, "GM Story A")
        story_b = _create_story(client, "GM Story B")
        _set_visibility(client, story_b, level="gm_only")

        response = client.get("/api/v1/stories")
        assert response.status_code == 200
        ids = [s["id"] for s in response.json()["items"]]
        assert story_a in ids
        assert story_b in ids


# ---------------------------------------------------------------------------
# No-owner stories — player cannot see
# ---------------------------------------------------------------------------


class TestNoOwnerVisibility:
    def test_player_cannot_see_story_with_no_owners(
        self, client: TestClient, seed_data: dict
    ):
        """A story with no owners is invisible to players (no bond-graph path)."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client, "Ownerless Story")

        auth_as(client, seed_data["player1"])
        response = client.get(f"/api/v1/stories/{story_id}")
        assert response.status_code == 404

    def test_ownerless_story_absent_from_player_list(
        self, client: TestClient, seed_data: dict
    ):
        """Ownerless story does not appear in a player's list results."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client, "Hidden Story")

        auth_as(client, seed_data["player1"])
        response = client.get("/api/v1/stories")
        assert response.status_code == 200
        ids = [s["id"] for s in response.json()["items"]]
        assert story_id not in ids


# ---------------------------------------------------------------------------
# Global visibility — all players see it
# ---------------------------------------------------------------------------


class TestGlobalVisibility:
    def test_global_story_visible_to_all_players(
        self, client: TestClient, seed_data: dict
    ):
        """A story at global visibility is visible to every authenticated player."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client, "Global Announcement")
        _set_visibility(client, story_id, level="global")

        for player_key in ("player1", "player2", "player3"):
            auth_as(client, seed_data[player_key])
            response = client.get(f"/api/v1/stories/{story_id}")
            assert response.status_code == 200, f"{player_key} should see global story"

    def test_global_story_in_list_for_all_players(
        self, client: TestClient, seed_data: dict
    ):
        """Global story appears in the list for every player."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client, "World Event")
        _set_visibility(client, story_id, level="global")

        for player_key in ("player1", "player2", "player3"):
            auth_as(client, seed_data[player_key])
            response = client.get("/api/v1/stories")
            assert response.status_code == 200
            ids = [s["id"] for s in response.json()["items"]]
            assert story_id in ids, f"Global story missing from {player_key} list"


# ---------------------------------------------------------------------------
# GM-only visibility — players cannot see
# ---------------------------------------------------------------------------


class TestGMOnlyVisibility:
    def test_gm_only_story_invisible_to_players(
        self, client: TestClient, seed_data: dict
    ):
        """A gm_only story returns 404 for any player."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client, "Secret GM Notes")
        _set_visibility(client, story_id, level="gm_only")

        auth_as(client, seed_data["player1"])
        response = client.get(f"/api/v1/stories/{story_id}")
        assert response.status_code == 404

    def test_gm_only_story_absent_from_player_list(
        self, client: TestClient, seed_data: dict
    ):
        """gm_only story does not appear in player list."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client, "GM-Only Story")
        _set_visibility(client, story_id, level="gm_only")

        auth_as(client, seed_data["player1"])
        response = client.get("/api/v1/stories")
        ids = [s["id"] for s in response.json()["items"]]
        assert story_id not in ids


# ---------------------------------------------------------------------------
# PC-owner access — private and above
# ---------------------------------------------------------------------------


class TestPCOwnerAccess:
    def test_pc_owner_sees_private_story(self, client: TestClient, seed_data: dict):
        """PC owner always sees the story at private level."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client, "Private PC Story")
        _add_owner(client, story_id, "character", seed_data["pc1"].id)
        _set_visibility(client, story_id, level="private")

        auth_as(client, seed_data["player1"])  # player1 owns pc1
        response = client.get(f"/api/v1/stories/{story_id}")
        assert response.status_code == 200

    def test_non_owner_cannot_see_private_story(
        self, client: TestClient, seed_data: dict
    ):
        """A private story owned by one PC is invisible to other players."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client, "Private PC Story")
        _add_owner(client, story_id, "character", seed_data["pc1"].id)
        _set_visibility(client, story_id, level="private")

        auth_as(client, seed_data["player2"])  # player2 owns pc2, not pc1
        response = client.get(f"/api/v1/stories/{story_id}")
        assert response.status_code == 404

    def test_pc_owner_sees_story_regardless_of_level(
        self, client: TestClient, seed_data: dict
    ):
        """PC owner sees the story even when visibility_level is 'bonded'."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client, "Bonded PC Story")
        _add_owner(client, story_id, "character", seed_data["pc1"].id)
        _set_visibility(client, story_id, level="bonded")

        auth_as(client, seed_data["player1"])
        response = client.get(f"/api/v1/stories/{story_id}")
        assert response.status_code == 200

    def test_pc_owner_story_appears_in_owner_list(
        self, client: TestClient, seed_data: dict
    ):
        """Story with PC owner appears in that PC owner's list."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client, "My PC Story")
        _add_owner(client, story_id, "character", seed_data["pc1"].id)

        auth_as(client, seed_data["player1"])
        response = client.get("/api/v1/stories")
        ids = [s["id"] for s in response.json()["items"]]
        assert story_id in ids


# ---------------------------------------------------------------------------
# Visibility overrides — GM can grant per-user access
# ---------------------------------------------------------------------------


class TestVisibilityOverrides:
    def test_override_grants_access_to_gm_only_story(
        self, client: TestClient, seed_data: dict
    ):
        """A user in visibility_overrides can see a gm_only story."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client, "GM Story with Override")
        _set_visibility(
            client,
            story_id,
            level="gm_only",
            overrides=[seed_data["player1"].id],
        )

        auth_as(client, seed_data["player1"])
        response = client.get(f"/api/v1/stories/{story_id}")
        assert response.status_code == 200

    def test_override_does_not_grant_access_to_non_overridden_player(
        self, client: TestClient, seed_data: dict
    ):
        """Only users explicitly in visibility_overrides get the override benefit."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client, "Partially Overridden Story")
        _set_visibility(
            client,
            story_id,
            level="gm_only",
            overrides=[seed_data["player1"].id],
        )

        auth_as(client, seed_data["player2"])  # not in overrides
        response = client.get(f"/api/v1/stories/{story_id}")
        assert response.status_code == 404

    def test_override_story_appears_in_overridden_player_list(
        self, client: TestClient, seed_data: dict
    ):
        """Overridden story appears in that player's list results."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client, "Override List Story")
        _set_visibility(
            client,
            story_id,
            level="gm_only",
            overrides=[seed_data["player1"].id],
        )

        auth_as(client, seed_data["player1"])
        response = client.get("/api/v1/stories")
        ids = [s["id"] for s in response.json()["items"]]
        assert story_id in ids


# ---------------------------------------------------------------------------
# Bond-graph traversal — familiar (default 2-hop)
# ---------------------------------------------------------------------------


class TestBondGraphFamiliarVisibility:
    """Uses the canonical seed data bond graph:

    pc1 ←→ group ←→ pc2   (both pc1 and pc2 have bidirectional bonds to group)
    pc3 has no bonds to anything in this graph.

    A story owned by group at familiar (2-hop) is visible to pc1 and pc2
    because: pc1/pc2 → group (1 hop) = bonded, group is the starting owner.
    Actually the traversal goes FROM the owner (group), so at 2 hops:
    group → pc1 (1-hop), group → pc2 (1-hop).
    So pc1 and pc2 are reachable at 1-hop from the group owner.
    pc3 has no bonds to group → not reachable → cannot see.
    """

    def test_familiar_story_visible_to_bonded_player(
        self, client: TestClient, seed_data: dict
    ):
        """Story owned by group is visible to players bonded to that group (1-hop from owner)."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client, "Group Story (Familiar)")
        _add_owner(client, story_id, "group", seed_data["group"].id)
        # Default visibility_level is familiar (no need to set explicitly)

        auth_as(client, seed_data["player1"])  # pc1 bonded to group
        response = client.get(f"/api/v1/stories/{story_id}")
        assert response.status_code == 200

    def test_familiar_story_visible_to_second_bonded_player(
        self, client: TestClient, seed_data: dict
    ):
        """Both players bonded to the same group can see a group-owned story."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client, "Group Story (Familiar) 2")
        _add_owner(client, story_id, "group", seed_data["group"].id)

        auth_as(client, seed_data["player2"])  # pc2 bonded to group
        response = client.get(f"/api/v1/stories/{story_id}")
        assert response.status_code == 200

    def test_familiar_story_invisible_to_unbonded_player(
        self, client: TestClient, seed_data: dict
    ):
        """Player with no bond to the group owner cannot see the story."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client, "Group Story (Familiar) 3")
        _add_owner(client, story_id, "group", seed_data["group"].id)

        auth_as(client, seed_data["player3"])  # pc3 has no bonds to group
        response = client.get(f"/api/v1/stories/{story_id}")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Mixed owners — union rule
# ---------------------------------------------------------------------------


class TestMixedOwnerUnionRule:
    def test_mixed_owner_union_both_owners_grant_access(
        self, client: TestClient, seed_data: dict
    ):
        """Story with PC owner AND group owner: PC owner sees it, group-bonded players see it."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client, "Mixed Owner Story")
        # PC1 is a direct owner.
        _add_owner(client, story_id, "character", seed_data["pc1"].id)
        # Group is also an owner — pc2 is bonded to the group.
        _add_owner(client, story_id, "group", seed_data["group"].id)

        # player1 (pc1) sees via PC ownership.
        auth_as(client, seed_data["player1"])
        assert client.get(f"/api/v1/stories/{story_id}").status_code == 200

        # player2 (pc2) sees via group bond (1-hop from group owner).
        auth_as(client, seed_data["player2"])
        assert client.get(f"/api/v1/stories/{story_id}").status_code == 200

    def test_mixed_owner_unbonded_player_still_excluded(
        self, client: TestClient, seed_data: dict
    ):
        """Player with no path to any owner cannot see a mixed-owner story."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client, "Mixed Owner Story Exclusive")
        _add_owner(client, story_id, "character", seed_data["pc1"].id)
        _add_owner(client, story_id, "group", seed_data["group"].id)
        # visibility_level at default familiar

        auth_as(client, seed_data["player3"])  # pc3 has no bonds to pc1 or group
        assert client.get(f"/api/v1/stories/{story_id}").status_code == 404


# ---------------------------------------------------------------------------
# See = Write enforcement
# ---------------------------------------------------------------------------


class TestSeeEqualsWrite:
    def test_visible_story_allows_entry_creation(
        self, client: TestClient, seed_data: dict
    ):
        """Player who can see a story can create entries on it."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client, "Entry Test Story")
        _set_visibility(client, story_id, level="global")

        auth_as(client, seed_data["player1"])
        response = client.post(
            f"/api/v1/stories/{story_id}/entries",
            json={"text": "Adding to the narrative."},
        )
        assert response.status_code == 201

    def test_invisible_story_blocks_entry_creation(
        self, client: TestClient, seed_data: dict
    ):
        """Player who cannot see a story gets 404 when trying to create entries."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client, "Hidden Entry Story")
        # No owners, default familiar → player cannot see

        auth_as(client, seed_data["player1"])
        response = client.post(
            f"/api/v1/stories/{story_id}/entries",
            json={"text": "Should be blocked."},
        )
        assert response.status_code == 404

    def test_pc_owner_can_create_entry(self, client: TestClient, seed_data: dict):
        """PC owner (private story) can create entries on their own story."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client, "Owner Entry Story")
        _add_owner(client, story_id, "character", seed_data["pc1"].id)
        _set_visibility(client, story_id, level="private")

        auth_as(client, seed_data["player1"])  # player1 owns pc1
        response = client.post(
            f"/api/v1/stories/{story_id}/entries",
            json={"text": "My private note."},
        )
        assert response.status_code == 201

    def test_non_owner_blocked_from_private_story_entries(
        self, client: TestClient, seed_data: dict
    ):
        """Non-owner player cannot create entries on a private story."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client, "Private Entry Story")
        _add_owner(client, story_id, "character", seed_data["pc1"].id)
        _set_visibility(client, story_id, level="private")

        auth_as(client, seed_data["player2"])  # player2 owns pc2, not pc1
        response = client.post(
            f"/api/v1/stories/{story_id}/entries",
            json={"text": "Sneaky entry."},
        )
        assert response.status_code == 404

    def test_gm_can_always_create_entries(self, client: TestClient, seed_data: dict):
        """GM can create entries on any story regardless of visibility."""
        auth_as(client, seed_data["gm"])
        story_id = _create_story(client, "GM Entry Test Story")
        _set_visibility(client, story_id, level="gm_only")

        response = client.post(
            f"/api/v1/stories/{story_id}/entries",
            json={"text": "GM annotation."},
        )
        assert response.status_code == 201


# ---------------------------------------------------------------------------
# List filtering — only visible stories appear
# ---------------------------------------------------------------------------


class TestListVisibilityFiltering:
    def test_list_shows_only_visible_stories_to_player(
        self, client: TestClient, seed_data: dict
    ):
        """Story list for a player only includes stories they can see."""
        auth_as(client, seed_data["gm"])

        # Visible: pc1-owned story (player1 can see via PC ownership)
        visible_id = _create_story(client, "Visible Story")
        _add_owner(client, visible_id, "character", seed_data["pc1"].id)

        # Hidden: gm_only story with no overrides
        hidden_id = _create_story(client, "Hidden GM Story")
        _set_visibility(client, hidden_id, level="gm_only")

        # Hidden: story with no owners
        ownerless_id = _create_story(client, "Ownerless Story")

        auth_as(client, seed_data["player1"])
        response = client.get("/api/v1/stories")
        assert response.status_code == 200
        ids = [s["id"] for s in response.json()["items"]]

        assert visible_id in ids
        assert hidden_id not in ids
        assert ownerless_id not in ids

    def test_gm_list_includes_all_stories(self, client: TestClient, seed_data: dict):
        """GM story list includes stories of all visibility levels."""
        auth_as(client, seed_data["gm"])

        visible_id = _create_story(client, "Visible")
        _add_owner(client, visible_id, "character", seed_data["pc1"].id)

        gm_only_id = _create_story(client, "GM Only")
        _set_visibility(client, gm_only_id, level="gm_only")

        ownerless_id = _create_story(client, "Ownerless")

        response = client.get("/api/v1/stories")
        ids = [s["id"] for s in response.json()["items"]]

        assert visible_id in ids
        assert gm_only_id in ids
        assert ownerless_id in ids
