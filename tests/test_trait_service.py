"""Tests for the trait instance service layer.

Exercises trait instance creation, retirement, replacement, and charge
management directly against the database (no HTTP layer) via the ``db``
fixture.

All acceptance criteria from Story 3.2.2 are covered here:
- Create core/role trait instances on full characters.
- Template type must match slot type.
- New traits start at charge=5.
- Slot count limits: max 2 core_trait, max 3 role_trait per character.
- No duplicate templates on the same character (one active instance per template).
- Retirement: sets is_active=False.
- Replacement: retire old + create new atomically.
- Charge management: decrement (min 0), recharge (reset to 5).
- Cannot create traits on simplified characters.
- Cannot create with soft-deleted template.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from wizards_engine.models.character import Character
from wizards_engine.models.slot import Slot, TraitTemplate
from wizards_engine.services.trait import (
    create_trait_instance,
    decrement_charge,
    get_active_traits,
    get_trait_instance,
    recharge_trait,
    replace_trait_instance,
    retire_trait_instance,
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


def _core_template(db: Session, name: str = "Core Trait") -> TraitTemplate:
    """Create and flush a core-type TraitTemplate."""
    t = TraitTemplate(
        name=name,
        description=f"A core trait named {name}.",
        type="core",
        is_deleted=False,
    )
    db.add(t)
    db.flush()
    db.refresh(t)
    return t


def _role_template(db: Session, name: str = "Role Trait") -> TraitTemplate:
    """Create and flush a role-type TraitTemplate."""
    t = TraitTemplate(
        name=name,
        description=f"A role trait named {name}.",
        type="role",
        is_deleted=False,
    )
    db.add(t)
    db.flush()
    db.refresh(t)
    return t


# ===========================================================================
# Creation — happy paths
# ===========================================================================


class TestCreateTraitInstance:
    """Successful creation of core and role trait instances."""

    def test_create_core_trait_on_full_character(self, db: Session) -> None:
        pc = _full_pc(db)
        template = _core_template(db, "Brave")
        slot = create_trait_instance(db, pc.id, "core_trait", template.id)

        assert slot.id is not None
        assert slot.slot_type == "core_trait"
        assert slot.owner_type == "character"
        assert slot.owner_id == pc.id
        assert slot.template_id == template.id
        assert slot.is_active is True

    def test_create_role_trait_on_full_character(self, db: Session) -> None:
        pc = _full_pc(db)
        template = _role_template(db, "Lockpicking")
        slot = create_trait_instance(db, pc.id, "role_trait", template.id)

        assert slot.slot_type == "role_trait"
        assert slot.is_active is True

    def test_new_trait_starts_at_full_charge(self, db: Session) -> None:
        """New trait instances always start with charge = 5."""
        pc = _full_pc(db)
        template = _core_template(db)
        slot = create_trait_instance(db, pc.id, "core_trait", template.id)

        assert slot.charge == 5

    def test_trait_inherits_name_from_template(self, db: Session) -> None:
        """Slot name is copied from the template at creation time."""
        pc = _full_pc(db)
        template = _core_template(db, "Tenacious")
        slot = create_trait_instance(db, pc.id, "core_trait", template.id)

        assert slot.name == "Tenacious"

    def test_trait_inherits_description_from_template(self, db: Session) -> None:
        """Slot description is copied from the template at creation time."""
        pc = _full_pc(db)
        template = _core_template(db, "Tenacious")
        slot = create_trait_instance(db, pc.id, "core_trait", template.id)

        assert slot.description == template.description

    def test_returns_slot_instance(self, db: Session) -> None:
        pc = _full_pc(db)
        template = _role_template(db)
        result = create_trait_instance(db, pc.id, "role_trait", template.id)

        assert isinstance(result, Slot)

    def test_create_two_core_traits_succeeds(self, db: Session) -> None:
        """Characters can have up to 2 active core traits."""
        pc = _full_pc(db)
        t1 = _core_template(db, "Brave")
        t2 = _core_template(db, "Clever")

        s1 = create_trait_instance(db, pc.id, "core_trait", t1.id)
        s2 = create_trait_instance(db, pc.id, "core_trait", t2.id)

        assert s1.is_active is True
        assert s2.is_active is True

    def test_create_three_role_traits_succeeds(self, db: Session) -> None:
        """Characters can have up to 3 active role traits."""
        pc = _full_pc(db)
        t1 = _role_template(db, "Lockpicking")
        t2 = _role_template(db, "Alchemy")
        t3 = _role_template(db, "Swordsmanship")

        slots = [
            create_trait_instance(db, pc.id, "role_trait", t1.id),
            create_trait_instance(db, pc.id, "role_trait", t2.id),
            create_trait_instance(db, pc.id, "role_trait", t3.id),
        ]

        assert all(s.is_active for s in slots)


# ===========================================================================
# Template type validation
# ===========================================================================


class TestTemplateTypeValidation:
    """Template type must match slot type."""

    def test_core_template_in_role_slot_raises(self, db: Session) -> None:
        """A core template cannot fill a role_trait slot."""
        pc = _full_pc(db)
        core_template = _core_template(db, "Brave")

        with pytest.raises(ValueError, match="requires a 'role' template"):
            create_trait_instance(db, pc.id, "role_trait", core_template.id)

    def test_role_template_in_core_slot_raises(self, db: Session) -> None:
        """A role template cannot fill a core_trait slot."""
        pc = _full_pc(db)
        role_template = _role_template(db, "Lockpicking")

        with pytest.raises(ValueError, match="requires a 'core' template"):
            create_trait_instance(db, pc.id, "core_trait", role_template.id)

    def test_error_message_includes_slot_type_context(self, db: Session) -> None:
        pc = _full_pc(db)
        core_template = _core_template(db)

        with pytest.raises(ValueError, match="role_trait"):
            create_trait_instance(db, pc.id, "role_trait", core_template.id)


# ===========================================================================
# Slot count limits
# ===========================================================================


class TestSlotCountLimits:
    """Slot limits: max 2 core_trait, max 3 role_trait per character."""

    def test_third_core_trait_raises(self, db: Session) -> None:
        """Adding a 3rd core trait when at the limit (2) raises ValueError."""
        pc = _full_pc(db)
        t1 = _core_template(db, "Brave")
        t2 = _core_template(db, "Clever")
        t3 = _core_template(db, "Tough")

        create_trait_instance(db, pc.id, "core_trait", t1.id)
        create_trait_instance(db, pc.id, "core_trait", t2.id)

        with pytest.raises(ValueError, match="limit: 2"):
            create_trait_instance(db, pc.id, "core_trait", t3.id)

    def test_fourth_role_trait_raises(self, db: Session) -> None:
        """Adding a 4th role trait when at the limit (3) raises ValueError."""
        pc = _full_pc(db)
        t1 = _role_template(db, "Lockpicking")
        t2 = _role_template(db, "Alchemy")
        t3 = _role_template(db, "Swordsmanship")
        t4 = _role_template(db, "Necromancy")

        create_trait_instance(db, pc.id, "role_trait", t1.id)
        create_trait_instance(db, pc.id, "role_trait", t2.id)
        create_trait_instance(db, pc.id, "role_trait", t3.id)

        with pytest.raises(ValueError, match="limit: 3"):
            create_trait_instance(db, pc.id, "role_trait", t4.id)

    def test_error_includes_current_count(self, db: Session) -> None:
        pc = _full_pc(db)
        t1 = _core_template(db, "A")
        t2 = _core_template(db, "B")
        t3 = _core_template(db, "C")

        create_trait_instance(db, pc.id, "core_trait", t1.id)
        create_trait_instance(db, pc.id, "core_trait", t2.id)

        with pytest.raises(ValueError, match="2 active core_trait"):
            create_trait_instance(db, pc.id, "core_trait", t3.id)

    def test_inactive_traits_do_not_count_toward_limit(self, db: Session) -> None:
        """Retired traits are excluded from the active count."""
        pc = _full_pc(db)
        t1 = _core_template(db, "Old Trait 1")
        t2 = _core_template(db, "Old Trait 2")
        t3 = _core_template(db, "New Trait")

        s1 = create_trait_instance(db, pc.id, "core_trait", t1.id)
        create_trait_instance(db, pc.id, "core_trait", t2.id)

        # Retire t1's instance — frees up a slot.
        s1.is_active = False
        db.flush()

        # Now t3 should succeed (only 1 active core_trait remains).
        s3 = create_trait_instance(db, pc.id, "core_trait", t3.id)
        assert s3.is_active is True

    def test_core_and_role_limits_are_independent(self, db: Session) -> None:
        """Hitting the core_trait limit does not affect role_trait slots."""
        pc = _full_pc(db)
        # Fill core slots.
        for i in range(2):
            t = _core_template(db, f"Core {i}")
            create_trait_instance(db, pc.id, "core_trait", t.id)
        # Role slots are still available.
        role_t = _role_template(db)
        slot = create_trait_instance(db, pc.id, "role_trait", role_t.id)
        assert slot.is_active is True


# ===========================================================================
# Duplicate template prevention
# ===========================================================================


class TestDuplicateTemplatePrevention:
    """A character can only have one active instance per template."""

    def test_duplicate_template_on_same_character_raises(self, db: Session) -> None:
        pc = _full_pc(db)
        template = _core_template(db)
        create_trait_instance(db, pc.id, "core_trait", template.id)

        with pytest.raises(ValueError, match="already has an active trait instance"):
            create_trait_instance(db, pc.id, "core_trait", template.id)

    def test_same_template_on_different_characters_is_allowed(self, db: Session) -> None:
        """Two characters can each have an active instance of the same template."""
        pc1 = _full_pc(db, "PC A")
        pc2 = _full_pc(db, "PC B")
        template = _core_template(db, "Shared Trait")

        s1 = create_trait_instance(db, pc1.id, "core_trait", template.id)
        s2 = create_trait_instance(db, pc2.id, "core_trait", template.id)

        assert s1.owner_id == pc1.id
        assert s2.owner_id == pc2.id

    def test_duplicate_allowed_after_retirement(self, db: Session) -> None:
        """After retiring an instance, a new active instance of the same template is allowed."""
        pc = _full_pc(db)
        template = _core_template(db)

        s1 = create_trait_instance(db, pc.id, "core_trait", template.id)
        # Retire it.
        s1.is_active = False
        db.flush()

        # Now create a new instance of the same template.
        s2 = create_trait_instance(db, pc.id, "core_trait", template.id)
        assert s2.is_active is True
        assert s2.id != s1.id


# ===========================================================================
# Character validation
# ===========================================================================


class TestCharacterValidation:
    """Traits can only be created on full (PC-level) characters."""

    def test_simplified_character_raises(self, db: Session) -> None:
        npc = _npc(db)
        template = _core_template(db)

        with pytest.raises(ValueError, match="simplified"):
            create_trait_instance(db, npc.id, "core_trait", template.id)

    def test_nonexistent_character_raises(self, db: Session) -> None:
        template = _core_template(db)

        with pytest.raises(ValueError, match="not found or has been deleted"):
            create_trait_instance(db, "NONEXISTENT0000000000000000", "core_trait", template.id)

    def test_deleted_character_raises(self, db: Session) -> None:
        pc = _full_pc(db)
        pc.is_deleted = True
        db.flush()
        template = _core_template(db)

        with pytest.raises(ValueError, match="not found or has been deleted"):
            create_trait_instance(db, pc.id, "core_trait", template.id)


# ===========================================================================
# Template validation
# ===========================================================================


class TestTemplateValidation:
    """Template must exist and not be soft-deleted."""

    def test_nonexistent_template_raises(self, db: Session) -> None:
        pc = _full_pc(db)

        with pytest.raises(ValueError, match="not found"):
            create_trait_instance(db, pc.id, "core_trait", "NONEXISTENT0000000000000000")

    def test_soft_deleted_template_raises(self, db: Session) -> None:
        pc = _full_pc(db)
        template = _core_template(db)
        template.is_deleted = True
        db.flush()

        with pytest.raises(ValueError, match="has been deleted"):
            create_trait_instance(db, pc.id, "core_trait", template.id)


# ===========================================================================
# Retirement
# ===========================================================================


class TestRetireTrait:
    """Retirement sets is_active=False and moves trait to Past."""

    def test_retire_sets_is_active_false(self, db: Session) -> None:
        pc = _full_pc(db)
        template = _core_template(db)
        slot = create_trait_instance(db, pc.id, "core_trait", template.id)

        retired = retire_trait_instance(db, slot.id)

        assert retired.is_active is False

    def test_retired_slot_still_exists_in_db(self, db: Session) -> None:
        """The row is not deleted on retirement — history is preserved."""
        pc = _full_pc(db)
        template = _core_template(db)
        slot = create_trait_instance(db, pc.id, "core_trait", template.id)
        slot_id = slot.id

        retire_trait_instance(db, slot_id)

        found = db.get(Slot, slot_id)
        assert found is not None
        assert found.is_active is False

    def test_retire_returns_updated_slot(self, db: Session) -> None:
        pc = _full_pc(db)
        template = _core_template(db)
        slot = create_trait_instance(db, pc.id, "core_trait", template.id)

        result = retire_trait_instance(db, slot.id)

        assert isinstance(result, Slot)
        assert result.id == slot.id

    def test_retire_nonexistent_slot_raises(self, db: Session) -> None:
        with pytest.raises(ValueError, match="not found"):
            retire_trait_instance(db, "NONEXISTENT0000000000000000")

    def test_retire_non_trait_slot_raises(self, db: Session) -> None:
        """Attempting to retire a bond slot raises an error."""
        pc = _full_pc(db)
        bond_slot = Slot(
            slot_type="pc_bond",
            owner_type="character",
            owner_id=pc.id,
            target_type="character",
            target_id=pc.id,
            name="Not a trait",
            is_active=True,
        )
        db.add(bond_slot)
        db.flush()
        db.refresh(bond_slot)

        with pytest.raises(ValueError, match="not a trait slot"):
            retire_trait_instance(db, bond_slot.id)


# ===========================================================================
# Replacement
# ===========================================================================


class TestReplaceTraitInstance:
    """Replacement atomically retires old trait and creates a new one."""

    def test_replace_retires_old_and_creates_new(self, db: Session) -> None:
        pc = _full_pc(db)
        old_template = _core_template(db, "Old Brave")
        new_template = _core_template(db, "New Brave")

        old_slot = create_trait_instance(db, pc.id, "core_trait", old_template.id)
        old_slot_id = old_slot.id

        new_slot = replace_trait_instance(
            db, pc.id, old_slot_id, "core_trait", new_template.id
        )

        # Old slot is retired.
        old_slot_reloaded = db.get(Slot, old_slot_id)
        assert old_slot_reloaded is not None
        assert old_slot_reloaded.is_active is False

        # New slot is active.
        assert new_slot.is_active is True
        assert new_slot.template_id == new_template.id

    def test_replacement_returns_new_slot(self, db: Session) -> None:
        pc = _full_pc(db)
        old_t = _core_template(db, "Old")
        new_t = _core_template(db, "New")
        old_slot = create_trait_instance(db, pc.id, "core_trait", old_t.id)

        result = replace_trait_instance(db, pc.id, old_slot.id, "core_trait", new_t.id)

        assert isinstance(result, Slot)
        assert result.id != old_slot.id

    def test_replace_wrong_owner_raises(self, db: Session) -> None:
        pc1 = _full_pc(db, "PC 1")
        pc2 = _full_pc(db, "PC 2")
        template = _core_template(db)
        slot = create_trait_instance(db, pc1.id, "core_trait", template.id)

        new_template = _core_template(db, "Another Trait")
        with pytest.raises(ValueError, match="does not belong to character"):
            replace_trait_instance(db, pc2.id, slot.id, "core_trait", new_template.id)

    def test_replace_wrong_slot_type_raises(self, db: Session) -> None:
        """Mismatch between the old slot's type and the requested slot_type raises."""
        pc = _full_pc(db)
        core_template = _core_template(db)
        slot = create_trait_instance(db, pc.id, "core_trait", core_template.id)

        new_template = _role_template(db)
        with pytest.raises(ValueError, match="slot_type"):
            replace_trait_instance(db, pc.id, slot.id, "role_trait", new_template.id)

    def test_replace_frees_slot_for_new_instance(self, db: Session) -> None:
        """Retiring the old slot via replace allows the new one to fit within the limit."""
        pc = _full_pc(db)
        t1 = _core_template(db, "Trait 1")
        t2 = _core_template(db, "Trait 2")
        t3 = _core_template(db, "Trait 3 — Replacement")

        # Fill both core slots.
        s1 = create_trait_instance(db, pc.id, "core_trait", t1.id)
        create_trait_instance(db, pc.id, "core_trait", t2.id)

        # Replace s1 with t3 — should succeed because s1 is retired first.
        new_slot = replace_trait_instance(db, pc.id, s1.id, "core_trait", t3.id)
        assert new_slot.is_active is True


# ===========================================================================
# Charge management
# ===========================================================================


class TestChargeManagement:
    """Decrement and recharge mechanics."""

    def test_decrement_charge_reduces_by_one(self, db: Session) -> None:
        pc = _full_pc(db)
        template = _core_template(db)
        slot = create_trait_instance(db, pc.id, "core_trait", template.id)

        assert slot.charge == 5
        updated = decrement_charge(db, slot.id)
        assert updated.charge == 4

    def test_decrement_charge_does_not_go_below_zero(self, db: Session) -> None:
        """Charge is clamped at 0 — it cannot go negative."""
        pc = _full_pc(db)
        template = _core_template(db)
        slot = create_trait_instance(db, pc.id, "core_trait", template.id)

        # Drain all charges.
        for _ in range(5):
            slot = decrement_charge(db, slot.id)

        assert slot.charge == 0

        # One more decrement — still 0.
        slot = decrement_charge(db, slot.id)
        assert slot.charge == 0

    def test_decrement_returns_updated_slot(self, db: Session) -> None:
        pc = _full_pc(db)
        template = _core_template(db)
        slot = create_trait_instance(db, pc.id, "core_trait", template.id)

        result = decrement_charge(db, slot.id)

        assert isinstance(result, Slot)

    def test_recharge_resets_to_five(self, db: Session) -> None:
        pc = _full_pc(db)
        template = _core_template(db)
        slot = create_trait_instance(db, pc.id, "core_trait", template.id)

        # Drain all charges.
        for _ in range(5):
            slot = decrement_charge(db, slot.id)
        assert slot.charge == 0

        recharged = recharge_trait(db, slot.id)
        assert recharged.charge == 5

    def test_recharge_returns_updated_slot(self, db: Session) -> None:
        pc = _full_pc(db)
        template = _core_template(db)
        slot = create_trait_instance(db, pc.id, "core_trait", template.id)

        result = recharge_trait(db, slot.id)

        assert isinstance(result, Slot)

    def test_decrement_nonexistent_slot_raises(self, db: Session) -> None:
        with pytest.raises(ValueError, match="not found"):
            decrement_charge(db, "NONEXISTENT0000000000000000")

    def test_recharge_nonexistent_slot_raises(self, db: Session) -> None:
        with pytest.raises(ValueError, match="not found"):
            recharge_trait(db, "NONEXISTENT0000000000000000")

    def test_decrement_non_trait_slot_raises(self, db: Session) -> None:
        """Charge management raises for non-trait slot types."""
        pc = _full_pc(db)
        bond_slot = Slot(
            slot_type="pc_bond",
            owner_type="character",
            owner_id=pc.id,
            target_type="character",
            target_id=pc.id,
            name="Not a trait",
            is_active=True,
        )
        db.add(bond_slot)
        db.flush()
        db.refresh(bond_slot)

        with pytest.raises(ValueError, match="not a trait slot"):
            decrement_charge(db, bond_slot.id)

    def test_recharge_non_trait_slot_raises(self, db: Session) -> None:
        pc = _full_pc(db)
        bond_slot = Slot(
            slot_type="pc_bond",
            owner_type="character",
            owner_id=pc.id,
            target_type="character",
            target_id=pc.id,
            name="Not a trait",
            is_active=True,
        )
        db.add(bond_slot)
        db.flush()
        db.refresh(bond_slot)

        with pytest.raises(ValueError, match="not a trait slot"):
            recharge_trait(db, bond_slot.id)


# ===========================================================================
# Query helpers
# ===========================================================================


class TestQueryHelpers:
    """get_trait_instance and get_active_traits."""

    def test_get_trait_instance_returns_slot(self, db: Session) -> None:
        pc = _full_pc(db)
        template = _core_template(db)
        slot = create_trait_instance(db, pc.id, "core_trait", template.id)

        found = get_trait_instance(db, slot.id)

        assert found is not None
        assert found.id == slot.id

    def test_get_trait_instance_returns_none_for_missing(self, db: Session) -> None:
        result = get_trait_instance(db, "NONEXISTENT0000000000000000")
        assert result is None

    def test_get_active_traits_returns_active_only(self, db: Session) -> None:
        pc = _full_pc(db)
        t1 = _core_template(db, "Active Trait")
        t2 = _core_template(db, "Retired Trait")

        active_slot = create_trait_instance(db, pc.id, "core_trait", t1.id)
        retired_slot = create_trait_instance(db, pc.id, "core_trait", t2.id)

        # Retire t2's instance.
        retire_trait_instance(db, retired_slot.id)

        active_traits = get_active_traits(db, pc.id, "core_trait")
        ids = [s.id for s in active_traits]
        assert active_slot.id in ids
        assert retired_slot.id not in ids

    def test_get_active_traits_filters_by_slot_type(self, db: Session) -> None:
        pc = _full_pc(db)
        core_t = _core_template(db)
        role_t = _role_template(db)

        core_slot = create_trait_instance(db, pc.id, "core_trait", core_t.id)
        role_slot = create_trait_instance(db, pc.id, "role_trait", role_t.id)

        core_traits = get_active_traits(db, pc.id, "core_trait")
        role_traits = get_active_traits(db, pc.id, "role_trait")

        core_ids = [s.id for s in core_traits]
        role_ids = [s.id for s in role_traits]

        assert core_slot.id in core_ids
        assert role_slot.id not in core_ids
        assert role_slot.id in role_ids
        assert core_slot.id not in role_ids

    def test_get_active_traits_empty_for_no_traits(self, db: Session) -> None:
        pc = _full_pc(db)
        result = get_active_traits(db, pc.id, "core_trait")
        assert result == []

    def test_get_active_traits_does_not_return_other_characters_traits(
        self, db: Session
    ) -> None:
        pc1 = _full_pc(db, "PC 1")
        pc2 = _full_pc(db, "PC 2")
        shared_template = _core_template(db, "Shared")

        s1 = create_trait_instance(db, pc1.id, "core_trait", shared_template.id)
        # pc2 gets a different template (no duplicate constraint).
        other_template = _core_template(db, "Other")
        create_trait_instance(db, pc2.id, "core_trait", other_template.id)

        pc1_traits = get_active_traits(db, pc1.id, "core_trait")
        assert all(s.owner_id == pc1.id for s in pc1_traits)
        assert s1.id in [s.id for s in pc1_traits]

    def test_get_active_traits_ordered_by_created_at(self, db: Session) -> None:
        """Results are ordered ascending by creation time."""
        pc = _full_pc(db)
        t1 = _role_template(db, "First")
        t2 = _role_template(db, "Second")
        t3 = _role_template(db, "Third")

        s1 = create_trait_instance(db, pc.id, "role_trait", t1.id)
        s2 = create_trait_instance(db, pc.id, "role_trait", t2.id)
        s3 = create_trait_instance(db, pc.id, "role_trait", t3.id)

        traits = get_active_traits(db, pc.id, "role_trait")
        ids = [s.id for s in traits]
        assert ids == [s1.id, s2.id, s3.id]
