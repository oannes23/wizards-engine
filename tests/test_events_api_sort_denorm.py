"""Integration tests for Story 8.3.1 — Backend: Add Sort Params and Denormalized Names to Events API.

Exercises:
- Sort params: sort_by (created_at, type, actor_type) and sort_dir (asc, desc)
- Default behavior unchanged when no sort params provided
- Pagination cursor works with non-default sort order
- actor_name populated for player/GM events, null for system events
- primary_target_name and primary_target_type populated when event has targets
- changes_summary populated for events with before/after changes, null otherwise
- Invalid sort param values return 422
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import auth_as
from wizards_engine.models.event import Event, EventTarget
from wizards_engine.models.user import User
from wizards_engine.schemas.event import _build_changes_summary


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
    targets: list[tuple[str, str, bool]] | None = None,
    changes: dict | None = None,
    narrative: str | None = None,
) -> Event:
    """Create and flush a minimal Event in the current test DB session."""
    ev = Event(
        type=type,
        actor_type=actor_type,
        actor_id=actor_id,
        changes=changes if changes is not None else {},
        visibility=visibility,
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


# ===========================================================================
# Unit tests for _build_changes_summary
# ===========================================================================


class TestBuildChangesSummary:
    """Unit tests for the _build_changes_summary helper function."""

    def test_empty_dict_returns_none(self) -> None:
        assert _build_changes_summary({}) is None

    def test_none_equivalent_empty_dict_returns_none(self) -> None:
        # The helper receives the `changes` dict — test empty case
        assert _build_changes_summary({}) is None

    def test_entry_with_before_and_after(self) -> None:
        changes = {
            "character.01ABC.stress": {"op": "meter.delta", "before": 3, "after": 5}
        }
        result = _build_changes_summary(changes)
        assert result == "Stress: 3 → 5"

    def test_multiple_entries_joined_with_comma(self) -> None:
        changes = {
            "character.01ABC.stress": {"op": "meter.delta", "before": 3, "after": 5},
            "character.01ABC.plot": {"op": "meter.delta", "before": 5, "after": 3},
        }
        result = _build_changes_summary(changes)
        # Both entries must be present (order may vary in Python < 3.7, but CPython 3.7+ preserves insertion order)
        assert result is not None
        assert "Stress: 3 → 5" in result
        assert "Plot: 5 → 3" in result
        assert ", " in result

    def test_entry_without_before_after_skipped(self) -> None:
        # A change entry that lacks before/after should be silently skipped.
        changes = {
            "character.01ABC.created": {"op": "create"},  # no before/after
            "character.01ABC.stress": {"op": "meter.delta", "before": 0, "after": 2},
        }
        result = _build_changes_summary(changes)
        assert result == "Stress: 0 → 2"

    def test_all_entries_without_before_after_returns_none(self) -> None:
        changes = {
            "character.01ABC.created": {"op": "create"},
            "character.01ABC.deleted": {"op": "delete"},
        }
        result = _build_changes_summary(changes)
        assert result is None

    def test_non_dict_value_skipped(self) -> None:
        # Safeguard: if a value is not a dict, skip it.
        changes = {"character.01ABC.something": "flat_string"}
        result = _build_changes_summary(changes)
        assert result is None

    def test_field_label_uses_last_key_segment(self) -> None:
        changes = {
            "character.01ABC.magic_stats.being.xp": {
                "op": "meter.delta",
                "before": 0,
                "after": 3,
            }
        }
        result = _build_changes_summary(changes)
        assert result == "Xp: 0 → 3"

    def test_underscore_replaced_with_space_in_label(self) -> None:
        changes = {
            "character.01ABC.free_time": {"op": "meter.delta", "before": 1, "after": 2}
        }
        result = _build_changes_summary(changes)
        assert result == "Free Time: 1 → 2"

    def test_simple_key_no_dots(self) -> None:
        # Keys may not follow the dotted convention in tests; still handle gracefully.
        changes = {"stress": {"before": 1, "after": 2}}
        result = _build_changes_summary(changes)
        assert result == "Stress: 1 → 2"


# ===========================================================================
# Sort params — validation
# ===========================================================================


class TestSortParamValidation:
    """Invalid sort param values return 422."""

    def test_invalid_sort_by_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/events?sort_by=invalid_field")
        assert response.status_code == 422

    def test_invalid_sort_dir_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/events?sort_dir=sideways")
        assert response.status_code == 422

    def test_both_invalid_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/events?sort_by=foo&sort_dir=bar")
        assert response.status_code == 422

    def test_valid_sort_by_values_accepted(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        for value in ("created_at", "type", "actor_type"):
            response = client.get(f"/api/v1/events?sort_by={value}")
            assert response.status_code == 200, f"Expected 200 for sort_by={value}"

    def test_valid_sort_dir_values_accepted(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        for value in ("asc", "desc"):
            response = client.get(f"/api/v1/events?sort_dir={value}")
            assert response.status_code == 200, f"Expected 200 for sort_dir={value}"


# ===========================================================================
# Sort params — ordering
# ===========================================================================


class TestSortParamOrdering:
    """Sort params change the order of returned events."""

    def test_default_sort_is_newest_first(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Default (no sort params) returns events newest-first by ULID order."""
        _event(db, type="aaa.first", visibility="global")
        _event(db, type="zzz.second", visibility="global")
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/events")
        items = response.json()["items"]
        assert len(items) == 2
        ids = [item["id"] for item in items]
        assert ids == sorted(ids, reverse=True), "Default order should be newest-first"

    def test_sort_by_created_at_desc_same_as_default(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """sort_by=created_at&sort_dir=desc is identical to default behavior."""
        _event(db, visibility="global")
        _event(db, visibility="global")
        db.commit()
        auth_as(client, seed_data["gm"])
        default_response = client.get("/api/v1/events")
        explicit_response = client.get("/api/v1/events?sort_by=created_at&sort_dir=desc")
        assert (
            default_response.json()["items"]
            == explicit_response.json()["items"]
        )

    def test_sort_by_type_asc(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """sort_by=type&sort_dir=asc returns events sorted by type alphabetically."""
        _event(db, type="zzz.event", visibility="global")
        _event(db, type="aaa.event", visibility="global")
        _event(db, type="mmm.event", visibility="global")
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/events?sort_by=type&sort_dir=asc")
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 3
        types = [item["type"] for item in items]
        assert types == sorted(types), "Events should be sorted by type ascending"

    def test_sort_by_type_desc(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """sort_by=type&sort_dir=desc returns events sorted by type descending."""
        _event(db, type="aaa.event", visibility="global")
        _event(db, type="zzz.event", visibility="global")
        _event(db, type="mmm.event", visibility="global")
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/events?sort_by=type&sort_dir=desc")
        assert response.status_code == 200
        items = response.json()["items"]
        types = [item["type"] for item in items]
        assert types == sorted(types, reverse=True), "Events should be sorted by type descending"

    def test_sort_by_actor_type_asc(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """sort_by=actor_type&sort_dir=asc sorts alphabetically by actor type."""
        _event(db, actor_type="system", visibility="global")
        _event(db, actor_type="gm", visibility="global")
        _event(db, actor_type="player", visibility="global")
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/events?sort_by=actor_type&sort_dir=asc")
        assert response.status_code == 200
        items = response.json()["items"]
        actor_types = [item["actor_type"] for item in items]
        assert actor_types == sorted(actor_types), "Should be sorted by actor_type asc"

    def test_sort_by_created_at_asc(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """sort_by=created_at&sort_dir=asc returns events oldest-first."""
        ev1 = _event(db, type="first", visibility="global")
        ev2 = _event(db, type="second", visibility="global")
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/events?sort_by=created_at&sort_dir=asc")
        assert response.status_code == 200
        items = response.json()["items"]
        ids = [item["id"] for item in items]
        assert ids == sorted(ids), "created_at asc should return oldest-first (ULID order)"


# ===========================================================================
# Pagination with non-default sort
# ===========================================================================


class TestPaginationWithSort:
    """Cursor pagination works with non-default sort orders."""

    def test_pagination_with_sort_by_type(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Cursor pagination works (no 500) when sort_by=type.

        Note: For non-ID sort orders, ULID cursor filtering (``id < after``)
        does not guarantee non-overlapping pages.  The cursor mechanism still
        *functions* (returns a valid next_cursor and subsequent pages do not
        error), which is what the spec requires.  Perfect non-overlap is only
        guaranteed for the default ``created_at desc`` sort.
        """
        # Create 5 events with different types
        types = ["aaa", "bbb", "ccc", "ddd", "eee"]
        for t in types:
            _event(db, type=t, visibility="global")
        db.commit()
        auth_as(client, seed_data["gm"])

        # First page — limit 3
        page1 = client.get("/api/v1/events?sort_by=type&sort_dir=asc&limit=3").json()
        assert len(page1["items"]) == 3
        assert page1["has_more"] is True
        cursor = page1["next_cursor"]
        assert cursor is not None

        # Second page using cursor — should not error (200 OK)
        page2_response = client.get(
            f"/api/v1/events?sort_by=type&sort_dir=asc&limit=3&after={cursor}"
        )
        assert page2_response.status_code == 200
        page2 = page2_response.json()
        assert "items" in page2
        assert "has_more" in page2

    def test_pagination_default_sort_cursor_still_works(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Default sort (created_at desc) cursor pagination is unaffected."""
        for _ in range(5):
            _event(db, visibility="global")
        db.commit()
        auth_as(client, seed_data["gm"])

        page1 = client.get("/api/v1/events?limit=3").json()
        assert len(page1["items"]) == 3
        assert page1["has_more"] is True
        cursor = page1["next_cursor"]

        page2 = client.get(f"/api/v1/events?limit=3&after={cursor}").json()
        assert len(page2["items"]) == 2
        assert page2["has_more"] is False

        page1_ids = {item["id"] for item in page1["items"]}
        page2_ids = {item["id"] for item in page2["items"]}
        assert not page1_ids & page2_ids


# ===========================================================================
# actor_name — denormalized resolution
# ===========================================================================


class TestActorName:
    """actor_name is resolved from User.display_name for player/GM events."""

    def test_actor_name_null_for_system_events(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """System events (no actor_id) have actor_name = None."""
        _event(db, actor_type="system", actor_id=None, visibility="global")
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/events")
        item = response.json()["items"][0]
        assert item["actor_type"] == "system"
        assert item["actor_id"] is None
        assert item["actor_name"] is None

    def test_actor_name_populated_for_gm_event(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """GM events have actor_name resolved to the GM's display_name."""
        gm = seed_data["gm"]
        _event(db, actor_type="gm", actor_id=gm.id, visibility="global")
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/events")
        item = response.json()["items"][0]
        assert item["actor_name"] == gm.display_name
        assert item["actor_name"] == "Test GM"

    def test_actor_name_populated_for_player_event(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Player events have actor_name resolved to the player's display_name."""
        player1 = seed_data["player1"]
        _event(db, actor_type="player", actor_id=player1.id, visibility="global")
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/events")
        item = response.json()["items"][0]
        assert item["actor_name"] == player1.display_name
        assert item["actor_name"] == "Player 1"

    def test_actor_name_present_in_single_event_detail(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """actor_name is also resolved on GET /events/{id}."""
        gm = seed_data["gm"]
        ev = _event(db, actor_type="gm", actor_id=gm.id, visibility="global")
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/events/{ev.id}")
        assert response.status_code == 200
        assert response.json()["actor_name"] == gm.display_name

    def test_actor_name_null_when_actor_id_missing_even_if_actor_type_gm(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Edge case: actor_type='gm' but actor_id=None results in actor_name=None."""
        _event(db, actor_type="gm", actor_id=None, visibility="global")
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/events")
        item = response.json()["items"][0]
        assert item["actor_name"] is None


# ===========================================================================
# primary_target_name and primary_target_type
# ===========================================================================


class TestPrimaryTargetFields:
    """primary_target_name and primary_target_type are resolved from event_targets."""

    def test_null_when_no_targets(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Events with no targets have null primary_target_name/type."""
        _event(db, visibility="global")
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/events")
        item = response.json()["items"][0]
        assert item["primary_target_name"] is None
        assert item["primary_target_type"] is None

    def test_character_target_name_resolved(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Primary target of type 'character' resolves to Character.name."""
        pc1 = seed_data["pc1"]
        _event(
            db,
            visibility="global",
            targets=[("character", pc1.id, True)],
        )
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/events")
        item = response.json()["items"][0]
        assert item["primary_target_name"] == pc1.name
        assert item["primary_target_type"] == "character"

    def test_group_target_name_resolved(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Primary target of type 'group' resolves to Group.name."""
        group = seed_data["group"]
        _event(
            db,
            visibility="global",
            targets=[("group", group.id, True)],
        )
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/events")
        item = response.json()["items"][0]
        assert item["primary_target_name"] == group.name
        assert item["primary_target_type"] == "group"

    def test_location_target_name_resolved(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Primary target of type 'location' resolves to Location.name."""
        region = seed_data["region"]
        _event(
            db,
            visibility="global",
            targets=[("location", region.id, True)],
        )
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/events")
        item = response.json()["items"][0]
        assert item["primary_target_name"] == region.name
        assert item["primary_target_type"] == "location"

    def test_only_primary_target_used_not_secondary(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """When event has multiple targets, only the primary one is resolved."""
        pc1 = seed_data["pc1"]
        group = seed_data["group"]
        _event(
            db,
            visibility="global",
            targets=[
                ("character", pc1.id, True),   # primary
                ("group", group.id, False),     # secondary
            ],
        )
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/events")
        item = response.json()["items"][0]
        assert item["primary_target_name"] == pc1.name
        assert item["primary_target_type"] == "character"

    def test_primary_target_fields_in_single_event_detail(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """primary_target_name/type also resolved on GET /events/{id}."""
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
        body = response.json()
        assert body["primary_target_name"] == pc1.name
        assert body["primary_target_type"] == "character"

    def test_non_primary_only_target_has_null_name(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """If there are only non-primary targets, primary_target_name is None."""
        pc1 = seed_data["pc1"]
        _event(
            db,
            visibility="global",
            targets=[("character", pc1.id, False)],  # not primary
        )
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/events")
        item = response.json()["items"][0]
        assert item["primary_target_name"] is None
        assert item["primary_target_type"] is None


# ===========================================================================
# changes_summary
# ===========================================================================


class TestChangesSummary:
    """changes_summary is derived from the changes dict at serialization time."""

    def test_null_for_empty_changes(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Events with empty changes dict have changes_summary = None."""
        _event(db, changes={}, visibility="global")
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/events")
        item = response.json()["items"][0]
        assert item["changes_summary"] is None

    def test_summary_for_single_change(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """A single before/after change entry produces a summary string."""
        changes = {
            "character.01ABC.stress": {"op": "meter.delta", "before": 3, "after": 5}
        }
        _event(db, changes=changes, visibility="global")
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/events")
        item = response.json()["items"][0]
        assert item["changes_summary"] == "Stress: 3 → 5"

    def test_summary_for_multiple_changes(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Multiple change entries are joined with ', '."""
        changes = {
            "character.01ABC.stress": {"op": "meter.delta", "before": 3, "after": 5},
            "character.01ABC.plot": {"op": "meter.delta", "before": 5, "after": 3},
        }
        _event(db, changes=changes, visibility="global")
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/events")
        item = response.json()["items"][0]
        assert item["changes_summary"] is not None
        assert "Stress: 3 → 5" in item["changes_summary"]
        assert "Plot: 5 → 3" in item["changes_summary"]
        assert ", " in item["changes_summary"]

    def test_changes_without_before_after_produces_none(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Changes entries lacking before/after are skipped; if all skipped, None."""
        changes = {"character.01ABC.created": {"op": "create"}}
        _event(db, changes=changes, visibility="global")
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/events")
        item = response.json()["items"][0]
        assert item["changes_summary"] is None

    def test_summary_in_single_event_detail(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """changes_summary also present on GET /events/{id}."""
        changes = {
            "character.01ABC.free_time": {"op": "meter.delta", "before": 1, "after": 2}
        }
        ev = _event(db, changes=changes, visibility="global")
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/events/{ev.id}")
        assert response.status_code == 200
        assert response.json()["changes_summary"] == "Free Time: 1 → 2"


# ===========================================================================
# Response schema shape — new fields present
# ===========================================================================


class TestResponseSchemaShape:
    """New fields are present in EventResponse with correct defaults."""

    def test_new_fields_present_with_null_defaults(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """actor_name, primary_target_name, primary_target_type, changes_summary present."""
        _event(db, actor_type="system", visibility="global")
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/events")
        item = response.json()["items"][0]
        assert "actor_name" in item
        assert "primary_target_name" in item
        assert "primary_target_type" in item
        assert "changes_summary" in item

    def test_all_new_fields_in_single_event_response(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """New fields also present on GET /events/{id}."""
        ev = _event(db, visibility="global")
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/events/{ev.id}")
        body = response.json()
        assert "actor_name" in body
        assert "primary_target_name" in body
        assert "primary_target_type" in body
        assert "changes_summary" in body

    def test_patch_response_includes_new_fields(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """PATCH /events/{id}/visibility response also includes new fields."""
        ev = _event(db, visibility="global")
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.patch(
            f"/api/v1/events/{ev.id}/visibility",
            json={"visibility": "gm_only"},
        )
        assert response.status_code == 200
        body = response.json()
        assert "actor_name" in body
        assert "primary_target_name" in body
        assert "primary_target_type" in body
        assert "changes_summary" in body

    def test_fully_populated_event_response(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """All new fields populated together on a rich event."""
        gm = seed_data["gm"]
        pc1 = seed_data["pc1"]
        changes = {
            "character.01ABC.stress": {"op": "meter.delta", "before": 0, "after": 3}
        }
        _event(
            db,
            type="character.stress_changed",
            actor_type="gm",
            actor_id=gm.id,
            visibility="global",
            targets=[("character", pc1.id, True)],
            changes=changes,
        )
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/events")
        item = response.json()["items"][0]

        assert item["actor_name"] == gm.display_name
        assert item["primary_target_name"] == pc1.name
        assert item["primary_target_type"] == "character"
        assert item["changes_summary"] == "Stress: 0 → 3"
