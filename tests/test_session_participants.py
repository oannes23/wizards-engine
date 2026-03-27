"""Tests for Story 2.2.5 — Session Participants.

Covers all acceptance criteria:

POST /api/v1/sessions/{id}/participants
  - Player registers own character → 201, participant in response
  - GM registers any character → 201
  - additional_contribution defaults to false
  - additional_contribution can be set to true on registration
  - Player cannot register a character they do not own → 403
  - Duplicate registration (same character, same session) → 409
  - Character does not exist → 404
  - Simplified character (NPC) rejected → 400 (character_not_full)
  - Session does not exist → 404
  - Unauthenticated → 401
  - Participant appears in session detail after registration

DELETE /api/v1/sessions/{id}/participants/{character_id}
  - Player removes own character → 204
  - GM removes any character → 204
  - Player cannot remove another player's character → 403
  - Participant not found → 404
  - Session does not exist → 404
  - Unauthenticated → 401
  - Participant no longer in session detail after removal

PATCH /api/v1/sessions/{id}/participants/{character_id}
  - Player updates own contribution flag → 200
  - GM updates any participant's contribution flag → 200
  - Player cannot update another player's record → 403
  - Session is active → 400 (session_not_draft)
  - Session is ended → 400 (session_not_draft)
  - Participant not found → 404
  - Session does not exist → 404
  - Unauthenticated → 401
  - Updated value is reflected in response
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as DBSession

from tests.conftest import auth_as
from wizards_engine.models.session import Session as SessionModel, SessionParticipant


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(db: DBSession, status: str = "draft") -> SessionModel:
    """Insert a Session row with the given status."""
    session = SessionModel(status=status, time_now=None, summary=None, notes=None)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def _make_participant(
    db: DBSession,
    session_id: str,
    character_id: str,
    additional_contribution: bool = False,
) -> SessionParticipant:
    """Insert a SessionParticipant row directly into the DB."""
    participant = SessionParticipant(
        session_id=session_id,
        character_id=character_id,
        additional_contribution=additional_contribution,
    )
    db.add(participant)
    db.commit()
    db.refresh(participant)
    return participant


# ---------------------------------------------------------------------------
# POST /api/v1/sessions/{id}/participants
# ---------------------------------------------------------------------------


class TestAddParticipant:
    def test_player_registers_own_character(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Player can register their own character; returns 201 with participant data."""
        session = _make_session(db)
        auth_as(client, seed_data["player1"])
        response = client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": seed_data["pc1"].id},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["session_id"] == session.id
        assert body["character_id"] == seed_data["pc1"].id
        assert body["additional_contribution"] is False

    def test_gm_registers_any_character(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """GM can register any character, not just their own."""
        session = _make_session(db)
        auth_as(client, seed_data["gm"])
        response = client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": seed_data["pc2"].id},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["character_id"] == seed_data["pc2"].id

    def test_additional_contribution_defaults_to_false(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """additional_contribution defaults to false when not provided."""
        session = _make_session(db)
        auth_as(client, seed_data["gm"])
        response = client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": seed_data["pc1"].id},
        )

        assert response.status_code == 201
        assert response.json()["additional_contribution"] is False

    def test_additional_contribution_can_be_set_true(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """additional_contribution can be set to true at registration."""
        session = _make_session(db)
        auth_as(client, seed_data["player1"])
        response = client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={
                "character_id": seed_data["pc1"].id,
                "additional_contribution": True,
            },
        )

        assert response.status_code == 201
        assert response.json()["additional_contribution"] is True

    def test_player_cannot_register_another_players_character(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Player receives 403 when trying to register a character they don't own."""
        session = _make_session(db)
        auth_as(client, seed_data["player1"])
        response = client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": seed_data["pc2"].id},
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "character_not_owned"

    def test_duplicate_registration_returns_409(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Registering the same character twice in one session returns 409."""
        session = _make_session(db)
        _make_participant(db, session.id, seed_data["pc1"].id)

        auth_as(client, seed_data["player1"])
        response = client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": seed_data["pc1"].id},
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "already_registered"

    def test_nonexistent_character_returns_404(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Registering a non-existent character returns 404."""
        session = _make_session(db)
        auth_as(client, seed_data["gm"])
        response = client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": "01DOESNOTEXIST0000000000000"},
        )

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_simplified_character_rejected(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Simplified (NPC) characters cannot be registered as participants."""
        session = _make_session(db)
        auth_as(client, seed_data["gm"])
        response = client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": seed_data["npc1"].id},
        )

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "character_not_full"

    def test_nonexistent_session_returns_404(
        self, client: TestClient, seed_data: dict
    ):
        """Registering to a non-existent session returns 404."""
        auth_as(client, seed_data["gm"])
        response = client.post(
            "/api/v1/sessions/01JZZZZZZZZZZZZZZZZZZZZZZZ/participants",
            json={"character_id": seed_data["pc1"].id},
        )

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_unauthenticated_returns_401(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Unauthenticated request to add participant returns 401."""
        session = _make_session(db)
        response = client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": seed_data["pc1"].id},
        )

        assert response.status_code == 401

    def test_participant_appears_in_session_detail(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """After registration, the participant is included in GET /sessions/{id}."""
        session = _make_session(db)
        auth_as(client, seed_data["gm"])
        client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": seed_data["pc1"].id},
        )

        detail = client.get(f"/api/v1/sessions/{session.id}").json()
        participant_ids = [p["character_id"] for p in detail["participants"]]
        assert seed_data["pc1"].id in participant_ids

    def test_gm_can_register_to_active_session(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """GM can register a participant to an active session (late join)."""
        session = _make_session(db, status="active")
        auth_as(client, seed_data["gm"])
        response = client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": seed_data["pc1"].id},
        )

        assert response.status_code == 201

    def test_player_can_register_to_active_session(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Player can register themselves to an active session (late join)."""
        session = _make_session(db, status="active")
        auth_as(client, seed_data["player1"])
        response = client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": seed_data["pc1"].id},
        )

        assert response.status_code == 201

    def test_multiple_different_players_can_register(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Multiple players can register their respective characters."""
        session = _make_session(db)

        auth_as(client, seed_data["player1"])
        r1 = client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": seed_data["pc1"].id},
        )

        auth_as(client, seed_data["player2"])
        r2 = client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": seed_data["pc2"].id},
        )

        assert r1.status_code == 201
        assert r2.status_code == 201

        detail = client.get(f"/api/v1/sessions/{session.id}").json()
        participant_ids = {p["character_id"] for p in detail["participants"]}
        assert seed_data["pc1"].id in participant_ids
        assert seed_data["pc2"].id in participant_ids


# ---------------------------------------------------------------------------
# DELETE /api/v1/sessions/{id}/participants/{character_id}
# ---------------------------------------------------------------------------


class TestRemoveParticipant:
    def test_player_removes_own_character(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Player can remove their own character from a session; returns 204."""
        session = _make_session(db)
        _make_participant(db, session.id, seed_data["pc1"].id)

        auth_as(client, seed_data["player1"])
        response = client.delete(
            f"/api/v1/sessions/{session.id}/participants/{seed_data['pc1'].id}"
        )

        assert response.status_code == 204
        assert response.content == b""

    def test_gm_removes_any_participant(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """GM can remove any participant from a session; returns 204."""
        session = _make_session(db)
        _make_participant(db, session.id, seed_data["pc2"].id)

        auth_as(client, seed_data["gm"])
        response = client.delete(
            f"/api/v1/sessions/{session.id}/participants/{seed_data['pc2'].id}"
        )

        assert response.status_code == 204

    def test_player_cannot_remove_another_players_character(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Player receives 403 when trying to remove another player's character."""
        session = _make_session(db)
        _make_participant(db, session.id, seed_data["pc2"].id)

        auth_as(client, seed_data["player1"])
        response = client.delete(
            f"/api/v1/sessions/{session.id}/participants/{seed_data['pc2'].id}"
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "character_not_owned"

    def test_participant_not_found_returns_404(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Deleting a non-existent participant returns 404."""
        session = _make_session(db)

        auth_as(client, seed_data["gm"])
        response = client.delete(
            f"/api/v1/sessions/{session.id}/participants/{seed_data['pc1'].id}"
        )

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_session_not_found_returns_404(
        self, client: TestClient, seed_data: dict
    ):
        """Deleting from a non-existent session returns 404."""
        auth_as(client, seed_data["gm"])
        response = client.delete(
            f"/api/v1/sessions/01JZZZZZZZZZZZZZZZZZZZZZZZ/participants/{seed_data['pc1'].id}"
        )

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_unauthenticated_returns_401(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Unauthenticated DELETE request returns 401."""
        session = _make_session(db)
        _make_participant(db, session.id, seed_data["pc1"].id)

        response = client.delete(
            f"/api/v1/sessions/{session.id}/participants/{seed_data['pc1'].id}"
        )

        assert response.status_code == 401

    def test_participant_no_longer_in_session_detail_after_removal(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """After removal, the participant is absent from GET /sessions/{id}."""
        session = _make_session(db)
        _make_participant(db, session.id, seed_data["pc1"].id)

        auth_as(client, seed_data["gm"])
        client.delete(
            f"/api/v1/sessions/{session.id}/participants/{seed_data['pc1'].id}"
        )

        detail = client.get(f"/api/v1/sessions/{session.id}").json()
        participant_ids = [p["character_id"] for p in detail["participants"]]
        assert seed_data["pc1"].id not in participant_ids

    def test_gm_removes_participant_from_active_session(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """GM can remove a participant from an active session (no resource clawback)."""
        session = _make_session(db, status="active")
        _make_participant(db, session.id, seed_data["pc1"].id)

        auth_as(client, seed_data["gm"])
        response = client.delete(
            f"/api/v1/sessions/{session.id}/participants/{seed_data['pc1'].id}"
        )

        assert response.status_code == 204

    def test_gm_cannot_remove_participant_from_ended_session(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """GM cannot remove a participant from an ended session — read-only."""
        session = _make_session(db, status="ended")
        _make_participant(db, session.id, seed_data["pc1"].id)

        auth_as(client, seed_data["gm"])
        response = client.delete(
            f"/api/v1/sessions/{session.id}/participants/{seed_data['pc1'].id}"
        )

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "session_ended"


# ---------------------------------------------------------------------------
# PATCH /api/v1/sessions/{id}/participants/{character_id}
# ---------------------------------------------------------------------------


class TestUpdateParticipant:
    def test_player_updates_own_contribution_flag(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Player can update their own contribution flag; returns 200."""
        session = _make_session(db)
        _make_participant(db, session.id, seed_data["pc1"].id)

        auth_as(client, seed_data["player1"])
        response = client.patch(
            f"/api/v1/sessions/{session.id}/participants/{seed_data['pc1'].id}",
            json={"additional_contribution": True},
        )

        assert response.status_code == 200
        assert response.json()["additional_contribution"] is True

    def test_gm_updates_any_participants_contribution_flag(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """GM can update any participant's contribution flag."""
        session = _make_session(db)
        _make_participant(db, session.id, seed_data["pc2"].id)

        auth_as(client, seed_data["gm"])
        response = client.patch(
            f"/api/v1/sessions/{session.id}/participants/{seed_data['pc2'].id}",
            json={"additional_contribution": True},
        )

        assert response.status_code == 200
        assert response.json()["additional_contribution"] is True

    def test_player_cannot_update_another_players_record(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Player receives 403 when trying to update another player's record."""
        session = _make_session(db)
        _make_participant(db, session.id, seed_data["pc2"].id)

        auth_as(client, seed_data["player1"])
        response = client.patch(
            f"/api/v1/sessions/{session.id}/participants/{seed_data['pc2'].id}",
            json={"additional_contribution": True},
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "character_not_owned"

    def test_patch_active_session_returns_400(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """PATCH contribution flag on an active session returns 400."""
        session = _make_session(db, status="active")
        _make_participant(db, session.id, seed_data["pc1"].id)

        auth_as(client, seed_data["gm"])
        response = client.patch(
            f"/api/v1/sessions/{session.id}/participants/{seed_data['pc1'].id}",
            json={"additional_contribution": True},
        )

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "session_not_draft"

    def test_patch_ended_session_returns_400(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """PATCH contribution flag on an ended session returns 400."""
        session = _make_session(db, status="ended")
        _make_participant(db, session.id, seed_data["pc1"].id)

        auth_as(client, seed_data["gm"])
        response = client.patch(
            f"/api/v1/sessions/{session.id}/participants/{seed_data['pc1'].id}",
            json={"additional_contribution": True},
        )

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "session_not_draft"

    def test_participant_not_found_returns_404(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """PATCH a non-existent participant returns 404."""
        session = _make_session(db)

        auth_as(client, seed_data["gm"])
        response = client.patch(
            f"/api/v1/sessions/{session.id}/participants/{seed_data['pc1'].id}",
            json={"additional_contribution": True},
        )

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_session_not_found_returns_404(
        self, client: TestClient, seed_data: dict
    ):
        """PATCH to a non-existent session returns 404."""
        auth_as(client, seed_data["gm"])
        response = client.patch(
            f"/api/v1/sessions/01JZZZZZZZZZZZZZZZZZZZZZZZ/participants/{seed_data['pc1'].id}",
            json={"additional_contribution": True},
        )

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_unauthenticated_returns_401(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Unauthenticated PATCH request returns 401."""
        session = _make_session(db)
        _make_participant(db, session.id, seed_data["pc1"].id)

        response = client.patch(
            f"/api/v1/sessions/{session.id}/participants/{seed_data['pc1'].id}",
            json={"additional_contribution": True},
        )

        assert response.status_code == 401

    def test_updated_value_reflected_in_response(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Updated contribution flag is reflected in the response body."""
        session = _make_session(db)
        _make_participant(db, session.id, seed_data["pc1"].id, additional_contribution=False)

        auth_as(client, seed_data["gm"])
        response = client.patch(
            f"/api/v1/sessions/{session.id}/participants/{seed_data['pc1'].id}",
            json={"additional_contribution": True},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["session_id"] == session.id
        assert body["character_id"] == seed_data["pc1"].id
        assert body["additional_contribution"] is True

    def test_flag_can_be_toggled_back_to_false(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Contribution flag can be set from true back to false."""
        session = _make_session(db)
        _make_participant(db, session.id, seed_data["pc1"].id, additional_contribution=True)

        auth_as(client, seed_data["gm"])
        response = client.patch(
            f"/api/v1/sessions/{session.id}/participants/{seed_data['pc1'].id}",
            json={"additional_contribution": False},
        )

        assert response.status_code == 200
        assert response.json()["additional_contribution"] is False


# ---------------------------------------------------------------------------
# ParticipantResponse.character_name
# ---------------------------------------------------------------------------


class TestParticipantCharacterName:
    def test_add_participant_includes_character_name(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """POST participant response includes the character's name."""
        session = _make_session(db)
        auth_as(client, seed_data["player1"])
        response = client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": seed_data["pc1"].id},
        )

        assert response.status_code == 201
        body = response.json()
        assert "character_name" in body
        assert body["character_name"] == seed_data["pc1"].name

    def test_session_detail_participants_include_character_name(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """GET session detail shows character_name in each participant."""
        session = _make_session(db)
        _make_participant(db, session.id, seed_data["pc1"].id)
        _make_participant(db, session.id, seed_data["pc2"].id)

        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/sessions/{session.id}")
        assert response.status_code == 200

        participants = response.json()["participants"]
        names = {p["character_name"] for p in participants}
        assert seed_data["pc1"].name in names
        assert seed_data["pc2"].name in names

    def test_update_participant_includes_character_name(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """PATCH participant response includes the character's name."""
        session = _make_session(db)
        _make_participant(db, session.id, seed_data["pc1"].id)

        auth_as(client, seed_data["gm"])
        response = client.patch(
            f"/api/v1/sessions/{session.id}/participants/{seed_data['pc1'].id}",
            json={"additional_contribution": True},
        )

        assert response.status_code == 200
        assert response.json()["character_name"] == seed_data["pc1"].name

    def test_session_list_participants_include_character_name(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """GET sessions list includes character_name in embedded participants."""
        session = _make_session(db)
        _make_participant(db, session.id, seed_data["pc1"].id)

        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/sessions")
        assert response.status_code == 200

        items = response.json()["items"]
        session_item = next(s for s in items if s["id"] == session.id)
        assert len(session_item["participants"]) == 1
        assert session_item["participants"][0]["character_name"] == seed_data["pc1"].name
