"""Integration tests for use_skill proposal calculation (Story 4.3.2).

Covers:
- Happy path: skill-only, with core trait, role trait, bond, all three, plus plot spend
- calculated_effect shape and values
- Skill validation: missing, unknown
- Core/role trait validation: not found, wrong owner, wrong slot_type, inactive, 0 charges
- Bond validation: not found, wrong owner, wrong slot_type, inactive
- Plot spend validation: negative, insufficient
- Recalculation on PATCH (selections change + rejected revision)

All tests use the ``client`` + ``seed_data`` + ``db`` fixtures.  Tests that
need traits or bonds beyond the seed data create them in-line using the
``db`` fixture before making HTTP requests.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import auth_as
from wizards_engine.models.character import Character
from wizards_engine.models.slot import Slot, TraitTemplate


# ===========================================================================
# Fixture helpers
# ===========================================================================


def _core_template(db: Session, name: str = "Brave") -> TraitTemplate:
    """Create and flush a core TraitTemplate."""
    t = TraitTemplate(name=name, description=f"Desc: {name}", type="core", is_deleted=False)
    db.add(t)
    db.flush()
    db.refresh(t)
    return t


def _role_template(db: Session, name: str = "Thief") -> TraitTemplate:
    """Create and flush a role TraitTemplate."""
    t = TraitTemplate(name=name, description=f"Desc: {name}", type="role", is_deleted=False)
    db.add(t)
    db.flush()
    db.refresh(t)
    return t


def _core_trait(
    db: Session,
    character_id: str,
    name: str = "Brave",
    charge: int = 5,
    is_active: bool = True,
    template: TraitTemplate | None = None,
) -> Slot:
    """Create and flush a core_trait slot on a character."""
    if template is None:
        template = _core_template(db, name)
    slot = Slot(
        slot_type="core_trait",
        owner_type="character",
        owner_id=character_id,
        name=name,
        template_id=template.id,
        charge=charge,
        is_active=is_active,
    )
    db.add(slot)
    db.flush()
    db.refresh(slot)
    return slot


def _role_trait(
    db: Session,
    character_id: str,
    name: str = "Thief",
    charge: int = 5,
    is_active: bool = True,
    template: TraitTemplate | None = None,
) -> Slot:
    """Create and flush a role_trait slot on a character."""
    if template is None:
        template = _role_template(db, name)
    slot = Slot(
        slot_type="role_trait",
        owner_type="character",
        owner_id=character_id,
        name=name,
        template_id=template.id,
        charge=charge,
        is_active=is_active,
    )
    db.add(slot)
    db.flush()
    db.refresh(slot)
    return slot


def _pc_bond(
    db: Session,
    character_id: str,
    name: str = "Bond with Kira",
    is_active: bool = True,
) -> Slot:
    """Create and flush a pc_bond slot on a character."""
    slot = Slot(
        slot_type="pc_bond",
        owner_type="character",
        owner_id=character_id,
        target_type="character",
        target_id=character_id,  # self-target for testing purposes
        name=name,
        is_active=is_active,
        charges=5,
        degradations=0,
        is_trauma=False,
    )
    db.add(slot)
    db.flush()
    db.refresh(slot)
    return slot


def _set_skill(db: Session, character: Character, skill: str, level: int) -> None:
    """Update a single skill level on a character in-place."""
    skills = dict(character.skills or {})
    skills[skill] = level
    character.skills = skills
    db.flush()
    db.refresh(character)


def _set_plot(db: Session, character: Character, plot: int) -> None:
    """Update the plot value on a character."""
    character.plot = plot
    db.flush()
    db.refresh(character)


# ===========================================================================
# Helpers
# ===========================================================================


def _post_use_skill(client: TestClient, character_id: str, selections: dict) -> dict:
    """POST a use_skill proposal and return the parsed JSON body."""
    resp = client.post(
        "/api/v1/proposals",
        json={
            "character_id": character_id,
            "action_type": "use_skill",
            "narrative": "I attempt the action.",
            "selections": selections,
        },
    )
    return resp


# ===========================================================================
# Happy path — calculated_effect shape
# ===========================================================================


class TestUseSkillHappyPath:
    """Successful use_skill submissions populate calculated_effect correctly."""

    def test_skill_only_no_modifiers(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Submitting with only a valid skill produces correct effect."""
        pc1 = seed_data["pc1"]
        _set_skill(db, pc1, "finesse", 2)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_use_skill(client, pc1.id, {"skill": "finesse"})
        assert resp.status_code == 201

        effect = resp.json()["calculated_effect"]
        assert effect["skill"] == "finesse"
        assert effect["skill_level"] == 2
        assert effect["dice_pool"] == 2
        assert effect["modifiers"] == []
        assert effect["plot_spend"] == 0
        assert effect["costs"]["trait_charges"] == []
        assert effect["costs"]["plot"] == 0

    def test_dice_pool_is_skill_plus_modifier_count(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """dice_pool = skill_level + len(modifiers), not skill + plot."""
        pc1 = seed_data["pc1"]
        _set_skill(db, pc1, "power", 1)
        _set_plot(db, pc1, 3)
        trait = _core_trait(db, pc1.id, "Tough")
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_use_skill(
            client,
            pc1.id,
            {
                "skill": "power",
                "modifiers": {"core_trait_id": trait.id},
                "plot_spend": 3,
            },
        )
        assert resp.status_code == 201
        effect = resp.json()["calculated_effect"]
        # dice_pool = 1 (skill) + 1 (core_trait) = 2; plot_spend = 3 (guaranteed 6s, not dice)
        assert effect["dice_pool"] == 2
        assert effect["plot_spend"] == 3

    def test_with_core_trait_modifier(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Core trait modifier adds +1 to dice_pool and records charge cost."""
        pc1 = seed_data["pc1"]
        trait = _core_trait(db, pc1.id, "Brave")
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_use_skill(
            client,
            pc1.id,
            {"skill": "awareness", "modifiers": {"core_trait_id": trait.id}},
        )
        assert resp.status_code == 201
        effect = resp.json()["calculated_effect"]

        assert effect["dice_pool"] == 1  # 0 skill + 1 modifier
        assert len(effect["modifiers"]) == 1
        mod = effect["modifiers"][0]
        assert mod["type"] == "core_trait"
        assert mod["id"] == trait.id
        assert mod["name"] == "Brave"
        assert mod["bonus"] == 1

        costs = effect["costs"]
        assert len(costs["trait_charges"]) == 1
        assert costs["trait_charges"][0] == {"trait_id": trait.id, "cost": 1}

    def test_with_role_trait_modifier(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Role trait modifier adds +1 to dice_pool and records charge cost."""
        pc1 = seed_data["pc1"]
        trait = _role_trait(db, pc1.id, "Lockpicking")
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_use_skill(
            client,
            pc1.id,
            {"skill": "finesse", "modifiers": {"role_trait_id": trait.id}},
        )
        assert resp.status_code == 201
        effect = resp.json()["calculated_effect"]

        assert effect["dice_pool"] == 1
        mod = effect["modifiers"][0]
        assert mod["type"] == "role_trait"
        assert mod["id"] == trait.id

    def test_with_bond_modifier(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Bond modifier adds +1 to dice_pool with NO charge cost."""
        pc1 = seed_data["pc1"]
        bond = _pc_bond(db, pc1.id, "Bond with Kira")
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_use_skill(
            client,
            pc1.id,
            {"skill": "influence", "modifiers": {"bond_id": bond.id}},
        )
        assert resp.status_code == 201
        effect = resp.json()["calculated_effect"]

        assert effect["dice_pool"] == 1
        mod = effect["modifiers"][0]
        assert mod["type"] == "bond"
        assert mod["id"] == bond.id
        assert mod["name"] == "Bond with Kira"
        # Bonds have no charge cost
        assert effect["costs"]["trait_charges"] == []

    def test_with_all_three_modifiers(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """All three modifier types can be selected simultaneously (+3d total)."""
        pc1 = seed_data["pc1"]
        _set_skill(db, pc1, "influence", 1)
        core = _core_trait(db, pc1.id, "Brave")
        role = _role_trait(db, pc1.id, "Diplomat")
        bond = _pc_bond(db, pc1.id, "Bond with the Council")
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_use_skill(
            client,
            pc1.id,
            {
                "skill": "influence",
                "modifiers": {
                    "core_trait_id": core.id,
                    "role_trait_id": role.id,
                    "bond_id": bond.id,
                },
            },
        )
        assert resp.status_code == 201
        effect = resp.json()["calculated_effect"]

        assert effect["dice_pool"] == 4  # 1 skill + 3 modifiers
        assert len(effect["modifiers"]) == 3
        types = {m["type"] for m in effect["modifiers"]}
        assert types == {"core_trait", "role_trait", "bond"}
        assert len(effect["costs"]["trait_charges"]) == 2  # core + role only

    def test_with_plot_spend(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Plot spend is recorded in the effect but does NOT add to dice_pool."""
        pc1 = seed_data["pc1"]
        _set_plot(db, pc1, 5)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_use_skill(
            client,
            pc1.id,
            {"skill": "composure", "plot_spend": 2},
        )
        assert resp.status_code == 201
        effect = resp.json()["calculated_effect"]

        assert effect["dice_pool"] == 0  # skill 0 + 0 modifiers
        assert effect["plot_spend"] == 2
        assert effect["costs"]["plot"] == 2

    def test_zero_skill_level_character(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """A character with skill level 0 can still submit use_skill (dice_pool = 0)."""
        pc1 = seed_data["pc1"]
        # pc1 starts with all skills at 0 in seed data
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_use_skill(client, pc1.id, {"skill": "technology"})
        assert resp.status_code == 201
        effect = resp.json()["calculated_effect"]
        assert effect["skill_level"] == 0
        assert effect["dice_pool"] == 0

    def test_all_8_canonical_skills_accepted(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Each of the 8 canonical skills is accepted."""
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["player1"])

        for skill in [
            "awareness", "composure", "influence", "finesse",
            "speed", "power", "knowledge", "technology",
        ]:
            resp = _post_use_skill(client, pc1.id, {"skill": skill})
            assert resp.status_code == 201, f"Expected 201 for skill={skill}, got {resp.status_code}"


# ===========================================================================
# Skill validation failures
# ===========================================================================


class TestSkillValidation:
    """Skill field validation."""

    def test_missing_skill_returns_422(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["player1"])
        resp = _post_use_skill(client, seed_data["pc1"].id, {})
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"]["code"] == "validation_error"
        assert "skill" in body["error"]["details"]["fields"]

    def test_unknown_skill_returns_422(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["player1"])
        resp = _post_use_skill(client, seed_data["pc1"].id, {"skill": "swordsmanship"})
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"]["code"] == "validation_error"
        assert "skill" in body["error"]["details"]["fields"]

    def test_empty_skill_string_returns_422(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["player1"])
        resp = _post_use_skill(client, seed_data["pc1"].id, {"skill": ""})
        assert resp.status_code == 422


# ===========================================================================
# Core trait modifier validation
# ===========================================================================


class TestCoreTraitModifierValidation:
    """Validation for modifiers.core_trait_id."""

    def test_nonexistent_core_trait_returns_422(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["player1"])
        resp = _post_use_skill(
            client,
            seed_data["pc1"].id,
            {"skill": "awareness", "modifiers": {"core_trait_id": "NONEXISTENT000000000000000"}},
        )
        assert resp.status_code == 422
        assert "modifiers.core_trait_id" in resp.json()["error"]["details"]["fields"]

    def test_core_trait_belonging_to_another_character_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """A trait owned by pc2 cannot be used by pc1."""
        pc2 = seed_data["pc2"]
        trait = _core_trait(db, pc2.id, "Brave")
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_use_skill(
            client,
            seed_data["pc1"].id,
            {"skill": "awareness", "modifiers": {"core_trait_id": trait.id}},
        )
        assert resp.status_code == 422
        assert "modifiers.core_trait_id" in resp.json()["error"]["details"]["fields"]

    def test_role_trait_used_as_core_trait_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Using a role_trait slot in core_trait_id position is rejected."""
        pc1 = seed_data["pc1"]
        role = _role_trait(db, pc1.id, "Thief")
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_use_skill(
            client,
            pc1.id,
            {"skill": "finesse", "modifiers": {"core_trait_id": role.id}},
        )
        assert resp.status_code == 422
        assert "modifiers.core_trait_id" in resp.json()["error"]["details"]["fields"]

    def test_inactive_core_trait_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        trait = _core_trait(db, pc1.id, "Retired Trait", is_active=False)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_use_skill(
            client,
            pc1.id,
            {"skill": "awareness", "modifiers": {"core_trait_id": trait.id}},
        )
        assert resp.status_code == 422
        assert "modifiers.core_trait_id" in resp.json()["error"]["details"]["fields"]

    def test_core_trait_with_zero_charges_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        trait = _core_trait(db, pc1.id, "Depleted Trait", charge=0)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_use_skill(
            client,
            pc1.id,
            {"skill": "awareness", "modifiers": {"core_trait_id": trait.id}},
        )
        assert resp.status_code == 422
        assert "modifiers.core_trait_id" in resp.json()["error"]["details"]["fields"]

    def test_core_trait_with_one_charge_is_accepted(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        trait = _core_trait(db, pc1.id, "Low Charge Trait", charge=1)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_use_skill(
            client,
            pc1.id,
            {"skill": "awareness", "modifiers": {"core_trait_id": trait.id}},
        )
        assert resp.status_code == 201


# ===========================================================================
# Role trait modifier validation
# ===========================================================================


class TestRoleTraitModifierValidation:
    """Validation for modifiers.role_trait_id."""

    def test_nonexistent_role_trait_returns_422(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["player1"])
        resp = _post_use_skill(
            client,
            seed_data["pc1"].id,
            {"skill": "awareness", "modifiers": {"role_trait_id": "NONEXISTENT000000000000000"}},
        )
        assert resp.status_code == 422
        assert "modifiers.role_trait_id" in resp.json()["error"]["details"]["fields"]

    def test_role_trait_belonging_to_another_character_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc2 = seed_data["pc2"]
        trait = _role_trait(db, pc2.id, "Thief")
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_use_skill(
            client,
            seed_data["pc1"].id,
            {"skill": "finesse", "modifiers": {"role_trait_id": trait.id}},
        )
        assert resp.status_code == 422
        assert "modifiers.role_trait_id" in resp.json()["error"]["details"]["fields"]

    def test_core_trait_used_as_role_trait_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        core = _core_trait(db, pc1.id, "Brave")
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_use_skill(
            client,
            pc1.id,
            {"skill": "awareness", "modifiers": {"role_trait_id": core.id}},
        )
        assert resp.status_code == 422
        assert "modifiers.role_trait_id" in resp.json()["error"]["details"]["fields"]

    def test_inactive_role_trait_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        trait = _role_trait(db, pc1.id, "Old Skill", is_active=False)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_use_skill(
            client,
            pc1.id,
            {"skill": "speed", "modifiers": {"role_trait_id": trait.id}},
        )
        assert resp.status_code == 422

    def test_role_trait_with_zero_charges_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        trait = _role_trait(db, pc1.id, "Depleted Role", charge=0)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_use_skill(
            client,
            pc1.id,
            {"skill": "knowledge", "modifiers": {"role_trait_id": trait.id}},
        )
        assert resp.status_code == 422


# ===========================================================================
# Bond modifier validation
# ===========================================================================


class TestBondModifierValidation:
    """Validation for modifiers.bond_id."""

    def test_nonexistent_bond_returns_422(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["player1"])
        resp = _post_use_skill(
            client,
            seed_data["pc1"].id,
            {"skill": "influence", "modifiers": {"bond_id": "NONEXISTENT000000000000000"}},
        )
        assert resp.status_code == 422
        assert "modifiers.bond_id" in resp.json()["error"]["details"]["fields"]

    def test_bond_belonging_to_another_character_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """pc2_bond belongs to pc2, cannot be used by pc1."""
        pc2_bond = seed_data["pc2_bond"]
        auth_as(client, seed_data["player1"])
        resp = _post_use_skill(
            client,
            seed_data["pc1"].id,
            {"skill": "influence", "modifiers": {"bond_id": pc2_bond.id}},
        )
        assert resp.status_code == 422
        assert "modifiers.bond_id" in resp.json()["error"]["details"]["fields"]

    def test_non_pc_bond_slot_type_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """An npc_bond cannot be used as a pc_bond modifier."""
        # npc1_bond is npc_bond, not pc_bond
        npc1_bond = seed_data["npc1_bond"]
        auth_as(client, seed_data["player1"])
        resp = _post_use_skill(
            client,
            seed_data["pc1"].id,
            {"skill": "influence", "modifiers": {"bond_id": npc1_bond.id}},
        )
        assert resp.status_code == 422

    def test_inactive_bond_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        bond = _pc_bond(db, pc1.id, "Old Bond", is_active=False)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_use_skill(
            client,
            pc1.id,
            {"skill": "influence", "modifiers": {"bond_id": bond.id}},
        )
        assert resp.status_code == 422

    def test_pc1_bond_from_seed_data_is_accepted(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """pc1_bond from seed_data is a valid active pc_bond for pc1."""
        pc1 = seed_data["pc1"]
        pc1_bond = seed_data["pc1_bond"]
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_use_skill(
            client,
            pc1.id,
            {"skill": "influence", "modifiers": {"bond_id": pc1_bond.id}},
        )
        assert resp.status_code == 201


# ===========================================================================
# Plot spend validation
# ===========================================================================


class TestPlotSpendValidation:
    """Validation for plot_spend."""

    def test_negative_plot_spend_returns_422(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["player1"])
        resp = _post_use_skill(
            client,
            seed_data["pc1"].id,
            {"skill": "speed", "plot_spend": -1},
        )
        assert resp.status_code == 422
        assert "plot_spend" in resp.json()["error"]["details"]["fields"]

    def test_zero_plot_spend_is_valid(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["player1"])
        resp = _post_use_skill(
            client,
            seed_data["pc1"].id,
            {"skill": "speed", "plot_spend": 0},
        )
        assert resp.status_code == 201
        assert resp.json()["calculated_effect"]["plot_spend"] == 0

    def test_insufficient_plot_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Character with plot=0 cannot spend 1 Plot."""
        pc1 = seed_data["pc1"]
        # pc1 starts with plot=0 in seed data
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_use_skill(
            client,
            pc1.id,
            {"skill": "speed", "plot_spend": 1},
        )
        assert resp.status_code == 422
        assert "plot_spend" in resp.json()["error"]["details"]["fields"]

    def test_exact_plot_balance_is_accepted(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Character can spend exactly as much Plot as they have."""
        pc1 = seed_data["pc1"]
        _set_plot(db, pc1, 3)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_use_skill(
            client,
            pc1.id,
            {"skill": "speed", "plot_spend": 3},
        )
        assert resp.status_code == 201
        assert resp.json()["calculated_effect"]["costs"]["plot"] == 3

    def test_exceeding_plot_balance_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        _set_plot(db, pc1, 2)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_use_skill(
            client,
            pc1.id,
            {"skill": "speed", "plot_spend": 3},
        )
        assert resp.status_code == 422
        assert "plot_spend" in resp.json()["error"]["details"]["fields"]

    def test_no_cap_on_plot_spend(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """There is no upper cap on plot_spend beyond available balance."""
        pc1 = seed_data["pc1"]
        _set_plot(db, pc1, 10)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_use_skill(
            client,
            pc1.id,
            {"skill": "speed", "plot_spend": 10},
        )
        assert resp.status_code == 201
        assert resp.json()["calculated_effect"]["plot_spend"] == 10


# ===========================================================================
# Recalculation on PATCH
# ===========================================================================


class TestRecalculationOnPatch:
    """calculated_effect is recomputed when selections change or on revision."""

    def test_patch_selections_recalculates_effect(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Updating selections on a pending use_skill proposal recalculates the effect."""
        pc1 = seed_data["pc1"]
        _set_skill(db, pc1, "finesse", 2)
        db.commit()

        auth_as(client, seed_data["player1"])
        # Create proposal with finesse level 2
        create_resp = _post_use_skill(client, pc1.id, {"skill": "finesse"})
        proposal_id = create_resp.json()["id"]
        assert create_resp.json()["calculated_effect"]["skill_level"] == 2

        # Update to awareness (still level 0)
        patch_resp = client.patch(
            f"/api/v1/proposals/{proposal_id}",
            json={"selections": {"skill": "awareness"}},
        )
        assert patch_resp.status_code == 200
        new_effect = patch_resp.json()["calculated_effect"]
        assert new_effect["skill"] == "awareness"
        assert new_effect["skill_level"] == 0

    def test_rejected_revision_recalculates_effect(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Patching a rejected use_skill proposal recalculates the effect."""
        from wizards_engine.models.proposal import Proposal

        pc1 = seed_data["pc1"]
        _set_skill(db, pc1, "power", 3)
        db.commit()

        auth_as(client, seed_data["player1"])
        # Create and immediately set to rejected via DB
        create_resp = _post_use_skill(client, pc1.id, {"skill": "power"})
        proposal_id = create_resp.json()["id"]

        # Force-set to rejected
        proposal_obj = db.get(Proposal, proposal_id)
        proposal_obj.status = "rejected"
        db.commit()

        # Revise (patch) — should recalculate
        patch_resp = client.patch(
            f"/api/v1/proposals/{proposal_id}",
            json={"narrative": "I try harder."},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["status"] == "pending"
        effect = patch_resp.json()["calculated_effect"]
        assert effect["skill"] == "power"
        assert effect["skill_level"] == 3

    def test_patch_narrative_only_does_not_recalculate(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Updating only narrative on a pending proposal does NOT change calculated_effect."""
        pc1 = seed_data["pc1"]
        _set_skill(db, pc1, "influence", 2)
        db.commit()

        auth_as(client, seed_data["player1"])
        create_resp = _post_use_skill(client, pc1.id, {"skill": "influence"})
        proposal_id = create_resp.json()["id"]
        original_effect = create_resp.json()["calculated_effect"]

        patch_resp = client.patch(
            f"/api/v1/proposals/{proposal_id}",
            json={"narrative": "New narrative."},
        )
        assert patch_resp.status_code == 200
        # Effect should be unchanged
        assert patch_resp.json()["calculated_effect"] == original_effect

    def test_patch_with_invalid_skill_on_update_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Updating selections with an invalid skill returns 422."""
        pc1 = seed_data["pc1"]
        db.commit()

        auth_as(client, seed_data["player1"])
        create_resp = _post_use_skill(client, pc1.id, {"skill": "awareness"})
        proposal_id = create_resp.json()["id"]

        patch_resp = client.patch(
            f"/api/v1/proposals/{proposal_id}",
            json={"selections": {"skill": "flying"}},
        )
        assert patch_resp.status_code == 422

    def test_non_use_skill_proposal_not_affected(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Patching a non-use_skill proposal does not trigger skill calculation."""
        from wizards_engine.models.proposal import Proposal

        pc1 = seed_data["pc1"]
        rest_proposal = Proposal(
            character_id=pc1.id,
            action_type="rest",
            origin="player",
            narrative="Take a rest.",
            selections={},
            calculated_effect={},
            status="pending",
        )
        db.add(rest_proposal)
        db.commit()
        db.refresh(rest_proposal)

        auth_as(client, seed_data["player1"])
        patch_resp = client.patch(
            f"/api/v1/proposals/{rest_proposal.id}",
            json={"narrative": "Resting peacefully."},
        )
        assert patch_resp.status_code == 200
        # calculated_effect stays empty for non-use_skill proposals
        assert patch_resp.json()["calculated_effect"] == {}
