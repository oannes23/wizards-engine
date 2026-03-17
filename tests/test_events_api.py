"""Integration tests for GET /api/v1/events and related endpoints (Story 4.1.2).

Exercises:
- GET /events list endpoint: pagination, all filters, visibility filtering
- GET /events/{id} single event detail: happy path, 404, visibility gating
- PATCH /events/{id}/visibility: GM-only, updates persisted, non-GM blocked

All tests use the function-scoped ``client`` + ``seed_data`` fixtures so each
test starts with a completely isolated in-memory database.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import auth_as
from tests.fixtures import seed_data as _seed_data_fn
from wizards_engine.models.event import Event, EventTarget
from wizards_engine.models.proposal import Proposal
from wizards_engine.models.session import Session as SessionModel
from wizards_engine.models.user import User


# ===========================================================================
# Test helpers
# ===========================================================================


def _event(
    db: Session,
    *,
    type: str = "test.event",
    actor_type: str = "gm",
    actor_id: str | None = None,
    visibility: str = "global",
    session_id: str | None = None,
    proposal_id: str | None = None,
    parent_event_id: str | None = None,
    targets: list[tuple[str, str, bool]] | None = None,
    changes: dict | None = None,
    narrative: str | None = None,
) -> Event:
    """Create and flush a minimal Event in the current test DB session.

    Returns:
        A flushed, refreshed Event ORM instance.
    """
    ev = Event(
        type=type,
        actor_type=actor_type,
        actor_id=actor_id,
        changes=changes if changes is not None else {},
        visibility=visibility,
        session_id=session_id,
        proposal_id=proposal_id,
        parent_event_id=parent_event_id,
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


def _session(db: Session, *, status: str = "draft") -> SessionModel:
    """Create and flush a session."""
    s = SessionModel(status=status)
    db.add(s)
    db.flush()
    db.refresh(s)
    return s


def _proposal(db: Session) -> Proposal:
    """Create and flush a minimal Proposal row."""
    p = Proposal(
        action_type="free_time",
        origin="player",
        narrative="Test proposal",
        selections={},
        status="pending",
    )
    db.add(p)
    db.flush()
    db.refresh(p)
    return p


# ===========================================================================
# GET /events — unauthenticated
# ===========================================================================


class TestListEventsAuth:
    """Unauthenticated requests are rejected."""

    def test_unauthenticated_returns_401(self, client: TestClient) -> None:
        response = client.get("/api/v1/events")
        assert response.status_code == 401


# ===========================================================================
# GET /events — basic listing
# ===========================================================================


class TestListEventsBasic:
    """Basic listing behaviour."""

    def test_empty_db_returns_empty_list(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/events")
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []
        assert body["has_more"] is False
        assert body["next_cursor"] is None

    def test_returns_global_events_for_gm(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        _event(db, visibility="global")
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/events")
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1

    def test_returns_global_events_for_player(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        _event(db, visibility="global")
        db.commit()
        auth_as(client, seed_data["player1"])
        response = client.get("/api/v1/events")
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1

    def test_gm_only_events_excluded_for_player(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        _event(db, visibility="gm_only")
        _event(db, visibility="global")
        db.commit()
        auth_as(client, seed_data["player1"])
        response = client.get("/api/v1/events")
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["visibility"] == "global"

    def test_gm_sees_gm_only_events(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        _event(db, visibility="gm_only")
        _event(db, visibility="global")
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/events")
        assert response.status_code == 200
        assert len(response.json()["items"]) == 2

    def test_silent_events_excluded_for_everyone(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """silent events must not appear in the normal feed, even for the GM."""
        _event(db, visibility="silent")
        _event(db, visibility="global")
        db.commit()

        auth_as(client, seed_data["gm"])
        gm_response = client.get("/api/v1/events")
        gm_items = gm_response.json()["items"]
        assert len(gm_items) == 1
        assert gm_items[0]["visibility"] == "global"

        auth_as(client, seed_data["player1"])
        player_response = client.get("/api/v1/events")
        player_items = player_response.json()["items"]
        assert len(player_items) == 1
        assert player_items[0]["visibility"] == "global"

    def test_items_sorted_newest_first(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        ev1 = _event(db, visibility="global", type="event.first")
        ev2 = _event(db, visibility="global", type="event.second")
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/events")
        items = response.json()["items"]
        assert len(items) == 2
        # Newest-first: the item with the larger ULID (lexicographically) comes first.
        item_ids = [item["id"] for item in items]
        assert item_ids == sorted(item_ids, reverse=True)


# ===========================================================================
# GET /events — response shape
# ===========================================================================


class TestListEventsShape:
    """Response schema is correct."""

    def test_event_response_has_required_fields(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        gm = seed_data["gm"]
        ev = _event(
            db,
            type="character.stress_changed",
            actor_type="gm",
            actor_id=gm.id,
            visibility="global",
            narrative="A test narrative.",
            changes={"key": "value"},
        )
        db.commit()
        auth_as(client, gm)
        response = client.get("/api/v1/events")
        item = response.json()["items"][0]

        assert item["id"] == ev.id
        assert item["type"] == "character.stress_changed"
        assert item["actor_type"] == "gm"
        assert item["actor_id"] == gm.id
        assert item["visibility"] == "global"
        assert item["narrative"] == "A test narrative."
        assert item["changes"] == {"key": "value"}
        assert item["created_objects"] is None
        assert item["deleted_objects"] is None
        assert item["proposal_id"] is None
        assert item["parent_event_id"] is None
        assert item["session_id"] is None
        assert item["metadata"] is None
        assert "created_at" in item
        assert item["targets"] == []

    def test_event_with_targets_includes_them(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        ev = _event(
            db,
            visibility="global",
            targets=[("character", pc1.id, True)],
        )
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/events")
        item = response.json()["items"][0]
        assert len(item["targets"]) == 1
        target = item["targets"][0]
        assert target["target_type"] == "character"
        assert target["target_id"] == pc1.id
        assert target["is_primary"] is True

    def test_metadata_field_surfaced(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """The metadata_ ORM attribute is exposed as 'metadata' in the response."""
        ev = Event(
            type="test.meta",
            actor_type="system",
            changes={},
            visibility="global",
            metadata_={"source": "unit_test"},
        )
        db.add(ev)
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/events")
        item = response.json()["items"][0]
        assert item["metadata"] == {"source": "unit_test"}


# ===========================================================================
# GET /events — pagination
# ===========================================================================


class TestListEventsPagination:
    """ULID cursor pagination behaviour."""

    def test_default_limit_50(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        for _ in range(55):
            _event(db, visibility="global")
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/events")
        body = response.json()
        assert len(body["items"]) == 50
        assert body["has_more"] is True
        assert body["next_cursor"] is not None

    def test_limit_param_respected(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        for _ in range(5):
            _event(db, visibility="global")
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/events?limit=3")
        body = response.json()
        assert len(body["items"]) == 3
        assert body["has_more"] is True

    def test_limit_capped_at_100(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        for _ in range(110):
            _event(db, visibility="global")
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/events?limit=200")
        body = response.json()
        assert len(body["items"]) == 100

    def test_after_cursor_returns_next_page(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        evs = [_event(db, visibility="global") for _ in range(5)]
        db.commit()
        auth_as(client, seed_data["gm"])

        # First page — limit 3.
        page1 = client.get("/api/v1/events?limit=3").json()
        assert len(page1["items"]) == 3
        assert page1["has_more"] is True
        cursor = page1["next_cursor"]

        # Second page.
        page2 = client.get(f"/api/v1/events?limit=3&after={cursor}").json()
        assert len(page2["items"]) == 2
        assert page2["has_more"] is False

        # No IDs overlap.
        page1_ids = {item["id"] for item in page1["items"]}
        page2_ids = {item["id"] for item in page2["items"]}
        assert not page1_ids & page2_ids

    def test_no_more_pages_when_all_fit(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        for _ in range(3):
            _event(db, visibility="global")
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/events?limit=10")
        body = response.json()
        assert len(body["items"]) == 3
        assert body["has_more"] is False
        assert body["next_cursor"] is None


# ===========================================================================
# GET /events — type filter
# ===========================================================================


class TestListEventsTypeFilter:
    """?type= filter with exact and prefix-wildcard matching."""

    def test_exact_type_filter(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        _event(db, type="character.stress_changed", visibility="global")
        _event(db, type="bond.created", visibility="global")
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/events?type=character.stress_changed")
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["type"] == "character.stress_changed"

    def test_wildcard_prefix_type_filter(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        _event(db, type="character.stress_changed", visibility="global")
        _event(db, type="character.created", visibility="global")
        _event(db, type="bond.created", visibility="global")
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/events?type=character.*")
        items = response.json()["items"]
        assert len(items) == 2
        types = {item["type"] for item in items}
        assert types == {"character.stress_changed", "character.created"}

    def test_type_filter_no_match_returns_empty(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        _event(db, type="bond.created", visibility="global")
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/events?type=session.*")
        assert response.json()["items"] == []


# ===========================================================================
# GET /events — other filters
# ===========================================================================


class TestListEventsFilters:
    """Other filter query parameters."""

    def test_target_type_filter(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        group = seed_data["group"]
        _event(db, visibility="global", targets=[("character", pc1.id, True)])
        _event(db, visibility="global", targets=[("group", group.id, True)])
        _event(db, visibility="global")  # no targets
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/events?target_type=character")
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["targets"][0]["target_type"] == "character"

    def test_target_id_filter(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        pc2 = seed_data["pc2"]
        ev1 = _event(db, visibility="global", targets=[("character", pc1.id, True)])
        _event(db, visibility="global", targets=[("character", pc2.id, True)])
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/events?target_id={pc1.id}")
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == ev1.id

    def test_target_type_and_id_combined(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        group = seed_data["group"]
        ev1 = _event(db, visibility="global", targets=[("character", pc1.id, True)])
        _event(db, visibility="global", targets=[("group", pc1.id, True)])  # wrong type
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/events?target_type=character&target_id={pc1.id}")
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == ev1.id

    def test_session_id_filter(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        sess = _session(db)
        ev1 = _event(db, visibility="global", session_id=sess.id)
        _event(db, visibility="global")  # no session
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/events?session_id={sess.id}")
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == ev1.id

    def test_actor_type_filter(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        _event(db, visibility="global", actor_type="gm")
        _event(db, visibility="global", actor_type="system")
        _event(db, visibility="global", actor_type="player")
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/events?actor_type=system")
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["actor_type"] == "system"

    def test_since_filter(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """?since= returns only events at or after the given timestamp."""
        import urllib.parse

        _event(db, visibility="global")
        db.commit()

        # Record a "dividing" time after the first event.
        dividing_time = datetime.now(tz=timezone.utc).isoformat()

        _event(db, visibility="global")
        db.commit()

        auth_as(client, seed_data["gm"])
        # URL-encode the datetime to preserve the '+' in '+00:00'.
        encoded_time = urllib.parse.quote(dividing_time)
        response = client.get(f"/api/v1/events?since={encoded_time}")
        assert response.status_code == 200, response.text
        items = response.json()["items"]
        assert len(items) == 1

    def test_until_filter(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """?until= returns only events at or before the given timestamp."""
        import urllib.parse

        _event(db, visibility="global")
        db.commit()

        # Record "dividing" time.
        dividing_time = datetime.now(tz=timezone.utc).isoformat()

        _event(db, visibility="global")
        db.commit()

        auth_as(client, seed_data["gm"])
        encoded_time = urllib.parse.quote(dividing_time)
        response = client.get(f"/api/v1/events?until={encoded_time}")
        assert response.status_code == 200, response.text
        items = response.json()["items"]
        assert len(items) == 1

    def test_proposal_id_filter(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """?proposal_id= returns only events linked to that proposal."""
        proposal = _proposal(db)
        ev_linked = _event(db, visibility="global", proposal_id=proposal.id)
        _event(db, visibility="global")  # no proposal
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/events?proposal_id={proposal.id}")
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == ev_linked.id
        assert items[0]["proposal_id"] == proposal.id

    def test_multiple_filters_combined_with_and(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        sess = _session(db)
        # Matches both type and session_id.
        ev_match = _event(
            db,
            type="character.stress_changed",
            visibility="global",
            session_id=sess.id,
            targets=[("character", pc1.id, True)],
        )
        # Matches type but not session_id.
        _event(db, type="character.stress_changed", visibility="global")
        # Matches session_id but not type.
        _event(db, type="bond.created", visibility="global", session_id=sess.id)
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.get(
            f"/api/v1/events?type=character.stress_changed&session_id={sess.id}"
        )
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == ev_match.id


# ===========================================================================
# GET /events — visibility filtering
# ===========================================================================


class TestListEventsVisibilityFiltering:
    """Results are filtered by the authenticated user's visibility access."""

    def test_player_cannot_see_private_event_not_their_own(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """A private event targeted at another PC is not visible to player2."""
        player1 = seed_data["player1"]
        pc1 = seed_data["pc1"]
        # Private event where actor is player1 / target is pc1.
        _event(
            db,
            visibility="private",
            actor_type="player",
            actor_id=player1.id,
            targets=[("character", pc1.id, True)],
        )
        db.commit()
        auth_as(client, seed_data["player2"])
        response = client.get("/api/v1/events")
        assert response.json()["items"] == []

    def test_player_sees_their_own_private_event(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        player1 = seed_data["player1"]
        _event(
            db,
            visibility="private",
            actor_type="player",
            actor_id=player1.id,
        )
        db.commit()
        auth_as(client, seed_data["player1"])
        response = client.get("/api/v1/events")
        assert len(response.json()["items"]) == 1


# ===========================================================================
# GET /events/{id} — basic
# ===========================================================================


class TestGetEventBasic:
    """Single event detail endpoint."""

    def test_unauthenticated_returns_401(self, client: TestClient, db: Session) -> None:
        response = client.get("/api/v1/events/nonexistent")
        assert response.status_code == 401

    def test_nonexistent_event_returns_404(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/events/01HXNONEXISTENTID12345678")
        assert response.status_code == 404

    def test_returns_event_for_authenticated_user(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        ev = _event(db, visibility="global", type="character.stress_changed")
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/events/{ev.id}")
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == ev.id
        assert body["type"] == "character.stress_changed"

    def test_response_includes_targets(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        ev = _event(
            db,
            visibility="global",
            targets=[("character", pc1.id, True)],
        )
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/events/{ev.id}")
        assert response.status_code == 200
        targets = response.json()["targets"]
        assert len(targets) == 1
        assert targets[0]["target_id"] == pc1.id
        assert targets[0]["is_primary"] is True


# ===========================================================================
# GET /events/{id} — visibility gating
# ===========================================================================


class TestGetEventVisibility:
    """Visibility rules applied to single event fetch."""

    def test_silent_event_returns_404_for_gm(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Silent events return 404 even for the GM on the normal endpoint."""
        ev = _event(db, visibility="silent")
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/events/{ev.id}")
        assert response.status_code == 404

    def test_silent_event_returns_404_for_player(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        ev = _event(db, visibility="silent")
        db.commit()
        auth_as(client, seed_data["player1"])
        response = client.get(f"/api/v1/events/{ev.id}")
        assert response.status_code == 404

    def test_gm_only_event_returns_404_for_player(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        ev = _event(db, visibility="gm_only")
        db.commit()
        auth_as(client, seed_data["player1"])
        response = client.get(f"/api/v1/events/{ev.id}")
        assert response.status_code == 404

    def test_gm_only_event_visible_to_gm(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        ev = _event(db, visibility="gm_only")
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/events/{ev.id}")
        assert response.status_code == 200

    def test_private_event_visible_to_actor(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        player1 = seed_data["player1"]
        ev = _event(
            db,
            visibility="private",
            actor_type="player",
            actor_id=player1.id,
        )
        db.commit()
        auth_as(client, seed_data["player1"])
        response = client.get(f"/api/v1/events/{ev.id}")
        assert response.status_code == 200

    def test_private_event_returns_404_for_uninvolved_player(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        player1 = seed_data["player1"]
        ev = _event(
            db,
            visibility="private",
            actor_type="player",
            actor_id=player1.id,
        )
        db.commit()
        auth_as(client, seed_data["player2"])
        response = client.get(f"/api/v1/events/{ev.id}")
        assert response.status_code == 404

    def test_global_event_visible_to_player(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        ev = _event(db, visibility="global")
        db.commit()
        auth_as(client, seed_data["player1"])
        response = client.get(f"/api/v1/events/{ev.id}")
        assert response.status_code == 200


# ===========================================================================
# PATCH /events/{id}/visibility
# ===========================================================================


class TestUpdateEventVisibility:
    """PATCH /events/{id}/visibility endpoint."""

    def test_unauthenticated_returns_401(self, client: TestClient, db: Session) -> None:
        response = client.patch(
            "/api/v1/events/01HXNONEXISTENTID12345678/visibility",
            json={"visibility": "gm_only"},
        )
        assert response.status_code == 401

    def test_player_gets_403(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        ev = _event(db, visibility="global")
        db.commit()
        auth_as(client, seed_data["player1"])
        response = client.patch(
            f"/api/v1/events/{ev.id}/visibility",
            json={"visibility": "gm_only"},
        )
        assert response.status_code == 403

    def test_nonexistent_event_returns_404(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = client.patch(
            "/api/v1/events/01HXNONEXISTENTID12345678/visibility",
            json={"visibility": "gm_only"},
        )
        assert response.status_code == 404

    def test_gm_can_update_visibility(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        ev = _event(db, visibility="global")
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.patch(
            f"/api/v1/events/{ev.id}/visibility",
            json={"visibility": "gm_only"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["visibility"] == "gm_only"
        assert body["id"] == ev.id

    def test_visibility_persisted_to_db(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        ev = _event(db, visibility="global")
        db.commit()
        auth_as(client, seed_data["gm"])
        client.patch(
            f"/api/v1/events/{ev.id}/visibility",
            json={"visibility": "private"},
        )
        # Fetch via GET to confirm persistence.
        response = client.get(f"/api/v1/events/{ev.id}")
        assert response.status_code == 200
        assert response.json()["visibility"] == "private"

    def test_invalid_visibility_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        ev = _event(db, visibility="global")
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.patch(
            f"/api/v1/events/{ev.id}/visibility",
            json={"visibility": "invisible"},
        )
        assert response.status_code == 422

    @pytest.mark.parametrize(
        "level",
        ["silent", "gm_only", "private", "bonded", "familiar", "public", "global"],
    )
    def test_all_valid_visibility_levels_accepted(
        self, client: TestClient, db: Session, seed_data: dict, level: str
    ) -> None:
        ev = _event(db, visibility="global")
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.patch(
            f"/api/v1/events/{ev.id}/visibility",
            json={"visibility": level},
        )
        assert response.status_code == 200
        assert response.json()["visibility"] == level

    def test_response_includes_full_event_shape(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """PATCH returns the full EventResponse, not just the changed field."""
        ev = _event(
            db,
            type="character.stress_changed",
            actor_type="gm",
            visibility="global",
            narrative="Original narrative.",
        )
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.patch(
            f"/api/v1/events/{ev.id}/visibility",
            json={"visibility": "gm_only"},
        )
        body = response.json()
        assert body["type"] == "character.stress_changed"
        assert body["narrative"] == "Original narrative."
        assert body["visibility"] == "gm_only"
