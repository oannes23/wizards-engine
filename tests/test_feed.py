"""Integration tests for per-Game Object feed endpoints (Story 4.4.1).

Exercises:
- GET /characters/{id}/feed
- GET /groups/{id}/feed
- GET /locations/{id}/feed

Coverage:
- Happy path: merged event + story entry items
- Discriminated union shape (event vs story_entry)
- Visibility filtering (silent excluded, gm_only excluded for players)
- Event-only filters exclude story entries
- ULID cursor pagination
- Filter parameters: type, actor_type, session_id, target_type, target_id,
  since, until
- 404 for non-existent Game Object
- 401 for unauthenticated requests
- Story entries via story ownership and via game_object_refs
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import auth_as
from wizards_engine.models.event import Event, EventTarget
from wizards_engine.models.story import Story, StoryEntry, StoryOwner


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _event(
    db: Session,
    *,
    event_type: str = "test.event",
    actor_type: str = "gm",
    actor_id: str | None = None,
    visibility: str = "global",
    session_id: str | None = None,
    targets: list[tuple[str, str, bool]] | None = None,
    narrative: str | None = None,
) -> Event:
    """Create and flush a minimal Event."""
    ev = Event(
        type=event_type,
        actor_type=actor_type,
        actor_id=actor_id,
        changes={},
        visibility=visibility,
        session_id=session_id,
        narrative=narrative,
    )
    db.add(ev)
    db.flush()

    for t_type, t_id, is_primary in (targets or []):
        et = EventTarget(
            event_id=ev.id,
            target_type=t_type,
            target_id=t_id,
            is_primary=is_primary,
        )
        db.add(et)

    db.flush()
    db.refresh(ev)
    return ev


def _story_with_entry(
    db: Session,
    *,
    owner_type: str,
    owner_id: str,
    entry_text: str = "A story entry.",
    author_id: str,
    visibility_level: str | None = None,
    game_object_refs: list[dict] | None = None,
) -> tuple[Story, StoryEntry]:
    """Create a Story with one StoryEntry and commit."""
    story = Story(
        name="Test Story",
        status="active",
        visibility_level=visibility_level,
    )
    db.add(story)
    db.flush()

    owner = StoryOwner(
        story_id=story.id,
        owner_type=owner_type,
        owner_id=owner_id,
    )
    db.add(owner)
    db.flush()

    entry = StoryEntry(
        story_id=story.id,
        text=entry_text,
        author_id=author_id,
        game_object_refs=game_object_refs,
    )
    db.add(entry)
    db.flush()

    db.refresh(story)
    db.refresh(entry)
    return story, entry


# ===========================================================================
# Character feed tests
# ===========================================================================


class TestCharacterFeed:
    """Tests for GET /api/v1/characters/{id}/feed."""

    def test_returns_event_targeting_character(self, client, db, seed_data):
        """An event targeting the character appears in the feed."""
        pc1 = seed_data["pc1"]
        gm = seed_data["gm"]
        ev = _event(
            db,
            visibility="global",
            targets=[("character", pc1.id, True)],
            narrative="Something happened.",
        )
        db.commit()

        auth_as(client, gm)
        resp = client.get(f"/api/v1/characters/{pc1.id}/feed")
        assert resp.status_code == 200

        data = resp.json()
        assert "items" in data
        ids = [item["id"] for item in data["items"]]
        assert ev.id in ids

    def test_event_item_shape(self, client, db, seed_data):
        """Event feed items have all required fields with type='event'."""
        pc1 = seed_data["pc1"]
        gm = seed_data["gm"]
        ev = _event(
            db,
            event_type="character.stress_changed",
            actor_type="gm",
            actor_id=gm.id,
            visibility="global",
            targets=[("character", pc1.id, True)],
            narrative="Stress changed.",
        )
        db.commit()

        auth_as(client, gm)
        resp = client.get(f"/api/v1/characters/{pc1.id}/feed")
        assert resp.status_code == 200

        items = resp.json()["items"]
        item = next(i for i in items if i["id"] == ev.id)

        assert item["type"] == "event"
        assert item["event_type"] == "character.stress_changed"
        assert item["actor_type"] == "gm"
        assert item["actor_id"] == gm.id
        assert item["narrative"] == "Stress changed."
        assert item["visibility"] == "global"
        assert item["is_own"] is True  # GM is actor_id == gm.id
        assert isinstance(item["timestamp"], str)
        assert isinstance(item["targets"], list)
        assert item["changes"] == {}
        # Event-specific optional fields present
        assert "proposal_id" in item
        assert "parent_event_id" in item
        assert "session_id" in item
        assert "metadata" in item

    def test_story_entry_item_shape(self, client, db, seed_data):
        """Story entry feed items have all required fields with type='story_entry'."""
        pc1 = seed_data["pc1"]
        player1 = seed_data["player1"]
        gm = seed_data["gm"]

        story, entry = _story_with_entry(
            db,
            owner_type="character",
            owner_id=pc1.id,
            entry_text="A narrative entry.",
            author_id=player1.id,
        )
        db.commit()

        auth_as(client, gm)
        resp = client.get(f"/api/v1/characters/{pc1.id}/feed")
        assert resp.status_code == 200

        items = resp.json()["items"]
        item = next(i for i in items if i["id"] == entry.id)

        assert item["type"] == "story_entry"
        assert item["story_id"] == story.id
        assert item["story_name"] == "Test Story"
        assert item["entry_text"] == "A narrative entry."
        assert item["author_id"] == player1.id
        assert item["visibility"] == "familiar"  # default
        assert item["is_own"] is False  # gm is not the author
        assert isinstance(item["targets"], list)
        assert {"type": "character", "id": pc1.id} in item["targets"]

    def test_mixed_items_sorted_newest_first(self, client, db, seed_data):
        """Feed returns events and story entries merged newest-first."""
        pc1 = seed_data["pc1"]
        gm = seed_data["gm"]

        ev = _event(
            db,
            visibility="global",
            targets=[("character", pc1.id, True)],
        )
        _story, entry = _story_with_entry(
            db,
            owner_type="character",
            owner_id=pc1.id,
            author_id=gm.id,
        )
        db.commit()

        auth_as(client, gm)
        resp = client.get(f"/api/v1/characters/{pc1.id}/feed")
        assert resp.status_code == 200

        items = resp.json()["items"]
        ids = [i["id"] for i in items]
        # Sorted newest-first (ULID lexicographic desc)
        assert ids == sorted(ids, reverse=True)
        assert ev.id in ids
        assert entry.id in ids

    def test_silent_event_excluded(self, client, db, seed_data):
        """Silent events are excluded from the normal feed."""
        pc1 = seed_data["pc1"]
        gm = seed_data["gm"]

        silent_ev = _event(
            db,
            visibility="silent",
            targets=[("character", pc1.id, True)],
        )
        db.commit()

        auth_as(client, gm)
        resp = client.get(f"/api/v1/characters/{pc1.id}/feed")
        assert resp.status_code == 200

        ids = [item["id"] for item in resp.json()["items"]]
        assert silent_ev.id not in ids

    def test_gm_only_event_hidden_from_player(self, client, db, seed_data):
        """gm_only events are not visible to players."""
        pc1 = seed_data["pc1"]
        player1 = seed_data["player1"]

        ev = _event(
            db,
            visibility="gm_only",
            targets=[("character", pc1.id, True)],
        )
        db.commit()

        auth_as(client, player1)
        resp = client.get(f"/api/v1/characters/{pc1.id}/feed")
        assert resp.status_code == 200

        ids = [item["id"] for item in resp.json()["items"]]
        assert ev.id not in ids

    def test_gm_only_event_visible_to_gm(self, client, db, seed_data):
        """gm_only events are visible to the GM."""
        pc1 = seed_data["pc1"]
        gm = seed_data["gm"]

        ev = _event(
            db,
            visibility="gm_only",
            targets=[("character", pc1.id, True)],
        )
        db.commit()

        auth_as(client, gm)
        resp = client.get(f"/api/v1/characters/{pc1.id}/feed")
        assert resp.status_code == 200

        ids = [item["id"] for item in resp.json()["items"]]
        assert ev.id in ids

    def test_event_not_targeting_character_excluded(self, client, db, seed_data):
        """Events targeting a different character are not in the feed."""
        pc1 = seed_data["pc1"]
        pc2 = seed_data["pc2"]
        gm = seed_data["gm"]

        other_ev = _event(
            db,
            visibility="global",
            targets=[("character", pc2.id, True)],
        )
        db.commit()

        auth_as(client, gm)
        resp = client.get(f"/api/v1/characters/{pc1.id}/feed")
        assert resp.status_code == 200

        ids = [item["id"] for item in resp.json()["items"]]
        assert other_ev.id not in ids

    def test_404_for_nonexistent_character(self, client, seed_data):
        """Returns 404 when the character does not exist."""
        gm = seed_data["gm"]
        auth_as(client, gm)
        resp = client.get("/api/v1/characters/DOESNOTEXIST12345678901234/feed")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "not_found"

    def test_401_when_unauthenticated(self, client, seed_data):
        """Returns 401 when no auth cookie is present."""
        pc1 = seed_data["pc1"]
        client.cookies.clear()
        resp = client.get(f"/api/v1/characters/{pc1.id}/feed")
        assert resp.status_code == 401

    def test_pagination_basics(self, client, db, seed_data):
        """Pagination envelope fields are present and correct."""
        pc1 = seed_data["pc1"]
        gm = seed_data["gm"]
        db.commit()

        auth_as(client, gm)
        resp = client.get(f"/api/v1/characters/{pc1.id}/feed")
        assert resp.status_code == 200

        data = resp.json()
        assert "items" in data
        assert "next_cursor" in data
        assert "has_more" in data

    def test_pagination_limit(self, client, db, seed_data):
        """limit parameter restricts the number of items returned."""
        pc1 = seed_data["pc1"]
        gm = seed_data["gm"]

        for i in range(5):
            _event(
                db,
                visibility="global",
                targets=[("character", pc1.id, True)],
            )
        db.commit()

        auth_as(client, gm)
        resp = client.get(f"/api/v1/characters/{pc1.id}/feed?limit=2")
        assert resp.status_code == 200

        data = resp.json()
        assert len(data["items"]) == 2
        assert data["has_more"] is True
        assert data["next_cursor"] is not None

    def test_pagination_after_cursor(self, client, db, seed_data):
        """after parameter returns items older than the given cursor."""
        pc1 = seed_data["pc1"]
        gm = seed_data["gm"]

        evs = [
            _event(
                db,
                visibility="global",
                targets=[("character", pc1.id, True)],
            )
            for _ in range(4)
        ]
        db.commit()

        # Get first page (limit=2).
        auth_as(client, gm)
        resp1 = client.get(f"/api/v1/characters/{pc1.id}/feed?limit=2")
        assert resp1.status_code == 200
        page1 = resp1.json()
        assert page1["has_more"] is True

        cursor = page1["next_cursor"]
        resp2 = client.get(f"/api/v1/characters/{pc1.id}/feed?limit=2&after={cursor}")
        assert resp2.status_code == 200
        page2 = resp2.json()

        # No overlap between pages.
        ids1 = {i["id"] for i in page1["items"]}
        ids2 = {i["id"] for i in page2["items"]}
        assert ids1.isdisjoint(ids2)

    def test_filter_type_prefix(self, client, db, seed_data):
        """?type=character.* returns only events matching the prefix."""
        pc1 = seed_data["pc1"]
        gm = seed_data["gm"]

        char_ev = _event(
            db,
            event_type="character.stress_changed",
            visibility="global",
            targets=[("character", pc1.id, True)],
        )
        other_ev = _event(
            db,
            event_type="session.started",
            visibility="global",
            targets=[("character", pc1.id, True)],
        )
        db.commit()

        auth_as(client, gm)
        resp = client.get(f"/api/v1/characters/{pc1.id}/feed?type=character.*")
        assert resp.status_code == 200

        ids = [item["id"] for item in resp.json()["items"]]
        assert char_ev.id in ids
        assert other_ev.id not in ids

    def test_filter_type_excludes_story_entries(self, client, db, seed_data):
        """?type= filter excludes story entries entirely."""
        pc1 = seed_data["pc1"]
        gm = seed_data["gm"]

        _story, entry = _story_with_entry(
            db,
            owner_type="character",
            owner_id=pc1.id,
            author_id=gm.id,
        )
        ev = _event(
            db,
            event_type="character.stress_changed",
            visibility="global",
            targets=[("character", pc1.id, True)],
        )
        db.commit()

        auth_as(client, gm)
        resp = client.get(f"/api/v1/characters/{pc1.id}/feed?type=character.*")
        assert resp.status_code == 200

        types = [item["type"] for item in resp.json()["items"]]
        assert "story_entry" not in types
        assert "event" in types

    def test_filter_actor_type_excludes_story_entries(self, client, db, seed_data):
        """?actor_type= filter excludes story entries entirely."""
        pc1 = seed_data["pc1"]
        gm = seed_data["gm"]

        _story, _entry = _story_with_entry(
            db,
            owner_type="character",
            owner_id=pc1.id,
            author_id=gm.id,
        )
        _ev = _event(
            db,
            actor_type="gm",
            visibility="global",
            targets=[("character", pc1.id, True)],
        )
        db.commit()

        auth_as(client, gm)
        resp = client.get(f"/api/v1/characters/{pc1.id}/feed?actor_type=gm")
        assert resp.status_code == 200

        types = [item["type"] for item in resp.json()["items"]]
        assert "story_entry" not in types

    def test_filter_session_id(self, client, db, seed_data):
        """?session_id= returns only events and entries from that session."""
        pc1 = seed_data["pc1"]
        gm = seed_data["gm"]

        from wizards_engine.models.session import Session as SessionModel
        session = SessionModel(status="ended", summary="Session 1")
        db.add(session)
        db.flush()

        ev_with_session = _event(
            db,
            visibility="global",
            session_id=session.id,
            targets=[("character", pc1.id, True)],
        )
        ev_no_session = _event(
            db,
            visibility="global",
            targets=[("character", pc1.id, True)],
        )
        db.commit()

        auth_as(client, gm)
        resp = client.get(f"/api/v1/characters/{pc1.id}/feed?session_id={session.id}")
        assert resp.status_code == 200

        ids = [item["id"] for item in resp.json()["items"]]
        assert ev_with_session.id in ids
        assert ev_no_session.id not in ids

    def test_filter_since_until(self, client, db, seed_data):
        """?since= and ?until= filter by timestamp."""
        pc1 = seed_data["pc1"]
        gm = seed_data["gm"]

        ev = _event(
            db,
            visibility="global",
            targets=[("character", pc1.id, True)],
        )
        db.commit()

        db.refresh(ev)
        ts = ev.created_at

        # since after the event → empty
        future = (ts + timedelta(seconds=1)).isoformat()
        auth_as(client, gm)
        resp = client.get(f"/api/v1/characters/{pc1.id}/feed?since={future}")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 0

        # until before the event → empty
        past = (ts - timedelta(seconds=1)).isoformat()
        resp2 = client.get(f"/api/v1/characters/{pc1.id}/feed?until={past}")
        assert resp2.status_code == 200
        assert len(resp2.json()["items"]) == 0

        # since before → includes the event
        earlier = (ts - timedelta(seconds=1)).isoformat()
        resp3 = client.get(f"/api/v1/characters/{pc1.id}/feed?since={earlier}")
        assert resp3.status_code == 200
        ids = [i["id"] for i in resp3.json()["items"]]
        assert ev.id in ids

    def test_story_entry_via_game_object_refs(self, client, db, seed_data):
        """Story entries that reference the character via game_object_refs appear in feed."""
        pc1 = seed_data["pc1"]
        pc2 = seed_data["pc2"]
        gm = seed_data["gm"]

        # Story owned by pc2, but entry references pc1.
        story, entry = _story_with_entry(
            db,
            owner_type="character",
            owner_id=pc2.id,
            author_id=gm.id,
            game_object_refs=[{"type": "character", "id": pc1.id}],
        )
        db.commit()

        auth_as(client, gm)
        resp = client.get(f"/api/v1/characters/{pc1.id}/feed")
        assert resp.status_code == 200

        ids = [item["id"] for item in resp.json()["items"]]
        assert entry.id in ids

    def test_story_entry_targets_include_refs(self, client, db, seed_data):
        """Story entry item targets = union of story owners + game_object_refs."""
        pc1 = seed_data["pc1"]
        pc2 = seed_data["pc2"]
        gm = seed_data["gm"]

        story, entry = _story_with_entry(
            db,
            owner_type="character",
            owner_id=pc1.id,
            author_id=gm.id,
            game_object_refs=[{"type": "character", "id": pc2.id}],
        )
        db.commit()

        auth_as(client, gm)
        resp = client.get(f"/api/v1/characters/{pc1.id}/feed")
        assert resp.status_code == 200

        items = resp.json()["items"]
        item = next(i for i in items if i["id"] == entry.id)
        target_tuples = {(t["type"], t["id"]) for t in item["targets"]}

        # Should include story owner (pc1) and ref (pc2).
        assert ("character", pc1.id) in target_tuples
        assert ("character", pc2.id) in target_tuples

    def test_is_own_true_for_event_actor(self, client, db, seed_data):
        """is_own is True when the authenticated player is the event actor."""
        pc1 = seed_data["pc1"]
        player1 = seed_data["player1"]

        ev = _event(
            db,
            actor_type="player",
            actor_id=player1.id,
            visibility="global",
            targets=[("character", pc1.id, True)],
        )
        db.commit()

        auth_as(client, player1)
        resp = client.get(f"/api/v1/characters/{pc1.id}/feed")
        assert resp.status_code == 200

        items = resp.json()["items"]
        item = next(i for i in items if i["id"] == ev.id)
        assert item["is_own"] is True

    def test_is_own_false_for_other_actor(self, client, db, seed_data):
        """is_own is False when a different player is the event actor."""
        pc1 = seed_data["pc1"]
        player1 = seed_data["player1"]
        player2 = seed_data["player2"]

        ev = _event(
            db,
            actor_type="player",
            actor_id=player2.id,
            visibility="global",
            targets=[("character", pc1.id, True)],
        )
        db.commit()

        auth_as(client, player1)
        resp = client.get(f"/api/v1/characters/{pc1.id}/feed")
        assert resp.status_code == 200

        items = resp.json()["items"]
        item = next(i for i in items if i["id"] == ev.id)
        assert item["is_own"] is False

    def test_is_own_true_for_story_entry_author(self, client, db, seed_data):
        """is_own is True when the authenticated user is the story entry author."""
        pc1 = seed_data["pc1"]
        player1 = seed_data["player1"]

        _story, entry = _story_with_entry(
            db,
            owner_type="character",
            owner_id=pc1.id,
            author_id=player1.id,
        )
        db.commit()

        auth_as(client, player1)
        resp = client.get(f"/api/v1/characters/{pc1.id}/feed")
        assert resp.status_code == 200

        items = resp.json()["items"]
        item = next(i for i in items if i["id"] == entry.id)
        assert item["is_own"] is True

    def test_gm_only_story_hidden_from_player(self, client, db, seed_data):
        """Story entries with gm_only visibility are hidden from players."""
        pc1 = seed_data["pc1"]
        player1 = seed_data["player1"]
        gm = seed_data["gm"]

        _story, entry = _story_with_entry(
            db,
            owner_type="character",
            owner_id=pc1.id,
            author_id=gm.id,
            visibility_level="gm_only",
        )
        db.commit()

        auth_as(client, player1)
        resp = client.get(f"/api/v1/characters/{pc1.id}/feed")
        assert resp.status_code == 200

        ids = [item["id"] for item in resp.json()["items"]]
        assert entry.id not in ids

    def test_empty_feed_response(self, client, db, seed_data):
        """Returns an empty items list when no events or entries exist."""
        pc1 = seed_data["pc1"]
        gm = seed_data["gm"]

        auth_as(client, gm)
        resp = client.get(f"/api/v1/characters/{pc1.id}/feed")
        assert resp.status_code == 200

        data = resp.json()
        assert data["items"] == []
        assert data["has_more"] is False
        assert data["next_cursor"] is None


# ===========================================================================
# Group feed tests
# ===========================================================================


class TestGroupFeed:
    """Tests for GET /api/v1/groups/{id}/feed."""

    def test_returns_event_targeting_group(self, client, db, seed_data):
        """An event targeting the group appears in the feed."""
        group = seed_data["group"]
        gm = seed_data["gm"]

        ev = _event(
            db,
            visibility="global",
            targets=[("group", group.id, True)],
        )
        db.commit()

        auth_as(client, gm)
        resp = client.get(f"/api/v1/groups/{group.id}/feed")
        assert resp.status_code == 200

        ids = [item["id"] for item in resp.json()["items"]]
        assert ev.id in ids

    def test_returns_story_entry_owned_by_group(self, client, db, seed_data):
        """Story entries on group-owned stories appear in the group feed."""
        group = seed_data["group"]
        gm = seed_data["gm"]

        _story, entry = _story_with_entry(
            db,
            owner_type="group",
            owner_id=group.id,
            author_id=gm.id,
        )
        db.commit()

        auth_as(client, gm)
        resp = client.get(f"/api/v1/groups/{group.id}/feed")
        assert resp.status_code == 200

        ids = [item["id"] for item in resp.json()["items"]]
        assert entry.id in ids

    def test_404_for_nonexistent_group(self, client, seed_data):
        """Returns 404 when the group does not exist."""
        gm = seed_data["gm"]
        auth_as(client, gm)
        resp = client.get("/api/v1/groups/DOESNOTEXIST12345678901234/feed")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "not_found"


# ===========================================================================
# Location feed tests
# ===========================================================================


class TestLocationFeed:
    """Tests for GET /api/v1/locations/{id}/feed."""

    def test_returns_event_targeting_location(self, client, db, seed_data):
        """An event targeting the location appears in the feed."""
        region = seed_data["region"]
        gm = seed_data["gm"]

        ev = _event(
            db,
            visibility="global",
            targets=[("location", region.id, True)],
        )
        db.commit()

        auth_as(client, gm)
        resp = client.get(f"/api/v1/locations/{region.id}/feed")
        assert resp.status_code == 200

        ids = [item["id"] for item in resp.json()["items"]]
        assert ev.id in ids

    def test_returns_story_entry_owned_by_location(self, client, db, seed_data):
        """Story entries on location-owned stories appear in the location feed."""
        region = seed_data["region"]
        gm = seed_data["gm"]

        _story, entry = _story_with_entry(
            db,
            owner_type="location",
            owner_id=region.id,
            author_id=gm.id,
        )
        db.commit()

        auth_as(client, gm)
        resp = client.get(f"/api/v1/locations/{region.id}/feed")
        assert resp.status_code == 200

        ids = [item["id"] for item in resp.json()["items"]]
        assert entry.id in ids

    def test_404_for_nonexistent_location(self, client, seed_data):
        """Returns 404 when the location does not exist."""
        gm = seed_data["gm"]
        auth_as(client, gm)
        resp = client.get("/api/v1/locations/DOESNOTEXIST12345678901234/feed")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "not_found"

    def test_deduplication_of_story_entries(self, client, db, seed_data):
        """A story entry that qualifies via both ownership and game_object_refs appears once."""
        region = seed_data["region"]
        gm = seed_data["gm"]

        # Story owned by region; entry also references region in game_object_refs.
        story, entry = _story_with_entry(
            db,
            owner_type="location",
            owner_id=region.id,
            author_id=gm.id,
            game_object_refs=[{"type": "location", "id": region.id}],
        )
        db.commit()

        auth_as(client, gm)
        resp = client.get(f"/api/v1/locations/{region.id}/feed")
        assert resp.status_code == 200

        entry_ids = [item["id"] for item in resp.json()["items"] if item["type"] == "story_entry"]
        # Entry should appear exactly once.
        assert entry_ids.count(entry.id) == 1

    def test_soft_deleted_story_excluded(self, client, db, seed_data):
        """Story entries from soft-deleted stories are excluded from the feed."""
        region = seed_data["region"]
        gm = seed_data["gm"]

        story, entry = _story_with_entry(
            db,
            owner_type="location",
            owner_id=region.id,
            author_id=gm.id,
        )
        story.is_deleted = True
        db.flush()
        db.commit()

        auth_as(client, gm)
        resp = client.get(f"/api/v1/locations/{region.id}/feed")
        assert resp.status_code == 200

        ids = [item["id"] for item in resp.json()["items"]]
        assert entry.id not in ids

    def test_soft_deleted_entry_excluded(self, client, db, seed_data):
        """Soft-deleted story entries are excluded from the feed."""
        region = seed_data["region"]
        gm = seed_data["gm"]

        _story, entry = _story_with_entry(
            db,
            owner_type="location",
            owner_id=region.id,
            author_id=gm.id,
        )
        entry.is_deleted = True
        db.flush()
        db.commit()

        auth_as(client, gm)
        resp = client.get(f"/api/v1/locations/{region.id}/feed")
        assert resp.status_code == 200

        ids = [item["id"] for item in resp.json()["items"]]
        assert entry.id not in ids
