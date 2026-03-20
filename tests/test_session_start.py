"""Tests for Story 5.1.1 — Session Start.

Covers all acceptance criteria for POST /api/v1/sessions/{id}/start.

Scenarios tested:
- Happy path: draft session with participants starts correctly
- FT distributed correctly (time_now delta formula)
- FT capped at 20 (clamped flag present in event changes)
- Plot overflow allowed (can exceed 5)
- Additional contribution gives +2 Plot instead of +1
- Session with no participants starts cleanly
- 3 events created with correct types, visibility, session_id
- character.last_session_time_now updated correctly
- 400 if session not in draft status (active or ended)
- 409 if another session is already active
- 400 if time_now is not set
- 404 if session does not exist
- 403 if non-GM tries to start
- 401 if unauthenticated
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as DBSession

from tests.conftest import auth_as
from wizards_engine.models.character import Character
from wizards_engine.models.event import Event
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


def _add_participant(
    db: DBSession,
    session: SessionModel,
    character: Character,
    additional_contribution: bool = False,
) -> SessionParticipant:
    """Register a character as a participant in *session*."""
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


# ---------------------------------------------------------------------------
# POST /api/v1/sessions/{id}/start — happy path
# ---------------------------------------------------------------------------


class TestSessionStartHappyPath:
    def test_start_session_returns_200_with_active_status(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Starting a draft session returns 200 with status='active'."""
        session = _make_session(db, status="draft", time_now=10)

        auth_as(client, seed_data["gm"])
        response = client.post(f"/api/v1/sessions/{session.id}/start")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "active"
        assert body["id"] == session.id

    def test_start_session_with_no_participants(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Session with no participants starts cleanly; no FT/Plot changes."""
        session = _make_session(db, status="draft", time_now=5)

        auth_as(client, seed_data["gm"])
        response = client.post(f"/api/v1/sessions/{session.id}/start")

        assert response.status_code == 200
        assert response.json()["status"] == "active"

    def test_ft_distributed_to_participant(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """FT gain = time_now - last_session_time_now, added to free_time."""
        pc = seed_data["pc1"]
        # pc1.free_time = 0, pc1.last_session_time_now = 0 (from seed)
        session = _make_session(db, status="draft", time_now=10)
        _add_participant(db, session, pc)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/start")

        db.refresh(pc)
        # ft_gained = 10 - 0 = 10; free_time = 0 + 10 = 10
        assert pc.free_time == 10

    def test_last_session_time_now_updated(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """character.last_session_time_now is updated to session.time_now."""
        pc = seed_data["pc1"]
        session = _make_session(db, status="draft", time_now=15)
        _add_participant(db, session, pc)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/start")

        db.refresh(pc)
        assert pc.last_session_time_now == 15

    def test_plot_distributed_plus_one_by_default(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Participant without additional_contribution receives +1 Plot."""
        pc = seed_data["pc1"]
        # pc1.plot = 0 from seed
        session = _make_session(db, status="draft", time_now=5)
        _add_participant(db, session, pc, additional_contribution=False)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/start")

        db.refresh(pc)
        assert pc.plot == 1

    def test_additional_contribution_gives_plus_two_plot(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Participant with additional_contribution=True receives +2 Plot."""
        pc = seed_data["pc1"]
        session = _make_session(db, status="draft", time_now=5)
        _add_participant(db, session, pc, additional_contribution=True)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/start")

        db.refresh(pc)
        assert pc.plot == 2

    def test_plot_can_exceed_five(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Plot overflow is allowed — can exceed 5 on session start."""
        pc = seed_data["pc1"]
        # Set plot to 5 directly.
        pc.plot = 5
        db.commit()

        session = _make_session(db, status="draft", time_now=5)
        _add_participant(db, session, pc, additional_contribution=True)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/start")

        db.refresh(pc)
        # 5 + 2 = 7 (overflow allowed)
        assert pc.plot == 7

    def test_ft_capped_at_twenty(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """FT is capped at 20 when the delta would push it over."""
        pc = seed_data["pc1"]
        # free_time = 15, last_session_time_now = 0
        pc.free_time = 15
        db.commit()

        # time_now=10 → ft_gained=10 → new_ft=25 → clamped to 20
        session = _make_session(db, status="draft", time_now=10)
        _add_participant(db, session, pc)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/start")

        db.refresh(pc)
        assert pc.free_time == 20

    def test_multiple_participants_all_receive_distribution(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """All registered participants receive FT and Plot on session start."""
        pc1 = seed_data["pc1"]
        pc2 = seed_data["pc2"]
        session = _make_session(db, status="draft", time_now=8)
        _add_participant(db, session, pc1)
        _add_participant(db, session, pc2)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/start")

        db.refresh(pc1)
        db.refresh(pc2)
        # Both start at free_time=0, last_session_time_now=0 → gain 8 FT each
        assert pc1.free_time == 8
        assert pc2.free_time == 8
        assert pc1.plot == 1
        assert pc2.plot == 1


# ---------------------------------------------------------------------------
# Events created correctly
# ---------------------------------------------------------------------------


class TestSessionStartEvents:
    def test_three_events_created(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Session start creates exactly 3 events."""
        session = _make_session(db, status="draft", time_now=5)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/start")

        events = _get_events_for_session(db, session.id)
        assert len(events) == 3

    def test_event_types_are_correct(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """The 3 events have the correct types: started, ft_distributed, plot_distributed."""
        session = _make_session(db, status="draft", time_now=5)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/start")

        events = _get_events_for_session(db, session.id)
        event_types = {e.type for e in events}
        assert "session.started" in event_types
        assert "session.ft_distributed" in event_types
        assert "session.plot_distributed" in event_types

    def test_session_started_event_is_global(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """session.started event has visibility='global'."""
        session = _make_session(db, status="draft", time_now=5)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/start")

        events = _get_events_for_session(db, session.id)
        started = next(e for e in events if e.type == "session.started")
        assert started.visibility == "global"

    def test_ft_and_plot_events_are_silent(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """session.ft_distributed and session.plot_distributed are silent."""
        session = _make_session(db, status="draft", time_now=5)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/start")

        events = _get_events_for_session(db, session.id)
        ft_event = next(e for e in events if e.type == "session.ft_distributed")
        plot_event = next(e for e in events if e.type == "session.plot_distributed")
        assert ft_event.visibility == "silent"
        assert plot_event.visibility == "silent"

    def test_all_events_have_system_actor_type(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """All 3 events have actor_type='system' and actor_id=None."""
        session = _make_session(db, status="draft", time_now=5)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/start")

        events = _get_events_for_session(db, session.id)
        for event in events:
            assert event.actor_type == "system"
            assert event.actor_id is None

    def test_all_events_tagged_with_session_id(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """All 3 events have session_id set to the started session's ID."""
        session = _make_session(db, status="draft", time_now=5)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/start")

        events = _get_events_for_session(db, session.id)
        assert len(events) == 3
        for event in events:
            assert event.session_id == session.id

    def test_started_event_changes_contain_status_transition(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """session.started event changes record draft→active status transition."""
        session = _make_session(db, status="draft", time_now=5)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/start")

        events = _get_events_for_session(db, session.id)
        started = next(e for e in events if e.type == "session.started")
        key = f"session.{session.id}.status"
        assert key in started.changes
        assert started.changes[key]["op"] == "field.set"
        assert started.changes[key]["before"] == "draft"
        assert started.changes[key]["after"] == "active"

    def test_ft_event_changes_contain_character_ft_and_last_time(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """session.ft_distributed event captures free_time and last_session_time_now changes."""
        pc = seed_data["pc1"]
        session = _make_session(db, status="draft", time_now=10)
        _add_participant(db, session, pc)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/start")

        events = _get_events_for_session(db, session.id)
        ft_event = next(e for e in events if e.type == "session.ft_distributed")

        ft_key = f"character.{pc.id}.free_time"
        time_key = f"character.{pc.id}.last_session_time_now"
        assert ft_key in ft_event.changes
        assert time_key in ft_event.changes

        assert ft_event.changes[ft_key]["op"] == "meter.delta"
        assert ft_event.changes[ft_key]["before"] == 0
        assert ft_event.changes[ft_key]["after"] == 10

        assert ft_event.changes[time_key]["op"] == "field.set"
        assert ft_event.changes[time_key]["before"] == 0
        assert ft_event.changes[time_key]["after"] == 10

    def test_ft_event_clamped_flag_set_when_hitting_cap(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """clamped=True is present in ft_event changes when FT hits the 20 cap."""
        pc = seed_data["pc1"]
        pc.free_time = 15
        db.commit()

        session = _make_session(db, status="draft", time_now=10)
        _add_participant(db, session, pc)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/start")

        events = _get_events_for_session(db, session.id)
        ft_event = next(e for e in events if e.type == "session.ft_distributed")

        ft_key = f"character.{pc.id}.free_time"
        assert ft_event.changes[ft_key].get("clamped") is True
        assert ft_event.changes[ft_key]["after"] == 20

    def test_ft_event_no_clamped_flag_when_not_hitting_cap(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """clamped key is absent in ft_event changes when FT does not hit the cap."""
        pc = seed_data["pc1"]
        session = _make_session(db, status="draft", time_now=5)
        _add_participant(db, session, pc)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/start")

        events = _get_events_for_session(db, session.id)
        ft_event = next(e for e in events if e.type == "session.ft_distributed")

        ft_key = f"character.{pc.id}.free_time"
        assert "clamped" not in ft_event.changes[ft_key]

    def test_plot_event_changes_contain_character_plot(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """session.plot_distributed event captures plot delta for each participant."""
        pc = seed_data["pc1"]
        session = _make_session(db, status="draft", time_now=5)
        _add_participant(db, session, pc)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/start")

        events = _get_events_for_session(db, session.id)
        plot_event = next(e for e in events if e.type == "session.plot_distributed")

        key = f"character.{pc.id}.plot"
        assert key in plot_event.changes
        assert plot_event.changes[key]["op"] == "meter.delta"
        assert plot_event.changes[key]["before"] == 0
        assert plot_event.changes[key]["after"] == 1

    def test_started_event_has_narrative(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """session.started event has a non-empty narrative."""
        session = _make_session(db, status="draft", time_now=5)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/start")

        events = _get_events_for_session(db, session.id)
        started = next(e for e in events if e.type == "session.started")
        assert started.narrative is not None
        assert len(started.narrative) > 0


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestSessionStartErrors:
    def test_404_if_session_not_found(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """Returns 404 when session ID does not exist."""
        auth_as(client, seed_data["gm"])
        response = client.post("/api/v1/sessions/01JZZZZZZZZZZZZZZZZZZZZZZZ/start")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_400_if_session_not_draft_active(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Returns 400 when attempting to start an already-active session."""
        session = _make_session(db, status="active", time_now=10)

        auth_as(client, seed_data["gm"])
        response = client.post(f"/api/v1/sessions/{session.id}/start")

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "session_not_draft"

    def test_400_if_session_not_draft_ended(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Returns 400 when attempting to start an ended session."""
        session = _make_session(db, status="ended", time_now=10)

        auth_as(client, seed_data["gm"])
        response = client.post(f"/api/v1/sessions/{session.id}/start")

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "session_not_draft"

    def test_409_if_another_session_already_active(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Returns 409 when another session is already active."""
        # Create an already-active session.
        _make_session(db, status="active", time_now=5)
        # Create the session we're trying to start.
        draft = _make_session(db, status="draft", time_now=10)

        auth_as(client, seed_data["gm"])
        response = client.post(f"/api/v1/sessions/{draft.id}/start")

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "active_session_exists"

    def test_400_if_time_now_not_set(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Returns 400 when session.time_now is None."""
        session = _make_session(db, status="draft", time_now=None)

        auth_as(client, seed_data["gm"])
        response = client.post(f"/api/v1/sessions/{session.id}/start")

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "time_now_not_set"

    def test_403_if_non_gm_tries_to_start(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Returns 403 when a non-GM player attempts to start a session."""
        session = _make_session(db, status="draft", time_now=5)

        auth_as(client, seed_data["player1"])
        response = client.post(f"/api/v1/sessions/{session.id}/start")

        assert response.status_code == 403

    def test_401_if_unauthenticated(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Returns 401 when the request has no auth cookie."""
        session = _make_session(db, status="draft", time_now=5)

        # Do not call auth_as — send unauthenticated request.
        response = client.post(f"/api/v1/sessions/{session.id}/start")

        assert response.status_code == 401

    def test_session_not_mutated_on_409(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """When 409 is returned, the draft session status is unchanged."""
        _make_session(db, status="active", time_now=5)
        draft = _make_session(db, status="draft", time_now=10)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{draft.id}/start")

        db.refresh(draft)
        assert draft.status == "draft"

    def test_no_events_created_on_error(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """No events are created when start fails due to missing time_now."""
        session = _make_session(db, status="draft", time_now=None)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/start")

        events = _get_events_for_session(db, session.id)
        assert events == []


# ---------------------------------------------------------------------------
# Edge cases not covered above
# ---------------------------------------------------------------------------


class TestSessionStartEdgeCases:
    def test_ft_delta_uses_nonzero_last_session_time_now(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """FT gain uses the character's actual last_session_time_now, not always 0.

        If a character already has last_session_time_now = 8 and the new session
        has time_now = 12, the ft_gained should be 4, not 12.
        """
        pc = seed_data["pc1"]
        pc.last_session_time_now = 8
        pc.free_time = 0
        db.commit()

        session = _make_session(db, status="draft", time_now=12)
        _add_participant(db, session, pc)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/start")

        db.refresh(pc)
        # ft_gained = 12 - 8 = 4
        assert pc.free_time == 4
        assert pc.last_session_time_now == 12

    def test_ft_at_19_gains_one_and_hits_exactly_20(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """FT at 19 gains 1 from a delta of 1 and lands exactly at 20 without clamping."""
        pc = seed_data["pc1"]
        pc.free_time = 19
        pc.last_session_time_now = 9
        db.commit()

        # time_now=10, last=9 → ft_gained=1 → 19+1=20 → exactly at cap, no clamp
        session = _make_session(db, status="draft", time_now=10)
        _add_participant(db, session, pc)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/start")

        db.refresh(pc)
        assert pc.free_time == 20

        # Verify clamped flag is NOT set when landing exactly on the cap
        events = _get_events_for_session(db, session.id)
        ft_event = next(e for e in events if e.type == "session.ft_distributed")
        ft_key = f"character.{pc.id}.free_time"
        assert ft_event.changes[ft_key]["after"] == 20
        assert "clamped" not in ft_event.changes[ft_key]

    def test_contribution_flag_locked_after_start(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """After session start, PATCH on a participant's contribution flag returns 400.

        The spec states: 'Locks all contribution flags (no further PATCH on participants)'.
        The route enforces this via the session_not_draft check on the now-active session.
        """
        pc = seed_data["pc1"]
        session = _make_session(db, status="draft", time_now=5)
        _add_participant(db, session, pc)

        auth_as(client, seed_data["gm"])
        start_resp = client.post(f"/api/v1/sessions/{session.id}/start")
        assert start_resp.status_code == 200
        assert start_resp.json()["status"] == "active"

        # Now attempt to PATCH the contribution flag — must be rejected.
        patch_resp = client.patch(
            f"/api/v1/sessions/{session.id}/participants/{pc.id}",
            json={"additional_contribution": True},
        )
        assert patch_resp.status_code == 400
        assert patch_resp.json()["error"]["code"] == "session_not_draft"
