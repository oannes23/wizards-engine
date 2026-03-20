"""Integration tests for Story 4.3.3 — GM Approval + Rejection.

Exercises:
- POST /proposals/{id}/approve: happy path, resource deduction, bond strain,
  gm_overrides, rider event, non-GM blocked, non-pending blocked,
  insufficient resources + force override
- POST /proposals/{id}/reject: happy path, creates event, non-GM blocked,
  non-pending blocked, rejection note stored in gm_notes

All tests use the function-scoped ``client`` + ``seed_data`` fixtures.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import auth_as
from wizards_engine.models.event import Event
from wizards_engine.models.proposal import Proposal
from wizards_engine.models.slot import Slot


# ===========================================================================
# Test helpers
# ===========================================================================


def _pending_proposal(
    db: Session,
    *,
    character_id: str,
    action_type: str = "use_skill",
    narrative: str = "I do something.",
    selections: dict | None = None,
    calculated_effect: dict | None = None,
) -> Proposal:
    """Create and flush a minimal pending Proposal."""
    p = Proposal(
        character_id=character_id,
        action_type=action_type,
        origin="player",
        narrative=narrative,
        selections=selections or {},
        calculated_effect=calculated_effect or {},
        status="pending",
    )
    db.add(p)
    db.flush()
    db.refresh(p)
    return p


def _core_trait_slot(
    db: Session,
    *,
    owner_id: str,
    name: str = "Brave",
    charge: int = 3,
) -> Slot:
    """Create and flush a core_trait slot for a character."""
    slot = Slot(
        slot_type="core_trait",
        owner_type="character",
        owner_id=owner_id,
        name=name,
        charge=charge,
        is_active=True,
    )
    db.add(slot)
    db.flush()
    db.refresh(slot)
    return slot


def _role_trait_slot(
    db: Session,
    *,
    owner_id: str,
    name: str = "Cunning",
    charge: int = 3,
) -> Slot:
    """Create and flush a role_trait slot for a character."""
    slot = Slot(
        slot_type="role_trait",
        owner_type="character",
        owner_id=owner_id,
        name=name,
        charge=charge,
        is_active=True,
    )
    db.add(slot)
    db.flush()
    db.refresh(slot)
    return slot


def _pc_bond_slot(
    db: Session,
    *,
    owner_id: str,
    name: str = "Test Bond",
    charges: int = 2,
    degradations: int = 0,
) -> Slot:
    """Create and flush a pc_bond slot for a character."""
    slot = Slot(
        slot_type="pc_bond",
        owner_type="character",
        owner_id=owner_id,
        name=name,
        charges=charges,
        degradations=degradations,
        is_trauma=False,
        is_active=True,
    )
    db.add(slot)
    db.flush()
    db.refresh(slot)
    return slot


def _use_skill_effect(
    *,
    skill: str = "awareness",
    skill_level: int = 0,
    trait_ids: list[str] | None = None,
    bond_id: str | None = None,
    plot_spend: int = 0,
) -> dict:
    """Build a minimal calculated_effect for a use_skill proposal."""
    modifiers = []
    trait_charges = []

    for tid in (trait_ids or []):
        modifiers.append({"type": "core_trait", "id": tid, "name": "Trait", "bonus": 1})
        trait_charges.append({"trait_id": tid, "cost": 1})

    if bond_id is not None:
        modifiers.append({"type": "bond", "id": bond_id, "name": "Bond", "bonus": 1})

    dice_pool = skill_level + len(modifiers)
    return {
        "dice_pool": dice_pool,
        "skill": skill,
        "skill_level": skill_level,
        "modifiers": modifiers,
        "plot_spend": plot_spend,
        "costs": {
            "trait_charges": trait_charges,
            "plot": plot_spend,
        },
    }


# ===========================================================================
# POST /proposals/{id}/approve — authentication
# ===========================================================================


class TestApproveProposalAuth:
    """Only the GM may approve proposals."""

    def test_unauthenticated_returns_401(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        p = _pending_proposal(db, character_id=seed_data["pc1"].id)
        db.commit()
        response = client.post(f"/api/v1/proposals/{p.id}/approve", json={})
        assert response.status_code == 401

    def test_player_cannot_approve(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        p = _pending_proposal(db, character_id=seed_data["pc1"].id)
        db.commit()
        auth_as(client, seed_data["player1"])
        response = client.post(f"/api/v1/proposals/{p.id}/approve", json={})
        assert response.status_code == 403

    def test_nonexistent_proposal_returns_404(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = client.post(
            "/api/v1/proposals/01JZZZZZZZZZZZZZZZZZZZZZZZ/approve", json={}
        )
        assert response.status_code == 404


# ===========================================================================
# POST /proposals/{id}/approve — status guard
# ===========================================================================


class TestApproveProposalStatusGuard:
    """Approval is only valid on pending proposals."""

    def test_approved_proposal_returns_409(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        p = _pending_proposal(db, character_id=seed_data["pc1"].id)
        p.status = "approved"
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.post(f"/api/v1/proposals/{p.id}/approve", json={})
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "proposal_not_pending"

    def test_rejected_proposal_returns_409(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        p = _pending_proposal(db, character_id=seed_data["pc1"].id)
        p.status = "rejected"
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.post(f"/api/v1/proposals/{p.id}/approve", json={})
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "proposal_not_pending"


# ===========================================================================
# POST /proposals/{id}/approve — basic happy path
# ===========================================================================


class TestApproveProposalHappyPath:
    """Basic approval for proposals without complex resource deductions."""

    def test_approve_minimal_proposal_returns_200(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Approving a proposal with no resources sets status to approved."""
        p = _pending_proposal(
            db, character_id=seed_data["pc1"].id, action_type="rest"
        )
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.post(f"/api/v1/proposals/{p.id}/approve", json={})
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "approved"
        assert body["event_id"] is not None

    def test_approval_creates_proposal_approved_event(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        p = _pending_proposal(
            db, character_id=seed_data["pc1"].id, action_type="rest"
        )
        db.commit()
        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/proposals/{p.id}/approve", json={})

        db.expire_all()
        event = db.query(Event).filter(Event.proposal_id == p.id).first()
        assert event is not None
        assert event.type == "proposal.approved"
        assert event.actor_type == "gm"
        assert event.visibility == "bonded"

    def test_gm_narrative_overrides_player_narrative(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        p = _pending_proposal(
            db,
            character_id=seed_data["pc1"].id,
            action_type="rest",
            narrative="Player says rest.",
        )
        db.commit()
        auth_as(client, seed_data["gm"])
        client.post(
            f"/api/v1/proposals/{p.id}/approve",
            json={"narrative": "GM says this is how it happened."},
        )

        db.expire_all()
        event = db.query(Event).filter(Event.proposal_id == p.id).first()
        assert event.narrative == "GM says this is how it happened."

    def test_player_narrative_used_when_no_gm_narrative(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        p = _pending_proposal(
            db,
            character_id=seed_data["pc1"].id,
            action_type="rest",
            narrative="Player's description.",
        )
        db.commit()
        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/proposals/{p.id}/approve", json={})

        db.expire_all()
        event = db.query(Event).filter(Event.proposal_id == p.id).first()
        assert event.narrative == "Player's description."

    def test_gm_overrides_stored_on_proposal(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        p = _pending_proposal(
            db, character_id=seed_data["pc1"].id, action_type="rest"
        )
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.post(
            f"/api/v1/proposals/{p.id}/approve",
            json={"gm_overrides": {"custom_field": "value"}},
        )
        assert response.status_code == 200
        assert response.json()["gm_overrides"] == {"custom_field": "value"}


# ===========================================================================
# POST /proposals/{id}/approve — trait charge deduction
# ===========================================================================


class TestApproveProposalTraitCharges:
    """Trait charges are decremented on approval."""

    def test_trait_charge_deducted_on_approval(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        trait = _core_trait_slot(db, owner_id=pc1.id, charge=3)
        effect = _use_skill_effect(trait_ids=[trait.id])
        p = _pending_proposal(
            db,
            character_id=pc1.id,
            action_type="use_skill",
            selections={"skill": "awareness"},
            calculated_effect=effect,
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.post(f"/api/v1/proposals/{p.id}/approve", json={})
        assert response.status_code == 200

        db.expire_all()
        db.refresh(trait)
        assert trait.charge == 2

    def test_two_trait_charges_deducted_when_both_modifiers_used(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        core = _core_trait_slot(db, owner_id=pc1.id, charge=3)
        role = _role_trait_slot(db, owner_id=pc1.id, charge=2)

        modifiers = [
            {"type": "core_trait", "id": core.id, "name": "Brave", "bonus": 1},
            {"type": "role_trait", "id": role.id, "name": "Cunning", "bonus": 1},
        ]
        effect = {
            "dice_pool": 2,
            "skill": "awareness",
            "skill_level": 0,
            "modifiers": modifiers,
            "plot_spend": 0,
            "costs": {
                "trait_charges": [
                    {"trait_id": core.id, "cost": 1},
                    {"trait_id": role.id, "cost": 1},
                ],
                "plot": 0,
            },
        }
        p = _pending_proposal(
            db,
            character_id=pc1.id,
            action_type="use_skill",
            calculated_effect=effect,
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.post(f"/api/v1/proposals/{p.id}/approve", json={})
        assert response.status_code == 200

        db.expire_all()
        db.refresh(core)
        db.refresh(role)
        assert core.charge == 2
        assert role.charge == 1

    def test_trait_charge_changes_recorded_in_event(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        trait = _core_trait_slot(db, owner_id=pc1.id, charge=3)
        effect = _use_skill_effect(trait_ids=[trait.id])
        p = _pending_proposal(
            db,
            character_id=pc1.id,
            action_type="use_skill",
            calculated_effect=effect,
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/proposals/{p.id}/approve", json={})

        db.expire_all()
        event = db.query(Event).filter(Event.proposal_id == p.id).first()
        change_key = f"slot.{trait.id}.charge"
        assert change_key in event.changes
        assert event.changes[change_key]["before"] == 3
        assert event.changes[change_key]["after"] == 2


# ===========================================================================
# POST /proposals/{id}/approve — Plot deduction
# ===========================================================================


class TestApproveProposalPlotDeduction:
    """Plot is deducted on approval."""

    def test_plot_deducted_on_approval(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        pc1.plot = 5
        db.flush()

        effect = _use_skill_effect(plot_spend=2)
        p = _pending_proposal(
            db,
            character_id=pc1.id,
            action_type="use_skill",
            calculated_effect=effect,
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.post(f"/api/v1/proposals/{p.id}/approve", json={})
        assert response.status_code == 200

        db.expire_all()
        db.refresh(pc1)
        assert pc1.plot == 3

    def test_plot_change_recorded_in_event(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        pc1.plot = 5
        db.flush()

        effect = _use_skill_effect(plot_spend=2)
        p = _pending_proposal(
            db,
            character_id=pc1.id,
            action_type="use_skill",
            calculated_effect=effect,
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/proposals/{p.id}/approve", json={})

        db.expire_all()
        event = db.query(Event).filter(Event.proposal_id == p.id).first()
        change_key = f"character.{pc1.id}.plot"
        assert change_key in event.changes
        assert event.changes[change_key]["before"] == 5
        assert event.changes[change_key]["after"] == 3


# ===========================================================================
# POST /proposals/{id}/approve — bond strain
# ===========================================================================


class TestApproveProposalBondStrain:
    """Bond charges are decremented when gm_overrides.bond_strained = true."""

    def test_bond_charges_decremented_on_strain(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        bond = _pc_bond_slot(db, owner_id=pc1.id, charges=2, degradations=0)

        effect = _use_skill_effect(bond_id=bond.id)
        p = _pending_proposal(
            db,
            character_id=pc1.id,
            action_type="use_skill",
            calculated_effect=effect,
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.post(
            f"/api/v1/proposals/{p.id}/approve",
            json={"gm_overrides": {"bond_strained": True}},
        )
        assert response.status_code == 200

        db.expire_all()
        db.refresh(bond)
        assert bond.charges == 1

    def test_bond_strain_change_recorded_in_event(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        bond = _pc_bond_slot(db, owner_id=pc1.id, charges=2, degradations=0)

        effect = _use_skill_effect(bond_id=bond.id)
        p = _pending_proposal(
            db,
            character_id=pc1.id,
            action_type="use_skill",
            calculated_effect=effect,
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        client.post(
            f"/api/v1/proposals/{p.id}/approve",
            json={"gm_overrides": {"bond_strained": True}},
        )

        db.expire_all()
        event = db.query(Event).filter(Event.proposal_id == p.id).first()
        change_key = f"slot.{bond.id}.charges"
        assert change_key in event.changes
        assert event.changes[change_key]["before"] == 2
        assert event.changes[change_key]["after"] == 1

    def test_bond_charges_hits_zero_resets_and_increments_degradations(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """When bond charges reach 0 on strain, degradations increments by 1
        and charges reset to the new effective max (5 - degradations)."""
        pc1 = seed_data["pc1"]
        # charges=1, so -1 hits 0 → degradation triggered.
        # After: degradations=1, charges resets to 5-1=4.
        bond = _pc_bond_slot(db, owner_id=pc1.id, charges=1, degradations=0)

        effect = _use_skill_effect(bond_id=bond.id)
        p = _pending_proposal(
            db,
            character_id=pc1.id,
            action_type="use_skill",
            calculated_effect=effect,
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.post(
            f"/api/v1/proposals/{p.id}/approve",
            json={"gm_overrides": {"bond_strained": True}},
        )
        assert response.status_code == 200

        db.expire_all()
        db.refresh(bond)
        assert bond.degradations == 1
        assert bond.charges == 4  # reset to 5 - 1 degradation

    def test_bond_strain_at_zero_recorded_as_reset_in_event(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        bond = _pc_bond_slot(db, owner_id=pc1.id, charges=1, degradations=0)

        effect = _use_skill_effect(bond_id=bond.id)
        p = _pending_proposal(
            db,
            character_id=pc1.id,
            action_type="use_skill",
            calculated_effect=effect,
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        client.post(
            f"/api/v1/proposals/{p.id}/approve",
            json={"gm_overrides": {"bond_strained": True}},
        )

        db.expire_all()
        event = db.query(Event).filter(Event.proposal_id == p.id).first()
        charges_key = f"slot.{bond.id}.charges"
        deg_key = f"slot.{bond.id}.degradations"
        assert event.changes[charges_key]["after"] == 4  # reset to 5-1
        assert event.changes[deg_key]["before"] == 0
        assert event.changes[deg_key]["after"] == 1

    def test_bond_strain_false_does_not_change_charges(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        bond = _pc_bond_slot(db, owner_id=pc1.id, charges=2, degradations=0)

        effect = _use_skill_effect(bond_id=bond.id)
        p = _pending_proposal(
            db,
            character_id=pc1.id,
            action_type="use_skill",
            calculated_effect=effect,
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.post(
            f"/api/v1/proposals/{p.id}/approve",
            json={"gm_overrides": {"bond_strained": False}},
        )
        assert response.status_code == 200

        db.expire_all()
        db.refresh(bond)
        assert bond.charges == 2  # unchanged


# ===========================================================================
# POST /proposals/{id}/approve — affordability re-validation
# ===========================================================================


class TestApproveProposalAffordability:
    """Resources are re-validated at approval time."""

    def test_insufficient_trait_charge_returns_409(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        trait = _core_trait_slot(db, owner_id=pc1.id, charge=0)  # 0 charges
        effect = _use_skill_effect(trait_ids=[trait.id])
        p = _pending_proposal(
            db,
            character_id=pc1.id,
            action_type="use_skill",
            calculated_effect=effect,
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.post(f"/api/v1/proposals/{p.id}/approve", json={})
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "insufficient_resources"

    def test_insufficient_plot_returns_409(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        pc1.plot = 0
        db.flush()

        effect = _use_skill_effect(plot_spend=2)
        p = _pending_proposal(
            db,
            character_id=pc1.id,
            action_type="use_skill",
            calculated_effect=effect,
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.post(f"/api/v1/proposals/{p.id}/approve", json={})
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "insufficient_resources"

    def test_force_bypasses_insufficient_resources(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        trait = _core_trait_slot(db, owner_id=pc1.id, charge=0)  # 0 charges
        effect = _use_skill_effect(trait_ids=[trait.id])
        p = _pending_proposal(
            db,
            character_id=pc1.id,
            action_type="use_skill",
            calculated_effect=effect,
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.post(
            f"/api/v1/proposals/{p.id}/approve",
            json={"gm_overrides": {"force": True}},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "approved"

    def test_force_still_deducts_available_resources(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Force overrides the check but still applies whatever deductions are possible."""
        pc1 = seed_data["pc1"]
        pc1.plot = 5
        db.flush()
        # trait has 0 charges — force skips check, but plot still gets deducted
        trait = _core_trait_slot(db, owner_id=pc1.id, charge=0)
        effect = _use_skill_effect(trait_ids=[trait.id], plot_spend=2)
        p = _pending_proposal(
            db,
            character_id=pc1.id,
            action_type="use_skill",
            calculated_effect=effect,
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.post(
            f"/api/v1/proposals/{p.id}/approve",
            json={"gm_overrides": {"force": True}},
        )
        assert response.status_code == 200

        db.expire_all()
        db.refresh(pc1)
        assert pc1.plot == 3  # 5 - 2

    def test_insufficient_resources_response_includes_details(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        trait = _core_trait_slot(db, owner_id=pc1.id, charge=0)
        effect = _use_skill_effect(trait_ids=[trait.id])
        p = _pending_proposal(
            db,
            character_id=pc1.id,
            action_type="use_skill",
            calculated_effect=effect,
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.post(f"/api/v1/proposals/{p.id}/approve", json={})
        body = response.json()
        assert "details" in body["error"]
        assert len(body["error"]["details"]) > 0


# ===========================================================================
# POST /proposals/{id}/approve — gm_overrides merge
# ===========================================================================


class TestApproveProposalGmOverrides:
    """GM overrides replace fields in calculated_effect."""

    def test_gm_override_waives_plot_cost(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """If GM sets costs.plot to 0, no plot is deducted."""
        pc1 = seed_data["pc1"]
        pc1.plot = 5
        db.flush()

        effect = _use_skill_effect(plot_spend=3)
        p = _pending_proposal(
            db,
            character_id=pc1.id,
            action_type="use_skill",
            calculated_effect=effect,
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.post(
            f"/api/v1/proposals/{p.id}/approve",
            json={"gm_overrides": {"costs": {"plot": 0, "trait_charges": []}}},
        )
        assert response.status_code == 200

        db.expire_all()
        db.refresh(pc1)
        assert pc1.plot == 5  # unchanged


# ===========================================================================
# POST /proposals/{id}/approve — rider event
# ===========================================================================


class TestApproveProposalRiderEvent:
    """Optional rider event is created atomically with the approval event."""

    def test_rider_event_created_with_parent_link(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        p = _pending_proposal(
            db, character_id=seed_data["pc1"].id, action_type="rest"
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.post(
            f"/api/v1/proposals/{p.id}/approve",
            json={
                "rider_event": {
                    "type": "clock.advanced",
                    "targets": [],
                    "changes": {},
                    "narrative": "The clock ticks forward.",
                    "visibility": "bonded",
                }
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["rider_event_id"] is not None

    def test_rider_event_has_parent_event_id(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        p = _pending_proposal(
            db, character_id=seed_data["pc1"].id, action_type="rest"
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.post(
            f"/api/v1/proposals/{p.id}/approve",
            json={
                "rider_event": {
                    "type": "clock.advanced",
                    "narrative": "Side effect.",
                    "visibility": "public",
                }
            },
        )
        body = response.json()
        rider_id = body["rider_event_id"]
        approval_event_id = body["event_id"]

        db.expire_all()
        rider = db.get(Event, rider_id)
        assert rider is not None
        assert rider.parent_event_id == approval_event_id
        assert rider.type == "clock.advanced"

    def test_no_rider_event_when_omitted(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        p = _pending_proposal(
            db, character_id=seed_data["pc1"].id, action_type="rest"
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.post(f"/api/v1/proposals/{p.id}/approve", json={})
        assert response.status_code == 200
        assert response.json()["rider_event_id"] is None


# ===========================================================================
# POST /proposals/{id}/approve — response shape
# ===========================================================================


class TestApproveProposalResponseShape:
    """Response shape matches ProposalResponse schema."""

    def test_response_has_all_fields(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        p = _pending_proposal(
            db, character_id=seed_data["pc1"].id, action_type="rest"
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.post(f"/api/v1/proposals/{p.id}/approve", json={})
        assert response.status_code == 200
        body = response.json()
        for field in (
            "id",
            "character_id",
            "action_type",
            "origin",
            "narrative",
            "selections",
            "calculated_effect",
            "status",
            "gm_notes",
            "gm_overrides",
            "event_id",
            "rider_event_id",
            "clock_id",
            "created_at",
            "updated_at",
        ):
            assert field in body, f"Missing field: {field}"

        assert body["id"] == p.id
        assert body["status"] == "approved"
        assert body["event_id"] is not None


# ===========================================================================
# POST /proposals/{id}/reject — authentication
# ===========================================================================


class TestRejectProposalAuth:
    """Only the GM may reject proposals."""

    def test_unauthenticated_returns_401(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        p = _pending_proposal(db, character_id=seed_data["pc1"].id)
        db.commit()
        response = client.post(f"/api/v1/proposals/{p.id}/reject", json={})
        assert response.status_code == 401

    def test_player_cannot_reject(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        p = _pending_proposal(db, character_id=seed_data["pc1"].id)
        db.commit()
        auth_as(client, seed_data["player1"])
        response = client.post(f"/api/v1/proposals/{p.id}/reject", json={})
        assert response.status_code == 403

    def test_nonexistent_proposal_returns_404(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = client.post(
            "/api/v1/proposals/01JZZZZZZZZZZZZZZZZZZZZZZZ/reject", json={}
        )
        assert response.status_code == 404


# ===========================================================================
# POST /proposals/{id}/reject — status guard
# ===========================================================================


class TestRejectProposalStatusGuard:
    """Rejection is only valid on pending proposals."""

    def test_approved_proposal_returns_409(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        p = _pending_proposal(db, character_id=seed_data["pc1"].id)
        p.status = "approved"
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.post(f"/api/v1/proposals/{p.id}/reject", json={})
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "proposal_not_pending"

    def test_already_rejected_returns_409(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        p = _pending_proposal(db, character_id=seed_data["pc1"].id)
        p.status = "rejected"
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.post(f"/api/v1/proposals/{p.id}/reject", json={})
        assert response.status_code == 409


# ===========================================================================
# POST /proposals/{id}/reject — happy path
# ===========================================================================


class TestRejectProposalHappyPath:
    """Rejection sets status, stores gm_notes, creates event."""

    def test_reject_minimal_returns_200(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        p = _pending_proposal(db, character_id=seed_data["pc1"].id)
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.post(f"/api/v1/proposals/{p.id}/reject", json={})
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "rejected"

    def test_rejection_note_stored_in_gm_notes(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        p = _pending_proposal(db, character_id=seed_data["pc1"].id)
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.post(
            f"/api/v1/proposals/{p.id}/reject",
            json={"rejection_note": "Needs more detail."},
        )
        assert response.status_code == 200
        assert response.json()["gm_notes"] == "Needs more detail."

    def test_rejection_without_note_gm_notes_is_none(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        p = _pending_proposal(db, character_id=seed_data["pc1"].id)
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.post(f"/api/v1/proposals/{p.id}/reject", json={})
        assert response.status_code == 200
        assert response.json()["gm_notes"] is None

    def test_rejection_creates_proposal_rejected_event(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        p = _pending_proposal(db, character_id=seed_data["pc1"].id)
        db.commit()
        auth_as(client, seed_data["gm"])
        client.post(
            f"/api/v1/proposals/{p.id}/reject",
            json={"rejection_note": "Not this time."},
        )

        db.expire_all()
        event = db.query(Event).filter(Event.proposal_id == p.id).first()
        assert event is not None
        assert event.type == "proposal.rejected"

    def test_rejection_event_is_private(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        p = _pending_proposal(db, character_id=seed_data["pc1"].id)
        db.commit()
        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/proposals/{p.id}/reject", json={})

        db.expire_all()
        event = db.query(Event).filter(Event.proposal_id == p.id).first()
        assert event.visibility == "private"

    def test_rejection_event_actor_is_gm(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        p = _pending_proposal(db, character_id=seed_data["pc1"].id)
        db.commit()
        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/proposals/{p.id}/reject", json={})

        db.expire_all()
        event = db.query(Event).filter(Event.proposal_id == p.id).first()
        assert event.actor_type == "gm"
        assert event.actor_id == seed_data["gm"].id

    def test_rejection_does_not_deduct_resources(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """No resources should be touched on rejection."""
        pc1 = seed_data["pc1"]
        pc1.plot = 5
        db.flush()
        trait = _core_trait_slot(db, owner_id=pc1.id, charge=3)

        effect = _use_skill_effect(trait_ids=[trait.id], plot_spend=2)
        p = _pending_proposal(
            db,
            character_id=pc1.id,
            action_type="use_skill",
            calculated_effect=effect,
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/proposals/{p.id}/reject", json={})

        db.expire_all()
        db.refresh(pc1)
        db.refresh(trait)
        assert pc1.plot == 5  # unchanged
        assert trait.charge == 3  # unchanged

    def test_rejection_response_has_correct_shape(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        p = _pending_proposal(db, character_id=seed_data["pc1"].id)
        db.commit()
        auth_as(client, seed_data["gm"])
        response = client.post(
            f"/api/v1/proposals/{p.id}/reject",
            json={"rejection_note": "Fix this."},
        )
        body = response.json()
        assert body["id"] == p.id
        assert body["status"] == "rejected"
        assert body["gm_notes"] == "Fix this."
        assert body["event_id"] is None  # reject does not set event_id
