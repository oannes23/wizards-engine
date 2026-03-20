"""Tests for Story 5.1.3 — Session End.

Covers all acceptance criteria for POST /api/v1/sessions/{id}/end.

Scenarios tested:
- Happy path: active session ends, status becomes ended, event created
- Plot clamping: characters with Plot > 5 get clamped to 5
- Characters with Plot <= 5 are unchanged (no clamp entry in event)
- Multiple participants with mixed Plot levels
- Session with no participants still ends correctly
- clamped flag on Plot changes (meter.set op)
- Event has correct type (session.ended), visibility (global), changes
- Event tagged with session_id
- Actor is system, actor_id is None
- Narrative is auto-generated ("Session ended.")
- 400 if session not active (draft, ended)
- 404 if session doesn't exist
- 403 if non-GM
- 401 if unauthenticated
- No request body needed (empty POST)
- Ended session is read-only: PATCH returns 400
- Adding participant to ended session is rejected (400)
- Removing participant from ended session is rejected (400)
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
    status: str = "active",
    time_now: int | None = 10,
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
# POST /api/v1/sessions/{id}/end — happy path
# ---------------------------------------------------------------------------


class TestSessionEndHappyPath:
    def test_end_session_returns_200_with_ended_status(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Ending an active session returns 200 with status='ended'."""
        session = _make_session(db, status="active", time_now=10)

        auth_as(client, seed_data["gm"])
        response = client.post(f"/api/v1/sessions/{session.id}/end")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ended"
        assert body["id"] == session.id

    def test_end_session_with_no_participants(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Session with no participants ends cleanly; no Plot changes in event."""
        session = _make_session(db, status="active", time_now=5)

        auth_as(client, seed_data["gm"])
        response = client.post(f"/api/v1/sessions/{session.id}/end")

        assert response.status_code == 200
        assert response.json()["status"] == "ended"

    def test_end_session_no_request_body_required(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """POST /sessions/{id}/end requires no request body."""
        session = _make_session(db, status="active", time_now=10)

        auth_as(client, seed_data["gm"])
        # Post with no body at all
        response = client.post(f"/api/v1/sessions/{session.id}/end")

        assert response.status_code == 200

    def test_session_status_persisted_to_ended(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Session status is persisted as 'ended' after the call."""
        session = _make_session(db, status="active", time_now=10)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/end")

        db.refresh(session)
        assert session.status == "ended"


# ---------------------------------------------------------------------------
# Plot clamping
# ---------------------------------------------------------------------------


class TestSessionEndPlotClamping:
    def test_plot_above_five_clamped_to_five(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Participant with Plot > 5 has Plot set to 5 after session end."""
        pc = seed_data["pc1"]
        pc.plot = 7
        db.commit()

        session = _make_session(db, status="active", time_now=10)
        _add_participant(db, session, pc)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/end")

        db.refresh(pc)
        assert pc.plot == 5

    def test_plot_at_five_not_changed(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Participant with Plot = 5 is unchanged after session end."""
        pc = seed_data["pc1"]
        pc.plot = 5
        db.commit()

        session = _make_session(db, status="active", time_now=10)
        _add_participant(db, session, pc)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/end")

        db.refresh(pc)
        assert pc.plot == 5

    def test_plot_below_five_not_changed(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Participant with Plot < 5 is unchanged after session end."""
        pc = seed_data["pc1"]
        pc.plot = 3
        db.commit()

        session = _make_session(db, status="active", time_now=10)
        _add_participant(db, session, pc)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/end")

        db.refresh(pc)
        assert pc.plot == 3

    def test_plot_at_zero_not_changed(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Participant with Plot = 0 is unchanged after session end."""
        pc = seed_data["pc1"]
        pc.plot = 0
        db.commit()

        session = _make_session(db, status="active", time_now=10)
        _add_participant(db, session, pc)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/end")

        db.refresh(pc)
        assert pc.plot == 0

    def test_multiple_participants_mixed_plot_levels(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Mixed Plot levels: some clamped, some unchanged."""
        pc1 = seed_data["pc1"]
        pc2 = seed_data["pc2"]
        pc1.plot = 7   # above cap — will be clamped
        pc2.plot = 3   # below cap — unchanged
        db.commit()

        session = _make_session(db, status="active", time_now=10)
        _add_participant(db, session, pc1)
        _add_participant(db, session, pc2)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/end")

        db.refresh(pc1)
        db.refresh(pc2)
        assert pc1.plot == 5
        assert pc2.plot == 3

    def test_three_participants_all_above_cap(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """All three participants with Plot > 5 get clamped to 5."""
        pc1 = seed_data["pc1"]
        pc2 = seed_data["pc2"]
        pc3 = seed_data["pc3"]
        pc1.plot = 6
        pc2.plot = 7
        pc3.plot = 8
        db.commit()

        session = _make_session(db, status="active", time_now=10)
        _add_participant(db, session, pc1)
        _add_participant(db, session, pc2)
        _add_participant(db, session, pc3)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/end")

        db.refresh(pc1)
        db.refresh(pc2)
        db.refresh(pc3)
        assert pc1.plot == 5
        assert pc2.plot == 5
        assert pc3.plot == 5


# ---------------------------------------------------------------------------
# Event created correctly
# ---------------------------------------------------------------------------


class TestSessionEndEvent:
    def test_exactly_one_event_created(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Session end creates exactly 1 event."""
        session = _make_session(db, status="active", time_now=5)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/end")

        events = _get_events_for_session(db, session.id)
        assert len(events) == 1

    def test_event_type_is_session_ended(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """The event has type 'session.ended'."""
        session = _make_session(db, status="active", time_now=5)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/end")

        events = _get_events_for_session(db, session.id)
        assert events[0].type == "session.ended"

    def test_event_visibility_is_global(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """The session.ended event has visibility='global'."""
        session = _make_session(db, status="active", time_now=5)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/end")

        events = _get_events_for_session(db, session.id)
        assert events[0].visibility == "global"

    def test_event_actor_is_system(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """The event has actor_type='system' and actor_id=None."""
        session = _make_session(db, status="active", time_now=5)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/end")

        events = _get_events_for_session(db, session.id)
        assert events[0].actor_type == "system"
        assert events[0].actor_id is None

    def test_event_tagged_with_session_id(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """The event has session_id set to the ended session's ID."""
        session = _make_session(db, status="active", time_now=5)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/end")

        events = _get_events_for_session(db, session.id)
        assert events[0].session_id == session.id

    def test_event_narrative_is_session_ended(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """The event narrative is 'Session ended.'"""
        session = _make_session(db, status="active", time_now=5)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/end")

        events = _get_events_for_session(db, session.id)
        assert events[0].narrative == "Session ended."

    def test_event_changes_contain_status_transition(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """session.ended event changes record active→ended status transition."""
        session = _make_session(db, status="active", time_now=5)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/end")

        events = _get_events_for_session(db, session.id)
        key = f"session.{session.id}.status"
        assert key in events[0].changes
        assert events[0].changes[key]["op"] == "field.set"
        assert events[0].changes[key]["before"] == "active"
        assert events[0].changes[key]["after"] == "ended"

    def test_event_changes_contain_clamped_plot_with_clamped_flag(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Clamped Plot changes use meter.set op with clamped=True."""
        pc = seed_data["pc1"]
        pc.plot = 7
        db.commit()

        session = _make_session(db, status="active", time_now=10)
        _add_participant(db, session, pc)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/end")

        events = _get_events_for_session(db, session.id)
        plot_key = f"character.{pc.id}.plot"
        assert plot_key in events[0].changes
        assert events[0].changes[plot_key]["op"] == "meter.set"
        assert events[0].changes[plot_key]["before"] == 7
        assert events[0].changes[plot_key]["after"] == 5
        assert events[0].changes[plot_key]["clamped"] is True

    def test_event_changes_do_not_include_unclamped_plot(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Participants whose Plot is <= 5 are not recorded in event changes."""
        pc = seed_data["pc1"]
        pc.plot = 3
        db.commit()

        session = _make_session(db, status="active", time_now=10)
        _add_participant(db, session, pc)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/end")

        events = _get_events_for_session(db, session.id)
        plot_key = f"character.{pc.id}.plot"
        assert plot_key not in events[0].changes

    def test_event_changes_include_only_clamped_participants_in_mixed_group(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Only clamped participants appear in event changes, not unclamped ones."""
        pc1 = seed_data["pc1"]
        pc2 = seed_data["pc2"]
        pc1.plot = 7   # will be clamped
        pc2.plot = 3   # will not be clamped
        db.commit()

        session = _make_session(db, status="active", time_now=10)
        _add_participant(db, session, pc1)
        _add_participant(db, session, pc2)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/end")

        events = _get_events_for_session(db, session.id)
        changes = events[0].changes

        assert f"character.{pc1.id}.plot" in changes
        assert f"character.{pc2.id}.plot" not in changes

    def test_event_changes_no_plot_entries_when_no_clamping_needed(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """When no Plot exceeds 5, the event changes only contain the status entry."""
        pc = seed_data["pc1"]
        pc.plot = 2
        db.commit()

        session = _make_session(db, status="active", time_now=10)
        _add_participant(db, session, pc)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/end")

        events = _get_events_for_session(db, session.id)
        # Only the status key should be present.
        assert len(events[0].changes) == 1
        assert f"session.{session.id}.status" in events[0].changes

    def test_event_has_no_targets(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """session.ended event has no EventTarget rows."""
        session = _make_session(db, status="active", time_now=5)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/end")

        events = _get_events_for_session(db, session.id)
        assert events[0].targets == []


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestSessionEndErrors:
    def test_404_if_session_not_found(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """Returns 404 when session ID does not exist."""
        auth_as(client, seed_data["gm"])
        response = client.post("/api/v1/sessions/01JZZZZZZZZZZZZZZZZZZZZZZZ/end")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_400_if_session_is_draft(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Returns 400 when attempting to end a draft session."""
        session = _make_session(db, status="draft", time_now=10)

        auth_as(client, seed_data["gm"])
        response = client.post(f"/api/v1/sessions/{session.id}/end")

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "session_not_active"

    def test_400_if_session_already_ended(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Returns 400 when attempting to end an already-ended session."""
        session = _make_session(db, status="ended", time_now=10)

        auth_as(client, seed_data["gm"])
        response = client.post(f"/api/v1/sessions/{session.id}/end")

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "session_not_active"

    def test_403_if_non_gm_tries_to_end(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Returns 403 when a non-GM player attempts to end a session."""
        session = _make_session(db, status="active", time_now=5)

        auth_as(client, seed_data["player1"])
        response = client.post(f"/api/v1/sessions/{session.id}/end")

        assert response.status_code == 403

    def test_401_if_unauthenticated(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """Returns 401 when the request has no auth cookie."""
        session = _make_session(db, status="active", time_now=5)

        # Do not call auth_as — send unauthenticated request.
        response = client.post(f"/api/v1/sessions/{session.id}/end")

        assert response.status_code == 401

    def test_session_not_mutated_on_400(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """When 400 is returned for draft session, its status is unchanged."""
        session = _make_session(db, status="draft", time_now=10)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/end")

        db.refresh(session)
        assert session.status == "draft"

    def test_no_events_created_on_error(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """No events are created when end fails due to non-active session."""
        session = _make_session(db, status="draft", time_now=10)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/end")

        events = _get_events_for_session(db, session.id)
        assert events == []

    def test_no_plot_changes_on_error(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """No character Plot is clamped when end fails."""
        pc = seed_data["pc1"]
        pc.plot = 7
        db.commit()

        session = _make_session(db, status="draft", time_now=10)
        _add_participant(db, session, pc)

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/sessions/{session.id}/end")

        db.refresh(pc)
        assert pc.plot == 7  # unchanged


# ---------------------------------------------------------------------------
# Ended session is read-only
# ---------------------------------------------------------------------------


class TestEndedSessionReadOnly:
    def test_patch_session_returns_400_after_end(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """PATCH on an ended session returns 400 with session_ended."""
        session = _make_session(db, status="active", time_now=10)

        auth_as(client, seed_data["gm"])
        end_resp = client.post(f"/api/v1/sessions/{session.id}/end")
        assert end_resp.status_code == 200

        patch_resp = client.patch(
            f"/api/v1/sessions/{session.id}",
            json={"summary": "Updated summary"},
        )
        assert patch_resp.status_code == 400
        assert patch_resp.json()["error"]["code"] == "session_ended"

    def test_add_participant_to_ended_session_returns_400(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """POST /participants on an ended session returns 400 with session_ended."""
        pc = seed_data["pc1"]
        session = _make_session(db, status="active", time_now=10)

        auth_as(client, seed_data["gm"])
        end_resp = client.post(f"/api/v1/sessions/{session.id}/end")
        assert end_resp.status_code == 200

        add_resp = client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": pc.id},
        )
        assert add_resp.status_code == 400
        assert add_resp.json()["error"]["code"] == "session_ended"

    def test_remove_participant_from_ended_session_returns_400(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """DELETE /participants/{id} on an ended session returns 400 with session_ended."""
        pc = seed_data["pc1"]
        session = _make_session(db, status="active", time_now=10)
        _add_participant(db, session, pc)

        auth_as(client, seed_data["gm"])
        end_resp = client.post(f"/api/v1/sessions/{session.id}/end")
        assert end_resp.status_code == 200

        remove_resp = client.delete(
            f"/api/v1/sessions/{session.id}/participants/{pc.id}",
        )
        assert remove_resp.status_code == 400
        assert remove_resp.json()["error"]["code"] == "session_ended"

    def test_patch_participant_on_ended_session_returns_400(
        self, client: TestClient, db: DBSession, seed_data: dict
    ) -> None:
        """PATCH /participants/{id} on an ended session returns 400.

        The existing PATCH handler checks session.status == 'draft', so ended
        sessions are already rejected with session_not_draft.
        """
        pc = seed_data["pc1"]
        session = _make_session(db, status="active", time_now=10)
        _add_participant(db, session, pc)

        auth_as(client, seed_data["gm"])
        end_resp = client.post(f"/api/v1/sessions/{session.id}/end")
        assert end_resp.status_code == 200

        patch_resp = client.patch(
            f"/api/v1/sessions/{session.id}/participants/{pc.id}",
            json={"additional_contribution": True},
        )
        assert patch_resp.status_code == 400
