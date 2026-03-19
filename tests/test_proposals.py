"""Integration tests for /api/v1/proposals — Proposal CRUD + Submission (Story 4.3.1).

Exercises:
- POST /proposals: happy path, auth, character ownership, system-only types
- GET /proposals: listing, pagination, filters, player vs GM visibility
- GET /proposals/{id}: happy path, 404, player cannot see other player's proposal
- PATCH /proposals/{id}: update fields, rejected→pending revision, approved blocked
- DELETE /proposals/{id}: happy path, approved blocked, 204

All tests use the function-scoped ``client`` + ``seed_data`` fixtures so each
test starts with a completely isolated in-memory database.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import auth_as
from wizards_engine.models.proposal import Proposal


# ===========================================================================
# Test helpers
# ===========================================================================


def _proposal(
    db: Session,
    *,
    character_id: str,
    action_type: str = "use_skill",
    narrative: str | None = "Test narrative",
    selections: dict | None = None,
    status: str = "pending",
    origin: str = "player",
) -> Proposal:
    """Create and flush a minimal Proposal in the current test DB session."""
    p = Proposal(
        character_id=character_id,
        action_type=action_type,
        origin=origin,
        narrative=narrative,
        selections=selections or {},
        calculated_effect={},
        status=status,
    )
    db.add(p)
    db.flush()
    db.refresh(p)
    return p


# ===========================================================================
# POST /proposals — authentication
# ===========================================================================


class TestCreateProposalAuth:
    """Unauthenticated and GM callers are rejected."""

    def test_unauthenticated_returns_401(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/proposals",
            json={
                "character_id": "00000000000000000000000001",
                "action_type": "use_skill",
                "narrative": "I look around.",
            },
        )
        assert response.status_code == 401

    def test_gm_cannot_submit_proposal(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = client.post(
            "/api/v1/proposals",
            json={
                "character_id": seed_data["pc1"].id,
                "action_type": "use_skill",
                "narrative": "I look around.",
            },
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"


# ===========================================================================
# POST /proposals — validation
# ===========================================================================


class TestCreateProposalValidation:
    """Request body validation: character ownership, action_type."""

    def test_wrong_character_id_returns_422(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """Player1 cannot submit for Player2's character."""
        auth_as(client, seed_data["player1"])
        response = client.post(
            "/api/v1/proposals",
            json={
                "character_id": seed_data["pc2"].id,
                "action_type": "use_skill",
                "narrative": "I look around.",
            },
        )
        assert response.status_code == 422
        body = response.json()
        assert body["error"]["code"] == "validation_error"
        assert "character_id" in body["error"]["details"]["fields"]

    def test_invalid_action_type_returns_422(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["player1"])
        response = client.post(
            "/api/v1/proposals",
            json={
                "character_id": seed_data["pc1"].id,
                "action_type": "fly_to_moon",
                "narrative": "Fly to the moon.",
            },
        )
        assert response.status_code == 422

    @pytest.mark.parametrize("system_type", ["resolve_clock", "resolve_trauma"])
    def test_system_only_action_types_rejected(
        self, client: TestClient, seed_data: dict, system_type: str
    ) -> None:
        auth_as(client, seed_data["player1"])
        response = client.post(
            "/api/v1/proposals",
            json={
                "character_id": seed_data["pc1"].id,
                "action_type": system_type,
                "narrative": "System action.",
            },
        )
        assert response.status_code == 422

    def test_player_with_no_character_linked_returns_422(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """A player with no linked character cannot submit a proposal for any character."""
        # player3 has pc3 linked; try submitting for pc1 (not theirs).
        auth_as(client, seed_data["player3"])
        response = client.post(
            "/api/v1/proposals",
            json={
                "character_id": seed_data["pc1"].id,
                "action_type": "use_skill",
                "narrative": "I look around.",
            },
        )
        # Ownership check fails: player3.character_id (pc3) != pc1.id.
        assert response.status_code == 422


# ===========================================================================
# POST /proposals — happy path
# ===========================================================================


class TestCreateProposalHappyPath:
    """Successful proposal creation."""

    @pytest.mark.parametrize(
        "action_type",
        [
            # regain_gnosis and rest work with no selections (just require FT >= 1).
            # Other downtime types are tested in test_downtime_actions.py.
            "regain_gnosis",
            "rest",
        ],
    )
    def test_simple_downtime_action_types_accepted(
        self, client: TestClient, seed_data: dict, db, action_type: str
    ) -> None:
        """Simple downtime actions with no modifiers are accepted when FT >= 1."""
        pc1 = seed_data["pc1"]
        pc1.free_time = 1
        db.flush()
        auth_as(client, seed_data["player1"])
        response = client.post(
            "/api/v1/proposals",
            json={
                "character_id": pc1.id,
                "action_type": action_type,
                "narrative": "Test action.",
            },
        )
        assert response.status_code == 201

    def test_use_magic_action_type_accepted(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """use_magic requires a valid 'suggested_stat' in selections."""
        pc1 = seed_data["pc1"]
        pc1.gnosis = 5
        auth_as(client, seed_data["player1"])
        response = client.post(
            "/api/v1/proposals",
            json={
                "character_id": pc1.id,
                "action_type": "use_magic",
                "narrative": "I cast a spell.",
                "selections": {
                    "suggested_stat": "being",
                    "sacrifice": [{"type": "gnosis", "amount": 1}],
                },
            },
        )
        assert response.status_code == 201

    def test_use_skill_action_type_accepted(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """use_skill requires a valid 'skill' in selections."""
        auth_as(client, seed_data["player1"])
        response = client.post(
            "/api/v1/proposals",
            json={
                "character_id": seed_data["pc1"].id,
                "action_type": "use_skill",
                "narrative": "Test action.",
                "selections": {"skill": "awareness"},
            },
        )
        assert response.status_code == 201

    def test_creates_proposal_with_correct_fields(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["player1"])
        response = client.post(
            "/api/v1/proposals",
            json={
                "character_id": seed_data["pc1"].id,
                "action_type": "use_skill",
                "narrative": "I check for traps.",
                "selections": {"skill": "awareness"},
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["character_id"] == seed_data["pc1"].id
        assert body["action_type"] == "use_skill"
        assert body["narrative"] == "I check for traps."
        assert body["selections"] == {"skill": "awareness"}
        assert body["status"] == "pending"
        assert body["origin"] == "player"
        # use_skill proposals have a populated calculated_effect (not empty)
        assert isinstance(body["calculated_effect"], dict)
        assert body["calculated_effect"]["skill"] == "awareness"
        assert body["gm_notes"] is None
        assert body["gm_overrides"] is None
        assert body["event_id"] is None
        assert body["rider_event_id"] is None
        assert body["clock_id"] is None
        assert "id" in body
        assert "created_at" in body
        assert "updated_at" in body

    def test_default_selections_is_empty_dict(
        self, client: TestClient, seed_data: dict, db
    ) -> None:
        pc1 = seed_data["pc1"]
        pc1.free_time = 1
        db.flush()
        auth_as(client, seed_data["player1"])
        response = client.post(
            "/api/v1/proposals",
            json={
                "character_id": pc1.id,
                "action_type": "rest",
                "narrative": "Rest.",
            },
        )
        assert response.status_code == 201
        assert response.json()["selections"] == {}


# ===========================================================================
# GET /proposals — authentication
# ===========================================================================


class TestListProposalsAuth:
    """Unauthenticated requests are rejected."""

    def test_unauthenticated_returns_401(self, client: TestClient) -> None:
        response = client.get("/api/v1/proposals")
        assert response.status_code == 401


# ===========================================================================
# GET /proposals — player visibility
# ===========================================================================


class TestListProposalsPlayerVisibility:
    """Players see only their own proposals."""

    def test_player_sees_only_own_proposals(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        pc2 = seed_data["pc2"]
        _proposal(db, character_id=pc1.id)
        _proposal(db, character_id=pc2.id)
        db.commit()

        auth_as(client, seed_data["player1"])
        response = client.get("/api/v1/proposals")
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["character_id"] == pc1.id

    def test_gm_sees_all_proposals(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        pc2 = seed_data["pc2"]
        _proposal(db, character_id=pc1.id)
        _proposal(db, character_id=pc2.id)
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/proposals")
        assert response.status_code == 200
        assert len(response.json()["items"]) == 2

    def test_player_with_no_proposals_sees_empty_list(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc2 = seed_data["pc2"]
        _proposal(db, character_id=pc2.id)
        db.commit()

        auth_as(client, seed_data["player1"])
        response = client.get("/api/v1/proposals")
        assert response.status_code == 200
        assert response.json()["items"] == []


# ===========================================================================
# GET /proposals — filters
# ===========================================================================


class TestListProposalsFilters:
    """Query parameter filters."""

    def test_status_filter(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        _proposal(db, character_id=pc1.id, status="pending")
        _proposal(db, character_id=pc1.id, status="approved")
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/proposals?status=pending")
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["status"] == "pending"

    def test_invalid_status_returns_422(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/proposals?status=maybe")
        assert response.status_code == 422

    def test_character_id_filter_for_gm(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        pc2 = seed_data["pc2"]
        p1 = _proposal(db, character_id=pc1.id)
        _proposal(db, character_id=pc2.id)
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/proposals?character_id={pc1.id}")
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == p1.id

    def test_action_type_filter(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        _proposal(db, character_id=pc1.id, action_type="use_skill")
        _proposal(db, character_id=pc1.id, action_type="rest")
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/proposals?action_type=rest")
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["action_type"] == "rest"

    def test_combined_filters(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        pc2 = seed_data["pc2"]
        match = _proposal(
            db, character_id=pc1.id, action_type="use_skill", status="pending"
        )
        _proposal(db, character_id=pc1.id, action_type="use_skill", status="approved")
        _proposal(db, character_id=pc2.id, action_type="use_skill", status="pending")
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.get(
            f"/api/v1/proposals?character_id={pc1.id}&action_type=use_skill&status=pending"
        )
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == match.id


# ===========================================================================
# GET /proposals — pagination
# ===========================================================================


class TestListProposalsPagination:
    """ULID cursor pagination."""

    def test_default_limit_50(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        for _ in range(55):
            _proposal(db, character_id=pc1.id)
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/proposals")
        body = response.json()
        assert len(body["items"]) == 50
        assert body["has_more"] is True
        assert body["next_cursor"] is not None

    def test_after_cursor(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        for _ in range(5):
            _proposal(db, character_id=pc1.id)
        db.commit()

        auth_as(client, seed_data["gm"])
        page1 = client.get("/api/v1/proposals?limit=3").json()
        assert len(page1["items"]) == 3
        cursor = page1["next_cursor"]

        page2 = client.get(f"/api/v1/proposals?limit=3&after={cursor}").json()
        assert len(page2["items"]) == 2
        assert page2["has_more"] is False

        page1_ids = {item["id"] for item in page1["items"]}
        page2_ids = {item["id"] for item in page2["items"]}
        assert not page1_ids & page2_ids


# ===========================================================================
# GET /proposals/{id}
# ===========================================================================


class TestGetProposal:
    """Single proposal detail endpoint."""

    def test_unauthenticated_returns_401(self, client: TestClient) -> None:
        response = client.get("/api/v1/proposals/01FAKEPROPOSALID000000001")
        assert response.status_code == 401

    def test_nonexistent_returns_404(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/proposals/01FAKEPROPOSALID000000001")
        assert response.status_code == 404

    def test_player_can_see_own_proposal(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        p = _proposal(db, character_id=pc1.id)
        db.commit()

        auth_as(client, seed_data["player1"])
        response = client.get(f"/api/v1/proposals/{p.id}")
        assert response.status_code == 200
        assert response.json()["id"] == p.id

    def test_player_cannot_see_other_players_proposal(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc2 = seed_data["pc2"]
        p = _proposal(db, character_id=pc2.id)
        db.commit()

        auth_as(client, seed_data["player1"])
        response = client.get(f"/api/v1/proposals/{p.id}")
        assert response.status_code == 404

    def test_gm_can_see_any_proposal(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        p = _proposal(db, character_id=pc1.id)
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/proposals/{p.id}")
        assert response.status_code == 200
        assert response.json()["id"] == p.id

    def test_response_shape(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        p = _proposal(
            db,
            character_id=pc1.id,
            action_type="use_magic",
            narrative="Cast a spell.",
            selections={"spell": "fireball"},
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        body = client.get(f"/api/v1/proposals/{p.id}").json()
        assert body["id"] == p.id
        assert body["character_id"] == pc1.id
        assert body["action_type"] == "use_magic"
        assert body["narrative"] == "Cast a spell."
        assert body["selections"] == {"spell": "fireball"}
        assert body["status"] == "pending"
        assert body["origin"] == "player"
        assert body["calculated_effect"] == {}
        assert body["gm_notes"] is None
        assert body["gm_overrides"] is None
        assert body["event_id"] is None
        assert body["rider_event_id"] is None
        assert body["clock_id"] is None
        assert "created_at" in body
        assert "updated_at" in body


# ===========================================================================
# PATCH /proposals/{id}
# ===========================================================================


class TestUpdateProposal:
    """PATCH /proposals/{id} endpoint."""

    def test_unauthenticated_returns_401(self, client: TestClient) -> None:
        response = client.patch(
            "/api/v1/proposals/01FAKEPROPOSALID000000001",
            json={"narrative": "New narrative."},
        )
        assert response.status_code == 401

    def test_player_can_update_own_pending_proposal(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        p = _proposal(db, character_id=pc1.id, narrative="Old narrative.")
        db.commit()

        auth_as(client, seed_data["player1"])
        response = client.patch(
            f"/api/v1/proposals/{p.id}",
            json={"narrative": "New narrative."},
        )
        assert response.status_code == 200
        assert response.json()["narrative"] == "New narrative."
        assert response.json()["status"] == "pending"

    def test_player_cannot_update_other_players_proposal(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc2 = seed_data["pc2"]
        p = _proposal(db, character_id=pc2.id)
        db.commit()

        auth_as(client, seed_data["player1"])
        response = client.patch(
            f"/api/v1/proposals/{p.id}",
            json={"narrative": "Tampered."},
        )
        assert response.status_code == 404

    def test_gm_can_update_any_proposal(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        p = _proposal(db, character_id=pc1.id, narrative="Original.")
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.patch(
            f"/api/v1/proposals/{p.id}",
            json={"narrative": "GM edited."},
        )
        assert response.status_code == 200
        assert response.json()["narrative"] == "GM edited."

    def test_update_selections(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        p = _proposal(db, character_id=pc1.id, selections={"skill": "awareness"})
        db.commit()

        auth_as(client, seed_data["player1"])
        response = client.patch(
            f"/api/v1/proposals/{p.id}",
            json={"selections": {"skill": "power"}},
        )
        assert response.status_code == 200
        assert response.json()["selections"] == {"skill": "power"}

    def test_approved_proposal_returns_409(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        p = _proposal(db, character_id=pc1.id, status="approved")
        db.commit()

        auth_as(client, seed_data["player1"])
        response = client.patch(
            f"/api/v1/proposals/{p.id}",
            json={"narrative": "Try to change."},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "proposal_approved"

    def test_rejected_proposal_can_be_updated(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        pc1.free_time = 1
        # Use 'rest' to isolate the revision workflow
        p = _proposal(db, character_id=pc1.id, action_type="rest", status="rejected", narrative="Old.")
        db.commit()

        auth_as(client, seed_data["player1"])
        response = client.patch(
            f"/api/v1/proposals/{p.id}",
            json={"narrative": "Revised."},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["narrative"] == "Revised."

    def test_rejected_proposal_reverts_to_pending(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Patching a rejected proposal changes its status back to pending."""
        pc1 = seed_data["pc1"]
        pc1.free_time = 1
        # Use 'rest' to isolate the revision workflow
        p = _proposal(db, character_id=pc1.id, action_type="rest", status="rejected")
        db.commit()

        auth_as(client, seed_data["player1"])
        response = client.patch(
            f"/api/v1/proposals/{p.id}",
            json={"narrative": "Revised."},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "pending"

    def test_revision_creates_proposal_revised_event(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Patching a rejected proposal creates a proposal.revised event."""
        from wizards_engine.models.event import Event

        pc1 = seed_data["pc1"]
        pc1.free_time = 1
        # Use 'rest' to isolate the revision event workflow
        p = _proposal(db, character_id=pc1.id, action_type="rest", status="rejected")
        db.commit()

        auth_as(client, seed_data["player1"])
        client.patch(
            f"/api/v1/proposals/{p.id}",
            json={"narrative": "Revised."},
        )

        # Check the event was created.
        event = db.query(Event).filter(Event.proposal_id == p.id).first()
        assert event is not None
        assert event.type == "proposal.revised"
        assert event.visibility == "private"

    def test_updating_pending_proposal_does_not_create_event(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Patching a pending (not rejected) proposal does NOT create an event."""
        from wizards_engine.models.event import Event

        pc1 = seed_data["pc1"]
        p = _proposal(db, character_id=pc1.id, status="pending")
        db.commit()

        auth_as(client, seed_data["player1"])
        client.patch(
            f"/api/v1/proposals/{p.id}",
            json={"narrative": "Updated."},
        )

        event_count = db.query(Event).filter(Event.proposal_id == p.id).count()
        assert event_count == 0

    def test_omitted_fields_are_not_changed(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        p = _proposal(
            db,
            character_id=pc1.id,
            narrative="Original.",
            selections={"skill": "awareness"},
        )
        db.commit()

        auth_as(client, seed_data["player1"])
        # Only update narrative; selections should be unchanged.
        response = client.patch(
            f"/api/v1/proposals/{p.id}",
            json={"narrative": "Updated."},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["narrative"] == "Updated."
        assert body["selections"] == {"skill": "awareness"}

    def test_nonexistent_proposal_returns_404(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = client.patch(
            "/api/v1/proposals/01FAKEPROPOSALID000000001",
            json={"narrative": "Test."},
        )
        assert response.status_code == 404


# ===========================================================================
# DELETE /proposals/{id}
# ===========================================================================


class TestDeleteProposal:
    """DELETE /proposals/{id} endpoint."""

    def test_unauthenticated_returns_401(self, client: TestClient) -> None:
        response = client.delete("/api/v1/proposals/01FAKEPROPOSALID000000001")
        assert response.status_code == 401

    def test_player_can_delete_own_pending_proposal(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        p = _proposal(db, character_id=pc1.id, status="pending")
        proposal_id = p.id
        db.commit()

        auth_as(client, seed_data["player1"])
        response = client.delete(f"/api/v1/proposals/{proposal_id}")
        assert response.status_code == 204

        # Verify hard delete: expire the session cache then re-query.
        db.expire_all()
        assert db.get(Proposal, proposal_id) is None

    def test_player_can_delete_own_rejected_proposal(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        p = _proposal(db, character_id=pc1.id, status="rejected")
        db.commit()

        auth_as(client, seed_data["player1"])
        response = client.delete(f"/api/v1/proposals/{p.id}")
        assert response.status_code == 204

    def test_player_cannot_delete_other_players_proposal(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc2 = seed_data["pc2"]
        p = _proposal(db, character_id=pc2.id, status="pending")
        db.commit()

        auth_as(client, seed_data["player1"])
        response = client.delete(f"/api/v1/proposals/{p.id}")
        assert response.status_code == 404

    def test_gm_can_delete_any_non_approved_proposal(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        p = _proposal(db, character_id=pc1.id, status="pending")
        proposal_id = p.id
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.delete(f"/api/v1/proposals/{proposal_id}")
        assert response.status_code == 204
        db.expire_all()
        assert db.get(Proposal, proposal_id) is None

    def test_approved_proposal_cannot_be_deleted(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        p = _proposal(db, character_id=pc1.id, status="approved")
        db.commit()

        auth_as(client, seed_data["player1"])
        response = client.delete(f"/api/v1/proposals/{p.id}")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "proposal_approved"

        # Proposal still exists.
        assert db.get(Proposal, p.id) is not None

    def test_approved_proposal_gm_cannot_delete_either(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        p = _proposal(db, character_id=pc1.id, status="approved")
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.delete(f"/api/v1/proposals/{p.id}")
        assert response.status_code == 409

    def test_nonexistent_proposal_returns_404(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = client.delete("/api/v1/proposals/01FAKEPROPOSALID000000001")
        assert response.status_code == 404

    def test_delete_returns_no_body(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        p = _proposal(db, character_id=pc1.id, status="pending")
        db.commit()

        auth_as(client, seed_data["player1"])
        response = client.delete(f"/api/v1/proposals/{p.id}")
        assert response.status_code == 204
        assert response.content == b""


# ===========================================================================
# proposal.revised event target uses character, not proposal
# ===========================================================================


class TestProposalRevisedEventTarget:
    """Revising a rejected proposal creates an event targeting the character."""

    def test_revised_event_targets_character(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """proposal.revised event should target the character, not the proposal."""
        from wizards_engine.models.event import Event, EventTarget  # noqa: PLC0415

        pc1 = seed_data["pc1"]
        pc1.free_time = 1
        p = _proposal(db, character_id=pc1.id, action_type="rest", status="rejected")
        db.commit()

        auth_as(client, seed_data["player1"])
        client.patch(
            f"/api/v1/proposals/{p.id}",
            json={"narrative": "Revised."},
        )

        event = db.query(Event).filter(Event.proposal_id == p.id).first()
        assert event is not None
        assert event.type == "proposal.revised"

        targets = event.targets
        # Event targets must not use "proposal" as target_type.
        for target in targets:
            assert target.target_type != "proposal", (
                "proposal.revised event should not use 'proposal' as target_type"
            )

        # The primary target should be the character.
        primary = next((t for t in targets if t.is_primary), None)
        assert primary is not None
        assert primary.target_type == "character"
        assert primary.target_id == pc1.id


# ===========================================================================
# Story 5.5.3 — Nullable narrative for session action types
# ===========================================================================


class TestNullableNarrative:
    """Story 5.5.3 — narrative is optional for session actions, required for downtime."""

    def test_session_action_null_narrative_accepted(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """use_skill with narrative=None is accepted (201)."""
        auth_as(client, seed_data["player1"])
        response = client.post(
            "/api/v1/proposals",
            json={
                "character_id": seed_data["pc1"].id,
                "action_type": "use_skill",
                "narrative": None,
                "selections": {"skill": "awareness"},
            },
        )
        assert response.status_code == 201
        assert response.json()["narrative"] is None

    def test_session_action_omitted_narrative_accepted(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """use_skill with narrative key absent is accepted (201)."""
        auth_as(client, seed_data["player1"])
        response = client.post(
            "/api/v1/proposals",
            json={
                "character_id": seed_data["pc1"].id,
                "action_type": "use_skill",
                "selections": {"skill": "awareness"},
            },
        )
        assert response.status_code == 201
        assert response.json()["narrative"] is None

    def test_use_magic_null_narrative_accepted(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """use_magic with no narrative is accepted (201)."""
        pc1 = seed_data["pc1"]
        pc1.gnosis = 5
        db.flush()

        auth_as(client, seed_data["player1"])
        response = client.post(
            "/api/v1/proposals",
            json={
                "character_id": pc1.id,
                "action_type": "use_magic",
                "selections": {
                    "suggested_stat": "being",
                    "sacrifice": [{"type": "gnosis", "amount": 1}],
                },
            },
        )
        assert response.status_code == 201
        assert response.json()["narrative"] is None

    def test_charge_magic_null_narrative_accepted(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """charge_magic with no narrative is accepted (201)."""
        from wizards_engine.models.magic_effect import MagicEffect
        from ulid import ULID

        pc1 = seed_data["pc1"]
        eff = MagicEffect(
            id=str(ULID()),
            character_id=pc1.id,
            name="Test Effect",
            description="A test effect.",
            effect_type="charged",
            power_level=1,
            charges_current=0,
            charges_max=3,
            is_active=True,
        )
        db.add(eff)
        db.flush()

        auth_as(client, seed_data["player1"])
        response = client.post(
            "/api/v1/proposals",
            json={
                "character_id": pc1.id,
                "action_type": "charge_magic",
                "selections": {
                    "effect_id": eff.id,
                    "suggested_stat": "enchanting",
                },
            },
        )
        assert response.status_code == 201
        assert response.json()["narrative"] is None

    @pytest.mark.parametrize(
        "downtime_type",
        ["regain_gnosis", "work_on_project", "rest", "new_trait", "new_bond"],
    )
    def test_downtime_action_null_narrative_rejected(
        self, client: TestClient, seed_data: dict, downtime_type: str
    ) -> None:
        """Downtime action with narrative=None is rejected with 422."""
        auth_as(client, seed_data["player1"])
        response = client.post(
            "/api/v1/proposals",
            json={
                "character_id": seed_data["pc1"].id,
                "action_type": downtime_type,
                "narrative": None,
            },
        )
        assert response.status_code == 422

    @pytest.mark.parametrize(
        "downtime_type",
        ["regain_gnosis", "work_on_project", "rest", "new_trait", "new_bond"],
    )
    def test_downtime_action_empty_narrative_rejected(
        self, client: TestClient, seed_data: dict, downtime_type: str
    ) -> None:
        """Downtime action with narrative="" is rejected with 422."""
        auth_as(client, seed_data["player1"])
        response = client.post(
            "/api/v1/proposals",
            json={
                "character_id": seed_data["pc1"].id,
                "action_type": downtime_type,
                "narrative": "",
            },
        )
        assert response.status_code == 422

    @pytest.mark.parametrize(
        "downtime_type",
        ["regain_gnosis", "work_on_project", "rest", "new_trait", "new_bond"],
    )
    def test_downtime_action_whitespace_only_narrative_rejected(
        self, client: TestClient, seed_data: dict, downtime_type: str
    ) -> None:
        """Downtime action with narrative containing only whitespace is rejected."""
        auth_as(client, seed_data["player1"])
        response = client.post(
            "/api/v1/proposals",
            json={
                "character_id": seed_data["pc1"].id,
                "action_type": downtime_type,
                "narrative": "   ",
            },
        )
        assert response.status_code == 422

    def test_patch_narrative_onto_pending_session_action(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """PATCH can set a narrative on a pending use_skill proposal that had none."""
        pc1 = seed_data["pc1"]
        p = _proposal(db, character_id=pc1.id, action_type="use_skill", narrative=None)
        db.commit()

        auth_as(client, seed_data["player1"])
        response = client.patch(
            f"/api/v1/proposals/{p.id}",
            json={"narrative": "Added later."},
        )
        assert response.status_code == 200
        assert response.json()["narrative"] == "Added later."

    def test_approval_with_both_null_narratives(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Approving a use_skill where narrative=None and gm_narrative=None produces event with narrative=None."""
        from wizards_engine.models.event import Event

        pc1 = seed_data["pc1"]
        p = _proposal(
            db,
            character_id=pc1.id,
            action_type="use_skill",
            narrative=None,
            selections={"skill": "awareness"},
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.post(
            f"/api/v1/proposals/{p.id}/approve",
            json={},
        )
        assert response.status_code == 200

        db.expire_all()
        approval_event = (
            db.query(Event)
            .filter(Event.proposal_id == p.id, Event.type == "proposal.approved")
            .first()
        )
        assert approval_event is not None
        assert approval_event.narrative is None
