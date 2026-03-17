"""Integration and edge-case tests for Stories 5.1.2 and 5.1.3.

These tests cover scenarios that fall between or beyond what the story-scoped
test files address:

Edge cases for 5.1.2 (Late Joins):
- FT exactly at 19 with delta=1 → lands at 20 exactly (capped but no overshoot)
- Re-adding a previously removed participant to an active session triggers
  a fresh distribution (second round of FT/Plot for that character)

Integration (end-to-end lifecycle):
- Full lifecycle: create draft → start → late join → end
  Verifies all state transitions, distributions, Plot clamping, and event
  creation across all three session operations in one test.
- Late join followed by end: verifies that Plot accumulated during late join
  is subject to end-of-session clamping.
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
    """Insert a Session row with the given status and time_now."""
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
    """Register a character as a participant, bypassing the API (no distribution)."""
    p = SessionParticipant(
        session_id=session.id,
        character_id=character.id,
        additional_contribution=additional_contribution,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _get_events_by_type(
    db: DBSession,
    session_id: str,
    event_type: str,
) -> list[Event]:
    """Return events of a specific type tagged with session_id, ordered by id."""
    return (
        db.query(Event)
        .filter(Event.session_id == session_id, Event.type == event_type)
        .order_by(Event.id)
        .all()
    )


def _get_all_events_for_session(db: DBSession, session_id: str) -> list[Event]:
    """Return all events tagged with session_id, ordered by id."""
    return (
        db.query(Event)
        .filter(Event.session_id == session_id)
        .order_by(Event.id)
        .all()
    )


# ---------------------------------------------------------------------------
# Edge cases for Story 5.1.2 — Late Joins
# ---------------------------------------------------------------------------


class TestLateJoinFtBoundary:
    def test_ft_lands_exactly_at_cap(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """FT delta that brings total to exactly 20 is NOT marked clamped.

        Clamping only occurs when the computed value would *exceed* the cap.
        Landing exactly on it is a normal distribution, not a clamp.
        """
        pc = seed_data["pc1"]
        pc.free_time = 19
        pc.last_session_time_now = 0
        db.commit()

        # delta = 1 → 19 + 1 = 20 → exactly at cap, not over
        session = _make_session(db, status="active", time_now=1)

        auth_as(client, seed_data["gm"])
        client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": pc.id},
        )

        db.refresh(pc)
        assert pc.free_time == 20

        events = _get_events_by_type(db, session.id, "session.participant_added")
        ft_key = f"character.{pc.id}.free_time"
        assert events[0].changes[ft_key]["after"] == 20
        # Exactly at cap — should NOT have clamped=True
        assert "clamped" not in events[0].changes[ft_key]

    def test_ft_one_over_cap_is_clamped(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """FT delta that pushes total to 21 is clamped to 20 and marked clamped."""
        pc = seed_data["pc1"]
        pc.free_time = 19
        pc.last_session_time_now = 0
        db.commit()

        # delta = 2 → 19 + 2 = 21 → clamped to 20
        session = _make_session(db, status="active", time_now=2)

        auth_as(client, seed_data["gm"])
        client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": pc.id},
        )

        db.refresh(pc)
        assert pc.free_time == 20

        events = _get_events_by_type(db, session.id, "session.participant_added")
        ft_key = f"character.{pc.id}.free_time"
        assert events[0].changes[ft_key]["after"] == 20
        assert events[0].changes[ft_key].get("clamped") is True


class TestLateJoinReRegistration:
    def test_readding_removed_participant_distributes_again(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """A participant removed then re-added to an active session gets a second
        distribution based on their *current* last_session_time_now.

        This tests that distribute_to_participant uses character.last_session_time_now
        (updated after the first distribution) rather than a stale value.
        """
        pc = seed_data["pc1"]
        pc.free_time = 0
        pc.last_session_time_now = 0
        pc.plot = 0
        db.commit()

        session = _make_session(db, status="active", time_now=10)

        auth_as(client, seed_data["gm"])

        # First registration — distributes FT=10, Plot=+1
        add_resp = client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": pc.id},
        )
        assert add_resp.status_code == 201

        db.refresh(pc)
        assert pc.free_time == 10
        assert pc.plot == 1
        assert pc.last_session_time_now == 10

        # Remove the participant.
        del_resp = client.delete(
            f"/api/v1/sessions/{session.id}/participants/{pc.id}",
        )
        assert del_resp.status_code == 204

        # Re-add — last_session_time_now is now 10, so delta = 10 - 10 = 0 FT.
        # Plot still gets +1 (participation income, not FT-dependent).
        re_add_resp = client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": pc.id},
        )
        assert re_add_resp.status_code == 201

        db.refresh(pc)
        # FT: 10 + 0 = 10 (no additional FT since time_now hasn't changed)
        assert pc.free_time == 10
        # Plot: 1 + 1 = 2
        assert pc.plot == 2
        # last_session_time_now still 10
        assert pc.last_session_time_now == 10

        # Two participant_added events should exist (one per registration).
        events = _get_events_by_type(db, session.id, "session.participant_added")
        assert len(events) == 2

    def test_readding_generates_new_participant_added_event(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Each re-registration creates a new session.participant_added event."""
        pc = seed_data["pc1"]
        session = _make_session(db, status="active", time_now=5)

        auth_as(client, seed_data["gm"])

        client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": pc.id},
        )
        client.delete(f"/api/v1/sessions/{session.id}/participants/{pc.id}")
        client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": pc.id},
        )

        events = _get_events_by_type(db, session.id, "session.participant_added")
        assert len(events) == 2


# ---------------------------------------------------------------------------
# Full lifecycle integration tests
# ---------------------------------------------------------------------------


class TestFullSessionLifecycle:
    def test_create_draft_start_late_join_end(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Full lifecycle: create draft → add participant → start → late join → end.

        This integration test walks through all session state transitions and
        verifies that the correct resources are distributed and clamped at each
        stage.

        Setup:
        - pc1 starts with FT=0, plot=0, last_session_time_now=0
        - pc2 starts with FT=0, plot=0, last_session_time_now=0
        - Session time_now = 8

        Expected at session start (pc1 only):
        - pc1 FT = 0 + (8 - 0) = 8
        - pc1 plot = 0 + 1 = 1
        - pc1 last_session_time_now = 8
        - pc2 unchanged (not yet added)

        Expected at late join (pc2):
        - pc2 FT = 0 + (8 - 0) = 8
        - pc2 plot = 0 + 2 = 2 (additional_contribution=True)
        - pc2 last_session_time_now = 8

        Expected at session end:
        - pc1 plot = 1 (below 5, unchanged)
        - pc2 plot = 2 (below 5, unchanged)
        - Session status = ended
        """
        pc1 = seed_data["pc1"]
        pc2 = seed_data["pc2"]
        gm = seed_data["gm"]

        auth_as(client, gm)

        # Step 1 — Create a draft session.
        create_resp = client.post(
            "/api/v1/sessions",
            json={"time_now": 8},
        )
        assert create_resp.status_code == 201
        session_id = create_resp.json()["id"]
        assert create_resp.json()["status"] == "draft"

        # Step 2 — Register pc1 as a participant (while draft — no distribution yet).
        reg_resp = client.post(
            f"/api/v1/sessions/{session_id}/participants",
            json={"character_id": pc1.id},
        )
        assert reg_resp.status_code == 201

        db.refresh(pc1)
        # Draft — no distribution.
        assert pc1.free_time == 0
        assert pc1.plot == 0

        # Step 3 — Start the session.
        start_resp = client.post(f"/api/v1/sessions/{session_id}/start")
        assert start_resp.status_code == 200
        assert start_resp.json()["status"] == "active"

        db.refresh(pc1)
        assert pc1.free_time == 8
        assert pc1.plot == 1
        assert pc1.last_session_time_now == 8

        # Step 4 — pc2 joins late with additional_contribution=True.
        late_resp = client.post(
            f"/api/v1/sessions/{session_id}/participants",
            json={"character_id": pc2.id, "additional_contribution": True},
        )
        assert late_resp.status_code == 201

        db.refresh(pc2)
        assert pc2.free_time == 8
        assert pc2.plot == 2
        assert pc2.last_session_time_now == 8

        # Verify pc1 is unaffected by the late join.
        db.refresh(pc1)
        assert pc1.free_time == 8
        assert pc1.plot == 1

        # Step 5 — End the session.
        end_resp = client.post(f"/api/v1/sessions/{session_id}/end")
        assert end_resp.status_code == 200
        assert end_resp.json()["status"] == "ended"

        # Both characters' Plot is below cap — no clamping.
        db.refresh(pc1)
        db.refresh(pc2)
        assert pc1.plot == 1
        assert pc2.plot == 2

        # Verify correct event types were created.
        all_events = _get_all_events_for_session(db, session_id)
        event_types = [e.type for e in all_events]
        assert "session.started" in event_types
        assert "session.ft_distributed" in event_types
        assert "session.plot_distributed" in event_types
        assert "session.participant_added" in event_types
        assert "session.ended" in event_types

    def test_late_join_accumulated_plot_clamped_at_end(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Plot accumulated via late join (overflow allowed) is clamped at end.

        pc1 starts with plot=5, late joins with additional_contribution=True
        → plot becomes 7.  Session end clamps to 5.
        """
        pc1 = seed_data["pc1"]
        pc1.plot = 5
        db.commit()

        session = _make_session(db, status="active", time_now=10)

        auth_as(client, seed_data["gm"])

        # Late join with additional_contribution=True → plot 5 + 2 = 7.
        client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": pc1.id, "additional_contribution": True},
        )

        db.refresh(pc1)
        assert pc1.plot == 7  # overflow allowed mid-session

        # End the session — plot should be clamped to 5.
        end_resp = client.post(f"/api/v1/sessions/{session.id}/end")
        assert end_resp.status_code == 200

        db.refresh(pc1)
        assert pc1.plot == 5

        # Verify the ended event records the clamp.
        ended_events = _get_events_by_type(db, session.id, "session.ended")
        assert len(ended_events) == 1
        changes = ended_events[0].changes
        plot_key = f"character.{pc1.id}.plot"
        assert plot_key in changes
        assert changes[plot_key]["before"] == 7
        assert changes[plot_key]["after"] == 5
        assert changes[plot_key]["clamped"] is True

    def test_end_session_all_participants_plot_at_or_below_cap(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """When all participants have Plot <= 5, ended event has only status change.

        Verifies that the event changes dict contains exactly 1 key (status)
        when no clamping is needed, even with multiple participants.
        """
        pc1 = seed_data["pc1"]
        pc2 = seed_data["pc2"]
        pc1.plot = 4
        pc2.plot = 5
        db.commit()

        session = _make_session(db, status="active", time_now=10)
        _add_participant_directly(db, session, pc1)
        _add_participant_directly(db, session, pc2)

        auth_as(client, seed_data["gm"])
        end_resp = client.post(f"/api/v1/sessions/{session.id}/end")
        assert end_resp.status_code == 200

        # Both characters unchanged.
        db.refresh(pc1)
        db.refresh(pc2)
        assert pc1.plot == 4
        assert pc2.plot == 5

        ended_events = _get_events_by_type(db, session.id, "session.ended")
        changes = ended_events[0].changes
        # Only the status key — no plot clamp entries.
        assert len(changes) == 1
        assert f"session.{session.id}.status" in changes
