"""Integration tests for Story 4.2.3 — GM World Object Actions.

Covers modify_group, modify_location, and modify_clock action types:

modify_group:
- Happy path: tier updated, event returned
- Event shape: type, actor, changes dict
- 404 for unknown group
- Validates tier >= 0 (Pydantic schema)

modify_location:
- Happy path: parent_id changed
- Clear parent (set to null)
- 404 for unknown location
- 422 when new parent does not exist
- 422 when new parent is the location itself
- 422 when new parent is a descendant (circular hierarchy)

modify_clock:
- Happy path: delta advance
- Happy path: set operation
- Progress clamped at 0 (floor)
- Progress soft cap: can exceed segments
- Event metadata annotation stored on event
- 404 for unknown clock
- Clock completion: auto-generates resolve_clock proposal
- Clock completion: proposal narrative includes clock name
- Clock completion: idempotent (no second proposal on re-advance)
- Clock completion: approved proposal blocks new generation
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import auth_as
from wizards_engine.models.clock import Clock
from wizards_engine.models.location import Location
from wizards_engine.models.proposal import Proposal


# ===========================================================================
# Helpers
# ===========================================================================


def _post(client: TestClient, body: dict) -> "Response":  # type: ignore[name-defined]
    """POST to /api/v1/gm/actions."""
    return client.post("/api/v1/gm/actions", json=body)


def _modify_group(
    client: TestClient,
    group_id: str,
    tier: int,
    *,
    narrative: str | None = None,
    visibility: str = "public",
) -> "Response":  # type: ignore[name-defined]
    """Convenience wrapper for a modify_group action."""
    body: dict = {
        "action_type": "modify_group",
        "target_id": group_id,
        "changes": {"tier": tier},
        "visibility": visibility,
    }
    if narrative is not None:
        body["narrative"] = narrative
    return _post(client, body)


def _modify_location(
    client: TestClient,
    location_id: str,
    parent_id: str | None,
    *,
    narrative: str | None = None,
    visibility: str = "public",
) -> "Response":  # type: ignore[name-defined]
    """Convenience wrapper for a modify_location action."""
    body: dict = {
        "action_type": "modify_location",
        "target_id": location_id,
        "changes": {"parent_id": parent_id},
        "visibility": visibility,
    }
    if narrative is not None:
        body["narrative"] = narrative
    return _post(client, body)


def _modify_clock(
    client: TestClient,
    clock_id: str,
    op: str,
    value: int,
    *,
    narrative: str | None = None,
    visibility: str = "public",
    metadata: dict | None = None,
) -> "Response":  # type: ignore[name-defined]
    """Convenience wrapper for a modify_clock action."""
    body: dict = {
        "action_type": "modify_clock",
        "target_id": clock_id,
        "changes": {"progress": {"op": op, "value": value}},
        "visibility": visibility,
    }
    if narrative is not None:
        body["narrative"] = narrative
    if metadata is not None:
        body["metadata"] = metadata
    return _post(client, body)


def _make_clock(db: Session, name: str, segments: int, progress: int = 0) -> Clock:
    """Create and persist a Clock in the test database."""
    clock = Clock(name=name, segments=segments, progress=progress)
    db.add(clock)
    db.commit()
    db.refresh(clock)
    return clock


# ===========================================================================
# modify_group
# ===========================================================================


class TestModifyGroup:
    """Tests for the modify_group action type."""

    def test_tier_updated(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Tier is applied to the group."""
        group = seed_data["group"]  # tier=2
        auth_as(client, seed_data["gm"])

        response = _modify_group(client, group.id, tier=5)
        assert response.status_code == 200

        db.expire(group)
        db.refresh(group)
        assert group.tier == 5

    def test_event_shape(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """Returned event has correct type, actor, changes, and target."""
        group = seed_data["group"]
        auth_as(client, seed_data["gm"])

        response = _modify_group(
            client, group.id, tier=3, narrative="Power shift.", visibility="gm_only"
        )
        assert response.status_code == 200
        body = response.json()

        assert body["type"] == "group.updated"
        assert body["actor_type"] == "gm"
        assert body["actor_id"] == seed_data["gm"].id
        assert body["narrative"] == "Power shift."
        assert body["visibility"] == "gm_only"

        assert len(body["targets"]) == 1
        assert body["targets"][0]["target_type"] == "group"
        assert body["targets"][0]["target_id"] == group.id
        assert body["targets"][0]["is_primary"] is True

    def test_changes_dict_before_and_after(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """Changes dict records before/after with meter.set op."""
        group = seed_data["group"]  # tier=2
        auth_as(client, seed_data["gm"])

        response = _modify_group(client, group.id, tier=4)
        changes = response.json()["changes"]
        key = f"group.{group.id}.tier"

        assert changes[key]["op"] == "meter.set"
        assert changes[key]["before"] == 2
        assert changes[key]["after"] == 4

    def test_unknown_group_returns_404(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """Unknown group ID yields 404."""
        auth_as(client, seed_data["gm"])
        response = _modify_group(client, "01NONEXISTENTGROUPID000000", tier=1)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_negative_tier_rejected_by_schema(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """Tier < 0 is rejected by Pydantic schema validation (FastAPI 422)."""
        group = seed_data["group"]
        auth_as(client, seed_data["gm"])
        response = _modify_group(client, group.id, tier=-1)
        assert response.status_code == 422

    def test_tier_zero_accepted(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Tier = 0 is valid."""
        group = seed_data["group"]
        auth_as(client, seed_data["gm"])
        response = _modify_group(client, group.id, tier=0)
        assert response.status_code == 200
        db.expire(group)
        db.refresh(group)
        assert group.tier == 0


# ===========================================================================
# modify_location
# ===========================================================================


class TestModifyLocation:
    """Tests for the modify_location action type."""

    def test_parent_id_changed(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """parent_id is updated on the location."""
        region = seed_data["region"]
        district = seed_data["district"]
        auth_as(client, seed_data["gm"])

        # Move district to be a root node (currently under region).
        response = _modify_location(client, district.id, parent_id=None)
        assert response.status_code == 200

        db.expire(district)
        db.refresh(district)
        assert district.parent_id is None

    def test_reassign_to_new_parent(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Re-parenting to a different existing location works."""
        region = seed_data["region"]
        district = seed_data["district"]

        # Create a second region to re-parent district into.
        new_region = Location(name="New Region")
        db.add(new_region)
        db.commit()
        db.refresh(new_region)

        auth_as(client, seed_data["gm"])
        response = _modify_location(client, district.id, parent_id=new_region.id)
        assert response.status_code == 200

        db.expire(district)
        db.refresh(district)
        assert district.parent_id == new_region.id

    def test_event_shape(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """Returned event has correct type, actor, changes, and target."""
        district = seed_data["district"]
        region = seed_data["region"]
        auth_as(client, seed_data["gm"])

        response = _modify_location(
            client, district.id, parent_id=None, narrative="Seceded.", visibility="gm_only"
        )
        assert response.status_code == 200
        body = response.json()

        assert body["type"] == "location.updated"
        assert body["actor_type"] == "gm"
        assert body["actor_id"] == seed_data["gm"].id
        assert body["narrative"] == "Seceded."
        assert body["visibility"] == "gm_only"

        assert len(body["targets"]) == 1
        assert body["targets"][0]["target_type"] == "location"
        assert body["targets"][0]["target_id"] == district.id
        assert body["targets"][0]["is_primary"] is True

    def test_changes_dict_before_and_after(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """Changes dict records before/after with field.set op."""
        district = seed_data["district"]
        region = seed_data["region"]
        auth_as(client, seed_data["gm"])

        response = _modify_location(client, district.id, parent_id=None)
        changes = response.json()["changes"]
        key = f"location.{district.id}.parent_id"

        assert changes[key]["op"] == "field.set"
        assert changes[key]["before"] == region.id
        assert changes[key]["after"] is None

    def test_unknown_location_returns_404(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """Unknown location ID yields 404."""
        auth_as(client, seed_data["gm"])
        response = _modify_location(client, "01NONEXISTENTLOCID000000000", parent_id=None)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_unknown_new_parent_returns_404(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """Non-existent parent_id yields 404 (parent location not found)."""
        district = seed_data["district"]
        auth_as(client, seed_data["gm"])
        response = _modify_location(
            client, district.id, parent_id="01NONEXISTENTPARENTID00000"
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_self_parent_returns_422(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """Setting a location as its own parent yields 422."""
        district = seed_data["district"]
        auth_as(client, seed_data["gm"])
        response = _modify_location(client, district.id, parent_id=district.id)
        assert response.status_code == 422

    def test_circular_hierarchy_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Setting a descendant as parent yields 422 (circular hierarchy)."""
        region = seed_data["region"]
        district = seed_data["district"]  # district.parent_id = region.id

        # Trying to set region's parent to district would create a cycle.
        auth_as(client, seed_data["gm"])
        response = _modify_location(client, region.id, parent_id=district.id)
        assert response.status_code == 422

    def test_deep_circular_hierarchy_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Circular hierarchy detection works for deeper descendants."""
        region = seed_data["region"]
        district = seed_data["district"]  # region → district

        # Create a grandchild.
        street = Location(name="Main Street", parent_id=district.id)
        db.add(street)
        db.commit()
        db.refresh(street)

        # Trying to set region's parent to street would create a cycle.
        auth_as(client, seed_data["gm"])
        response = _modify_location(client, region.id, parent_id=street.id)
        assert response.status_code == 422


# ===========================================================================
# modify_clock
# ===========================================================================


class TestModifyClockProgress:
    """Tests for modify_clock progress operations."""

    def test_delta_applied(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Delta advance increments clock progress."""
        clock = _make_clock(db, "Test Clock", segments=5, progress=2)
        auth_as(client, seed_data["gm"])

        response = _modify_clock(client, clock.id, op="delta", value=2)
        assert response.status_code == 200

        db.expire(clock)
        db.refresh(clock)
        assert clock.progress == 4

    def test_set_applied(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Set operation assigns progress directly."""
        clock = _make_clock(db, "Test Clock", segments=8)
        auth_as(client, seed_data["gm"])

        response = _modify_clock(client, clock.id, op="set", value=6)
        assert response.status_code == 200

        db.expire(clock)
        db.refresh(clock)
        assert clock.progress == 6

    def test_progress_clamped_at_floor(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Progress cannot go below 0."""
        clock = _make_clock(db, "Test Clock", segments=5, progress=2)
        auth_as(client, seed_data["gm"])

        response = _modify_clock(client, clock.id, op="delta", value=-10)
        assert response.status_code == 200

        db.expire(clock)
        db.refresh(clock)
        assert clock.progress == 0

        changes = response.json()["changes"]
        key = f"clock.{clock.id}.progress"
        assert changes[key]["clamped"] is True
        assert changes[key]["after"] == 0

    def test_no_clamped_flag_when_not_clamped(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """clamped key absent when no clamping occurred."""
        clock = _make_clock(db, "Test Clock", segments=5)
        auth_as(client, seed_data["gm"])

        response = _modify_clock(client, clock.id, op="set", value=3)
        changes = response.json()["changes"]
        key = f"clock.{clock.id}.progress"
        assert "clamped" not in changes[key]

    def test_progress_can_exceed_segments(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Soft cap: progress can exceed segments (over-achievement)."""
        clock = _make_clock(db, "Test Clock", segments=4, progress=4)
        auth_as(client, seed_data["gm"])

        response = _modify_clock(client, clock.id, op="delta", value=2)
        assert response.status_code == 200

        db.expire(clock)
        db.refresh(clock)
        assert clock.progress == 6
        # No clamping flag.
        changes = response.json()["changes"]
        key = f"clock.{clock.id}.progress"
        assert "clamped" not in changes[key]

    def test_event_shape(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Returned event has correct type, actor, changes, and target."""
        clock = _make_clock(db, "Test Clock", segments=6)
        auth_as(client, seed_data["gm"])

        response = _modify_clock(
            client,
            clock.id,
            op="delta",
            value=1,
            narrative="Pressure builds.",
            visibility="gm_only",
        )
        assert response.status_code == 200
        body = response.json()

        assert body["type"] == "clock.advanced"
        assert body["actor_type"] == "gm"
        assert body["actor_id"] == seed_data["gm"].id
        assert body["narrative"] == "Pressure builds."
        assert body["visibility"] == "gm_only"

        assert len(body["targets"]) == 1
        assert body["targets"][0]["target_type"] == "clock"
        assert body["targets"][0]["target_id"] == clock.id
        assert body["targets"][0]["is_primary"] is True

    def test_changes_dict_delta_op(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Delta op recorded as meter.delta."""
        clock = _make_clock(db, "Test Clock", segments=5, progress=1)
        auth_as(client, seed_data["gm"])

        response = _modify_clock(client, clock.id, op="delta", value=2)
        changes = response.json()["changes"]
        key = f"clock.{clock.id}.progress"

        assert changes[key]["op"] == "meter.delta"
        assert changes[key]["before"] == 1
        assert changes[key]["after"] == 3

    def test_changes_dict_set_op(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Set op recorded as meter.set."""
        clock = _make_clock(db, "Test Clock", segments=5, progress=1)
        auth_as(client, seed_data["gm"])

        response = _modify_clock(client, clock.id, op="set", value=4)
        changes = response.json()["changes"]
        key = f"clock.{clock.id}.progress"

        assert changes[key]["op"] == "meter.set"
        assert changes[key]["before"] == 1
        assert changes[key]["after"] == 4

    def test_annotation_metadata_stored_on_event(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Annotation metadata is stored in the event's metadata field."""
        from wizards_engine.models.event import Event

        clock = _make_clock(db, "Test Clock", segments=5)
        auth_as(client, seed_data["gm"])

        response = _modify_clock(
            client,
            clock.id,
            op="delta",
            value=1,
            metadata={"notes": "Session 3 activity."},
        )
        assert response.status_code == 200

        event_id = response.json()["id"]
        event = db.get(Event, event_id)
        assert event is not None
        assert event.metadata_ is not None
        assert event.metadata_["notes"] == "Session 3 activity."

    def test_unknown_clock_returns_404(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """Unknown clock ID yields 404."""
        auth_as(client, seed_data["gm"])
        response = _modify_clock(client, "01NONEXISTENTCLOCKID000000", op="delta", value=1)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"


# ===========================================================================
# Clock completion detection
# ===========================================================================


class TestModifyClockCompletion:
    """Tests for resolve_clock auto-proposal on clock completion."""

    def test_completion_creates_proposal(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Advancing to >= segments creates a resolve_clock proposal."""
        clock = _make_clock(db, "Heist Clock", segments=4, progress=3)
        auth_as(client, seed_data["gm"])

        response = _modify_clock(client, clock.id, op="delta", value=1)
        assert response.status_code == 200

        proposal = (
            db.query(Proposal)
            .filter(
                Proposal.clock_id == clock.id,
                Proposal.action_type == "resolve_clock",
                Proposal.status == "pending",
            )
            .first()
        )
        assert proposal is not None
        assert proposal.origin == "system"
        assert proposal.character_id is None

    def test_completion_proposal_narrative_contains_clock_name(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """The auto-generated proposal narrative names the completed clock."""
        clock = _make_clock(db, "The Great Heist", segments=3, progress=2)
        auth_as(client, seed_data["gm"])

        _modify_clock(client, clock.id, op="delta", value=1)

        proposal = (
            db.query(Proposal)
            .filter(
                Proposal.clock_id == clock.id,
                Proposal.action_type == "resolve_clock",
            )
            .first()
        )
        assert proposal is not None
        assert "The Great Heist" in proposal.narrative

    def test_below_completion_no_proposal(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """No proposal generated when progress < segments."""
        clock = _make_clock(db, "Slow Clock", segments=6, progress=0)
        auth_as(client, seed_data["gm"])

        _modify_clock(client, clock.id, op="delta", value=3)

        proposal = (
            db.query(Proposal)
            .filter(
                Proposal.clock_id == clock.id,
                Proposal.action_type == "resolve_clock",
            )
            .first()
        )
        assert proposal is None

    def test_completion_idempotent_second_advance(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Advancing a completed clock a second time does not create another proposal."""
        clock = _make_clock(db, "Done Clock", segments=3, progress=2)
        auth_as(client, seed_data["gm"])

        # First advance: completes the clock, generates proposal.
        _modify_clock(client, clock.id, op="delta", value=1)
        # Second advance: soft cap, no second proposal.
        _modify_clock(client, clock.id, op="delta", value=1)

        count = (
            db.query(Proposal)
            .filter(
                Proposal.clock_id == clock.id,
                Proposal.action_type == "resolve_clock",
            )
            .count()
        )
        assert count == 1

    def test_approved_proposal_blocks_new_generation(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """An existing approved resolve_clock proposal prevents a new one."""
        clock = _make_clock(db, "Resolved Clock", segments=3, progress=0)

        # Manually create an approved proposal for this clock.
        approved = Proposal(
            character_id=None,
            action_type="resolve_clock",
            origin="system",
            narrative="Already resolved.",
            selections={},
            calculated_effect={},
            status="approved",
            clock_id=clock.id,
        )
        db.add(approved)
        db.commit()

        auth_as(client, seed_data["gm"])
        # Advance past segments.
        _modify_clock(client, clock.id, op="set", value=5)

        count = (
            db.query(Proposal)
            .filter(
                Proposal.clock_id == clock.id,
                Proposal.action_type == "resolve_clock",
            )
            .count()
        )
        # Still just 1 — the approved one, no new pending.
        assert count == 1

    def test_completion_creates_silent_rider_event(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """A silent clock.resolve_generated rider event is created on completion."""
        from wizards_engine.models.event import Event

        clock = _make_clock(db, "Finale Clock", segments=2, progress=1)
        auth_as(client, seed_data["gm"])

        response = _modify_clock(client, clock.id, op="delta", value=1)
        assert response.status_code == 200

        primary_event_id = response.json()["id"]

        rider = (
            db.query(Event)
            .filter(
                Event.type == "clock.resolve_generated",
                Event.parent_event_id == primary_event_id,
            )
            .first()
        )
        assert rider is not None
        assert rider.visibility == "silent"
        assert rider.actor_type == "system"
