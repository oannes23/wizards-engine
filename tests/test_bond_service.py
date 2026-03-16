"""Tests for the bond service layer.

Exercises bond creation, validation, slot-type inference, bidirectionality
inference, slot limit enforcement, duplicate prevention, and query helpers.
All tests operate directly against the database (no HTTP layer) via the
``db`` fixture.

Game Objects are created inline where the test needs specific states, and the
canonical ``seed_data`` fixture is used where its pre-built entities are
sufficient.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from tests.conftest import auth_as  # noqa: F401 — imported for type clarity
from tests.fixtures import seed_data as _seed_data_fn
from wizards_engine.models.character import Character
from wizards_engine.models.group import Group
from wizards_engine.models.location import Location
from wizards_engine.models.slot import Slot
from wizards_engine.services.bond import (
    CreateBondResult,
    create_bond,
    get_bonds_for_owner,
    get_inbound_bonds,
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


# ===========================================================================
# Slot type inference
# ===========================================================================


class TestSlotTypeInference:
    """Auto-inferred slot_type matches spec table for all owner/target combos."""

    def test_full_character_to_character(self, db: Session) -> None:
        pc = _full_pc(db, "PC A")
        target = _full_pc(db, "PC B")
        result = create_bond(db, "character", pc.id, "character", target.id)
        assert result.bond.slot_type == "pc_bond"

    def test_full_character_to_group(self, db: Session) -> None:
        pc = _full_pc(db)
        g = _group(db)
        result = create_bond(db, "character", pc.id, "group", g.id)
        assert result.bond.slot_type == "pc_bond"

    def test_full_character_to_location(self, db: Session) -> None:
        pc = _full_pc(db)
        loc = _location(db)
        result = create_bond(db, "character", pc.id, "location", loc.id)
        assert result.bond.slot_type == "pc_bond"

    def test_simplified_character_to_character(self, db: Session) -> None:
        npc = _npc(db, "NPC A")
        target = _full_pc(db, "PC A")
        result = create_bond(db, "character", npc.id, "character", target.id)
        assert result.bond.slot_type == "npc_bond"

    def test_simplified_character_to_group(self, db: Session) -> None:
        npc = _npc(db)
        g = _group(db)
        result = create_bond(db, "character", npc.id, "group", g.id)
        assert result.bond.slot_type == "npc_bond"

    def test_simplified_character_to_location(self, db: Session) -> None:
        npc = _npc(db)
        loc = _location(db)
        result = create_bond(db, "character", npc.id, "location", loc.id)
        assert result.bond.slot_type == "npc_bond"

    def test_group_to_group(self, db: Session) -> None:
        g1 = _group(db, "Group A")
        g2 = _group(db, "Group B")
        result = create_bond(db, "group", g1.id, "group", g2.id)
        assert result.bond.slot_type == "group_relation"

    def test_group_to_location(self, db: Session) -> None:
        g = _group(db)
        loc = _location(db)
        result = create_bond(db, "group", g.id, "location", loc.id)
        assert result.bond.slot_type == "group_holding"

    def test_location_to_character(self, db: Session) -> None:
        loc = _location(db)
        pc = _full_pc(db)
        result = create_bond(db, "location", loc.id, "character", pc.id)
        assert result.bond.slot_type == "location_bond"

    def test_location_to_group(self, db: Session) -> None:
        loc = _location(db)
        g = _group(db)
        result = create_bond(db, "location", loc.id, "group", g.id)
        assert result.bond.slot_type == "location_bond"

    def test_location_to_location(self, db: Session) -> None:
        loc1 = _location(db, "Loc A")
        loc2 = _location(db, "Loc B")
        result = create_bond(db, "location", loc1.id, "location", loc2.id)
        assert result.bond.slot_type == "location_bond"

    def test_group_to_character_is_invalid(self, db: Session) -> None:
        """Groups cannot create bonds targeting Characters — spec defines no such type."""
        g = _group(db)
        pc = _full_pc(db)
        with pytest.raises(ValueError, match="Groups cannot create bonds"):
            create_bond(db, "group", g.id, "character", pc.id)


# ===========================================================================
# Bidirectionality inference
# ===========================================================================


class TestBidirectionalityInference:
    """Auto-inferred bidirectional flag matches the spec table."""

    def test_character_to_character_is_bidirectional(self, db: Session) -> None:
        pc_a = _full_pc(db, "PC A")
        pc_b = _full_pc(db, "PC B")
        result = create_bond(db, "character", pc_a.id, "character", pc_b.id)
        assert result.bond.bidirectional is True

    def test_character_to_group_is_bidirectional(self, db: Session) -> None:
        pc = _full_pc(db)
        g = _group(db)
        result = create_bond(db, "character", pc.id, "group", g.id)
        assert result.bond.bidirectional is True

    def test_group_to_group_is_bidirectional(self, db: Session) -> None:
        g1 = _group(db, "G1")
        g2 = _group(db, "G2")
        result = create_bond(db, "group", g1.id, "group", g2.id)
        assert result.bond.bidirectional is True

    def test_character_to_location_is_directional(self, db: Session) -> None:
        pc = _full_pc(db)
        loc = _location(db)
        result = create_bond(db, "character", pc.id, "location", loc.id)
        assert result.bond.bidirectional is False

    def test_group_to_location_is_directional(self, db: Session) -> None:
        g = _group(db)
        loc = _location(db)
        result = create_bond(db, "group", g.id, "location", loc.id)
        assert result.bond.bidirectional is False

    def test_location_to_character_is_directional(self, db: Session) -> None:
        loc = _location(db)
        pc = _full_pc(db)
        result = create_bond(db, "location", loc.id, "character", pc.id)
        assert result.bond.bidirectional is False

    def test_location_to_group_is_directional(self, db: Session) -> None:
        loc = _location(db)
        g = _group(db)
        result = create_bond(db, "location", loc.id, "group", g.id)
        assert result.bond.bidirectional is False

    def test_location_to_location_is_directional(self, db: Session) -> None:
        loc1 = _location(db, "L1")
        loc2 = _location(db, "L2")
        result = create_bond(db, "location", loc1.id, "location", loc2.id)
        assert result.bond.bidirectional is False


# ===========================================================================
# Bidirectionality GM override
# ===========================================================================


class TestBidirectionalityOverride:
    """GM may explicitly override the inferred bidirectional default."""

    def test_override_to_directional(self, db: Session) -> None:
        """Character↔Character defaults to bidirectional; GM sets it False."""
        pc_a = _full_pc(db, "A")
        pc_b = _full_pc(db, "B")
        result = create_bond(
            db, "character", pc_a.id, "character", pc_b.id, bidirectional=False
        )
        assert result.bond.bidirectional is False

    def test_override_to_bidirectional(self, db: Session) -> None:
        """Character→Location defaults to directional; GM sets it True."""
        pc = _full_pc(db)
        loc = _location(db)
        result = create_bond(
            db, "character", pc.id, "location", loc.id, bidirectional=True
        )
        assert result.bond.bidirectional is True

    def test_npc_to_npc_override_directional(self, db: Session) -> None:
        npc_a = _npc(db, "NPC A")
        npc_b = _npc(db, "NPC B")
        result = create_bond(
            db, "character", npc_a.id, "character", npc_b.id, bidirectional=False
        )
        assert result.bond.bidirectional is False


# ===========================================================================
# Source hard slot limits
# ===========================================================================


class TestSourceSlotLimits:
    """Hard enforcement: reject bond creation when source is at its limit."""

    def _fill_pc_bonds(self, db: Session, pc: Character, count: int) -> None:
        """Add *count* pc_bond slots to *pc* bypassing the service layer."""
        for i in range(count):
            target = _full_pc(db, f"Target {i}")
            slot = Slot(
                slot_type="pc_bond",
                owner_type="character",
                owner_id=pc.id,
                target_type="character",
                target_id=target.id,
                name=f"Bond {i}",
                is_active=True,
                bidirectional=False,
                stress=0,
                stress_degradations=0,
                is_trauma=False,
            )
            db.add(slot)
        db.flush()

    def _fill_npc_bonds(self, db: Session, npc: Character, count: int) -> None:
        """Add *count* npc_bond slots to *npc* bypassing the service layer."""
        for i in range(count):
            target = _location(db, f"Loc {i}")
            slot = Slot(
                slot_type="npc_bond",
                owner_type="character",
                owner_id=npc.id,
                target_type="location",
                target_id=target.id,
                name=f"NPC Bond {i}",
                is_active=True,
                bidirectional=False,
            )
            db.add(slot)
        db.flush()

    def _fill_group_relations(self, db: Session, g: Group, count: int) -> None:
        """Add *count* group_relation slots to *g* bypassing the service layer."""
        for i in range(count):
            target_g = _group(db, f"Peer Group {i}")
            slot = Slot(
                slot_type="group_relation",
                owner_type="group",
                owner_id=g.id,
                target_type="group",
                target_id=target_g.id,
                name=f"Relation {i}",
                is_active=True,
                bidirectional=True,
            )
            db.add(slot)
        db.flush()

    def test_pc_bond_at_limit_raises(self, db: Session) -> None:
        """PC at 8 active bonds → creation raises ValueError."""
        pc = _full_pc(db, "Limit PC")
        self._fill_pc_bonds(db, pc, 8)
        extra_target = _full_pc(db, "One More")
        with pytest.raises(ValueError, match="limit: 8"):
            create_bond(db, "character", pc.id, "character", extra_target.id)

    def test_pc_bond_at_7_succeeds(self, db: Session) -> None:
        """PC at 7 active bonds can still add one more."""
        pc = _full_pc(db, "Almost Full PC")
        self._fill_pc_bonds(db, pc, 7)
        extra_target = _full_pc(db, "Slot 8")
        result = create_bond(db, "character", pc.id, "character", extra_target.id)
        assert result.bond.slot_type == "pc_bond"

    def test_npc_bond_at_limit_raises(self, db: Session) -> None:
        """NPC at 7 active bonds → creation raises ValueError."""
        npc = _npc(db, "Limit NPC")
        self._fill_npc_bonds(db, npc, 7)
        extra_target = _location(db, "Extra Loc")
        with pytest.raises(ValueError, match="limit: 7"):
            create_bond(db, "character", npc.id, "location", extra_target.id)

    def test_npc_bond_at_6_succeeds(self, db: Session) -> None:
        """NPC at 6 active bonds can still add one more."""
        npc = _npc(db, "NPC 6")
        self._fill_npc_bonds(db, npc, 6)
        extra_target = _location(db, "Slot 7")
        result = create_bond(db, "character", npc.id, "location", extra_target.id)
        assert result.bond.slot_type == "npc_bond"

    def test_group_relation_at_limit_raises(self, db: Session) -> None:
        """Group at 7 group_relations → creation raises ValueError."""
        g = _group(db, "Limit Group")
        self._fill_group_relations(db, g, 7)
        extra_g = _group(db, "One More Group")
        with pytest.raises(ValueError, match="limit: 7"):
            create_bond(db, "group", g.id, "group", extra_g.id)

    def test_group_holding_is_unlimited(self, db: Session) -> None:
        """Group Holdings have no slot limit — can add arbitrarily many."""
        g = _group(db, "Holding Group")
        for i in range(15):
            loc = _location(db, f"Holding Loc {i}")
            result = create_bond(db, "group", g.id, "location", loc.id)
            assert result.bond.slot_type == "group_holding"

    def test_location_bond_is_unlimited(self, db: Session) -> None:
        """Location Bonds have no slot limit — can add arbitrarily many."""
        loc = _location(db, "Hub Location")
        for i in range(15):
            target_pc = _full_pc(db, f"PC {i}")
            result = create_bond(db, "location", loc.id, "character", target_pc.id)
            assert result.bond.slot_type == "location_bond"

    def test_inactive_bonds_do_not_count_toward_limit(self, db: Session) -> None:
        """Retired/past bonds are excluded from the active count."""
        pc = _full_pc(db, "PC with Past Bonds")
        # Add 8 inactive bonds directly.
        for i in range(8):
            target = _full_pc(db, f"Past Target {i}")
            slot = Slot(
                slot_type="pc_bond",
                owner_type="character",
                owner_id=pc.id,
                target_type="character",
                target_id=target.id,
                name=f"Past Bond {i}",
                is_active=False,  # retired
                bidirectional=False,
                stress=0,
                stress_degradations=0,
                is_trauma=False,
            )
            db.add(slot)
        db.flush()
        # Should succeed because all 8 existing bonds are inactive.
        new_target = _full_pc(db, "New Target")
        result = create_bond(db, "character", pc.id, "character", new_target.id)
        assert result.bond.is_active is True


# ===========================================================================
# Target soft limit warnings
# ===========================================================================


class TestTargetSoftLimitWarnings:
    """Soft warnings generated when target is at capacity on bidirectional bonds."""

    def test_no_warning_when_target_has_capacity(self, db: Session) -> None:
        pc_a = _full_pc(db, "A")
        pc_b = _full_pc(db, "B")
        result = create_bond(db, "character", pc_a.id, "character", pc_b.id)
        assert result.warnings == []

    def test_warning_when_npc_target_is_over_soft_limit(self, db: Session) -> None:
        """Bonding to an NPC that already has 7 inbound bonds triggers a warning."""
        popular_npc = _npc(db, "Popular NPC")
        # Fill the NPC's inbound limit via 7 other PCs bonding to it.
        for i in range(7):
            pc = _full_pc(db, f"Fan PC {i}")
            slot = Slot(
                slot_type="pc_bond",
                owner_type="character",
                owner_id=pc.id,
                target_type="character",
                target_id=popular_npc.id,
                name="Fan Bond",
                is_active=True,
                bidirectional=True,
                stress=0,
                stress_degradations=0,
                is_trauma=False,
            )
            db.add(slot)
        db.flush()

        # Now another PC bonds to the same NPC — should warn.
        new_pc = _full_pc(db, "Late PC")
        result = create_bond(
            db, "character", new_pc.id, "character", popular_npc.id
        )
        assert len(result.warnings) == 1
        assert "soft limit" in result.warnings[0]

    def test_bond_created_despite_soft_limit_warning(self, db: Session) -> None:
        """The bond is created even though the soft limit warning was triggered."""
        popular_npc = _npc(db, "Crowded NPC")
        for i in range(7):
            pc = _full_pc(db, f"Fan {i}")
            slot = Slot(
                slot_type="pc_bond",
                owner_type="character",
                owner_id=pc.id,
                target_type="character",
                target_id=popular_npc.id,
                name="Fan Bond",
                is_active=True,
                bidirectional=True,
                stress=0,
                stress_degradations=0,
                is_trauma=False,
            )
            db.add(slot)
        db.flush()

        new_pc = _full_pc(db, "New PC")
        result = create_bond(db, "character", new_pc.id, "character", popular_npc.id)
        assert result.bond.id is not None
        assert result.bond.is_active is True

    def test_no_warning_for_directional_bond_at_target(self, db: Session) -> None:
        """Directional bonds do not count against the target's capacity."""
        popular_loc = _location(db, "Popular Place")
        # Even if many characters bond to this location, no warning is expected
        # because Character→Location bonds are directional.
        for i in range(20):
            pc = _full_pc(db, f"Visitor {i}")
            create_bond(
                db, "character", pc.id, "location", popular_loc.id
            )
        # The location itself has no soft limit on inbound directional bonds.
        final_pc = _full_pc(db, "Final Visitor")
        result = create_bond(db, "character", final_pc.id, "location", popular_loc.id)
        assert result.warnings == []


# ===========================================================================
# Duplicate active bond prevention
# ===========================================================================


class TestDuplicatePrevention:
    """At most one active bond per (source, target) pair."""

    def test_duplicate_bond_raises(self, db: Session) -> None:
        pc = _full_pc(db)
        target = _full_pc(db, "Target")
        create_bond(db, "character", pc.id, "character", target.id)
        with pytest.raises(ValueError, match="already exists"):
            create_bond(db, "character", pc.id, "character", target.id)

    def test_duplicate_after_retire_is_allowed(self, db: Session) -> None:
        """After retiring the first bond, a new bond to the same target is allowed."""
        pc = _full_pc(db)
        target = _full_pc(db, "Target")
        result = create_bond(db, "character", pc.id, "character", target.id)
        # Retire the first bond.
        result.bond.is_active = False
        db.flush()
        # Now creating a new bond to the same target should succeed.
        new_result = create_bond(db, "character", pc.id, "character", target.id)
        assert new_result.bond.id != result.bond.id
        assert new_result.bond.is_active is True

    def test_seed_data_bonds_prevent_duplicates(self, db: Session) -> None:
        """Attempting to recreate a bond already in seed_data raises ValueError."""
        seed = _seed_data_fn(db)
        pc1 = seed["pc1"]
        group = seed["group"]
        # pc1 already has an active bond to the group from seed_data.
        with pytest.raises(ValueError, match="already exists"):
            create_bond(db, "character", pc1.id, "group", group.id)


# ===========================================================================
# Self-bond prevention
# ===========================================================================


class TestSelfBondPrevention:
    """A Game Object cannot have a bond to itself."""

    def test_self_bond_character_raises(self, db: Session) -> None:
        pc = _full_pc(db)
        with pytest.raises(ValueError, match="cannot have a bond to itself"):
            create_bond(db, "character", pc.id, "character", pc.id)

    def test_self_bond_group_raises(self, db: Session) -> None:
        g = _group(db)
        with pytest.raises(ValueError, match="cannot have a bond to itself"):
            create_bond(db, "group", g.id, "group", g.id)

    def test_self_bond_location_raises(self, db: Session) -> None:
        loc = _location(db)
        with pytest.raises(ValueError, match="cannot have a bond to itself"):
            create_bond(db, "location", loc.id, "location", loc.id)


# ===========================================================================
# Nonexistent / deleted source or target
# ===========================================================================


class TestExistenceValidation:
    """Source and target must exist and not be soft-deleted."""

    def test_missing_source_raises(self, db: Session) -> None:
        target = _full_pc(db)
        with pytest.raises(ValueError, match="not found or has been deleted"):
            create_bond(db, "character", "DOESNOTEXIST123456789012", "character", target.id)

    def test_missing_target_raises(self, db: Session) -> None:
        source = _full_pc(db)
        with pytest.raises(ValueError, match="not found or has been deleted"):
            create_bond(db, "character", source.id, "character", "DOESNOTEXIST123456789012")

    def test_deleted_source_raises(self, db: Session) -> None:
        pc = _full_pc(db, "Deleted PC")
        pc.is_deleted = True
        db.flush()
        target = _full_pc(db, "Live Target")
        with pytest.raises(ValueError, match="not found or has been deleted"):
            create_bond(db, "character", pc.id, "character", target.id)

    def test_deleted_target_raises(self, db: Session) -> None:
        source = _full_pc(db, "Live PC")
        target = _full_pc(db, "Dead Target")
        target.is_deleted = True
        db.flush()
        with pytest.raises(ValueError, match="not found or has been deleted"):
            create_bond(db, "character", source.id, "character", target.id)


# ===========================================================================
# Bond creation — field values and defaults
# ===========================================================================


class TestBondCreationFields:
    """Verify that created bonds have the expected field values."""

    def test_is_active_default_true(self, db: Session) -> None:
        pc = _full_pc(db)
        target = _full_pc(db, "T")
        result = create_bond(db, "character", pc.id, "character", target.id)
        assert result.bond.is_active is True

    def test_optional_fields_set_correctly(self, db: Session) -> None:
        pc = _full_pc(db)
        target = _full_pc(db, "T")
        result = create_bond(
            db,
            "character",
            pc.id,
            "character",
            target.id,
            source_label="Old Friend",
            target_label="Rival",
            description="We go way back.",
        )
        bond = result.bond
        assert bond.source_label == "Old Friend"
        assert bond.target_label == "Rival"
        assert bond.description == "We go way back."

    def test_pc_bond_mechanical_fields_initialised(self, db: Session) -> None:
        """PC bonds start with stress=5 (full charges) and stress_degradations=0."""
        pc = _full_pc(db)
        target = _full_pc(db, "T")
        result = create_bond(db, "character", pc.id, "character", target.id)
        bond = result.bond
        assert bond.stress == 5  # Full charges (base max)
        assert bond.stress_degradations == 0
        assert bond.is_trauma is False

    def test_npc_bond_has_no_mechanical_fields(self, db: Session) -> None:
        """NPC bonds do not set stress/degradation/is_trauma."""
        npc = _npc(db)
        target = _full_pc(db, "T")
        result = create_bond(db, "character", npc.id, "character", target.id)
        bond = result.bond
        assert bond.stress is None
        assert bond.stress_degradations is None
        assert bond.is_trauma is None

    def test_owner_and_target_ids_stored(self, db: Session) -> None:
        pc = _full_pc(db, "Owner")
        target = _full_pc(db, "Target")
        result = create_bond(db, "character", pc.id, "character", target.id)
        bond = result.bond
        assert bond.owner_type == "character"
        assert bond.owner_id == pc.id
        assert bond.target_type == "character"
        assert bond.target_id == target.id

    def test_empty_optional_fields_stored_as_none(self, db: Session) -> None:
        """When optional labels are not supplied, they are stored as None."""
        pc = _full_pc(db)
        target = _full_pc(db, "T")
        result = create_bond(db, "character", pc.id, "character", target.id)
        bond = result.bond
        assert bond.source_label is None
        assert bond.target_label is None
        assert bond.description is None

    def test_result_type(self, db: Session) -> None:
        pc = _full_pc(db)
        target = _full_pc(db, "T")
        result = create_bond(db, "character", pc.id, "character", target.id)
        assert isinstance(result, CreateBondResult)
        assert isinstance(result.bond, Slot)
        assert isinstance(result.warnings, list)


# ===========================================================================
# get_bonds_for_owner
# ===========================================================================


class TestGetBondsForOwner:
    """Tests for the get_bonds_for_owner query helper."""

    def test_returns_active_bonds_only_by_default(self, db: Session) -> None:
        pc = _full_pc(db, "PC")
        t1 = _full_pc(db, "T1")
        t2 = _full_pc(db, "T2")
        active = create_bond(db, "character", pc.id, "character", t1.id).bond
        inactive_bond = create_bond(db, "character", pc.id, "character", t2.id).bond
        inactive_bond.is_active = False
        db.flush()

        bonds = get_bonds_for_owner(db, "character", pc.id)
        ids = [b.id for b in bonds]
        assert active.id in ids
        assert inactive_bond.id not in ids

    def test_include_inactive_returns_all(self, db: Session) -> None:
        pc = _full_pc(db, "PC")
        t1 = _full_pc(db, "T1")
        t2 = _full_pc(db, "T2")
        active = create_bond(db, "character", pc.id, "character", t1.id).bond
        inactive_bond = create_bond(db, "character", pc.id, "character", t2.id).bond
        inactive_bond.is_active = False
        db.flush()

        bonds = get_bonds_for_owner(db, "character", pc.id, include_inactive=True)
        ids = [b.id for b in bonds]
        assert active.id in ids
        assert inactive_bond.id in ids

    def test_returns_empty_for_no_bonds(self, db: Session) -> None:
        pc = _full_pc(db)
        bonds = get_bonds_for_owner(db, "character", pc.id)
        assert bonds == []

    def test_does_not_return_other_owners_bonds(self, db: Session) -> None:
        pc_a = _full_pc(db, "A")
        pc_b = _full_pc(db, "B")
        target = _full_pc(db, "T")
        bond_b = create_bond(db, "character", pc_b.id, "character", target.id).bond
        bonds = get_bonds_for_owner(db, "character", pc_a.id)
        assert bond_b.id not in [b.id for b in bonds]

    def test_excludes_trait_slots(self, db: Session) -> None:
        """Trait-type slots (core_trait, group_trait, etc.) are never returned."""
        pc = _full_pc(db)
        trait = Slot(
            slot_type="core_trait",
            owner_type="character",
            owner_id=pc.id,
            name="Sharp Eye",
            is_active=True,
        )
        db.add(trait)
        db.flush()
        bonds = get_bonds_for_owner(db, "character", pc.id)
        assert all(b.slot_type != "core_trait" for b in bonds)

    def test_group_returns_its_own_relations_and_holdings(self, db: Session) -> None:
        g = _group(db, "The Org")
        peer_g = _group(db, "Peer")
        loc = _location(db)
        rel = create_bond(db, "group", g.id, "group", peer_g.id).bond
        holding = create_bond(db, "group", g.id, "location", loc.id).bond
        bonds = get_bonds_for_owner(db, "group", g.id)
        ids = [b.id for b in bonds]
        assert rel.id in ids
        assert holding.id in ids

    def test_seed_data_pc1_bonds(self, db: Session) -> None:
        """pc1 in seed_data should have at least one bond returned."""
        seed = _seed_data_fn(db)
        bonds = get_bonds_for_owner(db, "character", seed["pc1"].id)
        assert len(bonds) >= 1


# ===========================================================================
# get_inbound_bonds
# ===========================================================================


class TestGetInboundBonds:
    """Tests for the get_inbound_bonds query helper."""

    def test_returns_bidirectional_inbound_bonds(self, db: Session) -> None:
        pc_a = _full_pc(db, "A")
        pc_b = _full_pc(db, "B")
        # A bonds to B bidirectionally — B should see it as inbound.
        bond = create_bond(db, "character", pc_a.id, "character", pc_b.id).bond
        assert bond.bidirectional is True

        inbound = get_inbound_bonds(db, "character", pc_b.id)
        ids = [b.id for b in inbound]
        assert bond.id in ids

    def test_directional_bonds_not_in_inbound(self, db: Session) -> None:
        pc = _full_pc(db)
        loc = _location(db)
        # Character→Location is directional; location should not see it as inbound.
        bond = create_bond(db, "character", pc.id, "location", loc.id).bond
        assert bond.bidirectional is False

        inbound = get_inbound_bonds(db, "location", loc.id)
        assert bond.id not in [b.id for b in inbound]

    def test_returns_active_only_by_default(self, db: Session) -> None:
        pc_a = _full_pc(db, "A")
        pc_b = _full_pc(db, "B")
        bond = create_bond(db, "character", pc_a.id, "character", pc_b.id).bond
        bond.is_active = False
        db.flush()

        inbound = get_inbound_bonds(db, "character", pc_b.id)
        assert bond.id not in [b.id for b in inbound]

    def test_include_inactive_returns_retired_inbound(self, db: Session) -> None:
        pc_a = _full_pc(db, "A")
        pc_b = _full_pc(db, "B")
        bond = create_bond(db, "character", pc_a.id, "character", pc_b.id).bond
        bond.is_active = False
        db.flush()

        inbound = get_inbound_bonds(db, "character", pc_b.id, include_inactive=True)
        assert bond.id in [b.id for b in inbound]

    def test_returns_empty_when_no_inbound(self, db: Session) -> None:
        pc = _full_pc(db)
        inbound = get_inbound_bonds(db, "character", pc.id)
        assert inbound == []

    def test_group_sees_bidirectional_character_bond(self, db: Session) -> None:
        """A character's bidirectional bond to a group appears in the group's inbound."""
        pc = _full_pc(db)
        g = _group(db)
        bond = create_bond(db, "character", pc.id, "group", g.id).bond
        assert bond.bidirectional is True

        inbound = get_inbound_bonds(db, "group", g.id)
        assert bond.id in [b.id for b in inbound]
