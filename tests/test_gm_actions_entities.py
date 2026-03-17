"""Integration tests for Story 4.2.2 — GM Bond/Trait/Effect/XP actions.

Covers POST /api/v1/gm/actions for the following action types:
- create_bond
- modify_bond
- retire_bond
- create_trait
- modify_trait
- retire_trait
- create_effect
- modify_effect
- retire_effect
- award_xp

Each action type has a happy-path test and error-case tests.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import auth_as
from wizards_engine.models.magic_effect import MagicEffect
from wizards_engine.models.slot import Slot, TraitTemplate


# ===========================================================================
# Helpers
# ===========================================================================


def _post(client: TestClient, body: dict) -> "Response":  # type: ignore[name-defined]
    """POST to /api/v1/gm/actions."""
    return client.post("/api/v1/gm/actions", json=body)


# ===========================================================================
# create_bond
# ===========================================================================


class TestCreateBond:
    """GM create_bond action."""

    def test_create_bond_happy_path(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        pc2 = seed_data["pc2"]
        auth_as(client, seed_data["gm"])

        response = _post(
            client,
            {
                "action_type": "create_bond",
                "owner_type": "character",
                "owner_id": pc1.id,
                "target_type": "character",
                "target_id": pc2.id,
                "source_label": "My ally",
                "target_label": "Their ally",
                "description": "A new bond.",
                "visibility": "bonded",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["type"] == "bond.created"
        assert body["actor_type"] == "gm"
        assert len(body["created_objects"]) == 1
        assert body["created_objects"][0]["type"] == "slot"

        # Verify the slot was persisted.
        bond_id = body["created_objects"][0]["id"]
        bond = db.get(Slot, bond_id)
        assert bond is not None
        assert bond.owner_id == pc1.id
        assert bond.target_id == pc2.id
        assert bond.slot_type == "pc_bond"
        assert bond.source_label == "My ally"
        assert bond.is_active is True
        # PC bonds start with stress=5.
        assert bond.stress == 5

    def test_create_bond_bidirectional_override(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc3 = seed_data["pc3"]
        region = seed_data["region"]
        auth_as(client, seed_data["gm"])

        response = _post(
            client,
            {
                "action_type": "create_bond",
                "owner_type": "character",
                "owner_id": pc3.id,
                "target_type": "location",
                "target_id": region.id,
                "bidirectional": True,
                "visibility": "bonded",
            },
        )
        assert response.status_code == 200
        bond_id = response.json()["created_objects"][0]["id"]
        bond = db.get(Slot, bond_id)
        assert bond.bidirectional is True

    def test_create_bond_missing_source_returns_404(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "create_bond",
                "owner_type": "character",
                "owner_id": "01NONEXISTENTCHARACTER0000",
                "target_type": "character",
                "target_id": seed_data["pc2"].id,
                "visibility": "bonded",
            },
        )
        assert response.status_code == 404

    def test_create_bond_duplicate_returns_422(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """pc1 → group already exists in seed data."""
        pc1 = seed_data["pc1"]
        group = seed_data["group"]
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "create_bond",
                "owner_type": "character",
                "owner_id": pc1.id,
                "target_type": "group",
                "target_id": group.id,
                "visibility": "bonded",
            },
        )
        assert response.status_code == 422

    def test_create_bond_event_target_is_owner(
        self, client: TestClient, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        pc3 = seed_data["pc3"]
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "create_bond",
                "owner_type": "character",
                "owner_id": pc1.id,
                "target_type": "character",
                "target_id": pc3.id,
                "visibility": "bonded",
            },
        )
        assert response.status_code == 200
        targets = response.json()["targets"]
        assert any(t["target_id"] == pc1.id and t["is_primary"] for t in targets)


# ===========================================================================
# modify_bond
# ===========================================================================


class TestModifyBond:
    """GM modify_bond action."""

    def test_modify_bond_source_label(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        bond = seed_data["pc1_bond"]
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "modify_bond",
                "bond_id": bond.id,
                "changes": {"source_label": "New Label"},
                "visibility": "bonded",
            },
        )
        assert response.status_code == 200
        assert response.json()["type"] == "bond.updated"

        db.expire(bond)
        db.refresh(bond)
        assert bond.source_label == "New Label"

    def test_modify_bond_stress_delta(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        bond = seed_data["pc1_bond"]
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "modify_bond",
                "bond_id": bond.id,
                "changes": {"stress": {"op": "delta", "value": -2}},
                "visibility": "bonded",
            },
        )
        assert response.status_code == 200
        assert response.json()["type"] == "bond.stress_changed"

        db.expire(bond)
        db.refresh(bond)
        assert bond.stress == 3  # 5 - 2

    def test_modify_bond_stress_set(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        bond = seed_data["pc1_bond"]
        auth_as(client, seed_data["gm"])
        _post(
            client,
            {
                "action_type": "modify_bond",
                "bond_id": bond.id,
                "changes": {"stress": {"op": "set", "value": 3}},
                "visibility": "bonded",
            },
        )
        db.expire(bond)
        db.refresh(bond)
        assert bond.stress == 3

    def test_modify_bond_stress_at_max_triggers_degradation(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Setting stress to effective_max on a pc_bond triggers a degradation."""
        bond = seed_data["pc1_bond"]
        # bond starts at stress=5, degradations=0 -> effective_max=5.
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "modify_bond",
                "bond_id": bond.id,
                "changes": {"stress": {"op": "set", "value": 5}},
                "visibility": "bonded",
            },
        )
        assert response.status_code == 200

        db.expire(bond)
        db.refresh(bond)
        # Degradation applied: degradations=1, effective_max=4, stress reset to 4.
        assert bond.stress_degradations == 1
        assert bond.stress == 4

        changes = response.json()["changes"]
        assert any("stress_degradations" in k for k in changes), (
            "Expected stress_degradations in changes"
        )

    def test_modify_bond_missing_bond_returns_404(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "modify_bond",
                "bond_id": "01NONEXISTENTBOND000000000",
                "changes": {"source_label": "X"},
                "visibility": "bonded",
            },
        )
        assert response.status_code == 404

    def test_modify_bond_changes_dict_records_before_after(
        self, client: TestClient, seed_data: dict
    ) -> None:
        bond = seed_data["pc2_bond"]
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "modify_bond",
                "bond_id": bond.id,
                "changes": {"stress": {"op": "set", "value": 2}},
                "visibility": "bonded",
            },
        )
        changes = response.json()["changes"]
        key = f"slot.{bond.id}.stress"
        assert changes[key]["before"] == 5
        assert changes[key]["after"] == 2


# ===========================================================================
# retire_bond
# ===========================================================================


class TestRetireBond:
    """GM retire_bond action."""

    def test_retire_bond_happy_path(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        bond = seed_data["pc1_bond"]
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "retire_bond",
                "bond_id": bond.id,
                "visibility": "bonded",
            },
        )
        assert response.status_code == 200
        assert response.json()["type"] == "bond.retired"

        db.expire(bond)
        db.refresh(bond)
        assert bond.is_active is False

    def test_retire_bond_missing_bond_returns_404(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "retire_bond",
                "bond_id": "01NONEXISTENTBOND000000000",
                "visibility": "bonded",
            },
        )
        assert response.status_code == 404

    def test_retire_bond_records_before_after_in_changes(
        self, client: TestClient, seed_data: dict
    ) -> None:
        bond = seed_data["pc2_bond"]
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "retire_bond",
                "bond_id": bond.id,
                "visibility": "bonded",
            },
        )
        changes = response.json()["changes"]
        key = f"slot.{bond.id}.is_active"
        assert changes[key]["before"] is True
        assert changes[key]["after"] is False


# ===========================================================================
# create_trait
# ===========================================================================


class TestCreateTrait:
    """GM create_trait action."""

    def _make_core_template(self, db: Session, name: str = "Courage") -> TraitTemplate:
        """Create and flush a core trait template for testing."""
        template = TraitTemplate(
            name=name,
            description=f"{name} description",
            type="core",
        )
        db.add(template)
        db.flush()
        db.refresh(template)
        return template

    def _make_role_template(self, db: Session, name: str = "Scout") -> TraitTemplate:
        """Create and flush a role trait template for testing."""
        template = TraitTemplate(
            name=name,
            description=f"{name} description",
            type="role",
        )
        db.add(template)
        db.flush()
        db.refresh(template)
        return template

    def test_create_core_trait_happy_path(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        template = self._make_core_template(db)
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "create_trait",
                "owner_type": "character",
                "owner_id": pc1.id,
                "slot_type": "core_trait",
                "template_id": template.id,
                "visibility": "bonded",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["type"] == "trait.created"
        assert len(body["created_objects"]) == 1
        slot_id = body["created_objects"][0]["id"]

        slot = db.get(Slot, slot_id)
        assert slot is not None
        assert slot.slot_type == "core_trait"
        assert slot.template_id == template.id
        assert slot.charge == 5
        assert slot.is_active is True
        assert slot.name == template.name

    def test_create_role_trait_happy_path(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc2 = seed_data["pc2"]
        template = self._make_role_template(db)
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "create_trait",
                "owner_type": "character",
                "owner_id": pc2.id,
                "slot_type": "role_trait",
                "template_id": template.id,
                "visibility": "bonded",
            },
        )
        assert response.status_code == 200
        slot_id = response.json()["created_objects"][0]["id"]
        slot = db.get(Slot, slot_id)
        assert slot.slot_type == "role_trait"
        assert slot.charge == 5

    def test_create_group_trait_freeform(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        group = seed_data["group"]
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "create_trait",
                "owner_type": "group",
                "owner_id": group.id,
                "slot_type": "group_trait",
                "name": "Well-Connected",
                "description": "Extensive network of contacts.",
                "visibility": "bonded",
            },
        )
        assert response.status_code == 200
        slot_id = response.json()["created_objects"][0]["id"]
        slot = db.get(Slot, slot_id)
        assert slot.slot_type == "group_trait"
        assert slot.name == "Well-Connected"
        assert slot.charge is None

    def test_create_feature_trait_freeform(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        region = seed_data["region"]
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "create_trait",
                "owner_type": "location",
                "owner_id": region.id,
                "slot_type": "feature_trait",
                "name": "Ancient Ruins",
                "description": "Crumbling stone towers from a forgotten age.",
                "visibility": "bonded",
            },
        )
        assert response.status_code == 200
        slot_id = response.json()["created_objects"][0]["id"]
        slot = db.get(Slot, slot_id)
        assert slot.slot_type == "feature_trait"
        assert slot.name == "Ancient Ruins"

    def test_create_pc_trait_missing_template_returns_422(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "create_trait",
                "owner_type": "character",
                "owner_id": seed_data["pc1"].id,
                "slot_type": "core_trait",
                # no template_id
                "visibility": "bonded",
            },
        )
        assert response.status_code == 422

    def test_create_freeform_trait_missing_name_returns_422(
        self, client: TestClient, seed_data: dict
    ) -> None:
        group = seed_data["group"]
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "create_trait",
                "owner_type": "group",
                "owner_id": group.id,
                "slot_type": "group_trait",
                # no name
                "visibility": "bonded",
            },
        )
        assert response.status_code == 422

    def test_create_trait_invalid_slot_type_returns_422(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "create_trait",
                "owner_type": "character",
                "owner_id": seed_data["pc1"].id,
                "slot_type": "bad_type",
                "name": "X",
                "visibility": "bonded",
            },
        )
        assert response.status_code == 422

    def test_create_trait_simplified_character_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        npc1 = seed_data["npc1"]
        template = self._make_core_template(db)
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "create_trait",
                "owner_type": "character",
                "owner_id": npc1.id,
                "slot_type": "core_trait",
                "template_id": template.id,
                "visibility": "bonded",
            },
        )
        assert response.status_code == 422

    def test_create_trait_unknown_character_returns_404(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        template = self._make_core_template(db)
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "create_trait",
                "owner_type": "character",
                "owner_id": "01NONEXISTENTCHARACTER0000",
                "slot_type": "core_trait",
                "template_id": template.id,
                "visibility": "bonded",
            },
        )
        assert response.status_code == 404

    def test_create_trait_wrong_template_type_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        role_template = self._make_role_template(db)
        db.commit()

        auth_as(client, seed_data["gm"])
        # Using a role template for a core_trait slot.
        response = _post(
            client,
            {
                "action_type": "create_trait",
                "owner_type": "character",
                "owner_id": pc1.id,
                "slot_type": "core_trait",
                "template_id": role_template.id,
                "visibility": "bonded",
            },
        )
        assert response.status_code == 422

    def test_create_trait_slot_limit_enforced(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Core trait limit is 2. A third should fail."""
        pc1 = seed_data["pc1"]
        t1 = self._make_core_template(db, "Alpha")
        t2 = self._make_core_template(db, "Beta")
        t3 = self._make_core_template(db, "Gamma")
        db.commit()

        auth_as(client, seed_data["gm"])
        _post(
            client,
            {
                "action_type": "create_trait",
                "owner_type": "character",
                "owner_id": pc1.id,
                "slot_type": "core_trait",
                "template_id": t1.id,
                "visibility": "bonded",
            },
        )
        _post(
            client,
            {
                "action_type": "create_trait",
                "owner_type": "character",
                "owner_id": pc1.id,
                "slot_type": "core_trait",
                "template_id": t2.id,
                "visibility": "bonded",
            },
        )
        # Third should fail.
        response = _post(
            client,
            {
                "action_type": "create_trait",
                "owner_type": "character",
                "owner_id": pc1.id,
                "slot_type": "core_trait",
                "template_id": t3.id,
                "visibility": "bonded",
            },
        )
        assert response.status_code == 422

    def test_create_trait_duplicate_template_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        template = self._make_core_template(db)
        db.commit()

        auth_as(client, seed_data["gm"])
        _post(
            client,
            {
                "action_type": "create_trait",
                "owner_type": "character",
                "owner_id": pc1.id,
                "slot_type": "core_trait",
                "template_id": template.id,
                "visibility": "bonded",
            },
        )
        # Second with same template should fail.
        response = _post(
            client,
            {
                "action_type": "create_trait",
                "owner_type": "character",
                "owner_id": pc1.id,
                "slot_type": "core_trait",
                "template_id": template.id,
                "visibility": "bonded",
            },
        )
        assert response.status_code == 422


# ===========================================================================
# modify_trait
# ===========================================================================


class TestModifyTrait:
    """GM modify_trait action."""

    def _make_trait_slot(self, db: Session, owner_id: str) -> Slot:
        """Create and flush a freeform group_trait for testing."""
        template = TraitTemplate(
            name="Resourceful",
            description="Can find a way.",
            type="core",
        )
        db.add(template)
        db.flush()

        slot = Slot(
            slot_type="core_trait",
            owner_type="character",
            owner_id=owner_id,
            template_id=template.id,
            name=template.name,
            description=template.description,
            charge=5,
            is_active=True,
        )
        db.add(slot)
        db.flush()
        db.refresh(slot)
        db.commit()
        return slot

    def test_modify_trait_charge_delta(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        slot = self._make_trait_slot(db, seed_data["pc1"].id)
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "modify_trait",
                "trait_id": slot.id,
                "changes": {"charge": {"op": "delta", "value": -1}},
                "visibility": "bonded",
            },
        )
        assert response.status_code == 200
        assert response.json()["type"] == "trait.recharged"

        db.expire(slot)
        db.refresh(slot)
        assert slot.charge == 4

    def test_modify_trait_charge_set(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        slot = self._make_trait_slot(db, seed_data["pc1"].id)
        auth_as(client, seed_data["gm"])
        _post(
            client,
            {
                "action_type": "modify_trait",
                "trait_id": slot.id,
                "changes": {"charge": {"op": "set", "value": 3}},
                "visibility": "bonded",
            },
        )
        db.expire(slot)
        db.refresh(slot)
        assert slot.charge == 3

    def test_modify_trait_name_and_description(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        # Create a freeform group_trait for name modification.
        group = seed_data["group"]
        slot = Slot(
            slot_type="group_trait",
            owner_type="group",
            owner_id=group.id,
            name="Old Name",
            description="Old desc",
            is_active=True,
        )
        db.add(slot)
        db.commit()
        db.refresh(slot)

        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "modify_trait",
                "trait_id": slot.id,
                "changes": {
                    "name": "New Name",
                    "description": "New desc",
                },
                "visibility": "bonded",
            },
        )
        assert response.status_code == 200
        assert response.json()["type"] == "trait.updated"

        db.expire(slot)
        db.refresh(slot)
        assert slot.name == "New Name"
        assert slot.description == "New desc"

    def test_modify_trait_charge_clamped_at_zero(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        slot = self._make_trait_slot(db, seed_data["pc2"].id)
        auth_as(client, seed_data["gm"])
        _post(
            client,
            {
                "action_type": "modify_trait",
                "trait_id": slot.id,
                "changes": {"charge": {"op": "delta", "value": -100}},
                "visibility": "bonded",
            },
        )
        db.expire(slot)
        db.refresh(slot)
        assert slot.charge == 0

    def test_modify_trait_missing_trait_returns_404(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "modify_trait",
                "trait_id": "01NONEXISTENTTRAIT0000000",
                "changes": {"charge": {"op": "set", "value": 3}},
                "visibility": "bonded",
            },
        )
        assert response.status_code == 404

    def test_modify_trait_changes_dict_before_after(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        slot = self._make_trait_slot(db, seed_data["pc3"].id)
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "modify_trait",
                "trait_id": slot.id,
                "changes": {"charge": {"op": "set", "value": 2}},
                "visibility": "bonded",
            },
        )
        changes = response.json()["changes"]
        key = f"slot.{slot.id}.charge"
        assert changes[key]["before"] == 5
        assert changes[key]["after"] == 2


# ===========================================================================
# retire_trait
# ===========================================================================


class TestRetireTrait:
    """GM retire_trait action."""

    def _make_trait_slot(self, db: Session, owner_id: str) -> Slot:
        template = TraitTemplate(
            name="Durable",
            description="Tough.",
            type="role",
        )
        db.add(template)
        db.flush()

        slot = Slot(
            slot_type="role_trait",
            owner_type="character",
            owner_id=owner_id,
            template_id=template.id,
            name=template.name,
            description=template.description,
            charge=5,
            is_active=True,
        )
        db.add(slot)
        db.flush()
        db.refresh(slot)
        db.commit()
        return slot

    def test_retire_trait_happy_path(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        slot = self._make_trait_slot(db, seed_data["pc1"].id)
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "retire_trait",
                "trait_id": slot.id,
                "visibility": "bonded",
            },
        )
        assert response.status_code == 200
        assert response.json()["type"] == "trait.retired"

        db.expire(slot)
        db.refresh(slot)
        assert slot.is_active is False

    def test_retire_trait_missing_returns_404(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "retire_trait",
                "trait_id": "01NONEXISTENTTRAIT0000000",
                "visibility": "bonded",
            },
        )
        assert response.status_code == 404

    def test_retire_trait_records_before_after(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        slot = self._make_trait_slot(db, seed_data["pc2"].id)
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "retire_trait",
                "trait_id": slot.id,
                "visibility": "bonded",
            },
        )
        changes = response.json()["changes"]
        key = f"slot.{slot.id}.is_active"
        assert changes[key]["before"] is True
        assert changes[key]["after"] is False


# ===========================================================================
# create_effect
# ===========================================================================


class TestCreateEffect:
    """GM create_effect action."""

    def test_create_instant_effect(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "create_effect",
                "character_id": pc1.id,
                "name": "Spark",
                "description": "A small magical spark.",
                "effect_type": "instant",
                "power_level": 1,
                "visibility": "bonded",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["type"] == "magic.effect_created"
        assert len(body["created_objects"]) == 1
        effect_id = body["created_objects"][0]["id"]
        assert body["created_objects"][0]["type"] == "magic_effect"

        effect = db.get(MagicEffect, effect_id)
        assert effect is not None
        assert effect.name == "Spark"
        assert effect.effect_type == "instant"
        assert effect.is_active is True

    def test_create_charged_effect(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "create_effect",
                "character_id": pc1.id,
                "name": "Ward",
                "description": "A protective ward.",
                "effect_type": "charged",
                "power_level": 3,
                "charges_current": 5,
                "charges_max": 5,
                "visibility": "bonded",
            },
        )
        assert response.status_code == 200
        effect_id = response.json()["created_objects"][0]["id"]
        effect = db.get(MagicEffect, effect_id)
        assert effect.effect_type == "charged"
        assert effect.charges_current == 5
        assert effect.charges_max == 5

    def test_create_permanent_effect(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc2 = seed_data["pc2"]
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "create_effect",
                "character_id": pc2.id,
                "name": "Aura",
                "description": "Permanent magical aura.",
                "effect_type": "permanent",
                "power_level": 5,
                "visibility": "bonded",
            },
        )
        assert response.status_code == 200

    def test_create_effect_cap_enforced(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Can't create more than 9 charged/permanent effects."""
        pc3 = seed_data["pc3"]
        for i in range(9):
            db.add(
                MagicEffect(
                    character_id=pc3.id,
                    name=f"Effect {i}",
                    description="desc",
                    effect_type="charged",
                    power_level=1,
                    charges_current=3,
                    charges_max=3,
                    is_active=True,
                )
            )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "create_effect",
                "character_id": pc3.id,
                "name": "Overflow",
                "description": "over cap",
                "effect_type": "charged",
                "power_level": 1,
                "charges_current": 1,
                "charges_max": 1,
                "visibility": "bonded",
            },
        )
        assert response.status_code == 422

    def test_create_effect_missing_character_returns_404(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "create_effect",
                "character_id": "01NONEXISTENTCHARACTER0000",
                "name": "X",
                "description": "y",
                "effect_type": "instant",
                "power_level": 1,
                "visibility": "bonded",
            },
        )
        assert response.status_code == 404

    def test_create_effect_simplified_character_returns_422(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "create_effect",
                "character_id": seed_data["npc1"].id,
                "name": "X",
                "description": "y",
                "effect_type": "instant",
                "power_level": 1,
                "visibility": "bonded",
            },
        )
        assert response.status_code == 422

    def test_create_charged_effect_missing_charges_returns_422(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "create_effect",
                "character_id": seed_data["pc1"].id,
                "name": "X",
                "description": "y",
                "effect_type": "charged",
                "power_level": 2,
                # Missing charges_current / charges_max
                "visibility": "bonded",
            },
        )
        assert response.status_code == 422


# ===========================================================================
# modify_effect
# ===========================================================================


class TestModifyEffect:
    """GM modify_effect action."""

    def _make_effect(
        self, db: Session, character_id: str, effect_type: str = "charged"
    ) -> MagicEffect:
        effect = MagicEffect(
            character_id=character_id,
            name="Test Effect",
            description="A test.",
            effect_type=effect_type,
            power_level=2,
            charges_current=3 if effect_type == "charged" else None,
            charges_max=5 if effect_type == "charged" else None,
            is_active=True,
        )
        db.add(effect)
        db.flush()
        db.refresh(effect)
        db.commit()
        return effect

    def test_modify_effect_name_and_description(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        effect = self._make_effect(db, seed_data["pc1"].id)
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "modify_effect",
                "effect_id": effect.id,
                "changes": {
                    "name": "Renamed",
                    "description": "New desc",
                },
                "visibility": "bonded",
            },
        )
        assert response.status_code == 200
        assert response.json()["type"] == "magic.effect_updated"

        db.expire(effect)
        db.refresh(effect)
        assert effect.name == "Renamed"
        assert effect.description == "New desc"

    def test_modify_effect_charges_current_delta(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        effect = self._make_effect(db, seed_data["pc1"].id)
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "modify_effect",
                "effect_id": effect.id,
                "changes": {"charges_current": {"op": "delta", "value": -1}},
                "visibility": "bonded",
            },
        )
        assert response.status_code == 200
        assert response.json()["type"] == "magic.effect_charged"

        db.expire(effect)
        db.refresh(effect)
        assert effect.charges_current == 2

    def test_modify_effect_power_level_set(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        effect = self._make_effect(db, seed_data["pc2"].id)
        auth_as(client, seed_data["gm"])
        _post(
            client,
            {
                "action_type": "modify_effect",
                "effect_id": effect.id,
                "changes": {"power_level": {"op": "set", "value": 4}},
                "visibility": "bonded",
            },
        )
        db.expire(effect)
        db.refresh(effect)
        assert effect.power_level == 4

    def test_modify_effect_power_level_clamped(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        effect = self._make_effect(db, seed_data["pc2"].id)
        auth_as(client, seed_data["gm"])
        _post(
            client,
            {
                "action_type": "modify_effect",
                "effect_id": effect.id,
                "changes": {"power_level": {"op": "set", "value": 99}},
                "visibility": "bonded",
            },
        )
        db.expire(effect)
        db.refresh(effect)
        assert effect.power_level == 5

    def test_modify_effect_missing_effect_returns_404(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "modify_effect",
                "effect_id": "01NONEXISTENTEFFECT000000",
                "changes": {"name": "X"},
                "visibility": "bonded",
            },
        )
        assert response.status_code == 404

    def test_modify_effect_charges_before_after(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        effect = self._make_effect(db, seed_data["pc3"].id)
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "modify_effect",
                "effect_id": effect.id,
                "changes": {"charges_current": {"op": "set", "value": 1}},
                "visibility": "bonded",
            },
        )
        changes = response.json()["changes"]
        key = f"magic_effect.{effect.id}.charges_current"
        assert changes[key]["before"] == 3
        assert changes[key]["after"] == 1


# ===========================================================================
# retire_effect
# ===========================================================================


class TestRetireEffect:
    """GM retire_effect action."""

    def _make_effect(self, db: Session, character_id: str) -> MagicEffect:
        effect = MagicEffect(
            character_id=character_id,
            name="Lingering Curse",
            description="A curse.",
            effect_type="permanent",
            power_level=3,
            is_active=True,
        )
        db.add(effect)
        db.flush()
        db.refresh(effect)
        db.commit()
        return effect

    def test_retire_effect_happy_path(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        effect = self._make_effect(db, seed_data["pc1"].id)
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "retire_effect",
                "effect_id": effect.id,
                "visibility": "bonded",
            },
        )
        assert response.status_code == 200
        assert response.json()["type"] == "magic.effect_retired"

        db.expire(effect)
        db.refresh(effect)
        assert effect.is_active is False

    def test_retire_effect_missing_returns_404(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "retire_effect",
                "effect_id": "01NONEXISTENTEFFECT000000",
                "visibility": "bonded",
            },
        )
        assert response.status_code == 404

    def test_retire_effect_records_before_after(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        effect = self._make_effect(db, seed_data["pc2"].id)
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "retire_effect",
                "effect_id": effect.id,
                "visibility": "bonded",
            },
        )
        changes = response.json()["changes"]
        key = f"magic_effect.{effect.id}.is_active"
        assert changes[key]["before"] is True
        assert changes[key]["after"] is False


# ===========================================================================
# award_xp
# ===========================================================================


class TestAwardXp:
    """GM award_xp action."""

    def test_award_xp_basic(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "award_xp",
                "character_id": pc1.id,
                "magic_stat": "being",
                "xp_amount": 3,
                "visibility": "private",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["type"] == "character.magic_stat_changed"
        assert body["visibility"] == "private"

        db.expire(pc1)
        db.refresh(pc1)
        assert pc1.magic_stats["being"]["xp"] == 3
        assert pc1.magic_stats["being"]["level"] == 0

    def test_award_xp_triggers_level_up(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """5 XP = 1 level. XP resets to 0 on level-up (no overflow carry)."""
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "award_xp",
                "character_id": pc1.id,
                "magic_stat": "wyrding",
                "xp_amount": 5,
                "visibility": "private",
            },
        )
        assert response.status_code == 200

        db.expire(pc1)
        db.refresh(pc1)
        assert pc1.magic_stats["wyrding"]["level"] == 1
        assert pc1.magic_stats["wyrding"]["xp"] == 0  # No overflow carry.

    def test_award_xp_no_overflow_carry(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """7 XP = 1 level-up + 2 XP left over — but spec says no overflow carry."""
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "award_xp",
                "character_id": pc1.id,
                "magic_stat": "summoning",
                "xp_amount": 7,
                "visibility": "private",
            },
        )
        assert response.status_code == 200

        db.expire(pc1)
        db.refresh(pc1)
        # Spec: "Magic Stat XP: Resets to 0 on level-up. No overflow carry."
        assert pc1.magic_stats["summoning"]["level"] == 1
        assert pc1.magic_stats["summoning"]["xp"] == 0

    def test_award_xp_multiple_level_ups(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """xp_amount of 15 on a level-0 stat should level up 3 times."""
        pc2 = seed_data["pc2"]
        auth_as(client, seed_data["gm"])
        _post(
            client,
            {
                "action_type": "award_xp",
                "character_id": pc2.id,
                "magic_stat": "enchanting",
                "xp_amount": 5,
                "visibility": "private",
            },
        )
        _post(
            client,
            {
                "action_type": "award_xp",
                "character_id": pc2.id,
                "magic_stat": "enchanting",
                "xp_amount": 5,
                "visibility": "private",
            },
        )
        _post(
            client,
            {
                "action_type": "award_xp",
                "character_id": pc2.id,
                "magic_stat": "enchanting",
                "xp_amount": 5,
                "visibility": "private",
            },
        )

        db.expire(pc2)
        db.refresh(pc2)
        assert pc2.magic_stats["enchanting"]["level"] == 3
        assert pc2.magic_stats["enchanting"]["xp"] == 0

    def test_award_xp_level_cap_at_5(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Level cannot exceed 5 regardless of XP awarded."""
        pc3 = seed_data["pc3"]
        # Manually set enchanting to level 5.
        magic_stats = {k: dict(v) for k, v in pc3.magic_stats.items()}
        magic_stats["dreaming"]["level"] = 5
        magic_stats["dreaming"]["xp"] = 0
        pc3.magic_stats = magic_stats
        db.commit()

        auth_as(client, seed_data["gm"])
        _post(
            client,
            {
                "action_type": "award_xp",
                "character_id": pc3.id,
                "magic_stat": "dreaming",
                "xp_amount": 5,
                "visibility": "private",
            },
        )

        db.expire(pc3)
        db.refresh(pc3)
        assert pc3.magic_stats["dreaming"]["level"] == 5  # Still capped.

    def test_award_xp_level_change_in_changes_dict(
        self, client: TestClient, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "award_xp",
                "character_id": pc1.id,
                "magic_stat": "being",
                "xp_amount": 5,
                "visibility": "private",
            },
        )
        changes = response.json()["changes"]
        xp_key = f"character.{pc1.id}.magic_stats.being.xp"
        level_key = f"character.{pc1.id}.magic_stats.being.level"
        assert xp_key in changes
        assert level_key in changes
        assert changes[level_key]["before"] == 0
        assert changes[level_key]["after"] == 1

    def test_award_xp_no_level_change_no_level_in_changes(
        self, client: TestClient, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "award_xp",
                "character_id": pc1.id,
                "magic_stat": "being",
                "xp_amount": 2,
                "visibility": "private",
            },
        )
        changes = response.json()["changes"]
        level_key = f"character.{pc1.id}.magic_stats.being.level"
        assert level_key not in changes, (
            "Level key should not appear in changes when level did not change"
        )

    def test_award_xp_default_visibility_is_private(
        self, client: TestClient, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "award_xp",
                "character_id": pc1.id,
                "magic_stat": "being",
                "xp_amount": 1,
                # no visibility
            },
        )
        assert response.json()["visibility"] == "private"

    def test_award_xp_invalid_magic_stat_returns_422(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "award_xp",
                "character_id": seed_data["pc1"].id,
                "magic_stat": "sorcery",  # invalid
                "xp_amount": 3,
                "visibility": "private",
            },
        )
        assert response.status_code == 422

    def test_award_xp_simplified_character_returns_422(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "award_xp",
                "character_id": seed_data["npc1"].id,
                "magic_stat": "being",
                "xp_amount": 3,
                "visibility": "private",
            },
        )
        assert response.status_code == 422

    def test_award_xp_missing_character_returns_404(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = _post(
            client,
            {
                "action_type": "award_xp",
                "character_id": "01NONEXISTENTCHARACTER0000",
                "magic_stat": "being",
                "xp_amount": 3,
                "visibility": "private",
            },
        )
        assert response.status_code == 404
