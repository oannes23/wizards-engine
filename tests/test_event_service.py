"""Tests for the Event creation service.

Exercises event creation, field defaults, session auto-capture, rider event
session inheritance, target writing, and input validation.  All tests operate
directly against the database (no HTTP layer) via the ``db`` fixture.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from tests.fixtures import seed_data as _seed_data_fn
from wizards_engine.models.event import Event, EventTarget
from wizards_engine.models.session import Session as SessionModel
from wizards_engine.services.event import (
    VALID_ACTOR_TYPES,
    VALID_VISIBILITY_LEVELS,
    create_event,
)


# ===========================================================================
# Helpers
# ===========================================================================


def _active_session(db: Session) -> SessionModel:
    """Create and flush an active session."""
    s = SessionModel(status="active")
    db.add(s)
    db.flush()
    db.refresh(s)
    return s


def _draft_session(db: Session) -> SessionModel:
    """Create and flush a draft session."""
    s = SessionModel(status="draft")
    db.add(s)
    db.flush()
    db.refresh(s)
    return s


# ===========================================================================
# Happy-path creation
# ===========================================================================


class TestCreateEventBasic:
    """Minimal event creation and field persistence."""

    def test_returns_event_instance(self, db: Session) -> None:
        event = create_event(db, type="character.stress_changed", actor_type="gm")
        assert isinstance(event, Event)

    def test_event_gets_ulid(self, db: Session) -> None:
        event = create_event(db, type="character.stress_changed", actor_type="gm")
        assert event.id is not None
        assert len(event.id) == 26

    def test_type_stored(self, db: Session) -> None:
        event = create_event(db, type="character.stress_changed", actor_type="system")
        assert event.type == "character.stress_changed"

    def test_actor_type_stored(self, db: Session) -> None:
        event = create_event(db, type="bond.created", actor_type="player")
        assert event.actor_type == "player"

    def test_actor_id_stored(self, db: Session) -> None:
        seed = _seed_data_fn(db)
        gm = seed["gm"]
        event = create_event(
            db, type="session.ended", actor_type="gm", actor_id=gm.id
        )
        assert event.actor_id == gm.id

    def test_actor_id_defaults_to_none(self, db: Session) -> None:
        event = create_event(db, type="system.probe", actor_type="system")
        assert event.actor_id is None

    def test_visibility_default_is_public(self, db: Session) -> None:
        event = create_event(db, type="character.stress_changed", actor_type="gm")
        assert event.visibility == "public"

    def test_visibility_stored_explicitly(self, db: Session) -> None:
        event = create_event(
            db, type="character.notes_updated", actor_type="gm", visibility="gm_only"
        )
        assert event.visibility == "gm_only"

    def test_changes_defaults_to_empty_dict(self, db: Session) -> None:
        event = create_event(db, type="group.created", actor_type="gm")
        assert event.changes == {}

    def test_changes_stored(self, db: Session) -> None:
        changes = {
            "character.01HX.stress": {
                "op": "meter.delta",
                "before": 2,
                "after": 4,
            }
        }
        event = create_event(
            db, type="character.stress_changed", actor_type="gm", changes=changes
        )
        assert event.changes == changes

    def test_created_objects_stored(self, db: Session) -> None:
        created = [{"type": "character", "id": "01HXABC"}]
        event = create_event(
            db, type="character.created", actor_type="gm", created_objects=created
        )
        assert event.created_objects == created

    def test_deleted_objects_stored(self, db: Session) -> None:
        deleted = [{"type": "character", "id": "01HXABC"}]
        event = create_event(
            db, type="character.deleted", actor_type="gm", deleted_objects=deleted
        )
        assert event.deleted_objects == deleted

    def test_narrative_stored(self, db: Session) -> None:
        event = create_event(
            db,
            type="character.stress_changed",
            actor_type="gm",
            narrative="The character was wounded in combat.",
        )
        assert event.narrative == "The character was wounded in combat."

    def test_narrative_defaults_to_none(self, db: Session) -> None:
        event = create_event(db, type="character.stress_changed", actor_type="gm")
        assert event.narrative is None

    def test_metadata_stored(self, db: Session) -> None:
        meta = {"source": "manual_edit", "tool_version": "1.0"}
        event = create_event(
            db, type="character.stress_changed", actor_type="gm", metadata=meta
        )
        assert event.metadata_ == meta

    def test_metadata_defaults_to_none(self, db: Session) -> None:
        event = create_event(db, type="character.stress_changed", actor_type="gm")
        assert event.metadata_ is None

    def test_created_at_populated(self, db: Session) -> None:
        event = create_event(db, type="character.stress_changed", actor_type="gm")
        assert event.created_at is not None

    def test_proposal_id_defaults_to_none(self, db: Session) -> None:
        """proposal_id is None when not provided."""
        event = create_event(
            db,
            type="character.stress_changed",
            actor_type="gm",
        )
        assert event.proposal_id is None

    def test_parent_event_id_defaults_to_none(self, db: Session) -> None:
        """parent_event_id is None when not provided (non-rider event)."""
        event = create_event(db, type="character.stress_changed", actor_type="gm")
        assert event.parent_event_id is None

    def test_created_objects_defaults_to_none(self, db: Session) -> None:
        """created_objects is None when not provided."""
        event = create_event(db, type="character.stress_changed", actor_type="gm")
        assert event.created_objects is None

    def test_deleted_objects_defaults_to_none(self, db: Session) -> None:
        """deleted_objects is None when not provided."""
        event = create_event(db, type="character.stress_changed", actor_type="gm")
        assert event.deleted_objects is None

    def test_no_session_no_active_session_gives_none(self, db: Session) -> None:
        """When no session is active and none provided, session_id stays None."""
        event = create_event(db, type="character.stress_changed", actor_type="gm")
        assert event.session_id is None


# ===========================================================================
# All visibility levels accepted
# ===========================================================================


class TestVisibilityLevels:
    """All 7 visibility levels are accepted."""

    @pytest.mark.parametrize(
        "level",
        ["silent", "gm_only", "private", "bonded", "familiar", "public", "global"],
    )
    def test_visibility_level_accepted(self, db: Session, level: str) -> None:
        event = create_event(
            db, type="character.stress_changed", actor_type="gm", visibility=level
        )
        assert event.visibility == level


# ===========================================================================
# Validation errors
# ===========================================================================


class TestValidation:
    """Invalid inputs raise ValueError."""

    def test_invalid_actor_type_raises(self, db: Session) -> None:
        with pytest.raises(ValueError, match="actor_type"):
            create_event(db, type="character.stress_changed", actor_type="wizard")

    def test_invalid_visibility_raises(self, db: Session) -> None:
        with pytest.raises(ValueError, match="visibility"):
            create_event(
                db,
                type="character.stress_changed",
                actor_type="gm",
                visibility="invisible",
            )

    @pytest.mark.parametrize("valid_actor", list(VALID_ACTOR_TYPES))
    def test_all_valid_actor_types_accepted(self, db: Session, valid_actor: str) -> None:
        event = create_event(
            db, type="character.stress_changed", actor_type=valid_actor
        )
        assert event.actor_type == valid_actor

    @pytest.mark.parametrize("valid_visibility", list(VALID_VISIBILITY_LEVELS))
    def test_all_valid_visibility_levels_accepted(
        self, db: Session, valid_visibility: str
    ) -> None:
        event = create_event(
            db,
            type="character.stress_changed",
            actor_type="gm",
            visibility=valid_visibility,
        )
        assert event.visibility == valid_visibility


# ===========================================================================
# Session auto-capture
# ===========================================================================


class TestSessionAutoCapture:
    """Session ID is auto-captured from the active session when not provided."""

    def test_auto_captures_active_session(self, db: Session) -> None:
        active = _active_session(db)
        event = create_event(db, type="character.stress_changed", actor_type="gm")
        assert event.session_id == active.id

    def test_explicit_session_id_overrides_auto_capture(self, db: Session) -> None:
        _active_session(db)
        other = _draft_session(db)
        event = create_event(
            db,
            type="character.stress_changed",
            actor_type="gm",
            session_id=other.id,
        )
        assert event.session_id == other.id

    def test_no_active_session_gives_none(self, db: Session) -> None:
        _draft_session(db)  # draft, not active
        event = create_event(db, type="character.stress_changed", actor_type="gm")
        assert event.session_id is None

    def test_ended_session_not_auto_captured(self, db: Session) -> None:
        ended = SessionModel(status="ended")
        db.add(ended)
        db.flush()
        event = create_event(db, type="character.stress_changed", actor_type="gm")
        assert event.session_id is None


# ===========================================================================
# Rider events — session inheritance
# ===========================================================================


class TestRiderEvents:
    """Rider events (parent_event_id set) inherit session_id from parent."""

    def test_rider_inherits_parent_session_id(self, db: Session) -> None:
        active = _active_session(db)
        parent = create_event(
            db, type="character.stress_changed", actor_type="gm"
        )
        assert parent.session_id == active.id

        rider = create_event(
            db,
            type="character.trauma_triggered",
            actor_type="system",
            parent_event_id=parent.id,
        )
        assert rider.session_id == parent.session_id

    def test_rider_explicit_session_id_overrides_inheritance(
        self, db: Session
    ) -> None:
        active = _active_session(db)
        parent = create_event(db, type="character.stress_changed", actor_type="gm")
        other_session = _draft_session(db)

        rider = create_event(
            db,
            type="character.trauma_triggered",
            actor_type="system",
            parent_event_id=parent.id,
            session_id=other_session.id,
        )
        assert rider.session_id == other_session.id

    def test_rider_parent_event_id_stored(self, db: Session) -> None:
        parent = create_event(db, type="character.stress_changed", actor_type="gm")
        rider = create_event(
            db,
            type="character.trauma_triggered",
            actor_type="system",
            parent_event_id=parent.id,
        )
        assert rider.parent_event_id == parent.id

    def test_rider_with_no_session_parent_has_none(self, db: Session) -> None:
        """Rider inherits None when parent also has no session."""
        parent = create_event(db, type="character.stress_changed", actor_type="gm")
        assert parent.session_id is None

        rider = create_event(
            db,
            type="character.trauma_triggered",
            actor_type="system",
            parent_event_id=parent.id,
        )
        assert rider.session_id is None

    def test_rider_with_nonexistent_parent_id_raises_integrity_error(
        self, db: Session
    ) -> None:
        """FK constraint fires when parent_event_id points to a non-existent row."""
        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError):
            create_event(
                db,
                type="character.trauma_triggered",
                actor_type="system",
                parent_event_id="01HXNONEXISTENT1234567",
            )

    def test_parent_event_has_rider_in_rider_events(self, db: Session) -> None:
        """The parent event's rider_events relationship includes the rider after flush."""
        parent = create_event(db, type="character.stress_changed", actor_type="gm")
        rider = create_event(
            db,
            type="character.trauma_triggered",
            actor_type="system",
            parent_event_id=parent.id,
        )
        db.refresh(parent)
        assert rider.id in [r.id for r in parent.rider_events]


# ===========================================================================
# EventTarget rows
# ===========================================================================


class TestEventTargets:
    """EventTarget rows are created correctly."""

    def test_no_targets_creates_empty_relationship(self, db: Session) -> None:
        event = create_event(db, type="character.stress_changed", actor_type="gm")
        assert event.targets == []

    def test_single_target_written(self, db: Session) -> None:
        seed = _seed_data_fn(db)
        pc1 = seed["pc1"]
        targets = [
            {"target_type": "character", "target_id": pc1.id, "is_primary": True}
        ]
        event = create_event(
            db,
            type="character.stress_changed",
            actor_type="gm",
            targets=targets,
        )
        assert len(event.targets) == 1
        t = event.targets[0]
        assert t.target_type == "character"
        assert t.target_id == pc1.id
        assert t.is_primary is True

    def test_multiple_targets_written(self, db: Session) -> None:
        seed = _seed_data_fn(db)
        pc1 = seed["pc1"]
        pc2 = seed["pc2"]
        targets = [
            {"target_type": "character", "target_id": pc1.id, "is_primary": True},
            {"target_type": "character", "target_id": pc2.id, "is_primary": False},
        ]
        event = create_event(
            db,
            type="character.group_action",
            actor_type="gm",
            targets=targets,
        )
        assert len(event.targets) == 2
        target_ids = {t.target_id for t in event.targets}
        assert pc1.id in target_ids
        assert pc2.id in target_ids

    def test_is_primary_defaults_to_false(self, db: Session) -> None:
        seed = _seed_data_fn(db)
        pc1 = seed["pc1"]
        targets = [{"target_type": "character", "target_id": pc1.id}]
        event = create_event(
            db,
            type="character.stress_changed",
            actor_type="gm",
            targets=targets,
        )
        assert event.targets[0].is_primary is False

    def test_target_event_id_matches_event(self, db: Session) -> None:
        seed = _seed_data_fn(db)
        pc1 = seed["pc1"]
        targets = [
            {"target_type": "character", "target_id": pc1.id, "is_primary": True}
        ]
        event = create_event(
            db,
            type="character.stress_changed",
            actor_type="gm",
            targets=targets,
        )
        assert event.targets[0].event_id == event.id

    def test_targets_persisted_to_db(self, db: Session) -> None:
        """EventTarget rows are visible via a direct DB query after flush."""
        seed = _seed_data_fn(db)
        pc1 = seed["pc1"]
        targets = [
            {"target_type": "character", "target_id": pc1.id, "is_primary": True}
        ]
        event = create_event(
            db,
            type="character.stress_changed",
            actor_type="gm",
            targets=targets,
        )
        rows = (
            db.query(EventTarget)
            .filter(EventTarget.event_id == event.id)
            .all()
        )
        assert len(rows) == 1
        assert rows[0].target_id == pc1.id

    def test_mixed_target_types(self, db: Session) -> None:
        seed = _seed_data_fn(db)
        pc1 = seed["pc1"]
        group = seed["group"]
        targets = [
            {"target_type": "character", "target_id": pc1.id, "is_primary": True},
            {"target_type": "group", "target_id": group.id, "is_primary": False},
        ]
        event = create_event(
            db,
            type="character.group_action",
            actor_type="gm",
            targets=targets,
        )
        types = {t.target_type for t in event.targets}
        assert types == {"character", "group"}


# ===========================================================================
# Event persisted in DB
# ===========================================================================


class TestEventPersistence:
    """Events are visible via direct DB queries after flush."""

    def test_event_retrievable_by_id(self, db: Session) -> None:
        event = create_event(db, type="character.stress_changed", actor_type="gm")
        fetched = db.get(Event, event.id)
        assert fetched is not None
        assert fetched.id == event.id

    def test_event_count_increases(self, db: Session) -> None:
        before = db.query(Event).count()
        create_event(db, type="character.stress_changed", actor_type="gm")
        after = db.query(Event).count()
        assert after == before + 1

    def test_multiple_events_independent(self, db: Session) -> None:
        e1 = create_event(db, type="character.stress_changed", actor_type="gm")
        e2 = create_event(db, type="character.stress_changed", actor_type="player")
        assert e1.id != e2.id
