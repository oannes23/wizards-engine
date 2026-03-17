"""Tests for Story 5.1.2 — Late Joins.

Covers all acceptance criteria for the late-join distribution path of
POST /api/v1/sessions/{id}/participants when the session is ``active``.

Scenarios tested:
- Happy path: adding participant to active session distributes FT + Plot
- FT formula correct (time_now - last_session_time_now, capped at 20)
- Plot +1 default, +2 with additional_contribution
- Distribution only for the late joiner, not existing participants
- Event created with correct type, visibility, changes, targets
- Adding participant to draft session does NOT distribute (existing behaviour)
- character.last_session_time_now updated on the character after late join
- GM and player can both trigger late-join distribution (actor_type differs)
- FT capped at 20 (clamped flag in event changes)
- Plot can exceed 5 (overflow allowed)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as DBSession

from tests.conftest import auth_as
from wizards_engine.models.character import Character
from wizards_engine.models.event import Event, EventTarget
from wizards_engine.models.session import Session as SessionModel, SessionParticipant


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(
    db: DBSession,
    status: str = "draft",
    time_now: int | None = None,
) -> SessionModel:
    """Insert a Session row directly with the given status and time_now."""
    session = SessionModel(status=status, time_now=time_now)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def _add_participant_directly(
    db: DBSession,
    session: SessionModel,
    character: Character,
    additional_contribution: bool = False,
) -> SessionParticipant:
    """Register a character as a participant (bypassing the API — no distribution)."""
    p = SessionParticipant(
        session_id=session.id,
        character_id=character.id,
        additional_contribution=additional_contribution,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _get_events_for_session(db: DBSession, session_id: str) -> list[Event]:
    """Return all events tagged with *session_id*, ordered by creation."""
    return (
        db.query(Event)
        .filter(Event.session_id == session_id)
        .order_by(Event.id)
        .all()
    )


def _get_participant_added_events(db: DBSession, session_id: str) -> list[Event]:
    """Return only ``session.participant_added`` events for *session_id*."""
    return (
        db.query(Event)
        .filter(
            Event.session_id == session_id,
            Event.type == "session.participant_added",
        )
        .order_by(Event.id)
        .all()
    )


# ---------------------------------------------------------------------------
# Happy path — adding to an active session
# ---------------------------------------------------------------------------


class TestLateJoinHappyPath:
    def test_add_to_active_session_returns_201(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """POST /participants on an active session returns 201 with the participant."""
        session = _make_session(db, status="active", time_now=10)
        pc = seed_data["pc1"]

        auth_as(client, seed_data["gm"])
        response = client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": pc.id},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["character_id"] == pc.id
        assert body["session_id"] == session.id

    def test_ft_distributed_on_late_join(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """FT gain = time_now - last_session_time_now is applied to the character."""
        pc = seed_data["pc1"]
        # pc1.free_time = 0, pc1.last_session_time_now = 0
        session = _make_session(db, status="active", time_now=8)

        auth_as(client, seed_data["gm"])
        client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": pc.id},
        )

        db.refresh(pc)
        # ft_gained = 8 - 0 = 8; free_time = 0 + 8 = 8
        assert pc.free_time == 8

    def test_last_session_time_now_updated_on_late_join(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """character.last_session_time_now is updated to session.time_now."""
        pc = seed_data["pc1"]
        session = _make_session(db, status="active", time_now=15)

        auth_as(client, seed_data["gm"])
        client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": pc.id},
        )

        db.refresh(pc)
        assert pc.last_session_time_now == 15

    def test_plot_plus_one_by_default_on_late_join(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Plot +1 when additional_contribution is not set."""
        pc = seed_data["pc1"]
        session = _make_session(db, status="active", time_now=5)

        auth_as(client, seed_data["gm"])
        client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": pc.id, "additional_contribution": False},
        )

        db.refresh(pc)
        assert pc.plot == 1

    def test_plot_plus_two_with_additional_contribution(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Plot +2 when additional_contribution=True."""
        pc = seed_data["pc1"]
        session = _make_session(db, status="active", time_now=5)

        auth_as(client, seed_data["gm"])
        client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": pc.id, "additional_contribution": True},
        )

        db.refresh(pc)
        assert pc.plot == 2

    def test_ft_capped_at_twenty_on_late_join(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """FT is capped at 20 when the delta would push it over."""
        pc = seed_data["pc1"]
        pc.free_time = 18
        pc.last_session_time_now = 0
        db.commit()

        # time_now=5 → ft_gained=5 → 18+5=23 → clamped to 20
        session = _make_session(db, status="active", time_now=5)

        auth_as(client, seed_data["gm"])
        client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": pc.id},
        )

        db.refresh(pc)
        assert pc.free_time == 20

    def test_plot_can_exceed_five_on_late_join(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Plot overflow allowed — can exceed 5 on late join."""
        pc = seed_data["pc1"]
        pc.plot = 5
        db.commit()

        session = _make_session(db, status="active", time_now=3)

        auth_as(client, seed_data["gm"])
        client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": pc.id, "additional_contribution": True},
        )

        db.refresh(pc)
        # 5 + 2 = 7 (overflow allowed)
        assert pc.plot == 7

    def test_ft_formula_uses_actual_last_session_time_now(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """FT uses the character's last_session_time_now, not always 0."""
        pc = seed_data["pc1"]
        pc.last_session_time_now = 6
        pc.free_time = 2
        db.commit()

        # time_now=10, last=6 → ft_gained=4 → 2+4=6
        session = _make_session(db, status="active", time_now=10)

        auth_as(client, seed_data["gm"])
        client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": pc.id},
        )

        db.refresh(pc)
        assert pc.free_time == 6
        assert pc.last_session_time_now == 10


# ---------------------------------------------------------------------------
# Distribution only for the late joiner
# ---------------------------------------------------------------------------


class TestLateJoinOnlyForNewParticipant:
    def test_existing_participants_not_redistributed(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Adding a late joiner does not re-distribute resources to existing participants."""
        pc1 = seed_data["pc1"]
        pc2 = seed_data["pc2"]

        session = _make_session(db, status="active", time_now=10)
        # Register pc1 directly (bypassing API) — simulates already having received distribution
        _add_participant_directly(db, session, pc1)
        # Give pc1 a known state
        pc1.free_time = 7
        pc1.plot = 3
        pc1.last_session_time_now = 10  # already up to date
        db.commit()

        # Now add pc2 as a late joiner via the API
        auth_as(client, seed_data["gm"])
        client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": pc2.id},
        )

        db.refresh(pc1)
        db.refresh(pc2)

        # pc1 should be unchanged
        assert pc1.free_time == 7
        assert pc1.plot == 3
        assert pc1.last_session_time_now == 10

        # pc2 should have received distribution
        assert pc2.free_time == 10  # 0 + (10 - 0)
        assert pc2.plot == 1
        assert pc2.last_session_time_now == 10


# ---------------------------------------------------------------------------
# Event created correctly
# ---------------------------------------------------------------------------


class TestLateJoinEvent:
    def test_participant_added_event_created(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """One session.participant_added event is created for the late join."""
        pc = seed_data["pc1"]
        session = _make_session(db, status="active", time_now=5)

        auth_as(client, seed_data["gm"])
        client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": pc.id},
        )

        events = _get_participant_added_events(db, session.id)
        assert len(events) == 1

    def test_event_type_is_participant_added(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """The created event has type session.participant_added."""
        pc = seed_data["pc1"]
        session = _make_session(db, status="active", time_now=5)

        auth_as(client, seed_data["gm"])
        client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": pc.id},
        )

        events = _get_participant_added_events(db, session.id)
        assert events[0].type == "session.participant_added"

    def test_event_visibility_is_global(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Late-join event has visibility='global'."""
        pc = seed_data["pc1"]
        session = _make_session(db, status="active", time_now=5)

        auth_as(client, seed_data["gm"])
        client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": pc.id},
        )

        events = _get_participant_added_events(db, session.id)
        assert events[0].visibility == "global"

    def test_event_tagged_with_session_id(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Late-join event has session_id set to the active session's ID."""
        pc = seed_data["pc1"]
        session = _make_session(db, status="active", time_now=5)

        auth_as(client, seed_data["gm"])
        client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": pc.id},
        )

        events = _get_participant_added_events(db, session.id)
        assert events[0].session_id == session.id

    def test_event_actor_type_gm_when_gm_adds(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """actor_type is 'gm' when the GM adds the participant."""
        pc = seed_data["pc1"]
        session = _make_session(db, status="active", time_now=5)

        auth_as(client, seed_data["gm"])
        client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": pc.id},
        )

        events = _get_participant_added_events(db, session.id)
        assert events[0].actor_type == "gm"
        assert events[0].actor_id == seed_data["gm"].id

    def test_event_actor_type_player_when_player_self_registers(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """actor_type is 'player' when the player adds themselves."""
        pc = seed_data["pc1"]
        session = _make_session(db, status="active", time_now=5)

        auth_as(client, seed_data["player1"])
        client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": pc.id},
        )

        events = _get_participant_added_events(db, session.id)
        assert events[0].actor_type == "player"
        assert events[0].actor_id == seed_data["player1"].id

    def test_event_changes_contain_ft_delta(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Event changes include character.free_time with op=meter.delta."""
        pc = seed_data["pc1"]
        session = _make_session(db, status="active", time_now=10)

        auth_as(client, seed_data["gm"])
        client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": pc.id},
        )

        events = _get_participant_added_events(db, session.id)
        ev = events[0]
        ft_key = f"character.{pc.id}.free_time"
        assert ft_key in ev.changes
        assert ev.changes[ft_key]["op"] == "meter.delta"
        assert ev.changes[ft_key]["before"] == 0
        assert ev.changes[ft_key]["after"] == 10

    def test_event_changes_contain_last_session_time_now(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Event changes include character.last_session_time_now with op=field.set."""
        pc = seed_data["pc1"]
        session = _make_session(db, status="active", time_now=10)

        auth_as(client, seed_data["gm"])
        client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": pc.id},
        )

        events = _get_participant_added_events(db, session.id)
        ev = events[0]
        time_key = f"character.{pc.id}.last_session_time_now"
        assert time_key in ev.changes
        assert ev.changes[time_key]["op"] == "field.set"
        assert ev.changes[time_key]["before"] == 0
        assert ev.changes[time_key]["after"] == 10

    def test_event_changes_contain_plot_delta(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Event changes include character.plot with op=meter.delta."""
        pc = seed_data["pc1"]
        session = _make_session(db, status="active", time_now=5)

        auth_as(client, seed_data["gm"])
        client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": pc.id},
        )

        events = _get_participant_added_events(db, session.id)
        ev = events[0]
        plot_key = f"character.{pc.id}.plot"
        assert plot_key in ev.changes
        assert ev.changes[plot_key]["op"] == "meter.delta"
        assert ev.changes[plot_key]["before"] == 0
        assert ev.changes[plot_key]["after"] == 1

    def test_event_clamped_flag_set_when_ft_hits_cap(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """clamped=True is present in changes when FT hits the 20 cap."""
        pc = seed_data["pc1"]
        pc.free_time = 18
        pc.last_session_time_now = 0
        db.commit()

        session = _make_session(db, status="active", time_now=5)

        auth_as(client, seed_data["gm"])
        client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": pc.id},
        )

        events = _get_participant_added_events(db, session.id)
        ev = events[0]
        ft_key = f"character.{pc.id}.free_time"
        assert ev.changes[ft_key].get("clamped") is True
        assert ev.changes[ft_key]["after"] == 20

    def test_event_no_clamped_flag_when_ft_does_not_hit_cap(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """clamped key absent in changes when FT does not hit the cap."""
        pc = seed_data["pc1"]
        session = _make_session(db, status="active", time_now=5)

        auth_as(client, seed_data["gm"])
        client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": pc.id},
        )

        events = _get_participant_added_events(db, session.id)
        ft_key = f"character.{pc.id}.free_time"
        assert "clamped" not in events[0].changes[ft_key]

    def test_event_has_character_as_primary_target(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """The character is listed as the primary target on the event."""
        pc = seed_data["pc1"]
        session = _make_session(db, status="active", time_now=5)

        auth_as(client, seed_data["gm"])
        client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": pc.id},
        )

        events = _get_participant_added_events(db, session.id)
        ev = events[0]
        db.refresh(ev)
        targets = ev.targets
        assert len(targets) == 1
        assert targets[0].target_type == "character"
        assert targets[0].target_id == pc.id
        assert targets[0].is_primary is True


# ---------------------------------------------------------------------------
# Draft session — no distribution
# ---------------------------------------------------------------------------


class TestDraftSessionNoDistribution:
    def test_add_to_draft_session_does_not_distribute_ft(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Adding a participant to a draft session does not distribute FT."""
        pc = seed_data["pc1"]
        session = _make_session(db, status="draft", time_now=10)

        auth_as(client, seed_data["gm"])
        response = client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": pc.id},
        )

        assert response.status_code == 201
        db.refresh(pc)
        # FT should remain 0 — no distribution on draft
        assert pc.free_time == 0
        assert pc.plot == 0
        assert pc.last_session_time_now == 0

    def test_add_to_draft_session_creates_no_participant_added_event(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Adding to a draft session creates no session.participant_added event."""
        pc = seed_data["pc1"]
        session = _make_session(db, status="draft", time_now=10)

        auth_as(client, seed_data["gm"])
        client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": pc.id},
        )

        events = _get_participant_added_events(db, session.id)
        assert events == []


# ---------------------------------------------------------------------------
# Contribution flag locked after late join
# ---------------------------------------------------------------------------


class TestLateJoinContributionFlagLocked:
    def test_patch_contribution_rejected_after_late_join(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """PATCH on contribution flag returns 400 after late join (session is active)."""
        pc = seed_data["pc1"]
        session = _make_session(db, status="active", time_now=5)

        auth_as(client, seed_data["gm"])
        # Add participant (triggers distribution)
        add_resp = client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": pc.id},
        )
        assert add_resp.status_code == 201

        # Attempt to PATCH contribution flag — must fail since session is active
        patch_resp = client.patch(
            f"/api/v1/sessions/{session.id}/participants/{pc.id}",
            json={"additional_contribution": True},
        )
        assert patch_resp.status_code == 400
        assert patch_resp.json()["error"]["code"] == "session_not_draft"
