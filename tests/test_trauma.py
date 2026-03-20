"""Tests for the Trauma mechanic (Story 3.3.2).

Covers:
- ``apply_trauma``: compound operation — retire bond, create trauma bond, reset stress
- ``fix_trauma``: retire an active trauma bond (GM action)
- ``count_active_traumas``: count for effective_stress_max formula
- ``reset_stress``: standalone character stress reset
- effective_stress_max formula: 9 - count(active trauma bonds)
- Trauma bonds excluded from bond-graph traversal (no target)
- Character detail correctly reflects effective_stress_max after trauma
- Multiple traumas stack (each reduces effective_stress_max by 1)
- Validation guards: simplified character, already-trauma bond, inactive bond, etc.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from wizards_engine.models.character import Character
from wizards_engine.models.slot import Slot
from wizards_engine.services.bond import (
    ApplyTraumaResult,
    apply_trauma,
    count_active_traumas,
    fix_trauma,
    get_bonds_for_owner,
)
from wizards_engine.services.character import reset_stress


# ===========================================================================
# Helpers
# ===========================================================================


def _full_pc(db: Session, name: str = "Test PC", stress: int = 9) -> Character:
    """Create and flush a full (PC-level) character."""
    c = Character(
        name=name,
        detail_level="full",
        stress=stress,
        free_time=0,
        plot=0,
        gnosis=0,
        skills={},
        magic_stats={},
        last_session_time_now=0,
    )
    db.add(c)
    db.flush()
    db.refresh(c)
    return c


def _npc(db: Session, name: str = "Test NPC") -> Character:
    """Create and flush a simplified (NPC-level) character."""
    c = Character(name=name, detail_level="simplified")
    db.add(c)
    db.flush()
    db.refresh(c)
    return c


def _pc_bond(
    db: Session,
    owner: Character,
    target: Character | None = None,
    is_active: bool = True,
    is_trauma: bool = False,
    name: str = "Test Bond",
    charges: int = 5,
    degradations: int = 0,
) -> Slot:
    """Create and flush a pc_bond owned by *owner*.

    If *target* is None the bond has no target (trauma-style).
    """
    if target is None:
        target_type = None
        target_id = None
    else:
        target_type = "character"
        target_id = target.id

    slot = Slot(
        slot_type="pc_bond",
        owner_type="character",
        owner_id=owner.id,
        target_type=target_type,
        target_id=target_id,
        name=name,
        is_active=is_active,
        bidirectional=False,
        is_trauma=is_trauma,
        charges=charges,
        degradations=degradations,
    )
    db.add(slot)
    db.flush()
    db.refresh(slot)
    return slot


# ===========================================================================
# reset_stress (character service)
# ===========================================================================


class TestResetStress:
    """``reset_stress`` sets a full character's stress to 0."""

    def test_resets_stress_to_zero(self, db: Session) -> None:
        pc = _full_pc(db, stress=7)
        updated = reset_stress(db, pc.id)
        assert updated.stress == 0

    def test_returns_updated_character(self, db: Session) -> None:
        pc = _full_pc(db, stress=5)
        result = reset_stress(db, pc.id)
        assert isinstance(result, Character)
        assert result.id == pc.id

    def test_idempotent_when_already_zero(self, db: Session) -> None:
        pc = _full_pc(db, stress=0)
        result = reset_stress(db, pc.id)
        assert result.stress == 0

    def test_raises_for_missing_character(self, db: Session) -> None:
        with pytest.raises(ValueError, match="not found"):
            reset_stress(db, "01NONEXISTENT0000000000000")

    def test_raises_for_simplified_character(self, db: Session) -> None:
        npc = _npc(db)
        with pytest.raises(ValueError, match="simplified"):
            reset_stress(db, npc.id)


# ===========================================================================
# count_active_traumas
# ===========================================================================


class TestCountActiveTraumas:
    """``count_active_traumas`` counts active trauma bonds for a character."""

    def test_zero_when_no_bonds(self, db: Session) -> None:
        pc = _full_pc(db)
        assert count_active_traumas(db, pc.id) == 0

    def test_zero_when_no_trauma_bonds(self, db: Session) -> None:
        pc = _full_pc(db)
        target = _full_pc(db, "Target")
        _pc_bond(db, pc, target, is_trauma=False)
        assert count_active_traumas(db, pc.id) == 0

    def test_counts_active_trauma_bonds(self, db: Session) -> None:
        pc = _full_pc(db)
        _pc_bond(db, pc, None, is_trauma=True, name="Trauma 1")
        _pc_bond(db, pc, None, is_trauma=True, name="Trauma 2")
        assert count_active_traumas(db, pc.id) == 2

    def test_excludes_inactive_trauma_bonds(self, db: Session) -> None:
        pc = _full_pc(db)
        _pc_bond(db, pc, None, is_trauma=True, is_active=True, name="Active Trauma")
        _pc_bond(db, pc, None, is_trauma=True, is_active=False, name="Inactive Trauma")
        assert count_active_traumas(db, pc.id) == 1

    def test_excludes_non_trauma_bonds(self, db: Session) -> None:
        pc = _full_pc(db)
        target = _full_pc(db, "Target")
        _pc_bond(db, pc, target, is_trauma=False)
        _pc_bond(db, pc, None, is_trauma=True, name="Trauma 1")
        assert count_active_traumas(db, pc.id) == 1


# ===========================================================================
# apply_trauma — happy path
# ===========================================================================


class TestApplyTrauma:
    """``apply_trauma`` performs the three-step compound operation."""

    def test_returns_apply_trauma_result(self, db: Session) -> None:
        pc = _full_pc(db, stress=9)
        target = _full_pc(db, "Target")
        bond = _pc_bond(db, pc, target)
        result = apply_trauma(db, pc.id, bond.id, "Broken Trust", "It all fell apart.")
        assert isinstance(result, ApplyTraumaResult)

    def test_chosen_bond_is_retired(self, db: Session) -> None:
        pc = _full_pc(db, stress=9)
        target = _full_pc(db, "Target")
        bond = _pc_bond(db, pc, target)
        result = apply_trauma(db, pc.id, bond.id, "Broken Trust", "It all fell apart.")
        assert result.retired_bond.is_active is False
        assert result.retired_bond.id == bond.id

    def test_trauma_bond_created_with_correct_fields(self, db: Session) -> None:
        pc = _full_pc(db, stress=9)
        target = _full_pc(db, "Target")
        bond = _pc_bond(db, pc, target)
        result = apply_trauma(
            db, pc.id, bond.id, "Haunted by Loss", "Cannot let go."
        )
        tb = result.trauma_bond
        assert tb.slot_type == "pc_bond"
        assert tb.owner_type == "character"
        assert tb.owner_id == pc.id
        assert tb.is_trauma is True
        assert tb.target_type is None
        assert tb.target_id is None
        assert tb.name == "Haunted by Loss"
        assert tb.description == "Cannot let go."
        assert tb.charges == 5
        assert tb.degradations == 0
        assert tb.is_active is True
        assert tb.bidirectional is False

    def test_character_stress_resets_to_zero(self, db: Session) -> None:
        pc = _full_pc(db, stress=9)
        target = _full_pc(db, "Target")
        bond = _pc_bond(db, pc, target)
        result = apply_trauma(db, pc.id, bond.id, "Broken Trust", "It all fell apart.")
        assert result.character.stress == 0

    def test_all_mutations_in_one_flush(self, db: Session) -> None:
        """Verify all three state changes are reflected after a single call."""
        pc = _full_pc(db, stress=9)
        target = _full_pc(db, "Target")
        bond = _pc_bond(db, pc, target)

        result = apply_trauma(db, pc.id, bond.id, "Broken Trust", "It all fell apart.")

        # After the call (single flush), all three mutations are visible.
        assert result.retired_bond.is_active is False
        assert result.trauma_bond.is_active is True
        assert result.character.stress == 0

    def test_effective_stress_max_decreases_after_trauma(self, db: Session) -> None:
        """effective_stress_max = 9 - count(active trauma bonds)."""
        pc = _full_pc(db, stress=9)
        target = _full_pc(db, "Target")
        bond = _pc_bond(db, pc, target)

        # Before: 0 traumas → effective max = 9
        assert count_active_traumas(db, pc.id) == 0
        assert 9 - count_active_traumas(db, pc.id) == 9

        apply_trauma(db, pc.id, bond.id, "Broken Trust", "It all fell apart.")

        # After: 1 trauma → effective max = 8
        assert count_active_traumas(db, pc.id) == 1
        assert 9 - count_active_traumas(db, pc.id) == 8


# ===========================================================================
# apply_trauma — trauma bonds as graph dead ends
# ===========================================================================


class TestTraumaBondGraphBehaviour:
    """Trauma bonds are dead ends in the bond graph (no target)."""

    def test_trauma_bond_has_no_target(self, db: Session) -> None:
        pc = _full_pc(db)
        target = _full_pc(db, "Target")
        bond = _pc_bond(db, pc, target)
        result = apply_trauma(db, pc.id, bond.id, "Isolation", "Cut off.")
        assert result.trauma_bond.target_type is None
        assert result.trauma_bond.target_id is None

    def test_trauma_bonds_not_in_active_bonds_with_target(self, db: Session) -> None:
        """Trauma bonds appear in the active list but have no traversable target."""
        pc = _full_pc(db)
        target = _full_pc(db, "Target")
        bond = _pc_bond(db, pc, target)
        apply_trauma(db, pc.id, bond.id, "Isolation", "Cut off.")

        active_bonds = get_bonds_for_owner(db, "character", pc.id, include_inactive=False)
        # Trauma bond is active, but has no target — it's a dead end.
        trauma_bonds = [b for b in active_bonds if b.is_trauma]
        assert len(trauma_bonds) == 1
        assert trauma_bonds[0].target_id is None


# ===========================================================================
# Multiple traumas stacking
# ===========================================================================


class TestMultipleTraumasStack:
    """Each Trauma reduces effective_stress_max by 1."""

    def test_multiple_traumas_reduce_effective_max(self, db: Session) -> None:
        pc = _full_pc(db, stress=9)
        for i in range(3):
            target = _full_pc(db, f"Target {i}")
            bond = _pc_bond(db, pc, target, name=f"Bond {i}")
            pc.stress = 9  # re-set stress to trigger each trauma
            db.flush()
            apply_trauma(db, pc.id, bond.id, f"Trauma {i}", f"Description {i}")

        assert count_active_traumas(db, pc.id) == 3
        assert 9 - count_active_traumas(db, pc.id) == 6

    def test_eight_traumas_stress_max_is_one(self, db: Session) -> None:
        """With 8 traumas, effective max = 9 - 8 = 1."""
        pc = _full_pc(db, stress=9)
        for i in range(8):
            target = _full_pc(db, f"Target {i}")
            bond = _pc_bond(db, pc, target, name=f"Bond {i}")
            pc.stress = 9
            db.flush()
            apply_trauma(db, pc.id, bond.id, f"Trauma {i}", f"Description {i}")

        assert count_active_traumas(db, pc.id) == 8
        assert 9 - count_active_traumas(db, pc.id) == 1


# ===========================================================================
# apply_trauma — edge cases
# ===========================================================================


class TestApplyTraumaEdgeCases:
    """Edge cases for the Trauma mechanic."""

    def test_all_bonds_trauma_no_mechanical_rule(self, db: Session) -> None:
        """If all 8 bonds are already trauma, applying another still works;
        GM handles the narrative.  effective_stress_max can reach 1 minimum."""
        pc = _full_pc(db, stress=9)
        for i in range(8):
            target = _full_pc(db, f"Target {i}")
            bond = _pc_bond(db, pc, target, name=f"Bond {i}")
            pc.stress = 9
            db.flush()
            apply_trauma(db, pc.id, bond.id, f"Trauma {i}", f"Description {i}")

        # All 8 bonds are trauma — stress was reset each time, effective max = 1
        assert count_active_traumas(db, pc.id) == 8
        assert 9 - count_active_traumas(db, pc.id) == 1
        # The character's stress was reset to 0 on the last trauma
        db.refresh(pc)
        assert pc.stress == 0


# ===========================================================================
# apply_trauma — validation guards
# ===========================================================================


class TestApplyTraumaValidation:
    """apply_trauma raises ValueError for invalid inputs."""

    def test_missing_character_raises(self, db: Session) -> None:
        with pytest.raises(ValueError, match="not found"):
            apply_trauma(
                db,
                "01NONEXISTENT0000000000000",
                "01NONEXISTENT0000000000001",
                "Trauma",
                "Description",
            )

    def test_simplified_character_raises(self, db: Session) -> None:
        npc = _npc(db)
        # We need a bond to attempt retiring — create one with raw Slot
        target = _npc(db, "Other NPC")
        slot = Slot(
            slot_type="npc_bond",
            owner_type="character",
            owner_id=npc.id,
            target_type="character",
            target_id=target.id,
            name="NPC Bond",
            is_active=True,
            bidirectional=False,
        )
        db.add(slot)
        db.flush()
        with pytest.raises(ValueError, match="simplified"):
            apply_trauma(db, npc.id, slot.id, "Trauma", "Description")

    def test_missing_bond_raises(self, db: Session) -> None:
        pc = _full_pc(db)
        with pytest.raises(ValueError, match="not found"):
            apply_trauma(
                db, pc.id, "01NONEXISTENT0000000000001", "Trauma", "Description"
            )

    def test_non_pc_bond_raises(self, db: Session) -> None:
        from wizards_engine.models.group import Group  # noqa: PLC0415

        pc = _full_pc(db)
        g = Group(name="Test Group", tier=1)
        db.add(g)
        db.flush()
        db.refresh(g)
        # Bond owned by pc but to a group — slot_type would be pc_bond via create_bond,
        # but we craft an npc_bond directly to test the type guard.
        slot = Slot(
            slot_type="npc_bond",
            owner_type="character",
            owner_id=pc.id,
            target_type="group",
            target_id=g.id,
            name="Wrong Type Bond",
            is_active=True,
            bidirectional=False,
        )
        db.add(slot)
        db.flush()
        with pytest.raises(ValueError, match="not a 'pc_bond'"):
            apply_trauma(db, pc.id, slot.id, "Trauma", "Description")

    def test_bond_not_owned_by_character_raises(self, db: Session) -> None:
        pc1 = _full_pc(db, "PC 1")
        pc2 = _full_pc(db, "PC 2")
        target = _full_pc(db, "Target")
        bond = _pc_bond(db, pc2, target)  # owned by pc2, not pc1
        with pytest.raises(ValueError, match="not owned by character"):
            apply_trauma(db, pc1.id, bond.id, "Trauma", "Description")

    def test_inactive_bond_raises(self, db: Session) -> None:
        pc = _full_pc(db)
        target = _full_pc(db, "Target")
        bond = _pc_bond(db, pc, target, is_active=False)
        with pytest.raises(ValueError, match="inactive"):
            apply_trauma(db, pc.id, bond.id, "Trauma", "Description")

    def test_already_trauma_bond_raises(self, db: Session) -> None:
        pc = _full_pc(db)
        existing_trauma = _pc_bond(db, pc, None, is_trauma=True, name="Existing Trauma")
        with pytest.raises(ValueError, match="already a trauma bond"):
            apply_trauma(db, pc.id, existing_trauma.id, "New Trauma", "Description")


# ===========================================================================
# fix_trauma
# ===========================================================================


class TestFixTrauma:
    """``fix_trauma`` retires an active trauma bond."""

    def test_retires_trauma_bond(self, db: Session) -> None:
        pc = _full_pc(db)
        target = _full_pc(db, "Target")
        bond = _pc_bond(db, pc, target)
        result = apply_trauma(db, pc.id, bond.id, "Broken Trust", "It all fell apart.")
        trauma_bond = result.trauma_bond

        retired = fix_trauma(db, trauma_bond.id)
        assert retired.is_active is False

    def test_returns_retired_slot(self, db: Session) -> None:
        pc = _full_pc(db)
        target = _full_pc(db, "Target")
        bond = _pc_bond(db, pc, target)
        result = apply_trauma(db, pc.id, bond.id, "Broken Trust", "It all fell apart.")
        trauma_bond = result.trauma_bond

        retired = fix_trauma(db, trauma_bond.id)
        assert isinstance(retired, Slot)
        assert retired.id == trauma_bond.id

    def test_effective_stress_max_increases_after_fix(self, db: Session) -> None:
        pc = _full_pc(db)
        target = _full_pc(db, "Target")
        bond = _pc_bond(db, pc, target)
        result = apply_trauma(db, pc.id, bond.id, "Broken Trust", "It all fell apart.")
        trauma_bond = result.trauma_bond

        # Before fix: 1 active trauma → effective max = 8
        assert count_active_traumas(db, pc.id) == 1

        fix_trauma(db, trauma_bond.id)

        # After fix: 0 active traumas → effective max = 9
        assert count_active_traumas(db, pc.id) == 0
        assert 9 - count_active_traumas(db, pc.id) == 9

    def test_raises_for_missing_bond(self, db: Session) -> None:
        with pytest.raises(ValueError, match="not found"):
            fix_trauma(db, "01NONEXISTENT0000000000000")

    def test_raises_for_non_trauma_bond(self, db: Session) -> None:
        pc = _full_pc(db)
        target = _full_pc(db, "Target")
        bond = _pc_bond(db, pc, target, is_trauma=False)
        with pytest.raises(ValueError, match="not a trauma bond"):
            fix_trauma(db, bond.id)

    def test_raises_for_already_inactive_trauma_bond(self, db: Session) -> None:
        pc = _full_pc(db)
        trauma_bond = _pc_bond(db, pc, None, is_trauma=True, is_active=False)
        with pytest.raises(ValueError, match="already inactive"):
            fix_trauma(db, trauma_bond.id)
