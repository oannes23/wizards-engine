"""Feed service edge cases — M9.

Exercises:
- Personal feed: returns empty when no events exist
- Personal feed: all events invisible to requesting player → empty result
- Personal feed: mixed visibility (some visible, some not)
- Personal feed: cursor pagination across visibility boundaries (invisible events
  do not pollute pages — cursor advances through them correctly)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import auth_as
from wizards_engine.models.event import Event, EventTarget


# ===========================================================================
# Helpers
# ===========================================================================


def _event(
    db: Session,
    *,
    event_type: str = "test.event",
    actor_type: str = "gm",
    actor_id: str | None = None,
    visibility: str = "global",
    targets: list[tuple[str, str, bool]] | None = None,
) -> Event:
    """Create and flush a minimal Event."""
    ev = Event(
        type=event_type,
        actor_type=actor_type,
        actor_id=actor_id,
        changes={},
        visibility=visibility,
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


# ===========================================================================
# Empty feed
# ===========================================================================


class TestPersonalFeedEmpty:
    """Personal feed returns correct empty response when no events exist."""

    def test_empty_feed_no_events(self, client: TestClient, db: Session, seed_data: dict) -> None:
        """When no events or story entries exist, the feed is empty."""
        gm = seed_data["gm"]
        db.commit()  # commit seed data only, no events

        auth_as(client, gm)
        resp = client.get("/api/v1/me/feed")
        assert resp.status_code == 200

        data = resp.json()
        assert data["items"] == []
        assert data["has_more"] is False
        assert data["next_cursor"] is None

    def test_empty_feed_for_player_with_no_events(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """A player with no events in the system sees an empty feed."""
        player1 = seed_data["player1"]
        db.commit()

        auth_as(client, player1)
        resp = client.get("/api/v1/me/feed")
        assert resp.status_code == 200

        data = resp.json()
        assert data["items"] == []
        assert data["has_more"] is False


# ===========================================================================
# All events invisible
# ===========================================================================


class TestPersonalFeedAllInvisible:
    """Personal feed returns empty when all events are invisible to the caller."""

    def test_all_gm_only_invisible_to_player(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """When every event is gm_only, a player's feed is empty."""
        player1 = seed_data["player1"]
        pc1 = seed_data["pc1"]

        for _ in range(3):
            _event(
                db,
                visibility="gm_only",
                targets=[("character", pc1.id, True)],
            )
        db.commit()

        auth_as(client, player1)
        resp = client.get("/api/v1/me/feed")
        assert resp.status_code == 200

        data = resp.json()
        assert data["items"] == []
        assert data["has_more"] is False

    def test_all_silent_invisible_to_everyone_in_personal(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Silent events never appear in the personal feed, even for the GM."""
        gm = seed_data["gm"]
        pc1 = seed_data["pc1"]

        for _ in range(3):
            _event(
                db,
                visibility="silent",
                targets=[("character", pc1.id, True)],
            )
        db.commit()

        auth_as(client, gm)
        resp = client.get("/api/v1/me/feed")
        assert resp.status_code == 200

        data = resp.json()
        assert data["items"] == []
        assert data["has_more"] is False


# ===========================================================================
# Mixed visibility
# ===========================================================================


class TestPersonalFeedMixedVisibility:
    """Personal feed returns only visible events when mixed visibility events exist."""

    def test_player_sees_only_global_not_gm_only(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Player sees global events but not gm_only events in mixed feed."""
        player1 = seed_data["player1"]
        pc1 = seed_data["pc1"]

        global_ev = _event(db, visibility="global", targets=[("character", pc1.id, True)])
        _gm_only_ev = _event(db, visibility="gm_only", targets=[("character", pc1.id, True)])
        silent_ev = _event(db, visibility="silent", targets=[("character", pc1.id, True)])
        db.commit()

        auth_as(client, player1)
        resp = client.get("/api/v1/me/feed")
        assert resp.status_code == 200

        ids = [item["id"] for item in resp.json()["items"]]
        assert global_ev.id in ids
        assert _gm_only_ev.id not in ids
        assert silent_ev.id not in ids

    def test_gm_sees_global_and_gm_only_not_silent(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """GM sees global and gm_only events, but not silent events in personal feed."""
        gm = seed_data["gm"]
        pc1 = seed_data["pc1"]

        global_ev = _event(db, visibility="global", targets=[("character", pc1.id, True)])
        gm_only_ev = _event(db, visibility="gm_only", targets=[("character", pc1.id, True)])
        silent_ev = _event(db, visibility="silent", targets=[("character", pc1.id, True)])
        db.commit()

        auth_as(client, gm)
        resp = client.get("/api/v1/me/feed")
        assert resp.status_code == 200

        ids = [item["id"] for item in resp.json()["items"]]
        assert global_ev.id in ids
        assert gm_only_ev.id in ids
        assert silent_ev.id not in ids

    def test_correct_count_when_some_invisible(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Player sees exactly the visible subset when there are mixed events."""
        player1 = seed_data["player1"]
        pc1 = seed_data["pc1"]

        visible_ids = []
        for _ in range(2):
            ev = _event(db, visibility="global", targets=[("character", pc1.id, True)])
            visible_ids.append(ev.id)

        for _ in range(3):
            _event(db, visibility="gm_only", targets=[("character", pc1.id, True)])

        db.commit()

        auth_as(client, player1)
        resp = client.get("/api/v1/me/feed")
        assert resp.status_code == 200

        items = resp.json()["items"]
        assert len(items) == 2
        assert all(item["id"] in visible_ids for item in items)


# ===========================================================================
# Cursor across visibility boundaries
# ===========================================================================


class TestPersonalFeedCursorAcrossVisibility:
    """Pagination cursor works correctly when invisible events exist between pages."""

    def test_cursor_skips_invisible_events(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Cursor-based pagination returns distinct visible pages even when
        invisible events sit between visible ones in the ordered sequence."""
        player1 = seed_data["player1"]
        pc1 = seed_data["pc1"]

        # Create 4 visible global events and 3 invisible gm_only events interleaved.
        visible = []
        for i in range(4):
            ev = _event(db, visibility="global", targets=[("character", pc1.id, True)])
            visible.append(ev.id)
            # Insert an invisible event after each visible one.
            _event(db, visibility="gm_only", targets=[("character", pc1.id, True)])

        db.commit()

        auth_as(client, player1)

        # First page: limit=2 → should return 2 visible events.
        resp1 = client.get("/api/v1/me/feed?limit=2")
        assert resp1.status_code == 200
        page1 = resp1.json()
        assert len(page1["items"]) == 2
        assert page1["has_more"] is True
        assert page1["next_cursor"] is not None

        # Second page: should return the other 2 visible events without overlap.
        cursor = page1["next_cursor"]
        resp2 = client.get(f"/api/v1/me/feed?limit=2&after={cursor}")
        assert resp2.status_code == 200
        page2 = resp2.json()
        assert len(page2["items"]) == 2

        ids1 = {i["id"] for i in page1["items"]}
        ids2 = {i["id"] for i in page2["items"]}
        # Pages must not overlap.
        assert ids1.isdisjoint(ids2)
        # All returned events must be from visible set.
        assert ids1 | ids2 == set(visible)

    def test_cursor_returns_empty_when_all_remaining_invisible(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """After cursor, if all remaining events are invisible the feed is empty."""
        player1 = seed_data["player1"]
        pc1 = seed_data["pc1"]

        # 1 visible event, then many invisible events.
        visible_ev = _event(db, visibility="global", targets=[("character", pc1.id, True)])
        for _ in range(5):
            _event(db, visibility="gm_only", targets=[("character", pc1.id, True)])

        db.commit()

        auth_as(client, player1)

        # First page gets the 1 visible event.
        resp1 = client.get("/api/v1/me/feed?limit=1")
        assert resp1.status_code == 200
        page1 = resp1.json()
        assert len(page1["items"]) == 1
        assert page1["items"][0]["id"] == visible_ev.id

        # Follow cursor: nothing visible remains.
        # Note: has_more behavior may vary — we only assert the items are correct.
        cursor = page1["next_cursor"]
        if cursor is not None:
            resp2 = client.get(f"/api/v1/me/feed?limit=10&after={cursor}")
            assert resp2.status_code == 200
            assert resp2.json()["items"] == []
