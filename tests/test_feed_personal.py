"""Integration tests for personal, starred, and silent feed endpoints (Story 4.4.2).

Exercises:
- GET /api/v1/me/feed          — complete personal feed
- GET /api/v1/me/feed/starred  — starred feed
- GET /api/v1/me/feed/silent   — GM-only silent feed

Coverage:
- Personal feed: events visible to the user across all Game Objects
- Personal feed: story entries visible to the user
- Personal feed: silent events excluded
- Personal feed: gm_only events excluded for players, visible to GM
- Personal feed: is_own flag set correctly
- Personal feed: event-only filters exclude story entries
- Personal feed: pagination (limit, after cursor)
- Personal feed: full filter set (type, actor_type, session_id, since, until,
  target_type, target_id)
- Starred feed: only events/entries for starred objects
- Starred feed: empty when no objects are starred
- Starred feed: story entries via story ownership and game_object_refs
- Starred feed: event-only filters exclude story entries
- Starred feed: pagination
- Silent feed: only silent events
- Silent feed: 403 for non-GM callers
- Silent feed: 401 for unauthenticated callers
- Silent feed: story entries excluded
- Silent feed: pagination
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import auth_as
from wizards_engine.models.event import Event, EventTarget
from wizards_engine.models.starred import StarredObject
from wizards_engine.models.story import Story, StoryEntry, StoryOwner


# ---------------------------------------------------------------------------
# Test helpers (copied / extended from test_feed.py pattern)
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
    """Create a Story with one StoryEntry and flush."""
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


def _star(db: Session, user_id: str, object_type: str, object_id: str) -> StarredObject:
    """Create and flush a StarredObject row."""
    row = StarredObject(
        user_id=user_id,
        object_type=object_type,
        object_id=object_id,
    )
    db.add(row)
    db.flush()
    return row


# ===========================================================================
# Personal feed tests — GET /api/v1/me/feed
# ===========================================================================


class TestPersonalFeed:
    """Tests for GET /api/v1/me/feed."""

    def test_returns_global_event(self, client, db, seed_data):
        """A global event appears in the personal feed for any authenticated user."""
        gm = seed_data["gm"]
        pc1 = seed_data["pc1"]

        ev = _event(
            db,
            visibility="global",
            targets=[("character", pc1.id, True)],
        )
        db.commit()

        auth_as(client, gm)
        resp = client.get("/api/v1/me/feed")
        assert resp.status_code == 200

        ids = [item["id"] for item in resp.json()["items"]]
        assert ev.id in ids

    def test_response_envelope(self, client, db, seed_data):
        """Response has items, next_cursor, and has_more fields."""
        gm = seed_data["gm"]
        db.commit()

        auth_as(client, gm)
        resp = client.get("/api/v1/me/feed")
        assert resp.status_code == 200

        data = resp.json()
        assert "items" in data
        assert "next_cursor" in data
        assert "has_more" in data

    def test_silent_event_excluded(self, client, db, seed_data):
        """Silent events are never in the personal feed."""
        gm = seed_data["gm"]
        pc1 = seed_data["pc1"]

        silent_ev = _event(
            db,
            visibility="silent",
            targets=[("character", pc1.id, True)],
        )
        db.commit()

        auth_as(client, gm)
        resp = client.get("/api/v1/me/feed")
        assert resp.status_code == 200

        ids = [item["id"] for item in resp.json()["items"]]
        assert silent_ev.id not in ids

    def test_gm_only_event_hidden_from_player(self, client, db, seed_data):
        """gm_only events do not appear in a player's personal feed."""
        pc1 = seed_data["pc1"]
        player1 = seed_data["player1"]

        ev = _event(
            db,
            visibility="gm_only",
            targets=[("character", pc1.id, True)],
        )
        db.commit()

        auth_as(client, player1)
        resp = client.get("/api/v1/me/feed")
        assert resp.status_code == 200

        ids = [item["id"] for item in resp.json()["items"]]
        assert ev.id not in ids

    def test_gm_only_event_visible_to_gm(self, client, db, seed_data):
        """gm_only events appear in the GM's personal feed."""
        gm = seed_data["gm"]
        pc1 = seed_data["pc1"]

        ev = _event(
            db,
            visibility="gm_only",
            targets=[("character", pc1.id, True)],
        )
        db.commit()

        auth_as(client, gm)
        resp = client.get("/api/v1/me/feed")
        assert resp.status_code == 200

        ids = [item["id"] for item in resp.json()["items"]]
        assert ev.id in ids

    def test_includes_story_entries(self, client, db, seed_data):
        """Story entries at familiar visibility appear in the personal feed."""
        gm = seed_data["gm"]
        pc1 = seed_data["pc1"]

        _story, entry = _story_with_entry(
            db,
            owner_type="character",
            owner_id=pc1.id,
            author_id=gm.id,
        )
        db.commit()

        auth_as(client, gm)
        resp = client.get("/api/v1/me/feed")
        assert resp.status_code == 200

        ids = [item["id"] for item in resp.json()["items"]]
        assert entry.id in ids

    def test_is_own_true_for_event_actor(self, client, db, seed_data):
        """is_own is True when the authenticated player is the event actor."""
        player1 = seed_data["player1"]
        pc1 = seed_data["pc1"]

        ev = _event(
            db,
            actor_type="player",
            actor_id=player1.id,
            visibility="global",
            targets=[("character", pc1.id, True)],
        )
        db.commit()

        auth_as(client, player1)
        resp = client.get("/api/v1/me/feed")
        assert resp.status_code == 200

        items = resp.json()["items"]
        item = next(i for i in items if i["id"] == ev.id)
        assert item["is_own"] is True

    def test_is_own_false_for_other_actor(self, client, db, seed_data):
        """is_own is False when a different user is the event actor."""
        player1 = seed_data["player1"]
        player2 = seed_data["player2"]
        pc1 = seed_data["pc1"]

        ev = _event(
            db,
            actor_type="player",
            actor_id=player2.id,
            visibility="global",
            targets=[("character", pc1.id, True)],
        )
        db.commit()

        auth_as(client, player1)
        resp = client.get("/api/v1/me/feed")
        assert resp.status_code == 200

        items = resp.json()["items"]
        item = next(i for i in items if i["id"] == ev.id)
        assert item["is_own"] is False

    def test_is_own_true_for_story_entry_author(self, client, db, seed_data):
        """is_own is True when the authenticated user is the story entry author."""
        player1 = seed_data["player1"]
        pc1 = seed_data["pc1"]

        _story, entry = _story_with_entry(
            db,
            owner_type="character",
            owner_id=pc1.id,
            author_id=player1.id,
        )
        db.commit()

        auth_as(client, player1)
        resp = client.get("/api/v1/me/feed")
        assert resp.status_code == 200

        items = resp.json()["items"]
        item = next(i for i in items if i["id"] == entry.id)
        assert item["is_own"] is True

    def test_sorted_newest_first(self, client, db, seed_data):
        """Personal feed items are sorted newest-first by ULID."""
        gm = seed_data["gm"]
        pc1 = seed_data["pc1"]

        for _ in range(3):
            _event(db, visibility="global", targets=[("character", pc1.id, True)])
        db.commit()

        auth_as(client, gm)
        resp = client.get("/api/v1/me/feed")
        assert resp.status_code == 200

        ids = [i["id"] for i in resp.json()["items"]]
        assert ids == sorted(ids, reverse=True)

    def test_event_only_filter_excludes_story_entries(self, client, db, seed_data):
        """?type= filter excludes story entries from the personal feed."""
        gm = seed_data["gm"]
        pc1 = seed_data["pc1"]

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
        resp = client.get("/api/v1/me/feed?type=character.*")
        assert resp.status_code == 200

        types = [i["type"] for i in resp.json()["items"]]
        assert "story_entry" not in types
        assert "event" in types

    def test_filter_actor_type_excludes_story_entries(self, client, db, seed_data):
        """?actor_type= filter excludes story entries from the personal feed."""
        gm = seed_data["gm"]
        pc1 = seed_data["pc1"]

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
        resp = client.get("/api/v1/me/feed?actor_type=gm")
        assert resp.status_code == 200

        types = [i["type"] for i in resp.json()["items"]]
        assert "story_entry" not in types

    def test_filter_target_type(self, client, db, seed_data):
        """?target_type= filters events to those targeting the given object type."""
        gm = seed_data["gm"]
        pc1 = seed_data["pc1"]
        group = seed_data["group"]

        char_ev = _event(
            db,
            visibility="global",
            targets=[("character", pc1.id, True)],
        )
        group_ev = _event(
            db,
            visibility="global",
            targets=[("group", group.id, True)],
        )
        db.commit()

        auth_as(client, gm)
        resp = client.get("/api/v1/me/feed?target_type=character")
        assert resp.status_code == 200

        ids = [i["id"] for i in resp.json()["items"]]
        assert char_ev.id in ids
        assert group_ev.id not in ids

    def test_filter_target_id(self, client, db, seed_data):
        """?target_id= filters events to those targeting the given object."""
        gm = seed_data["gm"]
        pc1 = seed_data["pc1"]
        pc2 = seed_data["pc2"]

        ev_pc1 = _event(
            db,
            visibility="global",
            targets=[("character", pc1.id, True)],
        )
        ev_pc2 = _event(
            db,
            visibility="global",
            targets=[("character", pc2.id, True)],
        )
        db.commit()

        auth_as(client, gm)
        resp = client.get(f"/api/v1/me/feed?target_id={pc1.id}")
        assert resp.status_code == 200

        ids = [i["id"] for i in resp.json()["items"]]
        assert ev_pc1.id in ids
        assert ev_pc2.id not in ids

    def test_filter_session_id(self, client, db, seed_data):
        """?session_id= filters to events/entries from that session."""
        gm = seed_data["gm"]
        pc1 = seed_data["pc1"]

        from wizards_engine.models.session import Session as SessionModel
        session = SessionModel(status="ended", summary="S1")
        db.add(session)
        db.flush()

        ev_with = _event(
            db,
            visibility="global",
            session_id=session.id,
            targets=[("character", pc1.id, True)],
        )
        ev_without = _event(
            db,
            visibility="global",
            targets=[("character", pc1.id, True)],
        )
        db.commit()

        auth_as(client, gm)
        resp = client.get(f"/api/v1/me/feed?session_id={session.id}")
        assert resp.status_code == 200

        ids = [i["id"] for i in resp.json()["items"]]
        assert ev_with.id in ids
        assert ev_without.id not in ids

    def test_filter_since_until(self, client, db, seed_data):
        """?since= and ?until= filter by timestamp."""
        gm = seed_data["gm"]
        pc1 = seed_data["pc1"]

        ev = _event(db, visibility="global", targets=[("character", pc1.id, True)])
        db.commit()
        db.refresh(ev)
        ts = ev.created_at

        future = (ts + timedelta(seconds=1)).isoformat()
        auth_as(client, gm)
        resp = client.get(f"/api/v1/me/feed?since={future}")
        assert resp.status_code == 200
        assert ev.id not in [i["id"] for i in resp.json()["items"]]

        past = (ts - timedelta(seconds=1)).isoformat()
        resp2 = client.get(f"/api/v1/me/feed?until={past}")
        assert resp2.status_code == 200
        assert ev.id not in [i["id"] for i in resp2.json()["items"]]

        earlier = (ts - timedelta(seconds=1)).isoformat()
        resp3 = client.get(f"/api/v1/me/feed?since={earlier}")
        assert resp3.status_code == 200
        assert ev.id in [i["id"] for i in resp3.json()["items"]]

    def test_pagination_limit(self, client, db, seed_data):
        """limit parameter restricts the number of items returned."""
        gm = seed_data["gm"]
        pc1 = seed_data["pc1"]

        for _ in range(5):
            _event(db, visibility="global", targets=[("character", pc1.id, True)])
        db.commit()

        auth_as(client, gm)
        resp = client.get("/api/v1/me/feed?limit=2")
        assert resp.status_code == 200

        data = resp.json()
        assert len(data["items"]) == 2
        assert data["has_more"] is True
        assert data["next_cursor"] is not None

    def test_pagination_after_cursor(self, client, db, seed_data):
        """after cursor yields non-overlapping pages."""
        gm = seed_data["gm"]
        pc1 = seed_data["pc1"]

        for _ in range(4):
            _event(db, visibility="global", targets=[("character", pc1.id, True)])
        db.commit()

        auth_as(client, gm)
        resp1 = client.get("/api/v1/me/feed?limit=2")
        assert resp1.status_code == 200
        page1 = resp1.json()

        cursor = page1["next_cursor"]
        resp2 = client.get(f"/api/v1/me/feed?limit=2&after={cursor}")
        assert resp2.status_code == 200
        page2 = resp2.json()

        ids1 = {i["id"] for i in page1["items"]}
        ids2 = {i["id"] for i in page2["items"]}
        assert ids1.isdisjoint(ids2)

    def test_401_when_unauthenticated(self, client, seed_data):
        """Returns 401 when no auth cookie is present."""
        client.cookies.clear()
        resp = client.get("/api/v1/me/feed")
        assert resp.status_code == 401

    def test_empty_when_no_events_or_entries(self, client, db, seed_data):
        """Returns empty feed when no events or story entries exist."""
        gm = seed_data["gm"]
        db.commit()

        auth_as(client, gm)
        resp = client.get("/api/v1/me/feed")
        assert resp.status_code == 200

        data = resp.json()
        assert data["items"] == []
        assert data["has_more"] is False
        assert data["next_cursor"] is None

    def test_gm_only_story_hidden_from_player(self, client, db, seed_data):
        """Story entries at gm_only visibility are hidden from players."""
        player1 = seed_data["player1"]
        pc1 = seed_data["pc1"]
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
        resp = client.get("/api/v1/me/feed")
        assert resp.status_code == 200

        ids = [item["id"] for item in resp.json()["items"]]
        assert entry.id not in ids


# ===========================================================================
# Starred feed tests — GET /api/v1/me/feed/starred
# ===========================================================================


class TestStarredFeed:
    """Tests for GET /api/v1/me/feed/starred."""

    def test_empty_when_no_starred_objects(self, client, db, seed_data):
        """Returns empty feed when the user has no starred objects."""
        gm = seed_data["gm"]
        pc1 = seed_data["pc1"]

        _event(db, visibility="global", targets=[("character", pc1.id, True)])
        db.commit()

        auth_as(client, gm)
        resp = client.get("/api/v1/me/feed/starred")
        assert resp.status_code == 200

        data = resp.json()
        assert data["items"] == []
        assert data["has_more"] is False

    def test_returns_event_for_starred_object(self, client, db, seed_data):
        """Events targeting a starred object appear in the starred feed."""
        gm = seed_data["gm"]
        pc1 = seed_data["pc1"]

        _star(db, gm.id, "character", pc1.id)
        ev = _event(db, visibility="global", targets=[("character", pc1.id, True)])
        db.commit()

        auth_as(client, gm)
        resp = client.get("/api/v1/me/feed/starred")
        assert resp.status_code == 200

        ids = [item["id"] for item in resp.json()["items"]]
        assert ev.id in ids

    def test_excludes_event_for_non_starred_object(self, client, db, seed_data):
        """Events targeting objects not starred are excluded."""
        gm = seed_data["gm"]
        pc1 = seed_data["pc1"]
        pc2 = seed_data["pc2"]

        _star(db, gm.id, "character", pc1.id)
        ev_pc1 = _event(db, visibility="global", targets=[("character", pc1.id, True)])
        ev_pc2 = _event(db, visibility="global", targets=[("character", pc2.id, True)])
        db.commit()

        auth_as(client, gm)
        resp = client.get("/api/v1/me/feed/starred")
        assert resp.status_code == 200

        ids = [item["id"] for item in resp.json()["items"]]
        assert ev_pc1.id in ids
        assert ev_pc2.id not in ids

    def test_returns_story_entry_for_starred_object(self, client, db, seed_data):
        """Story entries on stories owned by a starred object appear in the starred feed."""
        gm = seed_data["gm"]
        pc1 = seed_data["pc1"]

        _star(db, gm.id, "character", pc1.id)
        _story, entry = _story_with_entry(
            db,
            owner_type="character",
            owner_id=pc1.id,
            author_id=gm.id,
        )
        db.commit()

        auth_as(client, gm)
        resp = client.get("/api/v1/me/feed/starred")
        assert resp.status_code == 200

        ids = [item["id"] for item in resp.json()["items"]]
        assert entry.id in ids

    def test_story_entry_via_game_object_refs_on_starred(self, client, db, seed_data):
        """Story entries referencing a starred object via game_object_refs appear."""
        gm = seed_data["gm"]
        pc1 = seed_data["pc1"]
        pc2 = seed_data["pc2"]

        # Star pc1 but story is owned by pc2; entry refs pc1.
        _star(db, gm.id, "character", pc1.id)
        _story, entry = _story_with_entry(
            db,
            owner_type="character",
            owner_id=pc2.id,
            author_id=gm.id,
            game_object_refs=[{"type": "character", "id": pc1.id}],
        )
        db.commit()

        auth_as(client, gm)
        resp = client.get("/api/v1/me/feed/starred")
        assert resp.status_code == 200

        ids = [item["id"] for item in resp.json()["items"]]
        assert entry.id in ids

    def test_silent_event_excluded_from_starred(self, client, db, seed_data):
        """Silent events are excluded from the starred feed."""
        gm = seed_data["gm"]
        pc1 = seed_data["pc1"]

        _star(db, gm.id, "character", pc1.id)
        silent_ev = _event(
            db,
            visibility="silent",
            targets=[("character", pc1.id, True)],
        )
        db.commit()

        auth_as(client, gm)
        resp = client.get("/api/v1/me/feed/starred")
        assert resp.status_code == 200

        ids = [item["id"] for item in resp.json()["items"]]
        assert silent_ev.id not in ids

    def test_event_only_filter_excludes_story_entries(self, client, db, seed_data):
        """?type= filter excludes story entries from the starred feed."""
        gm = seed_data["gm"]
        pc1 = seed_data["pc1"]

        _star(db, gm.id, "character", pc1.id)
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
        resp = client.get("/api/v1/me/feed/starred?type=character.*")
        assert resp.status_code == 200

        types = [i["type"] for i in resp.json()["items"]]
        assert "story_entry" not in types
        assert "event" in types

    def test_pagination_on_starred_feed(self, client, db, seed_data):
        """Pagination works on the starred feed."""
        gm = seed_data["gm"]
        pc1 = seed_data["pc1"]

        _star(db, gm.id, "character", pc1.id)
        for _ in range(4):
            _event(db, visibility="global", targets=[("character", pc1.id, True)])
        db.commit()

        auth_as(client, gm)
        resp1 = client.get("/api/v1/me/feed/starred?limit=2")
        assert resp1.status_code == 200
        page1 = resp1.json()
        assert len(page1["items"]) == 2
        assert page1["has_more"] is True

        cursor = page1["next_cursor"]
        resp2 = client.get(f"/api/v1/me/feed/starred?limit=2&after={cursor}")
        assert resp2.status_code == 200
        page2 = resp2.json()

        ids1 = {i["id"] for i in page1["items"]}
        ids2 = {i["id"] for i in page2["items"]}
        assert ids1.isdisjoint(ids2)

    def test_401_when_unauthenticated(self, client, seed_data):
        """Returns 401 when no auth cookie is present."""
        client.cookies.clear()
        resp = client.get("/api/v1/me/feed/starred")
        assert resp.status_code == 401

    def test_visibility_filtering_still_applies_in_starred(self, client, db, seed_data):
        """gm_only events are excluded for players even in the starred feed."""
        player1 = seed_data["player1"]
        pc1 = seed_data["pc1"]

        _star(db, player1.id, "character", pc1.id)
        ev = _event(
            db,
            visibility="gm_only",
            targets=[("character", pc1.id, True)],
        )
        db.commit()

        auth_as(client, player1)
        resp = client.get("/api/v1/me/feed/starred")
        assert resp.status_code == 200

        ids = [item["id"] for item in resp.json()["items"]]
        assert ev.id not in ids

    def test_response_envelope(self, client, db, seed_data):
        """Starred feed response has items, next_cursor, has_more."""
        gm = seed_data["gm"]
        db.commit()

        auth_as(client, gm)
        resp = client.get("/api/v1/me/feed/starred")
        assert resp.status_code == 200

        data = resp.json()
        assert "items" in data
        assert "next_cursor" in data
        assert "has_more" in data


# ===========================================================================
# Silent feed tests — GET /api/v1/me/feed/silent
# ===========================================================================


class TestSilentFeed:
    """Tests for GET /api/v1/me/feed/silent."""

    def test_gm_can_see_silent_events(self, client, db, seed_data):
        """The GM can access the silent feed and sees silent events."""
        gm = seed_data["gm"]
        pc1 = seed_data["pc1"]

        silent_ev = _event(
            db,
            visibility="silent",
            targets=[("character", pc1.id, True)],
        )
        db.commit()

        auth_as(client, gm)
        resp = client.get("/api/v1/me/feed/silent")
        assert resp.status_code == 200

        ids = [item["id"] for item in resp.json()["items"]]
        assert silent_ev.id in ids

    def test_403_for_player(self, client, db, seed_data):
        """Returns 403 when a player (non-GM) calls the silent feed."""
        player1 = seed_data["player1"]
        db.commit()

        auth_as(client, player1)
        resp = client.get("/api/v1/me/feed/silent")
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "insufficient_role"

    def test_401_when_unauthenticated(self, client, seed_data):
        """Returns 401 when no auth cookie is present."""
        client.cookies.clear()
        resp = client.get("/api/v1/me/feed/silent")
        assert resp.status_code == 401

    def test_non_silent_events_excluded(self, client, db, seed_data):
        """Non-silent events do NOT appear in the silent feed."""
        gm = seed_data["gm"]
        pc1 = seed_data["pc1"]

        global_ev = _event(
            db,
            visibility="global",
            targets=[("character", pc1.id, True)],
        )
        gm_only_ev = _event(
            db,
            visibility="gm_only",
            targets=[("character", pc1.id, True)],
        )
        silent_ev = _event(
            db,
            visibility="silent",
            targets=[("character", pc1.id, True)],
        )
        db.commit()

        auth_as(client, gm)
        resp = client.get("/api/v1/me/feed/silent")
        assert resp.status_code == 200

        ids = [item["id"] for item in resp.json()["items"]]
        assert silent_ev.id in ids
        assert global_ev.id not in ids
        assert gm_only_ev.id not in ids

    def test_no_story_entries_in_silent_feed(self, client, db, seed_data):
        """Story entries never appear in the silent feed."""
        gm = seed_data["gm"]
        pc1 = seed_data["pc1"]

        _story, entry = _story_with_entry(
            db,
            owner_type="character",
            owner_id=pc1.id,
            author_id=gm.id,
        )
        silent_ev = _event(
            db,
            visibility="silent",
            targets=[("character", pc1.id, True)],
        )
        db.commit()

        auth_as(client, gm)
        resp = client.get("/api/v1/me/feed/silent")
        assert resp.status_code == 200

        types = [item["type"] for item in resp.json()["items"]]
        assert "story_entry" not in types
        assert "event" in types

    def test_response_envelope(self, client, db, seed_data):
        """Silent feed response has items, next_cursor, has_more."""
        gm = seed_data["gm"]
        db.commit()

        auth_as(client, gm)
        resp = client.get("/api/v1/me/feed/silent")
        assert resp.status_code == 200

        data = resp.json()
        assert "items" in data
        assert "next_cursor" in data
        assert "has_more" in data

    def test_empty_when_no_silent_events(self, client, db, seed_data):
        """Returns empty feed when no silent events exist."""
        gm = seed_data["gm"]
        db.commit()

        auth_as(client, gm)
        resp = client.get("/api/v1/me/feed/silent")
        assert resp.status_code == 200

        data = resp.json()
        assert data["items"] == []
        assert data["has_more"] is False
        assert data["next_cursor"] is None

    def test_pagination_on_silent_feed(self, client, db, seed_data):
        """Pagination works on the silent feed."""
        gm = seed_data["gm"]
        pc1 = seed_data["pc1"]

        for _ in range(4):
            _event(db, visibility="silent", targets=[("character", pc1.id, True)])
        db.commit()

        auth_as(client, gm)
        resp1 = client.get("/api/v1/me/feed/silent?limit=2")
        assert resp1.status_code == 200
        page1 = resp1.json()
        assert len(page1["items"]) == 2
        assert page1["has_more"] is True

        cursor = page1["next_cursor"]
        resp2 = client.get(f"/api/v1/me/feed/silent?limit=2&after={cursor}")
        assert resp2.status_code == 200
        page2 = resp2.json()

        ids1 = {i["id"] for i in page1["items"]}
        ids2 = {i["id"] for i in page2["items"]}
        assert ids1.isdisjoint(ids2)

    def test_filter_type_on_silent_feed(self, client, db, seed_data):
        """?type= filter works on the silent feed."""
        gm = seed_data["gm"]
        pc1 = seed_data["pc1"]

        char_ev = _event(
            db,
            event_type="character.silent_change",
            visibility="silent",
            targets=[("character", pc1.id, True)],
        )
        other_ev = _event(
            db,
            event_type="session.bookkeeping",
            visibility="silent",
            targets=[("character", pc1.id, True)],
        )
        db.commit()

        auth_as(client, gm)
        resp = client.get("/api/v1/me/feed/silent?type=character.*")
        assert resp.status_code == 200

        ids = [i["id"] for i in resp.json()["items"]]
        assert char_ev.id in ids
        assert other_ev.id not in ids

    def test_event_item_type_in_silent_feed(self, client, db, seed_data):
        """Items in the silent feed have type='event'."""
        gm = seed_data["gm"]
        pc1 = seed_data["pc1"]

        _event(db, visibility="silent", targets=[("character", pc1.id, True)])
        db.commit()

        auth_as(client, gm)
        resp = client.get("/api/v1/me/feed/silent")
        assert resp.status_code == 200

        items = resp.json()["items"]
        assert len(items) > 0
        for item in items:
            assert item["type"] == "event"
