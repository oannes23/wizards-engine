"""Integration tests for Story 5.5.2 — POST /api/v1/characters/{id}/maintain-bond.

Covers:
- Happy path: bond with partial charges → charges become effective_max, FT decremented
- Happy path: bond with 0 charges → restored to effective max
- Happy path: degraded bond (2 degradations → effective max 3 → charges restored to 3)
- Happy path: GM can maintain on behalf of any character
- Happy path: bond with NULL stress → treated as 0, restored to effective max
- Auth: unauthenticated → 401
- Auth: wrong player → 403
- Character not found → 404
- Character deleted → 404
- Not a PC (detail_level != "full") → 422 not_a_pc
- Narrative empty string → 422 narrative_required
- Narrative whitespace only → 422 narrative_required
- Narrative missing → 422 (Pydantic validation error)
- Bond not found → 404 bond_not_found
- Bond not owned by character → 422 bond_not_owned
- Bond not active → 422 bond_not_active
- Not a pc_bond slot type (e.g. core_trait) → 422 not_a_pc_bond
- Trauma bond → 422 cannot_maintain_trauma
- Bond already at effective max → 409 bond_already_maintained
- Insufficient FT (FT=0) → 409 insufficient_free_time
- Proposal with action_type maintain_bond → 422 (rejected)
- Event created with correct changes dict (including correct stress before/after)
- Event includes narrative
- GM as actor sets actor_type to "gm"
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import auth_as
from wizards_engine.models.event import Event, EventTarget
from wizards_engine.models.slot import Slot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _maintain_bond(
    client: TestClient,
    character_id: str,
    bond_instance_id: str,
    narrative: str = "I spent the evening tending to this connection.",
) -> "Response":  # type: ignore[name-defined]
    """POST to the maintain-bond endpoint for a character."""
    return client.post(
        f"/api/v1/characters/{character_id}/maintain-bond",
        json={
            "bond_instance_id": bond_instance_id,
            "narrative": narrative,
        },
    )


def _create_pc_bond_slot(
    db: Session,
    character_id: str,
    stress: int | None = 2,
    stress_degradations: int = 0,
    is_active: bool = True,
    is_trauma: bool = False,
) -> Slot:
    """Create and commit a pc_bond slot for a given character."""
    slot = Slot(
        slot_type="pc_bond",
        owner_type="character",
        owner_id=character_id,
        name="Test Bond",
        description="A test bond slot.",
        stress=stress,
        stress_degradations=stress_degradations,
        is_active=is_active,
        is_trauma=is_trauma,
        bidirectional=True,
    )
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return slot


def _set_free_time(db: Session, character, *, free_time: int) -> None:
    """Directly update a character's free_time and commit."""
    character.free_time = free_time
    db.commit()
    db.refresh(character)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class TestMaintainBondAuth:
    """Authentication and authorisation gates."""

    def test_unauthenticated_returns_401(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        slot = _create_pc_bond_slot(db, seed_data["pc1"].id, stress=2)
        _set_free_time(db, seed_data["pc1"], free_time=3)
        response = _maintain_bond(client, seed_data["pc1"].id, slot.id)
        assert response.status_code == 401

    def test_wrong_player_returns_403(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """player2 cannot call maintain-bond for pc1 (owned by player1)."""
        slot = _create_pc_bond_slot(db, seed_data["pc1"].id, stress=2)
        _set_free_time(db, seed_data["pc1"], free_time=3)
        auth_as(client, seed_data["player2"])
        response = _maintain_bond(client, seed_data["pc1"].id, slot.id)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"

    def test_owner_can_maintain_own_bond(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        slot = _create_pc_bond_slot(db, seed_data["pc1"].id, stress=2)
        _set_free_time(db, seed_data["pc1"], free_time=3)
        auth_as(client, seed_data["player1"])
        response = _maintain_bond(client, seed_data["pc1"].id, slot.id)
        assert response.status_code == 200

    def test_gm_can_maintain_any_character(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """GM may call maintain-bond on behalf of any character."""
        slot = _create_pc_bond_slot(db, seed_data["pc2"].id, stress=1)
        _set_free_time(db, seed_data["pc2"], free_time=2)
        auth_as(client, seed_data["gm"])
        response = _maintain_bond(client, seed_data["pc2"].id, slot.id)
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# 404 cases
# ---------------------------------------------------------------------------


class TestMaintainBondNotFound:
    """404 error cases for character and bond lookup."""

    def test_nonexistent_character_returns_404(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = _maintain_bond(client, "01AAAAAAAAAAAAAAAAAAAAAA", "01BBBBBBBBBBBBBBBBBBBBBB")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_deleted_character_returns_404(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        pc = seed_data["pc3"]
        slot = _create_pc_bond_slot(db, pc.id, stress=2)
        pc.is_deleted = True
        db.commit()
        db.refresh(pc)

        auth_as(client, seed_data["gm"])
        response = _maintain_bond(client, pc.id, slot.id)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_nonexistent_bond_returns_404(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        _set_free_time(db, seed_data["pc1"], free_time=3)
        auth_as(client, seed_data["gm"])
        response = _maintain_bond(client, seed_data["pc1"].id, "01CCCCCCCCCCCCCCCCCCCCCC")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "bond_not_found"


# ---------------------------------------------------------------------------
# 422 — validation errors
# ---------------------------------------------------------------------------


class TestMaintainBondValidation:
    """422 error cases for request and business rule validation."""

    def test_not_a_pc_returns_422(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """NPC (simplified) character cannot use maintain-bond."""
        npc = seed_data["npc1"]
        # npc1_bond is an npc_bond type but we need to test not_a_pc
        # so we check that a simplified character is rejected before slot checks
        slot = _create_pc_bond_slot(db, npc.id, stress=2)
        auth_as(client, seed_data["gm"])
        response = _maintain_bond(client, npc.id, slot.id)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "not_a_pc"

    def test_empty_narrative_returns_422(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        slot = _create_pc_bond_slot(db, seed_data["pc1"].id, stress=2)
        _set_free_time(db, seed_data["pc1"], free_time=3)
        auth_as(client, seed_data["player1"])
        response = _maintain_bond(client, seed_data["pc1"].id, slot.id, narrative="")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "narrative_required"

    def test_whitespace_only_narrative_returns_422(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        slot = _create_pc_bond_slot(db, seed_data["pc1"].id, stress=2)
        _set_free_time(db, seed_data["pc1"], free_time=3)
        auth_as(client, seed_data["player1"])
        response = _maintain_bond(client, seed_data["pc1"].id, slot.id, narrative="   ")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "narrative_required"

    def test_missing_narrative_field_returns_422(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Pydantic rejects a body missing the required narrative field."""
        slot = _create_pc_bond_slot(db, seed_data["pc1"].id, stress=2)
        _set_free_time(db, seed_data["pc1"], free_time=3)
        auth_as(client, seed_data["player1"])
        response = client.post(
            f"/api/v1/characters/{seed_data['pc1'].id}/maintain-bond",
            json={"bond_instance_id": slot.id},
        )
        assert response.status_code == 422

    def test_bond_not_owned_by_character_returns_422(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """A bond belonging to pc2 cannot be maintained via pc1's endpoint."""
        pc2_slot = _create_pc_bond_slot(db, seed_data["pc2"].id, stress=2)
        _set_free_time(db, seed_data["pc1"], free_time=3)
        auth_as(client, seed_data["gm"])
        response = _maintain_bond(client, seed_data["pc1"].id, pc2_slot.id)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "bond_not_owned"

    def test_inactive_bond_returns_422(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        slot = _create_pc_bond_slot(db, seed_data["pc1"].id, stress=2, is_active=False)
        _set_free_time(db, seed_data["pc1"], free_time=3)
        auth_as(client, seed_data["player1"])
        response = _maintain_bond(client, seed_data["pc1"].id, slot.id)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "bond_not_active"

    def test_non_pc_bond_slot_type_returns_422(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """A core_trait slot is not a maintainable bond."""
        trait_slot = Slot(
            slot_type="core_trait",
            owner_type="character",
            owner_id=seed_data["pc1"].id,
            name="Test Trait",
            description="A test trait.",
            charge=2,
            is_active=True,
        )
        db.add(trait_slot)
        db.commit()
        db.refresh(trait_slot)

        _set_free_time(db, seed_data["pc1"], free_time=3)
        auth_as(client, seed_data["player1"])
        response = _maintain_bond(client, seed_data["pc1"].id, trait_slot.id)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "not_a_pc_bond"

    def test_trauma_bond_returns_422(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """A trauma bond cannot be maintained."""
        trauma_slot = _create_pc_bond_slot(
            db, seed_data["pc1"].id, stress=2, is_trauma=True
        )
        _set_free_time(db, seed_data["pc1"], free_time=3)
        auth_as(client, seed_data["player1"])
        response = _maintain_bond(client, seed_data["pc1"].id, trauma_slot.id)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "cannot_maintain_trauma"


# ---------------------------------------------------------------------------
# 409 — business logic errors
# ---------------------------------------------------------------------------


class TestMaintainBondBusinessErrors:
    """409 error cases for resource and cap constraints."""

    def test_bond_already_at_effective_max_returns_409(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Bond with stress == effective_max (5, no degradations) returns 409."""
        slot = _create_pc_bond_slot(db, seed_data["pc1"].id, stress=5, stress_degradations=0)
        _set_free_time(db, seed_data["pc1"], free_time=3)
        auth_as(client, seed_data["player1"])
        response = _maintain_bond(client, seed_data["pc1"].id, slot.id)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "bond_already_maintained"

    def test_degraded_bond_already_at_effective_max_returns_409(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Bond with 2 degradations and stress=3 (=effective_max) returns 409."""
        slot = _create_pc_bond_slot(db, seed_data["pc1"].id, stress=3, stress_degradations=2)
        _set_free_time(db, seed_data["pc1"], free_time=3)
        auth_as(client, seed_data["player1"])
        response = _maintain_bond(client, seed_data["pc1"].id, slot.id)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "bond_already_maintained"

    def test_insufficient_free_time_returns_409(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        slot = _create_pc_bond_slot(db, seed_data["pc1"].id, stress=2)
        _set_free_time(db, seed_data["pc1"], free_time=0)
        auth_as(client, seed_data["player1"])
        response = _maintain_bond(client, seed_data["pc1"].id, slot.id)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "insufficient_free_time"


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestMaintainBondHappyPath:
    """Successful maintain-bond executions."""

    def test_partial_charges_restored_to_effective_max(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Bond with partial charges gets set to effective_max; FT decremented by 1."""
        pc = seed_data["pc1"]
        slot = _create_pc_bond_slot(db, pc.id, stress=2, stress_degradations=0)
        _set_free_time(db, pc, free_time=5)

        auth_as(client, seed_data["player1"])
        response = _maintain_bond(client, pc.id, slot.id)
        assert response.status_code == 200

        body = response.json()
        assert body["id"] == pc.id

        # Verify FT decremented in DB
        db.refresh(pc)
        assert pc.free_time == 4

        # Verify slot stress updated in DB
        db.refresh(slot)
        assert slot.stress == 5  # effective_max = 5 - 0 = 5

    def test_zero_charges_restored_to_effective_max(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Bond with stress=0 is restored to effective_max (5)."""
        pc = seed_data["pc1"]
        slot = _create_pc_bond_slot(db, pc.id, stress=0, stress_degradations=0)
        _set_free_time(db, pc, free_time=2)

        auth_as(client, seed_data["player1"])
        response = _maintain_bond(client, pc.id, slot.id)
        assert response.status_code == 200

        db.refresh(slot)
        assert slot.stress == 5

    def test_degraded_bond_restored_to_reduced_effective_max(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Bond with 2 degradations has effective_max=3; restored to 3, not 5."""
        pc = seed_data["pc1"]
        slot = _create_pc_bond_slot(db, pc.id, stress=1, stress_degradations=2)
        _set_free_time(db, pc, free_time=3)

        auth_as(client, seed_data["player1"])
        response = _maintain_bond(client, pc.id, slot.id)
        assert response.status_code == 200

        db.refresh(slot)
        assert slot.stress == 3  # effective_max = 5 - 2 = 3

    def test_gm_maintain_happy_path(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """GM successfully maintains a bond for pc2."""
        pc = seed_data["pc2"]
        slot = _create_pc_bond_slot(db, pc.id, stress=3, stress_degradations=0)
        _set_free_time(db, pc, free_time=4)

        auth_as(client, seed_data["gm"])
        response = _maintain_bond(client, pc.id, slot.id)
        assert response.status_code == 200

        db.refresh(slot)
        assert slot.stress == 5

        db.refresh(pc)
        assert pc.free_time == 3

    def test_null_stress_treated_as_zero_restored_to_effective_max(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Bond with stress=NULL is treated as 0 and restored to effective_max."""
        pc = seed_data["pc1"]
        slot = _create_pc_bond_slot(db, pc.id, stress=None, stress_degradations=0)
        _set_free_time(db, pc, free_time=2)

        auth_as(client, seed_data["player1"])
        response = _maintain_bond(client, pc.id, slot.id)
        assert response.status_code == 200

        db.refresh(slot)
        assert slot.stress == 5


# ---------------------------------------------------------------------------
# Event creation
# ---------------------------------------------------------------------------


class TestMaintainBondEvent:
    """Verify the event record created by maintain-bond."""

    def test_event_created_with_correct_shape(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        pc = seed_data["pc1"]
        player = seed_data["player1"]
        slot = _create_pc_bond_slot(db, pc.id, stress=2, stress_degradations=0)
        _set_free_time(db, pc, free_time=5)

        auth_as(client, player)
        narrative_text = "I spent the evening in quiet reflection, strengthening this bond."
        response = _maintain_bond(client, pc.id, slot.id, narrative=narrative_text)
        assert response.status_code == 200

        event: Event | None = (
            db.query(Event)
            .filter(Event.type == "player.maintain_bond")
            .order_by(Event.created_at.desc())
            .first()
        )
        assert event is not None
        assert event.type == "player.maintain_bond"
        assert event.actor_type == "player"
        assert event.actor_id == player.id
        assert event.visibility == "private"
        assert event.narrative == narrative_text

        # Changes dict
        changes = event.changes
        assert f"slot.{slot.id}.stress" in changes
        assert f"character.{pc.id}.free_time" in changes

        stress_change = changes[f"slot.{slot.id}.stress"]
        assert stress_change["op"] == "meter.set"
        assert stress_change["before"] == 2
        assert stress_change["after"] == 5

        ft_change = changes[f"character.{pc.id}.free_time"]
        assert ft_change["op"] == "meter.delta"
        assert ft_change["before"] == 5
        assert ft_change["after"] == 4

    def test_event_has_primary_character_target(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        pc = seed_data["pc1"]
        slot = _create_pc_bond_slot(db, pc.id, stress=1)
        _set_free_time(db, pc, free_time=2)

        auth_as(client, seed_data["player1"])
        _maintain_bond(client, pc.id, slot.id)

        event: Event | None = (
            db.query(Event)
            .filter(Event.type == "player.maintain_bond")
            .order_by(Event.created_at.desc())
            .first()
        )
        assert event is not None

        targets = (
            db.query(EventTarget)
            .filter(EventTarget.event_id == event.id)
            .all()
        )
        assert len(targets) == 1
        assert targets[0].target_type == "character"
        assert targets[0].target_id == pc.id
        assert targets[0].is_primary is True

    def test_event_actor_type_is_gm_when_gm_calls(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """When GM calls the endpoint, actor_type is 'gm' and actor_id is the GM's id."""
        pc = seed_data["pc2"]
        gm = seed_data["gm"]
        slot = _create_pc_bond_slot(db, pc.id, stress=3)
        _set_free_time(db, pc, free_time=3)

        auth_as(client, gm)
        _maintain_bond(client, pc.id, slot.id)

        event: Event | None = (
            db.query(Event)
            .filter(Event.type == "player.maintain_bond")
            .order_by(Event.created_at.desc())
            .first()
        )
        assert event is not None
        assert event.actor_type == "gm"
        assert event.actor_id == gm.id

    def test_null_stress_event_records_before_as_zero(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """When stress is NULL, the event's 'before' value is recorded as 0."""
        pc = seed_data["pc1"]
        slot = _create_pc_bond_slot(db, pc.id, stress=None, stress_degradations=0)
        _set_free_time(db, pc, free_time=2)

        auth_as(client, seed_data["player1"])
        _maintain_bond(client, pc.id, slot.id)

        event: Event | None = (
            db.query(Event)
            .filter(Event.type == "player.maintain_bond")
            .order_by(Event.created_at.desc())
            .first()
        )
        assert event is not None
        stress_change = event.changes[f"slot.{slot.id}.stress"]
        assert stress_change["before"] == 0
        assert stress_change["after"] == 5

    def test_degraded_bond_event_records_correct_effective_max(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Event records after=3 (effective_max) when degradations=2."""
        pc = seed_data["pc1"]
        slot = _create_pc_bond_slot(db, pc.id, stress=1, stress_degradations=2)
        _set_free_time(db, pc, free_time=3)

        auth_as(client, seed_data["player1"])
        _maintain_bond(client, pc.id, slot.id)

        event: Event | None = (
            db.query(Event)
            .filter(Event.type == "player.maintain_bond")
            .order_by(Event.created_at.desc())
            .first()
        )
        assert event is not None
        stress_change = event.changes[f"slot.{slot.id}.stress"]
        assert stress_change["before"] == 1
        assert stress_change["after"] == 3  # effective_max = 5 - 2 = 3


# ---------------------------------------------------------------------------
# Proposal rejection
# ---------------------------------------------------------------------------


class TestMaintainBondProposalRejection:
    """maintain_bond must no longer be accepted as a proposal action_type."""

    def test_proposal_with_maintain_bond_action_type_returns_422(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Creating a proposal with action_type='maintain_bond' must be rejected."""
        auth_as(client, seed_data["player1"])
        response = client.post(
            "/api/v1/proposals",
            json={
                "character_id": seed_data["pc1"].id,
                "action_type": "maintain_bond",
                "narrative": "I want to maintain my bond.",
                "selections": {},
            },
        )
        assert response.status_code == 422
