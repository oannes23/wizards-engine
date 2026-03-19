"""Integration tests for Story 5.5.1 — POST /api/v1/characters/{id}/recharge-trait.

Covers:
- Happy path: trait with partial charges → charges become 5, FT decremented
- Happy path: GM can recharge on behalf of any character
- Happy path: trait with charge=0 → recharged to 5
- Happy path: trait with NULL charge → treated as 0, recharged to 5
- Auth: unauthenticated → 401
- Auth: wrong player → 403
- Character not found → 404
- Character deleted → 404
- Not a PC (detail_level != "full") → 422 not_a_pc
- Narrative empty string → 422 narrative_required
- Narrative missing from body → 422 (Pydantic validation error)
- Trait not found → 404 trait_not_found
- Trait not owned by character → 422 trait_not_owned
- Trait not active → 422 trait_not_active
- Trait not a core/role trait (e.g., pc_bond) → 422 not_a_trait
- Trait already at 5 charges → 409 trait_already_full
- Insufficient FT (FT=0) → 409 insufficient_free_time
- Proposal with action_type recharge_trait → 422 (rejected by VALID_ACTION_TYPES)
- Event created with correct type, visibility, narrative, changes, and targets
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


def _recharge_trait(
    client: TestClient,
    character_id: str,
    trait_instance_id: str,
    narrative: str = "I spent time meditating to restore this trait.",
) -> "Response":  # type: ignore[name-defined]
    """POST to the recharge-trait endpoint for a character."""
    return client.post(
        f"/api/v1/characters/{character_id}/recharge-trait",
        json={
            "trait_instance_id": trait_instance_id,
            "narrative": narrative,
        },
    )


def _create_trait_slot(
    db: Session,
    character_id: str,
    slot_type: str = "core_trait",
    charge: int | None = 2,
    is_active: bool = True,
) -> Slot:
    """Create and commit a trait slot for a given character."""
    slot = Slot(
        slot_type=slot_type,
        owner_type="character",
        owner_id=character_id,
        name="Test Trait",
        description="A test trait slot.",
        charge=charge,
        is_active=is_active,
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


class TestRechargeTraitAuth:
    """Authentication and authorisation gates."""

    def test_unauthenticated_returns_401(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        slot = _create_trait_slot(db, seed_data["pc1"].id)
        _set_free_time(db, seed_data["pc1"], free_time=3)
        response = _recharge_trait(client, seed_data["pc1"].id, slot.id)
        assert response.status_code == 401

    def test_wrong_player_returns_403(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """player2 cannot call recharge-trait for pc1 (owned by player1)."""
        slot = _create_trait_slot(db, seed_data["pc1"].id)
        _set_free_time(db, seed_data["pc1"], free_time=3)
        auth_as(client, seed_data["player2"])
        response = _recharge_trait(client, seed_data["pc1"].id, slot.id)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"

    def test_owner_can_recharge_own_trait(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        slot = _create_trait_slot(db, seed_data["pc1"].id)
        _set_free_time(db, seed_data["pc1"], free_time=3)
        auth_as(client, seed_data["player1"])
        response = _recharge_trait(client, seed_data["pc1"].id, slot.id)
        assert response.status_code == 200

    def test_gm_can_recharge_any_character(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """GM may call recharge-trait on behalf of any character."""
        slot = _create_trait_slot(db, seed_data["pc2"].id)
        _set_free_time(db, seed_data["pc2"], free_time=2)
        auth_as(client, seed_data["gm"])
        response = _recharge_trait(client, seed_data["pc2"].id, slot.id)
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# 404 cases
# ---------------------------------------------------------------------------


class TestRechargeTraitNotFound:
    """404 error cases for character and trait lookup."""

    def test_nonexistent_character_returns_404(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = _recharge_trait(client, "01AAAAAAAAAAAAAAAAAAAAAA", "01BBBBBBBBBBBBBBBBBBBBBB")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_deleted_character_returns_404(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        pc = seed_data["pc3"]
        slot = _create_trait_slot(db, pc.id)
        pc.is_deleted = True
        db.commit()
        db.refresh(pc)

        auth_as(client, seed_data["gm"])
        response = _recharge_trait(client, pc.id, slot.id)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_nonexistent_trait_returns_404(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        _set_free_time(db, seed_data["pc1"], free_time=3)
        auth_as(client, seed_data["gm"])
        response = _recharge_trait(client, seed_data["pc1"].id, "01CCCCCCCCCCCCCCCCCCCCCC")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "trait_not_found"


# ---------------------------------------------------------------------------
# 422 — validation errors
# ---------------------------------------------------------------------------


class TestRechargeTraitValidation:
    """422 error cases for request and business rule validation."""

    def test_not_a_pc_returns_422(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """NPC (simplified) character cannot use recharge-trait."""
        npc = seed_data["npc1"]
        slot = _create_trait_slot(db, npc.id)
        auth_as(client, seed_data["gm"])
        response = _recharge_trait(client, npc.id, slot.id)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "not_a_pc"

    def test_empty_narrative_returns_422(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        slot = _create_trait_slot(db, seed_data["pc1"].id)
        _set_free_time(db, seed_data["pc1"], free_time=3)
        auth_as(client, seed_data["player1"])
        response = _recharge_trait(client, seed_data["pc1"].id, slot.id, narrative="")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "narrative_required"

    def test_whitespace_only_narrative_returns_422(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        slot = _create_trait_slot(db, seed_data["pc1"].id)
        _set_free_time(db, seed_data["pc1"], free_time=3)
        auth_as(client, seed_data["player1"])
        response = _recharge_trait(client, seed_data["pc1"].id, slot.id, narrative="   ")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "narrative_required"

    def test_missing_narrative_field_returns_422(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Pydantic rejects a body missing the required narrative field."""
        slot = _create_trait_slot(db, seed_data["pc1"].id)
        _set_free_time(db, seed_data["pc1"], free_time=3)
        auth_as(client, seed_data["player1"])
        response = client.post(
            f"/api/v1/characters/{seed_data['pc1'].id}/recharge-trait",
            json={"trait_instance_id": slot.id},
        )
        assert response.status_code == 422

    def test_trait_not_owned_by_character_returns_422(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """A trait belonging to pc2 cannot be recharged via pc1's endpoint."""
        pc2_slot = _create_trait_slot(db, seed_data["pc2"].id)
        _set_free_time(db, seed_data["pc1"], free_time=3)
        auth_as(client, seed_data["gm"])
        response = _recharge_trait(client, seed_data["pc1"].id, pc2_slot.id)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "trait_not_owned"

    def test_inactive_trait_returns_422(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        slot = _create_trait_slot(db, seed_data["pc1"].id, is_active=False, charge=2)
        _set_free_time(db, seed_data["pc1"], free_time=3)
        auth_as(client, seed_data["player1"])
        response = _recharge_trait(client, seed_data["pc1"].id, slot.id)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "trait_not_active"

    def test_pc_bond_slot_returns_422(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """A pc_bond slot is not a rechargeable trait."""
        bond_slot = seed_data["pc1_bond"]
        _set_free_time(db, seed_data["pc1"], free_time=3)
        auth_as(client, seed_data["player1"])
        response = _recharge_trait(client, seed_data["pc1"].id, bond_slot.id)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "not_a_trait"


# ---------------------------------------------------------------------------
# 409 — business logic errors
# ---------------------------------------------------------------------------


class TestRechargeTraitBusinessErrors:
    """409 error cases for resource and cap constraints."""

    def test_trait_already_full_returns_409(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        slot = _create_trait_slot(db, seed_data["pc1"].id, charge=5)
        _set_free_time(db, seed_data["pc1"], free_time=3)
        auth_as(client, seed_data["player1"])
        response = _recharge_trait(client, seed_data["pc1"].id, slot.id)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "trait_already_full"

    def test_insufficient_free_time_returns_409(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        slot = _create_trait_slot(db, seed_data["pc1"].id, charge=2)
        _set_free_time(db, seed_data["pc1"], free_time=0)
        auth_as(client, seed_data["player1"])
        response = _recharge_trait(client, seed_data["pc1"].id, slot.id)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "insufficient_free_time"


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestRechargeTraitHappyPath:
    """Successful recharge-trait executions."""

    def test_partial_charges_recharged_to_5(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Trait with partial charges gets set to 5; FT decremented by 1."""
        from wizards_engine.models.character import Character

        pc = seed_data["pc1"]
        slot = _create_trait_slot(db, pc.id, charge=2)
        _set_free_time(db, pc, free_time=5)

        auth_as(client, seed_data["player1"])
        response = _recharge_trait(client, pc.id, slot.id)
        assert response.status_code == 200

        body = response.json()
        assert body["id"] == pc.id
        # CharacterResponse does not include free_time; verify via DB
        db.refresh(pc)
        assert pc.free_time == 4

        # Verify slot updated in DB
        db.refresh(slot)
        assert slot.charge == 5

    def test_zero_charge_recharged_to_5(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Trait with charge=0 is recharged to 5."""
        pc = seed_data["pc1"]
        slot = _create_trait_slot(db, pc.id, charge=0)
        _set_free_time(db, pc, free_time=2)

        auth_as(client, seed_data["player1"])
        response = _recharge_trait(client, pc.id, slot.id)
        assert response.status_code == 200

        db.refresh(slot)
        assert slot.charge == 5

    def test_null_charge_treated_as_zero_recharged_to_5(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Trait with charge=NULL is treated as 0 and recharged to 5."""
        pc = seed_data["pc1"]
        slot = _create_trait_slot(db, pc.id, charge=None)
        _set_free_time(db, pc, free_time=2)

        auth_as(client, seed_data["player1"])
        response = _recharge_trait(client, pc.id, slot.id)
        assert response.status_code == 200

        db.refresh(slot)
        assert slot.charge == 5

    def test_role_trait_can_be_recharged(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """role_trait slots work the same as core_trait."""
        pc = seed_data["pc1"]
        slot = _create_trait_slot(db, pc.id, slot_type="role_trait", charge=1)
        _set_free_time(db, pc, free_time=3)

        auth_as(client, seed_data["player1"])
        response = _recharge_trait(client, pc.id, slot.id)
        assert response.status_code == 200

        db.refresh(slot)
        assert slot.charge == 5

    def test_gm_recharge_happy_path(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """GM successfully recharges a trait for pc2."""
        pc = seed_data["pc2"]
        slot = _create_trait_slot(db, pc.id, charge=3)
        _set_free_time(db, pc, free_time=4)

        auth_as(client, seed_data["gm"])
        response = _recharge_trait(client, pc.id, slot.id)
        assert response.status_code == 200

        db.refresh(slot)
        assert slot.charge == 5


# ---------------------------------------------------------------------------
# Event creation
# ---------------------------------------------------------------------------


class TestRechargeTraitEvent:
    """Verify the event record created by recharge-trait."""

    def test_event_created_with_correct_shape(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        pc = seed_data["pc1"]
        player = seed_data["player1"]
        slot = _create_trait_slot(db, pc.id, charge=2)
        _set_free_time(db, pc, free_time=5)

        auth_as(client, player)
        narrative_text = "I spent a quiet evening reflecting on my core values."
        response = _recharge_trait(client, pc.id, slot.id, narrative=narrative_text)
        assert response.status_code == 200

        event: Event | None = (
            db.query(Event)
            .filter(Event.type == "player.recharge_trait")
            .order_by(Event.created_at.desc())
            .first()
        )
        assert event is not None
        assert event.type == "player.recharge_trait"
        assert event.actor_type == "player"
        assert event.actor_id == player.id
        assert event.visibility == "private"
        assert event.narrative == narrative_text

        # Changes dict
        changes = event.changes
        assert f"slot.{slot.id}.charge" in changes
        assert f"character.{pc.id}.free_time" in changes

        charge_change = changes[f"slot.{slot.id}.charge"]
        assert charge_change["op"] == "meter.set"
        assert charge_change["before"] == 2
        assert charge_change["after"] == 5

        ft_change = changes[f"character.{pc.id}.free_time"]
        assert ft_change["op"] == "meter.delta"
        assert ft_change["before"] == 5
        assert ft_change["after"] == 4

    def test_event_has_primary_character_target(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        pc = seed_data["pc1"]
        slot = _create_trait_slot(db, pc.id, charge=1)
        _set_free_time(db, pc, free_time=2)

        auth_as(client, seed_data["player1"])
        _recharge_trait(client, pc.id, slot.id)

        event: Event | None = (
            db.query(Event)
            .filter(Event.type == "player.recharge_trait")
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
        slot = _create_trait_slot(db, pc.id, charge=3)
        _set_free_time(db, pc, free_time=3)

        auth_as(client, gm)
        _recharge_trait(client, pc.id, slot.id)

        event: Event | None = (
            db.query(Event)
            .filter(Event.type == "player.recharge_trait")
            .order_by(Event.created_at.desc())
            .first()
        )
        assert event is not None
        assert event.actor_type == "gm"
        assert event.actor_id == gm.id

    def test_null_charge_event_records_before_as_zero(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """When charge is NULL, the event's 'before' value is recorded as 0."""
        pc = seed_data["pc1"]
        slot = _create_trait_slot(db, pc.id, charge=None)
        _set_free_time(db, pc, free_time=2)

        auth_as(client, seed_data["player1"])
        _recharge_trait(client, pc.id, slot.id)

        event: Event | None = (
            db.query(Event)
            .filter(Event.type == "player.recharge_trait")
            .order_by(Event.created_at.desc())
            .first()
        )
        assert event is not None
        charge_change = event.changes[f"slot.{slot.id}.charge"]
        assert charge_change["before"] == 0
        assert charge_change["after"] == 5


# ---------------------------------------------------------------------------
# Proposal rejection
# ---------------------------------------------------------------------------


class TestRechargeTraitProposalRejection:
    """recharge_trait must no longer be accepted as a proposal action_type."""

    def test_proposal_with_recharge_trait_action_type_returns_422(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Creating a proposal with action_type='recharge_trait' must be rejected."""
        auth_as(client, seed_data["player1"])
        response = client.post(
            "/api/v1/proposals",
            json={
                "character_id": seed_data["pc1"].id,
                "action_type": "recharge_trait",
                "narrative": "I want to recharge my trait.",
                "selections": {},
            },
        )
        assert response.status_code == 422
