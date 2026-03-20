"""Integration tests for GET /api/v1/sessions/{id}/timeline (Story 5.1.5).

Exercises:
- 404 if session doesn't exist
- Empty timeline (session exists but no events)
- Returns only events with matching session_id
- Events from other sessions excluded
- Events with no session_id excluded
- Silent events excluded for everyone
- Visibility filtering: player only sees events they should see
- GM sees all non-silent events
- ULID cursor pagination
- Limit parameter respected
- Unauthenticated requests return 401
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import auth_as
from wizards_engine.models.event import Event, EventTarget
from wizards_engine.models.session import Session as SessionModel
from wizards_engine.models.user import User


# ===========================================================================
# Test helpers
# ===========================================================================


def _session(db: Session, *, status: str = "draft") -> SessionModel:
    """Create and flush a session."""
    s = SessionModel(status=status)
    db.add(s)
    db.flush()
    db.refresh(s)
    return s


def _event(
    db: Session,
    *,
    type: str = "test.event",
    actor_type: str = "gm",
    actor_id: str | None = None,
    visibility: str = "global",
    session_id: str | None = None,
    targets: list[tuple[str, str, bool]] | None = None,
    changes: dict | None = None,
) -> Event:
    """Create and flush a minimal Event."""
    ev = Event(
        type=type,
        actor_type=actor_type,
        actor_id=actor_id,
        changes=changes if changes is not None else {},
        visibility=visibility,
        session_id=session_id,
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
# Auth
# ===========================================================================


class TestSessionTimelineAuth:
    """Unauthenticated requests are rejected."""

    def test_unauthenticated_returns_401(self, client: TestClient, db: Session) -> None:
        response = client.get("/api/v1/sessions/nonexistent/timeline")
        assert response.status_code == 401


# ===========================================================================
# 404 handling
# ===========================================================================


class TestSessionTimelineNotFound:
    """Session existence is validated first."""

    def test_nonexistent_session_returns_404(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/sessions/01JZZZZZZZZZZZZZZZZZZZZZZZ/timeline")
        assert response.status_code == 404
        body = response.json()
        assert body["error"]["code"] == "not_found"


# ===========================================================================
# Empty timeline
# ===========================================================================


class TestSessionTimelineEmpty:
    """Session exists but has no events."""

    def test_empty_timeline_returns_empty_list(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        sess = _session(db)
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/sessions/{sess.id}/timeline")
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []
        assert body["has_more"] is False
        assert body["next_cursor"] is None


# ===========================================================================
# Session filtering
# ===========================================================================


class TestSessionTimelineFiltering:
    """Only events for the given session_id are returned."""

    def test_returns_events_with_matching_session_id(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        sess = _session(db)
        ev = _event(db, visibility="global", session_id=sess.id)
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/sessions/{sess.id}/timeline")
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == ev.id
        assert items[0]["session_id"] == sess.id

    def test_events_from_other_sessions_excluded(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        sess1 = _session(db)
        sess2 = _session(db)
        ev_sess1 = _event(db, visibility="global", session_id=sess1.id)
        _event(db, visibility="global", session_id=sess2.id)  # other session
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/sessions/{sess1.id}/timeline")
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == ev_sess1.id

    def test_events_with_no_session_id_excluded(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        sess = _session(db)
        _event(db, visibility="global", session_id=None)  # no session
        ev_with_session = _event(db, visibility="global", session_id=sess.id)
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/sessions/{sess.id}/timeline")
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == ev_with_session.id

    def test_multiple_events_same_session_all_returned(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        sess = _session(db)
        ev1 = _event(db, visibility="global", session_id=sess.id, type="event.first")
        ev2 = _event(db, visibility="global", session_id=sess.id, type="event.second")
        ev3 = _event(db, visibility="global", session_id=sess.id, type="event.third")
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/sessions/{sess.id}/timeline")
        items = response.json()["items"]
        assert len(items) == 3
        returned_ids = {item["id"] for item in items}
        assert returned_ids == {ev1.id, ev2.id, ev3.id}


# ===========================================================================
# Silent event exclusion
# ===========================================================================


class TestSessionTimelineSilentExclusion:
    """Silent events are excluded for all users, including the GM."""

    def test_silent_events_excluded_for_gm(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        sess = _session(db)
        _event(db, visibility="silent", session_id=sess.id)
        ev_global = _event(db, visibility="global", session_id=sess.id)
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/sessions/{sess.id}/timeline")
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == ev_global.id

    def test_silent_events_excluded_for_player(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        sess = _session(db)
        _event(db, visibility="silent", session_id=sess.id)
        ev_global = _event(db, visibility="global", session_id=sess.id)
        db.commit()
        auth_as(client, seed_data["player1"])
        response = client.get(f"/api/v1/sessions/{sess.id}/timeline")
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == ev_global.id

    def test_all_silent_returns_empty_for_gm(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        sess = _session(db)
        _event(db, visibility="silent", session_id=sess.id)
        _event(db, visibility="silent", session_id=sess.id)
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/sessions/{sess.id}/timeline")
        assert response.json()["items"] == []


# ===========================================================================
# Visibility filtering
# ===========================================================================


class TestSessionTimelineVisibilityFiltering:
    """Visibility rules are applied per authenticated user."""

    def test_player_cannot_see_gm_only_event(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        sess = _session(db)
        _event(db, visibility="gm_only", session_id=sess.id)
        db.commit()
        auth_as(client, seed_data["player1"])
        response = client.get(f"/api/v1/sessions/{sess.id}/timeline")
        assert response.json()["items"] == []

    def test_gm_sees_gm_only_events(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        sess = _session(db)
        ev = _event(db, visibility="gm_only", session_id=sess.id)
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/sessions/{sess.id}/timeline")
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == ev.id

    def test_gm_sees_more_events_than_player(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        sess = _session(db)
        ev_global = _event(db, visibility="global", session_id=sess.id)
        _event(db, visibility="gm_only", session_id=sess.id)
        db.commit()

        auth_as(client, seed_data["gm"])
        gm_response = client.get(f"/api/v1/sessions/{sess.id}/timeline")
        assert len(gm_response.json()["items"]) == 2

        auth_as(client, seed_data["player1"])
        player_response = client.get(f"/api/v1/sessions/{sess.id}/timeline")
        player_items = player_response.json()["items"]
        assert len(player_items) == 1
        assert player_items[0]["id"] == ev_global.id

    def test_player_cannot_see_private_event_not_their_own(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Private event for player1 is not visible to player2."""
        sess = _session(db)
        player1 = seed_data["player1"]
        pc1 = seed_data["pc1"]
        _event(
            db,
            visibility="private",
            actor_type="player",
            actor_id=player1.id,
            targets=[("character", pc1.id, True)],
            session_id=sess.id,
        )
        db.commit()
        auth_as(client, seed_data["player2"])
        response = client.get(f"/api/v1/sessions/{sess.id}/timeline")
        assert response.json()["items"] == []

    def test_player_sees_their_own_private_event(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        sess = _session(db)
        player1 = seed_data["player1"]
        ev = _event(
            db,
            visibility="private",
            actor_type="player",
            actor_id=player1.id,
            session_id=sess.id,
        )
        db.commit()
        auth_as(client, seed_data["player1"])
        response = client.get(f"/api/v1/sessions/{sess.id}/timeline")
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == ev.id


# ===========================================================================
# Pagination
# ===========================================================================


class TestSessionTimelinePagination:
    """ULID cursor pagination."""

    def test_default_limit_50(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        sess = _session(db)
        for _ in range(55):
            _event(db, visibility="global", session_id=sess.id)
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/sessions/{sess.id}/timeline")
        body = response.json()
        assert len(body["items"]) == 50
        assert body["has_more"] is True
        assert body["next_cursor"] is not None

    def test_limit_param_respected(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        sess = _session(db)
        for _ in range(5):
            _event(db, visibility="global", session_id=sess.id)
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/sessions/{sess.id}/timeline?limit=3")
        body = response.json()
        assert len(body["items"]) == 3
        assert body["has_more"] is True

    def test_limit_capped_at_100(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        sess = _session(db)
        for _ in range(110):
            _event(db, visibility="global", session_id=sess.id)
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/sessions/{sess.id}/timeline?limit=200")
        assert len(response.json()["items"]) == 100

    def test_after_cursor_returns_next_page(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        sess = _session(db)
        for _ in range(5):
            _event(db, visibility="global", session_id=sess.id)
        db.commit()
        auth_as(client, seed_data["gm"])

        page1 = client.get(f"/api/v1/sessions/{sess.id}/timeline?limit=3").json()
        assert len(page1["items"]) == 3
        assert page1["has_more"] is True
        cursor = page1["next_cursor"]

        page2 = client.get(
            f"/api/v1/sessions/{sess.id}/timeline?limit=3&after={cursor}"
        ).json()
        assert len(page2["items"]) == 2
        assert page2["has_more"] is False

        # No overlap.
        page1_ids = {item["id"] for item in page1["items"]}
        page2_ids = {item["id"] for item in page2["items"]}
        assert not page1_ids & page2_ids

    def test_no_more_pages_when_all_fit(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        sess = _session(db)
        for _ in range(3):
            _event(db, visibility="global", session_id=sess.id)
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/sessions/{sess.id}/timeline?limit=10")
        body = response.json()
        assert len(body["items"]) == 3
        assert body["has_more"] is False
        assert body["next_cursor"] is None

    def test_items_sorted_newest_first(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        sess = _session(db)
        _event(db, visibility="global", session_id=sess.id, type="event.first")
        _event(db, visibility="global", session_id=sess.id, type="event.second")
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/sessions/{sess.id}/timeline")
        items = response.json()["items"]
        assert len(items) == 2
        ids = [item["id"] for item in items]
        assert ids == sorted(ids, reverse=True)


# ===========================================================================
# Response shape
# ===========================================================================


class TestSessionTimelineResponseShape:
    """Response matches the EventResponse schema."""

    def test_response_envelope_shape(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        sess = _session(db)
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/sessions/{sess.id}/timeline")
        body = response.json()
        assert "items" in body
        assert "has_more" in body
        assert "next_cursor" in body

    def test_event_response_fields(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        sess = _session(db)
        gm = seed_data["gm"]
        ev = _event(
            db,
            type="character.stress_changed",
            actor_type="gm",
            actor_id=gm.id,
            visibility="global",
            session_id=sess.id,
            changes={"stress": {"before": 0, "after": 1}},
        )
        db.commit()
        auth_as(client, gm)
        response = client.get(f"/api/v1/sessions/{sess.id}/timeline")
        item = response.json()["items"][0]

        assert item["id"] == ev.id
        assert item["type"] == "character.stress_changed"
        assert item["actor_type"] == "gm"
        assert item["actor_id"] == gm.id
        assert item["visibility"] == "global"
        assert item["session_id"] == sess.id
        assert "created_at" in item
        assert item["targets"] == []

    def test_event_targets_included(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        sess = _session(db)
        pc1 = seed_data["pc1"]
        _event(
            db,
            visibility="global",
            session_id=sess.id,
            targets=[("character", pc1.id, True)],
        )
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/sessions/{sess.id}/timeline")
        item = response.json()["items"][0]
        assert len(item["targets"]) == 1
        assert item["targets"][0]["target_type"] == "character"
        assert item["targets"][0]["target_id"] == pc1.id
        assert item["targets"][0]["is_primary"] is True


# ===========================================================================
# Mixed visibility levels within one session
# ===========================================================================


class TestSessionTimelineMixedVisibility:
    """A session with events at multiple visibility levels is correctly filtered.

    Seed bond graph: pc1 → group ← pc2.  pc3 has no bonds.
    """

    def test_player_sees_only_visible_subset(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Player1 (bonded to group) sees global + bonded-to-group events.
        player3 (no bonds) sees only global.
        """
        sess = _session(db)
        group = seed_data["group"]

        ev_global = _event(db, visibility="global", session_id=sess.id, type="event.global")
        ev_gm_only = _event(db, visibility="gm_only", session_id=sess.id, type="event.gm_only")
        _event(db, visibility="silent", session_id=sess.id, type="event.silent")
        ev_bonded = _event(
            db,
            visibility="bonded",
            session_id=sess.id,
            type="event.bonded",
            targets=[("group", group.id, True)],
        )

        db.commit()

        # GM sees everything except silent: global + gm_only + bonded.
        auth_as(client, seed_data["gm"])
        gm_items = client.get(f"/api/v1/sessions/{sess.id}/timeline").json()["items"]
        gm_ids = {i["id"] for i in gm_items}
        assert gm_ids == {ev_global.id, ev_gm_only.id, ev_bonded.id}

        # player1 is bonded to group (1-hop) — sees global + bonded.
        auth_as(client, seed_data["player1"])
        p1_items = client.get(f"/api/v1/sessions/{sess.id}/timeline").json()["items"]
        p1_ids = {i["id"] for i in p1_items}
        assert p1_ids == {ev_global.id, ev_bonded.id}

        # player3 has no bonds — sees only global.
        auth_as(client, seed_data["player3"])
        p3_items = client.get(f"/api/v1/sessions/{sess.id}/timeline").json()["items"]
        p3_ids = {i["id"] for i in p3_items}
        assert p3_ids == {ev_global.id}

    def test_private_event_visible_to_actor_only(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """A private event is visible to the actor's character owner and GM, not others."""
        sess = _session(db)
        player1 = seed_data["player1"]
        pc1 = seed_data["pc1"]

        ev_private = _event(
            db,
            visibility="private",
            actor_type="player",
            actor_id=player1.id,
            session_id=sess.id,
            targets=[("character", pc1.id, True)],
        )
        ev_global = _event(db, visibility="global", session_id=sess.id)
        db.commit()

        # GM sees both.
        auth_as(client, seed_data["gm"])
        gm_ids = {i["id"] for i in client.get(f"/api/v1/sessions/{sess.id}/timeline").json()["items"]}
        assert gm_ids == {ev_private.id, ev_global.id}

        # player1 (actor) sees both.
        auth_as(client, seed_data["player1"])
        p1_ids = {i["id"] for i in client.get(f"/api/v1/sessions/{sess.id}/timeline").json()["items"]}
        assert p1_ids == {ev_private.id, ev_global.id}

        # player2 sees only global.
        auth_as(client, seed_data["player2"])
        p2_ids = {i["id"] for i in client.get(f"/api/v1/sessions/{sess.id}/timeline").json()["items"]}
        assert p2_ids == {ev_global.id}


# ===========================================================================
# Multi-page pagination with cursor
# ===========================================================================


class TestSessionTimelineMultiPagePagination:
    """Verify cursor pagination works correctly across multiple pages."""

    def test_full_traversal_yields_all_events_no_duplicates(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Walk through all pages with limit=5 and collect every ID.

        All events must appear exactly once; the final page must have
        has_more=False and next_cursor=None.
        """
        sess = _session(db)
        total = 13
        expected_ids = set()
        for i in range(total):
            ev = _event(db, visibility="global", session_id=sess.id, type=f"event.{i}")
            expected_ids.add(ev.id)
        db.commit()

        auth_as(client, seed_data["gm"])
        collected_ids: set[str] = set()
        cursor: str | None = None
        page_count = 0

        while True:
            url = f"/api/v1/sessions/{sess.id}/timeline?limit=5"
            if cursor:
                url += f"&after={cursor}"
            body = client.get(url).json()
            page_count += 1
            for item in body["items"]:
                collected_ids.add(item["id"])
            if not body["has_more"]:
                assert body["next_cursor"] is None
                break
            cursor = body["next_cursor"]
            assert cursor is not None

        assert collected_ids == expected_ids
        # 13 events at 5/page = ceil(13/5) = 3 pages.
        assert page_count == 3

    def test_next_cursor_is_last_item_id(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """next_cursor must equal the ID of the last item on the page."""
        sess = _session(db)
        for _ in range(5):
            _event(db, visibility="global", session_id=sess.id)
        db.commit()

        auth_as(client, seed_data["gm"])
        body = client.get(f"/api/v1/sessions/{sess.id}/timeline?limit=3").json()
        last_id = body["items"][-1]["id"]
        assert body["next_cursor"] == last_id


# ===========================================================================
# Session lifecycle events integration
# ===========================================================================


class TestSessionTimelineLifecycleEvents:
    """Verify that real session lifecycle events appear correctly on the timeline.

    Uses the actual POST /sessions/{id}/start endpoint to create the canonical
    3-event bundle (session.started global, session.ft_distributed silent,
    session.plot_distributed silent).  The timeline must show only the
    session.started event — the two silent ones must be excluded.
    """

    def test_only_started_event_visible_after_session_start(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        gm = seed_data["gm"]
        auth_as(client, gm)

        # Create + configure a draft session.
        create_resp = client.post(
            "/api/v1/sessions",
            json={"time_now": 100},
        )
        assert create_resp.status_code == 201
        session_id = create_resp.json()["id"]

        # Start the session — creates 3 events.
        start_resp = client.post(f"/api/v1/sessions/{session_id}/start")
        assert start_resp.status_code == 200

        # Timeline should show only session.started (global).
        # session.ft_distributed and session.plot_distributed are silent — excluded.
        timeline = client.get(f"/api/v1/sessions/{session_id}/timeline").json()
        items = timeline["items"]

        event_types = {i["type"] for i in items}
        assert "session.started" in event_types
        assert "session.ft_distributed" not in event_types
        assert "session.plot_distributed" not in event_types

    def test_timeline_shows_started_and_ended_events(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        gm = seed_data["gm"]
        auth_as(client, gm)

        create_resp = client.post("/api/v1/sessions", json={"time_now": 100})
        assert create_resp.status_code == 201
        session_id = create_resp.json()["id"]

        client.post(f"/api/v1/sessions/{session_id}/start")
        client.post(f"/api/v1/sessions/{session_id}/end")

        timeline = client.get(f"/api/v1/sessions/{session_id}/timeline").json()
        event_types = {i["type"] for i in timeline["items"]}

        assert "session.started" in event_types
        assert "session.ended" in event_types
        # Silent events must remain excluded.
        assert "session.ft_distributed" not in event_types
        assert "session.plot_distributed" not in event_types
