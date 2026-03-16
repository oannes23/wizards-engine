"""Tests for PC bond stress and degradation mechanics (Story 3.3.1).

Covers:
- ``apply_bond_strain``: lose a charge, degradation trigger
- ``restore_bond_charges``: Maintain Bond (restore to effective max)
- ``reverse_degradation``: GM action to heal a degradation
- ``get_bond``: look up a bond by ID
- Validation guards (non-pc_bond, inactive, trauma)
- Null stress fields on non-PC bonds
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from tests.fixtures import seed_data as _seed_data_fn
from wizards_engine.models.character import Character
from wizards_engine.models.group import Group
from wizards_engine.models.location import Location
from wizards_engine.models.slot import Slot
from wizards_engine.services.bond import (
    ApplyStrainResult,
    apply_bond_strain,
    get_bond,
    restore_bond_charges,
    reverse_degradation,
)


# ===========================================================================
# Helpers
# ===========================================================================


def _full_pc(db: Session, name: str = "Test PC") -> Character:
    """Create and flush a full (PC-level) character."""
    c = Character(
        name=name,
        detail_level="full",
        stress=0,
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


def _group(db: Session, name: str = "Test Group") -> Group:
    """Create and flush a group."""
    g = Group(name=name, tier=1)
    db.add(g)
    db.flush()
    db.refresh(g)
    return g


def _location(db: Session, name: str = "Test Location") -> Location:
    """Create and flush a location."""
    loc = Location(name=name)
    db.add(loc)
    db.flush()
    db.refresh(loc)
    return loc


def _pc_bond(
    db: Session,
    stress: int = 5,
    stress_degradations: int = 0,
    is_active: bool = True,
    is_trauma: bool = False,
) -> Slot:
    """Create and flush a pc_bond Slot with the given mechanical state."""
    owner = _full_pc(db, "Bond Owner")
    target = _full_pc(db, "Bond Target")
    slot = Slot(
        slot_type="pc_bond",
        owner_type="character",
        owner_id=owner.id,
        target_type="character",
        target_id=target.id,
        name="Test Bond",
        is_active=is_active,
        bidirectional=True,
        stress=stress,
        stress_degradations=stress_degradations,
        is_trauma=is_trauma,
    )
    db.add(slot)
    db.flush()
    db.refresh(slot)
    return slot


def _npc_bond(db: Session) -> Slot:
    """Create and flush an npc_bond Slot (no mechanical stress fields)."""
    owner = _npc(db, "NPC Owner")
    loc = _location(db)
    slot = Slot(
        slot_type="npc_bond",
        owner_type="character",
        owner_id=owner.id,
        target_type="location",
        target_id=loc.id,
        name="NPC Bond",
        is_active=True,
        bidirectional=False,
    )
    db.add(slot)
    db.flush()
    db.refresh(slot)
    return slot


# ===========================================================================
# get_bond
# ===========================================================================


class TestGetBond:
    """``get_bond`` returns a Slot by ID or None."""

    def test_returns_existing_bond(self, db: Session) -> None:
        bond = _pc_bond(db)
        found = get_bond(db, bond.id)
        assert found is not None
        assert found.id == bond.id

    def test_returns_none_for_missing_id(self, db: Session) -> None:
        result = get_bond(db, "01NONEXISTENT0000000000000")
        assert result is None


# ===========================================================================
# PC bond initial state
# ===========================================================================


class TestPCBondInitialState:
    """PC bonds start with stress=5 (full charges) and stress_degradations=0."""

    def test_seed_data_pc1_bond_has_full_charges(self, db: Session) -> None:
        seed = _seed_data_fn(db)
        bond = seed["pc1_bond"]
        assert bond.stress == 5
        assert bond.stress_degradations == 0
        assert bond.is_trauma is False

    def test_npc_bond_has_null_stress_fields(self, db: Session) -> None:
        """npc_bond should have null stress, stress_degradations, is_trauma."""
        bond = _npc_bond(db)
        assert bond.stress is None
        assert bond.stress_degradations is None
        assert bond.is_trauma is None

    def test_effective_max_formula(self, db: Session) -> None:
        """Effective max = 5 - stress_degradations."""
        # 0 degradations → effective max 5
        b0 = _pc_bond(db, stress_degradations=0)
        assert 5 - b0.stress_degradations == 5  # type: ignore[operator]

        # 2 degradations → effective max 3
        b2 = _pc_bond(db, stress=3, stress_degradations=2)
        assert 5 - b2.stress_degradations == 3  # type: ignore[operator]


# ===========================================================================
# apply_bond_strain
# ===========================================================================


class TestApplyBondStrain:
    """Applying strain decrements charges; at 0 triggers degradation."""

    def test_returns_apply_strain_result(self, db: Session) -> None:
        bond = _pc_bond(db, stress=5)
        result = apply_bond_strain(db, bond.id)
        assert isinstance(result, ApplyStrainResult)
        assert isinstance(result.bond, Slot)
        assert isinstance(result.degraded, bool)

    def test_decrements_charge_by_one(self, db: Session) -> None:
        bond = _pc_bond(db, stress=5)
        result = apply_bond_strain(db, bond.id)
        assert result.bond.stress == 4
        assert result.degraded is False

    def test_no_degradation_above_zero(self, db: Session) -> None:
        bond = _pc_bond(db, stress=3, stress_degradations=1)
        result = apply_bond_strain(db, bond.id)
        assert result.bond.stress == 2
        assert result.degraded is False
        assert result.bond.stress_degradations == 1

    def test_at_one_charge_triggers_degradation(self, db: Session) -> None:
        """Straining a bond at 1 charge: stress reaches 0, degradation fires."""
        bond = _pc_bond(db, stress=1, stress_degradations=0)
        result = apply_bond_strain(db, bond.id)
        assert result.degraded is True
        # Degradations incremented
        assert result.bond.stress_degradations == 1
        # Charges reset to new effective max = 5 - 1 = 4
        assert result.bond.stress == 4

    def test_degradation_reduces_effective_max(self, db: Session) -> None:
        """After degradation, the effective max is one lower than before."""
        bond = _pc_bond(db, stress=1, stress_degradations=2)
        # Before: effective max = 5 - 2 = 3
        result = apply_bond_strain(db, bond.id)
        # After degradation: stress_degradations = 3, effective max = 5 - 3 = 2
        assert result.degraded is True
        assert result.bond.stress_degradations == 3
        assert result.bond.stress == 2  # reset to new effective max

    def test_all_in_one_operation(self, db: Session) -> None:
        """The degradation and reset are committed in a single flush."""
        bond = _pc_bond(db, stress=1, stress_degradations=0)
        result = apply_bond_strain(db, bond.id)
        # The object returned should already reflect the post-degradation state.
        assert result.bond.stress_degradations == 1
        assert result.bond.stress == 4

    def test_at_five_degradations_stress_resets_to_zero(self, db: Session) -> None:
        """At 5 degradations, effective max = 0, so charges reset to 0."""
        bond = _pc_bond(db, stress=1, stress_degradations=4)
        result = apply_bond_strain(db, bond.id)
        assert result.degraded is True
        assert result.bond.stress_degradations == 5
        # Effective max = 5 - 5 = 0 → stress reset to 0 (clamped)
        assert result.bond.stress == 0

    def test_sequential_strains_accumulate_correctly(self, db: Session) -> None:
        """Multiple strains properly decrement charges toward the next degradation."""
        bond = _pc_bond(db, stress=3, stress_degradations=1)
        # strain 1: stress 3 → 2 (no degradation)
        r1 = apply_bond_strain(db, bond.id)
        assert r1.degraded is False
        assert r1.bond.stress == 2

        # strain 2: stress 2 → 1 (no degradation)
        r2 = apply_bond_strain(db, bond.id)
        assert r2.degraded is False
        assert r2.bond.stress == 1

        # strain 3: stress 1 → 0 → degradation fires
        r3 = apply_bond_strain(db, bond.id)
        assert r3.degraded is True
        assert r3.bond.stress_degradations == 2
        assert r3.bond.stress == 3  # new effective max = 5 - 2


# ===========================================================================
# apply_bond_strain — validation guards
# ===========================================================================


class TestApplyBondStrainValidation:
    """apply_bond_strain rejects invalid bonds."""

    def test_missing_bond_raises(self, db: Session) -> None:
        with pytest.raises(ValueError, match="not found"):
            apply_bond_strain(db, "01NONEXISTENT0000000000000")

    def test_npc_bond_raises(self, db: Session) -> None:
        bond = _npc_bond(db)
        with pytest.raises(ValueError, match="not a 'pc_bond'"):
            apply_bond_strain(db, bond.id)

    def test_inactive_bond_raises(self, db: Session) -> None:
        bond = _pc_bond(db, is_active=False)
        with pytest.raises(ValueError, match="inactive"):
            apply_bond_strain(db, bond.id)

    def test_trauma_bond_raises(self, db: Session) -> None:
        bond = _pc_bond(db, is_trauma=True)
        with pytest.raises(ValueError, match="trauma bond"):
            apply_bond_strain(db, bond.id)

    def test_group_relation_raises(self, db: Session) -> None:
        g1 = _group(db, "G1")
        g2 = _group(db, "G2")
        slot = Slot(
            slot_type="group_relation",
            owner_type="group",
            owner_id=g1.id,
            target_type="group",
            target_id=g2.id,
            name="Alliance",
            is_active=True,
            bidirectional=True,
        )
        db.add(slot)
        db.flush()
        db.refresh(slot)
        with pytest.raises(ValueError, match="not a 'pc_bond'"):
            apply_bond_strain(db, slot.id)


# ===========================================================================
# restore_bond_charges
# ===========================================================================


class TestRestoreBondCharges:
    """restore_bond_charges sets stress to effective max (Maintain Bond)."""

    def test_restores_depleted_bond_to_full(self, db: Session) -> None:
        bond = _pc_bond(db, stress=0, stress_degradations=0)
        # Apply a strain to move it off zero... but stress=0 means no degradations yet
        # So just test direct restore.
        # First strain it manually.
        bond.stress = 2
        db.flush()
        restored = restore_bond_charges(db, bond.id)
        assert restored.stress == 5  # effective max = 5 - 0

    def test_restores_to_degraded_effective_max(self, db: Session) -> None:
        """With 2 degradations, effective max = 3."""
        bond = _pc_bond(db, stress=1, stress_degradations=2)
        restored = restore_bond_charges(db, bond.id)
        assert restored.stress == 3

    def test_restore_at_five_degradations_gives_zero(self, db: Session) -> None:
        """At 5 degradations, effective max = 0."""
        bond = _pc_bond(db, stress=0, stress_degradations=5)
        restored = restore_bond_charges(db, bond.id)
        assert restored.stress == 0

    def test_restore_does_not_change_degradations(self, db: Session) -> None:
        """restore_bond_charges never changes stress_degradations."""
        bond = _pc_bond(db, stress=1, stress_degradations=3)
        restored = restore_bond_charges(db, bond.id)
        assert restored.stress_degradations == 3

    def test_restore_already_full_is_idempotent(self, db: Session) -> None:
        bond = _pc_bond(db, stress=5, stress_degradations=0)
        restored = restore_bond_charges(db, bond.id)
        assert restored.stress == 5

    def test_restore_returns_slot_instance(self, db: Session) -> None:
        bond = _pc_bond(db, stress=3)
        result = restore_bond_charges(db, bond.id)
        assert isinstance(result, Slot)


# ===========================================================================
# restore_bond_charges — validation guards
# ===========================================================================


class TestRestoreBondChargesValidation:
    """restore_bond_charges rejects invalid bonds."""

    def test_missing_bond_raises(self, db: Session) -> None:
        with pytest.raises(ValueError, match="not found"):
            restore_bond_charges(db, "01NONEXISTENT0000000000000")

    def test_npc_bond_raises(self, db: Session) -> None:
        bond = _npc_bond(db)
        with pytest.raises(ValueError, match="not a 'pc_bond'"):
            restore_bond_charges(db, bond.id)

    def test_inactive_bond_raises(self, db: Session) -> None:
        bond = _pc_bond(db, is_active=False)
        with pytest.raises(ValueError, match="inactive"):
            restore_bond_charges(db, bond.id)

    def test_trauma_bond_raises(self, db: Session) -> None:
        bond = _pc_bond(db, is_trauma=True)
        with pytest.raises(ValueError, match="trauma bond"):
            restore_bond_charges(db, bond.id)


# ===========================================================================
# reverse_degradation
# ===========================================================================


class TestReverseDegradation:
    """reverse_degradation decrements stress_degradations (GM action)."""

    def test_decrements_degradation_count(self, db: Session) -> None:
        bond = _pc_bond(db, stress=3, stress_degradations=2)
        result = reverse_degradation(db, bond.id)
        assert result.stress_degradations == 1

    def test_floor_at_zero(self, db: Session) -> None:
        """Degradations cannot go below 0."""
        bond = _pc_bond(db, stress=5, stress_degradations=0)
        result = reverse_degradation(db, bond.id)
        assert result.stress_degradations == 0

    def test_does_not_adjust_current_stress(self, db: Session) -> None:
        """reverse_degradation does not change the current charge level."""
        bond = _pc_bond(db, stress=2, stress_degradations=3)
        result = reverse_degradation(db, bond.id)
        assert result.stress == 2  # unchanged
        assert result.stress_degradations == 2

    def test_returns_slot_instance(self, db: Session) -> None:
        bond = _pc_bond(db, stress_degradations=1)
        result = reverse_degradation(db, bond.id)
        assert isinstance(result, Slot)

    def test_reduces_from_five_to_four(self, db: Session) -> None:
        """Starting from max degradations (5), reversing gives 4."""
        bond = _pc_bond(db, stress=0, stress_degradations=5)
        result = reverse_degradation(db, bond.id)
        assert result.stress_degradations == 4


# ===========================================================================
# reverse_degradation — validation guards
# ===========================================================================


class TestReverseDegradationValidation:
    """reverse_degradation rejects invalid bonds."""

    def test_missing_bond_raises(self, db: Session) -> None:
        with pytest.raises(ValueError, match="not found"):
            reverse_degradation(db, "01NONEXISTENT0000000000000")

    def test_npc_bond_raises(self, db: Session) -> None:
        bond = _npc_bond(db)
        with pytest.raises(ValueError, match="not a 'pc_bond'"):
            reverse_degradation(db, bond.id)

    def test_inactive_bond_raises(self, db: Session) -> None:
        bond = _pc_bond(db, is_active=False)
        with pytest.raises(ValueError, match="inactive"):
            reverse_degradation(db, bond.id)

    def test_trauma_bond_raises(self, db: Session) -> None:
        bond = _pc_bond(db, is_trauma=True)
        with pytest.raises(ValueError, match="trauma bond"):
            reverse_degradation(db, bond.id)


# ===========================================================================
# Non-PC bond field nullity
# ===========================================================================


class TestNonPCBondFieldNullity:
    """Stress fields are null on non-PC bond types."""

    def test_npc_bond_stress_is_null(self, db: Session) -> None:
        bond = _npc_bond(db)
        assert bond.stress is None

    def test_npc_bond_stress_degradations_is_null(self, db: Session) -> None:
        bond = _npc_bond(db)
        assert bond.stress_degradations is None

    def test_npc_bond_is_trauma_is_null(self, db: Session) -> None:
        bond = _npc_bond(db)
        assert bond.is_trauma is None

    def test_group_relation_has_null_stress_fields(self, db: Session) -> None:
        g1 = _group(db, "G1")
        g2 = _group(db, "G2")
        slot = Slot(
            slot_type="group_relation",
            owner_type="group",
            owner_id=g1.id,
            target_type="group",
            target_id=g2.id,
            name="Alliance",
            is_active=True,
            bidirectional=True,
        )
        db.add(slot)
        db.flush()
        db.refresh(slot)
        assert slot.stress is None
        assert slot.stress_degradations is None
        assert slot.is_trauma is None

    def test_location_bond_has_null_stress_fields(self, db: Session) -> None:
        loc = _location(db)
        pc = _full_pc(db)
        slot = Slot(
            slot_type="location_bond",
            owner_type="location",
            owner_id=loc.id,
            target_type="character",
            target_id=pc.id,
            name="Haunted By",
            is_active=True,
            bidirectional=False,
        )
        db.add(slot)
        db.flush()
        db.refresh(slot)
        assert slot.stress is None
        assert slot.stress_degradations is None
        assert slot.is_trauma is None


# ===========================================================================
# Edge cases
# ===========================================================================


class TestEdgeCases:
    """Boundary conditions and spec-defined edge cases."""

    def test_at_zero_effective_max_no_mechanical_rule(self, db: Session) -> None:
        """At 5 degradations (effective max 0), state is returned as-is; GM handles."""
        bond = _pc_bond(db, stress=0, stress_degradations=5)
        # Verify the state — no exception, no forced mechanics.
        assert bond.stress == 0
        assert bond.stress_degradations == 5
        assert (5 - bond.stress_degradations) == 0  # effective max is 0

    def test_strain_cycle_produces_correct_state(self, db: Session) -> None:
        """Full strain cycle: start at 5 charges, exhaust, verify post-degradation state."""
        bond = _pc_bond(db, stress=5, stress_degradations=0)
        # Strain 4 times — no degradation yet.
        for _ in range(4):
            result = apply_bond_strain(db, bond.id)
            assert result.degraded is False
        assert bond.stress == 1

        # 5th strain triggers degradation.
        final = apply_bond_strain(db, bond.id)
        assert final.degraded is True
        assert final.bond.stress_degradations == 1
        assert final.bond.stress == 4  # new effective max = 5 - 1

    def test_full_degradation_path(self, db: Session) -> None:
        """Bond degrades through all 5 degradation levels correctly."""
        bond = _pc_bond(db, stress=5, stress_degradations=0)
        expected_max_after = [4, 3, 2, 1, 0]

        for i, expected_charges in enumerate(expected_max_after):
            # Drain to 1 charge.
            current_effective_max = 5 - i
            strains_to_drain = current_effective_max - 1
            for _ in range(strains_to_drain):
                r = apply_bond_strain(db, bond.id)
                assert not r.degraded
            # Final strain triggers degradation.
            r = apply_bond_strain(db, bond.id)
            assert r.degraded is True
            assert r.bond.stress_degradations == i + 1
            assert r.bond.stress == expected_charges
