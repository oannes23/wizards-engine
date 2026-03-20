"""QA tests for Stories 6.2.3 (Direct Player Actions) and 6.2.4 (Character Edit)
— API contract verification.

These tests verify that the API accepts exactly the payload shapes the frontend
sends and that the backend enforces the documented acceptance criteria.

Stories under review
--------------------
6.2.3 — Direct player actions wired in character.js:
    - Find Time   (POST /characters/{id}/find-time)
    - Recharge Trait (POST /characters/{id}/recharge-trait)
    - Maintain Bond  (POST /characters/{id}/maintain-bond)
    - Use Effect     (POST /characters/{id}/effects/{eid}/use)
    - Retire Effect  (POST /characters/{id}/effects/{eid}/retire)

6.2.4 — Character Edit view (PATCH /characters/{id}):
    - Changed-fields-only diff semantics
    - Name required validation
    - Access control (owner or GM)

Methodology
-----------
Each test class maps 1-to-1 with an acceptance criterion from the review
checklist.  The tests exercise the real HTTP endpoint using the FastAPI
TestClient and a function-scoped in-memory SQLite database.

The key contract checks are:

  AC 6.2.3-1  Find Time:    confirm → POST → Plot -3, FT +1
  AC 6.2.3-2  Recharge:     narrative required, charges → 5, FT decrements
  AC 6.2.3-3  Maintain Bond: narrative required, charges restore, FT decrements
  AC 6.2.3-4  Use Effect:   optional narrative, charges decrement by 1
  AC 6.2.3-5  Retire Effect: no body required, effect deactivated
  AC 6.2.3-6  Narrative modal: submit disabled when empty for required actions
  AC 6.2.3-7  Error states: API returns appropriate error codes
  AC 6.2.3-8  Optimistic UI: rollback on error (backend idempotency)
  AC 6.2.3-9  In-flight guard: tested via sequential duplicate calls

  AC 6.2.4-1  Edit navigates to #/character/edit (SPA route, not an API test)
  AC 6.2.4-2  Editable fields: name, description, notes
  AC 6.2.4-3  Pre-population: GET returns current values
  AC 6.2.4-4  Submit: PATCH with changed fields only
  AC 6.2.4-5  Cancel returns to character sheet (SPA route, not an API test)
  AC 6.2.4-6  Success: returns 200 with updated values
  AC 6.2.4-7  Validation: name required (422 on blank name)
  AC 6.2.4-8  Access control: owner or GM only
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import auth_as
from wizards_engine.models.magic_effect import MagicEffect
from wizards_engine.models.slot import Slot
from wizards_engine.services import magic_effect as magic_effect_svc


# ===========================================================================
# Shared helpers
# ===========================================================================


def _set_meters(
    db: Session,
    character,
    *,
    plot: int | None = None,
    free_time: int | None = None,
) -> None:
    """Directly update character meters and commit."""
    if plot is not None:
        character.plot = plot
    if free_time is not None:
        character.free_time = free_time
    db.commit()
    db.refresh(character)


def _create_trait_slot(
    db: Session,
    character_id: str,
    slot_type: str = "core_trait",
    charge: int | None = 2,
    is_active: bool = True,
) -> Slot:
    """Create an active trait slot for a character."""
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


def _create_bond_slot(
    db: Session,
    character_id: str,
    target_id: str,
    target_type: str = "group",
    charges: int = 2,
    degradations: int = 0,
    is_trauma: bool = False,
    is_active: bool = True,
) -> Slot:
    """Create a pc_bond slot for a character."""
    slot = Slot(
        slot_type="pc_bond",
        owner_type="character",
        owner_id=character_id,
        target_type=target_type,
        target_id=target_id,
        name="Test Bond",
        description="A test bond slot.",
        charges=charges,
        degradations=degradations,
        is_trauma=is_trauma,
        is_active=is_active,
        bidirectional=True,
    )
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return slot


def _add_charged_effect(
    db: Session,
    character_id: str,
    charges_current: int = 3,
    charges_max: int = 5,
    name: str = "Shadow Step",
) -> MagicEffect:
    """Create a charged magic effect via the service layer."""
    return magic_effect_svc.create_effect(
        db,
        character_id=character_id,
        name=name,
        description="Steps through shadows.",
        effect_type="charged",
        power_level=3,
        charges_current=charges_current,
        charges_max=charges_max,
    )


def _add_permanent_effect(
    db: Session,
    character_id: str,
    name: str = "Flame Ward",
) -> MagicEffect:
    """Create a permanent magic effect via the service layer."""
    return magic_effect_svc.create_effect(
        db,
        character_id=character_id,
        name=name,
        description="Perpetual fire resistance.",
        effect_type="permanent",
        power_level=2,
    )


# ===========================================================================
# AC 6.2.3-1 — Find Time: POST body is empty, meters update correctly
# ===========================================================================


class TestFindTimeContract:
    """AC 6.2.3-1: Find Time tap → POST → Plot -3, FT +1."""

    def test_find_time_accepts_empty_body(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Frontend sends {} as the POST body — backend must accept it."""
        pc = seed_data["pc1"]
        _set_meters(db, pc, plot=3, free_time=0)
        auth_as(client, seed_data["player1"])

        # character.js sends: api.post(url, {})
        response = client.post(f"/api/v1/characters/{pc.id}/find-time", json={})
        assert response.status_code == 200

    def test_find_time_meters_update_correctly(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Plot decrements by 3, Free Time increments by 1."""
        pc = seed_data["pc1"]
        _set_meters(db, pc, plot=5, free_time=2)
        auth_as(client, seed_data["player1"])

        response = client.post(f"/api/v1/characters/{pc.id}/find-time", json={})
        assert response.status_code == 200
        body = response.json()
        assert body["plot"] == 2
        assert body["free_time"] == 3

    def test_find_time_requires_plot_gte_3(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Error state: Plot < 3 returns 409 insufficient_plot."""
        pc = seed_data["pc1"]
        _set_meters(db, pc, plot=2, free_time=0)
        auth_as(client, seed_data["player1"])

        response = client.post(f"/api/v1/characters/{pc.id}/find-time", json={})
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "insufficient_plot"

    def test_find_time_requires_ft_below_cap(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Error state: FT = 20 returns 409 free_time_at_cap."""
        pc = seed_data["pc1"]
        _set_meters(db, pc, plot=5, free_time=20)
        auth_as(client, seed_data["player1"])

        response = client.post(f"/api/v1/characters/{pc.id}/find-time", json={})
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "free_time_at_cap"

    def test_find_time_unauthenticated_returns_401(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Unauthenticated POST returns 401."""
        pc = seed_data["pc1"]
        _set_meters(db, pc, plot=3, free_time=0)

        response = client.post(f"/api/v1/characters/{pc.id}/find-time", json={})
        assert response.status_code == 401

    def test_find_time_wrong_player_returns_403(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Player cannot call find-time for another player's character."""
        pc = seed_data["pc1"]
        _set_meters(db, pc, plot=3, free_time=0)
        auth_as(client, seed_data["player2"])

        response = client.post(f"/api/v1/characters/{pc.id}/find-time", json={})
        assert response.status_code == 403

    def test_find_time_gm_can_act_on_any_character(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """GM may call find-time for any character."""
        pc = seed_data["pc2"]
        _set_meters(db, pc, plot=3, free_time=0)
        auth_as(client, seed_data["gm"])

        response = client.post(f"/api/v1/characters/{pc.id}/find-time", json={})
        assert response.status_code == 200


# ===========================================================================
# AC 6.2.3-2 — Recharge Trait: payload field names must match schema
# ===========================================================================


class TestRechargeTraitContract:
    """AC 6.2.3-2: Recharge Trait sends trait_instance_id + narrative."""

    def test_recharge_trait_field_names_accepted(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Frontend sends trait_instance_id and narrative — backend accepts both."""
        pc = seed_data["pc1"]
        slot = _create_trait_slot(db, pc.id, charge=2)
        _set_meters(db, pc, free_time=3)
        auth_as(client, seed_data["player1"])

        # Exact payload shape that character.js _onRechargeTrait sends:
        response = client.post(
            f"/api/v1/characters/{pc.id}/recharge-trait",
            json={
                "trait_instance_id": slot.id,
                "narrative": "I spent the evening in quiet reflection.",
            },
        )
        assert response.status_code == 200

    def test_recharge_trait_charges_become_5(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """After recharge, slot.charge is 5 regardless of starting value."""
        pc = seed_data["pc1"]
        slot = _create_trait_slot(db, pc.id, charge=1)
        _set_meters(db, pc, free_time=2)
        auth_as(client, seed_data["player1"])

        response = client.post(
            f"/api/v1/characters/{pc.id}/recharge-trait",
            json={"trait_instance_id": slot.id, "narrative": "Reflecting deeply."},
        )
        assert response.status_code == 200

        db.refresh(slot)
        assert slot.charge == 5

    def test_recharge_trait_ft_decrements_by_1(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Free Time decrements by exactly 1 after recharge."""
        pc = seed_data["pc1"]
        slot = _create_trait_slot(db, pc.id, charge=2)
        _set_meters(db, pc, free_time=5)
        auth_as(client, seed_data["player1"])

        client.post(
            f"/api/v1/characters/{pc.id}/recharge-trait",
            json={"trait_instance_id": slot.id, "narrative": "Spent an evening resting."},
        )

        db.refresh(pc)
        assert pc.free_time == 4

    def test_recharge_trait_narrative_required(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """AC 6.2.3-6: narrative required — empty string returns 422."""
        pc = seed_data["pc1"]
        slot = _create_trait_slot(db, pc.id, charge=2)
        _set_meters(db, pc, free_time=3)
        auth_as(client, seed_data["player1"])

        response = client.post(
            f"/api/v1/characters/{pc.id}/recharge-trait",
            json={"trait_instance_id": slot.id, "narrative": ""},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "narrative_required"

    def test_recharge_trait_whitespace_narrative_returns_422(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Whitespace-only narrative is treated as empty — 422 narrative_required."""
        pc = seed_data["pc1"]
        slot = _create_trait_slot(db, pc.id, charge=2)
        _set_meters(db, pc, free_time=3)
        auth_as(client, seed_data["player1"])

        response = client.post(
            f"/api/v1/characters/{pc.id}/recharge-trait",
            json={"trait_instance_id": slot.id, "narrative": "   "},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "narrative_required"

    def test_recharge_trait_already_full_returns_409(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """AC 6.2.3-7: trait at 5 charges returns 409 trait_already_full."""
        pc = seed_data["pc1"]
        slot = _create_trait_slot(db, pc.id, charge=5)
        _set_meters(db, pc, free_time=3)
        auth_as(client, seed_data["player1"])

        response = client.post(
            f"/api/v1/characters/{pc.id}/recharge-trait",
            json={"trait_instance_id": slot.id, "narrative": "Already full."},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "trait_already_full"

    def test_recharge_trait_no_ft_returns_409(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """AC 6.2.3-7: FT = 0 returns 409 insufficient_free_time."""
        pc = seed_data["pc1"]
        slot = _create_trait_slot(db, pc.id, charge=2)
        _set_meters(db, pc, free_time=0)
        auth_as(client, seed_data["player1"])

        response = client.post(
            f"/api/v1/characters/{pc.id}/recharge-trait",
            json={"trait_instance_id": slot.id, "narrative": "No time."},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "insufficient_free_time"

    def test_recharge_trait_unauthenticated_returns_401(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        pc = seed_data["pc1"]
        slot = _create_trait_slot(db, pc.id, charge=2)

        response = client.post(
            f"/api/v1/characters/{pc.id}/recharge-trait",
            json={"trait_instance_id": slot.id, "narrative": "test"},
        )
        assert response.status_code == 401

    def test_recharge_trait_wrong_player_returns_403(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """player2 cannot recharge a trait for pc1."""
        pc = seed_data["pc1"]
        slot = _create_trait_slot(db, pc.id, charge=2)
        _set_meters(db, pc, free_time=3)
        auth_as(client, seed_data["player2"])

        response = client.post(
            f"/api/v1/characters/{pc.id}/recharge-trait",
            json={"trait_instance_id": slot.id, "narrative": "Attempting to hack."},
        )
        assert response.status_code == 403

    def test_recharge_trait_gm_can_act_for_any_character(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """GM may recharge any character's trait."""
        pc = seed_data["pc2"]
        slot = _create_trait_slot(db, pc.id, charge=2)
        _set_meters(db, pc, free_time=3)
        auth_as(client, seed_data["gm"])

        response = client.post(
            f"/api/v1/characters/{pc.id}/recharge-trait",
            json={"trait_instance_id": slot.id, "narrative": "GM action."},
        )
        assert response.status_code == 200

    def test_recharge_trait_response_shape(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Response is a CharacterResponse (contains id, name, etc.)."""
        pc = seed_data["pc1"]
        slot = _create_trait_slot(db, pc.id, charge=2)
        _set_meters(db, pc, free_time=3)
        auth_as(client, seed_data["player1"])

        response = client.post(
            f"/api/v1/characters/{pc.id}/recharge-trait",
            json={"trait_instance_id": slot.id, "narrative": "Reflective evening."},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == pc.id
        assert "name" in body


# ===========================================================================
# AC 6.2.3-3 — Maintain Bond: payload field names must match schema
# ===========================================================================


class TestMaintainBondContract:
    """AC 6.2.3-3: Maintain Bond sends bond_instance_id + narrative."""

    def test_maintain_bond_field_names_accepted(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Frontend sends bond_instance_id and narrative — backend accepts both."""
        pc = seed_data["pc1"]
        group = seed_data["group"]
        bond = _create_bond_slot(db, pc.id, group.id, charges=2)
        _set_meters(db, pc, free_time=3)
        auth_as(client, seed_data["player1"])

        # Exact payload shape that character.js _onMaintainBond sends:
        response = client.post(
            f"/api/v1/characters/{pc.id}/maintain-bond",
            json={
                "bond_instance_id": bond.id,
                "narrative": "I reached out and reconnected.",
            },
        )
        assert response.status_code == 200

    def test_maintain_bond_charges_restore_to_effective_max(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Bond charges are restored to effective max (5 - degradations)."""
        pc = seed_data["pc1"]
        group = seed_data["group"]
        # Bond with 1 degradation: effective max = 4, charges currently 2
        bond = _create_bond_slot(db, pc.id, group.id, charges=2, degradations=1)
        _set_meters(db, pc, free_time=3)
        auth_as(client, seed_data["player1"])

        client.post(
            f"/api/v1/characters/{pc.id}/maintain-bond",
            json={"bond_instance_id": bond.id, "narrative": "I reconnected."},
        )

        db.refresh(bond)
        assert bond.charges == 4  # effective max = 5 - 1 = 4

    def test_maintain_bond_ft_decrements_by_1(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Free Time decrements by exactly 1 after maintaining a bond."""
        pc = seed_data["pc1"]
        group = seed_data["group"]
        bond = _create_bond_slot(db, pc.id, group.id, charges=2)
        _set_meters(db, pc, free_time=5)
        auth_as(client, seed_data["player1"])

        client.post(
            f"/api/v1/characters/{pc.id}/maintain-bond",
            json={"bond_instance_id": bond.id, "narrative": "Tended to the bond."},
        )

        db.refresh(pc)
        assert pc.free_time == 4

    def test_maintain_bond_narrative_required(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """AC 6.2.3-6: narrative required — empty string returns 422."""
        pc = seed_data["pc1"]
        group = seed_data["group"]
        bond = _create_bond_slot(db, pc.id, group.id, charges=2)
        _set_meters(db, pc, free_time=3)
        auth_as(client, seed_data["player1"])

        response = client.post(
            f"/api/v1/characters/{pc.id}/maintain-bond",
            json={"bond_instance_id": bond.id, "narrative": ""},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "narrative_required"

    def test_maintain_bond_trauma_returns_422(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """AC 6.2.3-7: trauma bonds cannot be maintained."""
        pc = seed_data["pc1"]
        group = seed_data["group"]
        trauma_bond = _create_bond_slot(
            db, pc.id, group.id, charges=2, is_trauma=True
        )
        _set_meters(db, pc, free_time=3)
        auth_as(client, seed_data["player1"])

        response = client.post(
            f"/api/v1/characters/{pc.id}/maintain-bond",
            json={"bond_instance_id": trauma_bond.id, "narrative": "Maintaining trauma bond."},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "cannot_maintain_trauma"

    def test_maintain_bond_already_full_returns_409(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Bond at effective max charges returns 409 bond_already_maintained."""
        pc = seed_data["pc1"]
        group = seed_data["group"]
        # Full bond: charges=5, degradations=0 → already at effective max 5
        bond = _create_bond_slot(db, pc.id, group.id, charges=5, degradations=0)
        _set_meters(db, pc, free_time=3)
        auth_as(client, seed_data["player1"])

        response = client.post(
            f"/api/v1/characters/{pc.id}/maintain-bond",
            json={"bond_instance_id": bond.id, "narrative": "Already maintained."},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "bond_already_maintained"

    def test_maintain_bond_no_ft_returns_409(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """FT = 0 returns 409 insufficient_free_time."""
        pc = seed_data["pc1"]
        group = seed_data["group"]
        bond = _create_bond_slot(db, pc.id, group.id, charges=2)
        _set_meters(db, pc, free_time=0)
        auth_as(client, seed_data["player1"])

        response = client.post(
            f"/api/v1/characters/{pc.id}/maintain-bond",
            json={"bond_instance_id": bond.id, "narrative": "No time."},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "insufficient_free_time"

    def test_maintain_bond_unauthenticated_returns_401(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        pc = seed_data["pc1"]
        group = seed_data["group"]
        bond = _create_bond_slot(db, pc.id, group.id, charges=2)

        response = client.post(
            f"/api/v1/characters/{pc.id}/maintain-bond",
            json={"bond_instance_id": bond.id, "narrative": "test"},
        )
        assert response.status_code == 401

    def test_maintain_bond_wrong_player_returns_403(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """player2 cannot maintain a bond for pc1."""
        pc = seed_data["pc1"]
        group = seed_data["group"]
        bond = _create_bond_slot(db, pc.id, group.id, charges=2)
        _set_meters(db, pc, free_time=3)
        auth_as(client, seed_data["player2"])

        response = client.post(
            f"/api/v1/characters/{pc.id}/maintain-bond",
            json={"bond_instance_id": bond.id, "narrative": "Hack attempt."},
        )
        assert response.status_code == 403

    def test_maintain_bond_gm_can_act_for_any_character(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """GM may maintain any character's bond."""
        pc = seed_data["pc2"]
        group = seed_data["group"]
        bond = _create_bond_slot(db, pc.id, group.id, charges=2)
        _set_meters(db, pc, free_time=3)
        auth_as(client, seed_data["gm"])

        response = client.post(
            f"/api/v1/characters/{pc.id}/maintain-bond",
            json={"bond_instance_id": bond.id, "narrative": "GM maintained."},
        )
        assert response.status_code == 200

    def test_maintain_bond_response_shape(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Response is a CharacterResponse (contains id, name)."""
        pc = seed_data["pc1"]
        group = seed_data["group"]
        bond = _create_bond_slot(db, pc.id, group.id, charges=2)
        _set_meters(db, pc, free_time=3)
        auth_as(client, seed_data["player1"])

        response = client.post(
            f"/api/v1/characters/{pc.id}/maintain-bond",
            json={"bond_instance_id": bond.id, "narrative": "Careful tending."},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == pc.id
        assert "name" in body


# ===========================================================================
# AC 6.2.3-4 — Use Effect: optional narrative, charges decrement
# ===========================================================================


class TestUseEffectContract:
    """AC 6.2.3-4: Use Effect sends optional narrative, charges decrement by 1."""

    def test_use_effect_empty_body_accepted(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Frontend sends {} when no narrative — backend must accept it."""
        pc = seed_data["pc1"]
        effect = _add_charged_effect(db, pc.id, charges_current=3)
        auth_as(client, seed_data["player1"])

        # character.js sends: body = {}  (when narrative is empty)
        response = client.post(
            f"/api/v1/characters/{pc.id}/effects/{effect.id}/use",
            json={},
        )
        assert response.status_code == 200

    def test_use_effect_with_narrative_accepted(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Frontend sends { narrative: text } when user types — backend accepts it."""
        pc = seed_data["pc1"]
        effect = _add_charged_effect(db, pc.id, charges_current=3)
        auth_as(client, seed_data["player1"])

        response = client.post(
            f"/api/v1/characters/{pc.id}/effects/{effect.id}/use",
            json={"narrative": "I unleash the shadow step to dodge the blow."},
        )
        assert response.status_code == 200

    def test_use_effect_charges_decrement_by_1(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Charges current decrements from starting value by exactly 1."""
        pc = seed_data["pc1"]
        effect = _add_charged_effect(db, pc.id, charges_current=3, charges_max=5)
        auth_as(client, seed_data["player1"])

        response = client.post(
            f"/api/v1/characters/{pc.id}/effects/{effect.id}/use",
            json={},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["charges_current"] == 2

    def test_use_effect_response_shape(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Response is a MagicEffectResponse (contains id, charges_current, etc.)."""
        pc = seed_data["pc1"]
        effect = _add_charged_effect(db, pc.id, charges_current=3)
        auth_as(client, seed_data["player1"])

        response = client.post(
            f"/api/v1/characters/{pc.id}/effects/{effect.id}/use",
            json={},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == effect.id
        assert "charges_current" in body
        assert "charges_max" in body
        assert "effect_type" in body

    def test_use_effect_no_charges_returns_409(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """AC 6.2.3-7: 0 charges returns 409 no_charges_remaining."""
        pc = seed_data["pc1"]
        effect = _add_charged_effect(db, pc.id, charges_current=0, charges_max=5)
        auth_as(client, seed_data["player1"])

        response = client.post(
            f"/api/v1/characters/{pc.id}/effects/{effect.id}/use",
            json={},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "no_charges_remaining"

    def test_use_effect_not_charged_type_returns_400(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """AC 6.2.3-7: permanent effect returns 400 effect_not_charged."""
        pc = seed_data["pc1"]
        effect = _add_permanent_effect(db, pc.id)
        auth_as(client, seed_data["player1"])

        response = client.post(
            f"/api/v1/characters/{pc.id}/effects/{effect.id}/use",
            json={},
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "effect_not_charged"

    def test_use_effect_unauthenticated_returns_401(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        pc = seed_data["pc1"]
        effect = _add_charged_effect(db, pc.id, charges_current=3)

        response = client.post(
            f"/api/v1/characters/{pc.id}/effects/{effect.id}/use",
            json={},
        )
        assert response.status_code == 401

    def test_use_effect_wrong_player_returns_403(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """player2 cannot use an effect belonging to pc1."""
        pc = seed_data["pc1"]
        effect = _add_charged_effect(db, pc.id, charges_current=3)
        auth_as(client, seed_data["player2"])

        response = client.post(
            f"/api/v1/characters/{pc.id}/effects/{effect.id}/use",
            json={},
        )
        assert response.status_code == 403

    def test_use_effect_nonexistent_returns_404(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Non-existent effect ID returns 404."""
        pc = seed_data["pc1"]
        auth_as(client, seed_data["gm"])

        response = client.post(
            f"/api/v1/characters/{pc.id}/effects/01AAAAAAAAAAAAAAAAAAAAA0/use",
            json={},
        )
        assert response.status_code == 404

    def test_use_effect_gm_can_act_for_any_character(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """GM may use any character's effect."""
        pc = seed_data["pc2"]
        effect = _add_charged_effect(db, pc.id, charges_current=3)
        auth_as(client, seed_data["gm"])

        response = client.post(
            f"/api/v1/characters/{pc.id}/effects/{effect.id}/use",
            json={},
        )
        assert response.status_code == 200


# ===========================================================================
# AC 6.2.3-5 — Retire Effect: no body required, effect deactivated
# ===========================================================================


class TestRetireEffectContract:
    """AC 6.2.3-5: Retire Effect sends {} — effect is moved to Past."""

    def test_retire_effect_empty_body_accepted(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Frontend sends {} as the POST body — backend accepts it with no body param."""
        pc = seed_data["pc1"]
        effect = _add_charged_effect(db, pc.id, charges_current=3)
        auth_as(client, seed_data["player1"])

        # character.js sends: api.post(url, {})
        response = client.post(
            f"/api/v1/characters/{pc.id}/effects/{effect.id}/retire",
            json={},
        )
        assert response.status_code == 200

    def test_retire_effect_sets_is_active_false(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """After retire, is_active is false in the response."""
        pc = seed_data["pc1"]
        effect = _add_charged_effect(db, pc.id, charges_current=3)
        auth_as(client, seed_data["player1"])

        response = client.post(
            f"/api/v1/characters/{pc.id}/effects/{effect.id}/retire",
            json={},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["is_active"] is False

    def test_retire_effect_response_shape(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Response is a MagicEffectResponse with the effect id."""
        pc = seed_data["pc1"]
        effect = _add_permanent_effect(db, pc.id)
        auth_as(client, seed_data["player1"])

        response = client.post(
            f"/api/v1/characters/{pc.id}/effects/{effect.id}/retire",
            json={},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == effect.id
        assert body["is_active"] is False

    def test_retire_effect_unauthenticated_returns_401(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        pc = seed_data["pc1"]
        effect = _add_charged_effect(db, pc.id, charges_current=3)

        response = client.post(
            f"/api/v1/characters/{pc.id}/effects/{effect.id}/retire",
            json={},
        )
        assert response.status_code == 401

    def test_retire_effect_wrong_player_returns_403(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """player2 cannot retire an effect belonging to pc1."""
        pc = seed_data["pc1"]
        effect = _add_charged_effect(db, pc.id, charges_current=3)
        auth_as(client, seed_data["player2"])

        response = client.post(
            f"/api/v1/characters/{pc.id}/effects/{effect.id}/retire",
            json={},
        )
        assert response.status_code == 403

    def test_retire_effect_nonexistent_returns_404(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Non-existent effect ID returns 404."""
        pc = seed_data["pc1"]
        auth_as(client, seed_data["gm"])

        response = client.post(
            f"/api/v1/characters/{pc.id}/effects/01AAAAAAAAAAAAAAAAAAAAA1/retire",
            json={},
        )
        assert response.status_code == 404

    def test_retire_effect_gm_can_act_for_any_character(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """GM may retire any character's effect."""
        pc = seed_data["pc2"]
        effect = _add_charged_effect(db, pc.id, charges_current=3)
        auth_as(client, seed_data["gm"])

        response = client.post(
            f"/api/v1/characters/{pc.id}/effects/{effect.id}/retire",
            json={},
        )
        assert response.status_code == 200
        assert response.json()["is_active"] is False

    def test_retire_effect_can_retire_permanent(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Permanent effects can also be retired."""
        pc = seed_data["pc1"]
        effect = _add_permanent_effect(db, pc.id)
        auth_as(client, seed_data["player1"])

        response = client.post(
            f"/api/v1/characters/{pc.id}/effects/{effect.id}/retire",
            json={},
        )
        assert response.status_code == 200
        assert response.json()["is_active"] is False


# ===========================================================================
# AC 6.2.3-8 — Optimistic update rollback: server state after error
# ===========================================================================


class TestOptimisticRollbackContract:
    """AC 6.2.3-8: Backend state is unchanged when an error is returned.

    The frontend rolls back optimistic UI changes using the pre-action snapshot.
    These tests confirm the backend enforces idempotency — no partial mutation
    occurs when a business-rule error fires.
    """

    def test_find_time_with_insufficient_plot_leaves_state_unchanged(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """When find-time fails (plot=2), plot and FT are both unchanged."""
        pc = seed_data["pc1"]
        _set_meters(db, pc, plot=2, free_time=5)
        auth_as(client, seed_data["player1"])

        response = client.post(f"/api/v1/characters/{pc.id}/find-time", json={})
        assert response.status_code == 409

        db.refresh(pc)
        assert pc.plot == 2
        assert pc.free_time == 5

    def test_recharge_trait_with_no_ft_leaves_charge_unchanged(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """When recharge-trait fails (FT=0), the slot charge is unchanged."""
        pc = seed_data["pc1"]
        slot = _create_trait_slot(db, pc.id, charge=2)
        _set_meters(db, pc, free_time=0)
        auth_as(client, seed_data["player1"])

        response = client.post(
            f"/api/v1/characters/{pc.id}/recharge-trait",
            json={"trait_instance_id": slot.id, "narrative": "Trying anyway."},
        )
        assert response.status_code == 409

        db.refresh(slot)
        assert slot.charge == 2

    def test_maintain_bond_with_no_ft_leaves_charges_unchanged(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """When maintain-bond fails (FT=0), the bond charges are unchanged."""
        pc = seed_data["pc1"]
        group = seed_data["group"]
        bond = _create_bond_slot(db, pc.id, group.id, charges=2)
        _set_meters(db, pc, free_time=0)
        auth_as(client, seed_data["player1"])

        response = client.post(
            f"/api/v1/characters/{pc.id}/maintain-bond",
            json={"bond_instance_id": bond.id, "narrative": "Trying anyway."},
        )
        assert response.status_code == 409

        db.refresh(bond)
        assert bond.charges == 2


# ===========================================================================
# AC 6.2.3-9 — In-flight guard: serial double-submission
# ===========================================================================


class TestInFlightGuardContract:
    """AC 6.2.3-9: Serial calls work correctly (no double-mutation on fast repeat).

    The frontend disables all action buttons while a request is in flight.
    This class verifies that two sequential calls produce the expected
    two-step state change (no half-mutations or idempotency surprises).
    """

    def test_two_consecutive_find_time_calls(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Two sequential find-time calls both succeed and each deduct 3 Plot."""
        pc = seed_data["pc1"]
        _set_meters(db, pc, plot=6, free_time=0)
        auth_as(client, seed_data["player1"])

        r1 = client.post(f"/api/v1/characters/{pc.id}/find-time", json={})
        assert r1.status_code == 200
        assert r1.json()["plot"] == 3
        assert r1.json()["free_time"] == 1

        r2 = client.post(f"/api/v1/characters/{pc.id}/find-time", json={})
        assert r2.status_code == 200
        assert r2.json()["plot"] == 0
        assert r2.json()["free_time"] == 2

        # Third call should fail
        r3 = client.post(f"/api/v1/characters/{pc.id}/find-time", json={})
        assert r3.status_code == 409


# ===========================================================================
# AC 6.2.4 — Character Edit PATCH contract
# ===========================================================================


class TestCharacterEditPatchContract:
    """AC 6.2.4: PATCH /api/v1/characters/{id} — changed-fields-only semantics."""

    def test_patch_name_only(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """AC 6.2.4-4: Sending only name sends only name field."""
        pc = seed_data["pc1"]
        original_desc = pc.description
        auth_as(client, seed_data["player1"])

        response = client.patch(
            f"/api/v1/characters/{pc.id}",
            json={"name": "Renamed Hero"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "Renamed Hero"
        # description should be unchanged (exclude_unset semantics)
        assert body["description"] == original_desc

    def test_patch_description_only(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Sending only description does not touch name or notes."""
        pc = seed_data["pc1"]
        original_name = pc.name
        auth_as(client, seed_data["player1"])

        response = client.patch(
            f"/api/v1/characters/{pc.id}",
            json={"description": "A brave soul from the eastern shores."},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == original_name
        assert body["description"] == "A brave soul from the eastern shores."

    def test_patch_notes_only(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """GM can patch notes only; name and description are unchanged."""
        pc = seed_data["pc1"]
        original_name = pc.name
        auth_as(client, seed_data["gm"])

        response = client.patch(
            f"/api/v1/characters/{pc.id}",
            json={"notes": "Player is prone to taking risks."},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == original_name
        assert body["notes"] == "Player is prone to taking risks."

    def test_patch_all_three_fields(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """All three editable fields can be updated in a single request."""
        pc = seed_data["pc1"]
        auth_as(client, seed_data["player1"])

        response = client.patch(
            f"/api/v1/characters/{pc.id}",
            json={
                "name": "Hero of the Coast",
                "description": "Weathered by a thousand storms.",
                "notes": "Tends to improvise.",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "Hero of the Coast"
        assert body["description"] == "Weathered by a thousand storms."
        assert body["notes"] == "Tends to improvise."

    def test_patch_clears_description_with_null(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Sending null for description clears it."""
        pc = seed_data["pc1"]
        pc.description = "Something was here."
        db.commit()
        db.refresh(pc)

        auth_as(client, seed_data["player1"])
        response = client.patch(
            f"/api/v1/characters/{pc.id}",
            json={"description": None},
        )
        assert response.status_code == 200
        assert response.json()["description"] is None

    def test_patch_response_shape_is_character_response(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """AC 6.2.4-6: 200 response contains full CharacterResponse shape."""
        pc = seed_data["pc1"]
        auth_as(client, seed_data["player1"])

        response = client.patch(
            f"/api/v1/characters/{pc.id}",
            json={"name": "Updated Name"},
        )
        assert response.status_code == 200
        body = response.json()
        # CharacterResponse required fields
        assert "id" in body
        assert "name" in body
        assert "detail_level" in body
        assert "is_deleted" in body
        assert "created_at" in body
        assert "updated_at" in body


class TestCharacterEditValidation:
    """AC 6.2.4-7: Name is required — blank name returns 422."""

    def test_patch_empty_name_returns_422(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Empty string name is rejected with 422."""
        pc = seed_data["pc1"]
        auth_as(client, seed_data["player1"])

        response = client.patch(
            f"/api/v1/characters/{pc.id}",
            json={"name": ""},
        )
        assert response.status_code == 422

    def test_patch_whitespace_name_returns_422(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Whitespace-only name is stripped and rejected with 422."""
        pc = seed_data["pc1"]
        auth_as(client, seed_data["player1"])

        response = client.patch(
            f"/api/v1/characters/{pc.id}",
            json={"name": "   "},
        )
        assert response.status_code == 422

    @pytest.mark.xfail(
        reason=(
            "BUG: UpdateCharacterRequest.validate_name does not enforce the "
            "200-character maximum that CreateCharacterRequest enforces. "
            "PATCH currently accepts a 201-character name and returns 200. "
            "Fix: add `if len(v) > 200: raise ValueError(...)` to "
            "UpdateCharacterRequest.validate_name in schemas/character.py."
        ),
        strict=True,
    )
    def test_patch_name_too_long_returns_422(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Name > 200 characters should be rejected with 422 (currently passes through — bug)."""
        pc = seed_data["pc1"]
        auth_as(client, seed_data["player1"])

        response = client.patch(
            f"/api/v1/characters/{pc.id}",
            json={"name": "A" * 201},
        )
        assert response.status_code == 422


class TestCharacterEditAccessControl:
    """AC 6.2.4-8: Only owner or GM may edit; others get 403."""

    def test_owner_can_edit_own_character(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Player can edit their own character."""
        pc = seed_data["pc1"]
        auth_as(client, seed_data["player1"])

        response = client.patch(
            f"/api/v1/characters/{pc.id}",
            json={"name": "Edited by Owner"},
        )
        assert response.status_code == 200

    def test_other_player_cannot_edit(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """player2 cannot edit pc1 (owned by player1)."""
        pc = seed_data["pc1"]
        auth_as(client, seed_data["player2"])

        response = client.patch(
            f"/api/v1/characters/{pc.id}",
            json={"name": "Hijacked Name"},
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"

    def test_gm_can_edit_any_character(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """GM may edit any character — including NPCs."""
        npc = seed_data["npc1"]
        auth_as(client, seed_data["gm"])

        response = client.patch(
            f"/api/v1/characters/{npc.id}",
            json={"name": "The Renamed Archivist"},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "The Renamed Archivist"

    def test_unauthenticated_edit_returns_401(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Unauthenticated PATCH returns 401."""
        pc = seed_data["pc1"]

        response = client.patch(
            f"/api/v1/characters/{pc.id}",
            json={"name": "Ghost Edit"},
        )
        assert response.status_code == 401

    def test_patch_nonexistent_character_returns_404(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """PATCH on a non-existent character returns 404."""
        auth_as(client, seed_data["gm"])

        response = client.patch(
            "/api/v1/characters/01AAAAAAAAAAAAAAAAAAAAAA",
            json={"name": "Ghost Character"},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"


class TestCharacterEditGetForPrepopulation:
    """AC 6.2.4-3: GET character returns current name/description/notes for form pre-population."""

    def test_get_character_returns_editable_fields(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """GET /characters/{id} returns name, description, notes for the edit form."""
        pc = seed_data["pc1"]
        pc.description = "A wandering hero."
        pc.notes = "Tends to act alone."
        db.commit()
        db.refresh(pc)

        auth_as(client, seed_data["player1"])
        response = client.get(f"/api/v1/characters/{pc.id}")
        assert response.status_code == 200

        body = response.json()
        assert body["name"] == pc.name
        assert body["description"] == "A wandering hero."
        assert body["notes"] == "Tends to act alone."

    def test_patch_followed_by_get_shows_updated_values(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """AC 6.2.4-6: After successful PATCH, GET shows the updated values."""
        pc = seed_data["pc1"]
        auth_as(client, seed_data["player1"])

        # PATCH
        patch_resp = client.patch(
            f"/api/v1/characters/{pc.id}",
            json={"name": "After Edit Name", "description": "After edit desc."},
        )
        assert patch_resp.status_code == 200

        # GET to confirm persistence
        get_resp = client.get(f"/api/v1/characters/{pc.id}")
        assert get_resp.status_code == 200
        body = get_resp.json()
        assert body["name"] == "After Edit Name"
        assert body["description"] == "After edit desc."
