"""Tests for the bond-distance presence service (BFS traversal algorithm).

Exercises:
- 1-hop direct bonds (common tier)
- 2-hop via Character intermediary (familiar tier)
- 3-hop via two intermediaries (known tier)
- Exclusion of inactive bonds
- Exclusion of soft-deleted game objects
- Exclusion of trauma bonds
- Character-intermediary constraint (no Group→Group traversal)
- Bidirectional vs directional bond traversal
- Reverse: Location perspective (presence) and Character perspective (locations)
- Empty result when no bonds exist
- API endpoint integration (GET /characters/{id} and GET /locations/{id})

Bond graph used throughout (see story spec):

    PC1 --bond(directional)--> Location_A          [1-hop from PC1: common]
    PC1 <-> NPC1               (bidirectional)      [intermediary]
    NPC1 --bond--> Location_B                       [2-hop via NPC1: familiar]
    NPC1 --bond--> Group1      (bidirectional)      [Group1 reachable from NPC1]
    Group1 --bond--> Location_C (holding, directional) [reachable via Group1]
    PC2 <-> Group1             (bidirectional)      [PC2 member of Group1]
    PC2 --bond--> Location_D                        [3-hop via NPC1→Group1→PC2: known]
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import auth_as
from wizards_engine.models.character import Character
from wizards_engine.models.group import Group
from wizards_engine.models.location import Location
from wizards_engine.models.slot import Slot
from wizards_engine.services.bond import create_bond
from wizards_engine.services.presence import (
    compute_presence,
    get_locations_for_character,
    get_presence_for_location,
)


# ===========================================================================
# Fixture helpers
# ===========================================================================


def _full_pc(db: Session, name: str) -> Character:
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


def _npc(db: Session, name: str) -> Character:
    """Create and flush a simplified (NPC-level) character."""
    c = Character(name=name, detail_level="simplified")
    db.add(c)
    db.flush()
    db.refresh(c)
    return c


def _group(db: Session, name: str) -> Group:
    """Create and flush a group."""
    g = Group(name=name, tier=1)
    db.add(g)
    db.flush()
    db.refresh(g)
    return g


def _location(db: Session, name: str) -> Location:
    """Create and flush a location."""
    loc = Location(name=name)
    db.add(loc)
    db.flush()
    db.refresh(loc)
    return loc


def _make_bond(
    db: Session,
    owner_type: str,
    owner_id: str,
    target_type: str,
    target_id: str,
    *,
    bidirectional: bool = False,
    slot_type: str | None = None,
    is_active: bool = True,
) -> Slot:
    """Insert a bond slot directly (bypasses service validation)."""
    if slot_type is None:
        # Infer a reasonable default.
        if owner_type == "character":
            obj = db.get(Character, owner_id)
            slot_type = "pc_bond" if obj and obj.detail_level == "full" else "npc_bond"
        elif owner_type == "group":
            slot_type = "group_holding" if target_type == "location" else "group_relation"
        else:
            slot_type = "location_bond"

    slot = Slot(
        slot_type=slot_type,
        owner_type=owner_type,
        owner_id=owner_id,
        target_type=target_type,
        target_id=target_id,
        name=f"{owner_type} bond",
        bidirectional=bidirectional,
        is_active=is_active,
    )
    if slot_type == "pc_bond":
        slot.charges = 0
        slot.degradations = 0
        slot.is_trauma = False
    db.add(slot)
    db.flush()
    db.refresh(slot)
    return slot


# ===========================================================================
# Graph factory
# ===========================================================================


def _build_graph(db: Session) -> dict:
    """Build the canonical test bond graph.

    PC1 --bond(directional)--> Location_A          (1-hop from PC1)
    PC1 <-> NPC1               (bidirectional)
    NPC1 --bond--> Location_B                       (2-hop from PC1 via NPC1)
    NPC1 <-> Group1            (bidirectional)
    Group1 --bond--> Location_C (holding, directional)
    PC2 <-> Group1             (bidirectional)
    PC2 --bond--> Location_D   (3-hop from PC1 via NPC1→Group1→PC2)

    Returns a dict of named entities.
    """
    pc1 = _full_pc(db, "PC1")
    pc2 = _full_pc(db, "PC2")
    npc1 = _npc(db, "NPC1")
    group1 = _group(db, "Group1")
    loc_a = _location(db, "Location_A")
    loc_b = _location(db, "Location_B")
    loc_c = _location(db, "Location_C")
    loc_d = _location(db, "Location_D")

    # PC1 -> Location_A  (directional, 1-hop from PC1)
    _make_bond(db, "character", pc1.id, "location", loc_a.id, bidirectional=False)

    # PC1 <-> NPC1  (bidirectional)
    _make_bond(db, "character", pc1.id, "character", npc1.id, bidirectional=True)

    # NPC1 -> Location_B  (directional, 2-hop from PC1 via NPC1)
    _make_bond(db, "character", npc1.id, "location", loc_b.id, bidirectional=False)

    # NPC1 <-> Group1  (bidirectional)
    # Group can't own bonds to Characters, so NPC1 owns this bond.
    _make_bond(db, "character", npc1.id, "group", group1.id, bidirectional=True)

    # Group1 -> Location_C  (holding, directional)
    _make_bond(db, "group", group1.id, "location", loc_c.id, bidirectional=False)

    # PC2 <-> Group1  (bidirectional, PC2 is a member)
    _make_bond(db, "character", pc2.id, "group", group1.id, bidirectional=True)

    # PC2 -> Location_D  (directional, 3-hop from PC1 via NPC1→Group1→PC2)
    _make_bond(db, "character", pc2.id, "location", loc_d.id, bidirectional=False)

    return {
        "pc1": pc1,
        "pc2": pc2,
        "npc1": npc1,
        "group1": group1,
        "loc_a": loc_a,
        "loc_b": loc_b,
        "loc_c": loc_c,
        "loc_d": loc_d,
    }


# ===========================================================================
# Helper to extract IDs from tier results
# ===========================================================================


def _ids(tier: list[dict]) -> set[str]:
    return {item["id"] for item in tier}


# ===========================================================================
# Tests — Character perspective (get_locations_for_character)
# ===========================================================================


class TestLocationsForCharacter:
    """Tests for get_locations_for_character — Character → Location traversal."""

    def test_common_direct_bond(self, db: Session) -> None:
        """Locations directly bonded to the character appear in common tier."""
        g = _build_graph(db)
        result = get_locations_for_character(db, g["pc1"].id)
        assert g["loc_a"].id in _ids(result["common"])

    def test_familiar_via_character_intermediary(self, db: Session) -> None:
        """Location reachable through one Character intermediary is familiar."""
        g = _build_graph(db)
        result = get_locations_for_character(db, g["pc1"].id)
        # NPC1 -> Location_B  (2-hop: PC1 -> NPC1 -> Location_B)
        assert g["loc_b"].id in _ids(result["familiar"])

    def test_locations_not_above_max_hops(self, db: Session) -> None:
        """Locations beyond 3 hops do not appear in any tier."""
        g = _build_graph(db)
        result = get_locations_for_character(db, g["pc1"].id)
        all_ids = (
            _ids(result["common"])
            | _ids(result["familiar"])
            | _ids(result["known"])
        )
        # Location_D is at hop 4 from PC1 via NPC1->Group1->PC2->Location_D
        # (4 hops with the constraint). It should NOT appear.
        assert g["loc_d"].id not in all_ids

    def test_start_node_not_in_results(self, db: Session) -> None:
        """The starting character never appears in their own location tiers."""
        g = _build_graph(db)
        result = get_locations_for_character(db, g["pc1"].id)
        all_ids = (
            _ids(result["common"])
            | _ids(result["familiar"])
            | _ids(result["known"])
        )
        assert g["pc1"].id not in all_ids

    def test_empty_when_no_bonds(self, db: Session) -> None:
        """A character with no bonds returns empty tiers."""
        pc = _full_pc(db, "Lonely PC")
        result = get_locations_for_character(db, pc.id)
        assert result["common"] == []
        assert result["familiar"] == []
        assert result["known"] == []

    def test_only_collects_locations_not_characters(self, db: Session) -> None:
        """Characters reachable via bonds do not appear in the location tiers."""
        g = _build_graph(db)
        result = get_locations_for_character(db, g["pc1"].id)
        all_items = (
            result["common"] + result["familiar"] + result["known"]
        )
        for item in all_items:
            assert item["type"] == "location", f"Non-location item found: {item}"

    def test_closest_tier_wins(self, db: Session) -> None:
        """A location reachable at multiple distances appears only in the closest tier."""
        pc = _full_pc(db, "PC X")
        npc = _npc(db, "NPC Y")
        loc = _location(db, "Shared Location")

        # PC X directly bonded to location (1-hop: common)
        _make_bond(db, "character", pc.id, "location", loc.id, bidirectional=False)
        # PC X <-> NPC Y (bidirectional)
        _make_bond(db, "character", pc.id, "character", npc.id, bidirectional=True)
        # NPC Y -> same location (would be 2-hop, but already reached at 1)
        _make_bond(db, "character", npc.id, "location", loc.id, bidirectional=False)

        result = get_locations_for_character(db, pc.id)
        # Must appear in common (1-hop), not familiar (2-hop)
        assert loc.id in _ids(result["common"])
        assert loc.id not in _ids(result["familiar"])


# ===========================================================================
# Tests — Location perspective (get_presence_for_location)
# ===========================================================================


class TestPresenceForLocation:
    """Tests for get_presence_for_location — Location → Character traversal."""

    def test_common_direct_character_bond(self, db: Session) -> None:
        """Character directly bonded to the location is in the common tier."""
        g = _build_graph(db)
        # NPC1 -> Location_B (directional)
        result = get_presence_for_location(db, g["loc_b"].id)
        # Traversal: Location_B <- NPC1 (inbound via adjacency: NPC1->Location_B is directional,
        # so Location_B has no outbound adj to NPC1 in the adjacency list).
        # With directional bonds, Location_B cannot reach NPC1 by traversal
        # because there's no reverse edge.  NPC1 directly owns the bond.
        # So from Location_B's perspective, it has NO outbound traversal edges.
        # This is correct — directional means Location_B doesn't "know" NPC1 directly.
        # The only way location sees common presence is if a bond goes TO the location
        # bidirectionally OR if Location owns a bond pointing to a character.
        assert result["common"] == []

    def test_bidirectional_bond_creates_presence(self, db: Session) -> None:
        """A bidirectional bond character↔location puts the character in common."""
        pc = _full_pc(db, "PC for Location")
        loc = _location(db, "Shared Location")

        # Character bonds to location bidirectionally (GM override)
        _make_bond(db, "character", pc.id, "location", loc.id, bidirectional=True)

        result = get_presence_for_location(db, loc.id)
        assert pc.id in _ids(result["common"])

    def test_location_bond_to_character_creates_presence(self, db: Session) -> None:
        """A location_bond from the location to a character creates common presence."""
        loc = _location(db, "Notable Location")
        pc = _full_pc(db, "Notable PC")

        # Location owns a bond pointing to the character
        _make_bond(db, "location", loc.id, "character", pc.id, bidirectional=False)

        result = get_presence_for_location(db, loc.id)
        assert pc.id in _ids(result["common"])

    def test_familiar_via_one_character_intermediary(self, db: Session) -> None:
        """Character reachable through one Character intermediary is familiar."""
        loc = _location(db, "Central Location")
        npc = _npc(db, "NPC Intermediary")
        pc = _full_pc(db, "Distant PC")

        # Location -> NPC (loc_bond, directional)
        _make_bond(db, "location", loc.id, "character", npc.id, bidirectional=False)
        # NPC <-> PC (bidirectional)
        _make_bond(db, "character", npc.id, "character", pc.id, bidirectional=True)

        result = get_presence_for_location(db, loc.id)
        # loc->npc (hop1: npc is common), npc->pc (hop2: pc is familiar)
        assert npc.id in _ids(result["common"])
        assert pc.id in _ids(result["familiar"])

    def test_only_collects_characters_not_locations(self, db: Session) -> None:
        """Locations reachable via bonds do not appear in the presence tiers."""
        loc = _location(db, "Start Loc")
        pc = _full_pc(db, "PC with bonds")
        loc2 = _location(db, "Another Loc")

        _make_bond(db, "location", loc.id, "character", pc.id, bidirectional=False)
        _make_bond(db, "character", pc.id, "location", loc2.id, bidirectional=False)

        result = get_presence_for_location(db, loc.id)
        all_items = result["common"] + result["familiar"] + result["known"]
        for item in all_items:
            assert item["type"] == "character", f"Non-character found: {item}"

    def test_empty_when_no_bonds(self, db: Session) -> None:
        """A location with no bonds returns empty presence tiers."""
        loc = _location(db, "Empty Location")
        result = get_presence_for_location(db, loc.id)
        assert result["common"] == []
        assert result["familiar"] == []
        assert result["known"] == []


# ===========================================================================
# Tests — Known tier (3-hop to location via Character↔Character path)
# ===========================================================================


class TestKnownTierCharacterPerspective:
    """Test the known (3-hop) tier for Character → Location traversal.

    A valid 3-hop path to a Location under the Character-intermediary constraint:
    PC1(start) --1--> NPC1(char) --2--> PC2(char) --3--> Location_X

    Group1 as a non-character intermediary cannot be followed by a Location hop;
    it must be followed by a Character.  So:
    PC1 --1--> Group1(group) --2--> BLOCKED (can only go to character next)
    PC1 --1--> NPC1(char) --2--> Group1(group) --3--> BLOCKED (must go char next)
    """

    def test_known_location_at_hop_3_via_two_chars(self, db: Session) -> None:
        """Location at 3-hop via two Character intermediaries is 'known'."""
        pc1 = _full_pc(db, "PC1 Known")
        npc1 = _npc(db, "NPC1 Known")
        pc2 = _full_pc(db, "PC2 Known")
        loc_known = _location(db, "Location Known")

        # PC1 <-> NPC1
        _make_bond(db, "character", pc1.id, "character", npc1.id, bidirectional=True)
        # NPC1 <-> PC2
        _make_bond(db, "character", npc1.id, "character", pc2.id, bidirectional=True)
        # PC2 -> Location Known
        _make_bond(db, "character", pc2.id, "location", loc_known.id, bidirectional=False)

        result = get_locations_for_character(db, pc1.id)
        assert loc_known.id in _ids(result["known"])
        assert loc_known.id not in _ids(result["common"])
        assert loc_known.id not in _ids(result["familiar"])

    def test_location_beyond_3_hops_excluded(self, db: Session) -> None:
        """Location at hop 4 does not appear in any tier."""
        pc1 = _full_pc(db, "PC1 Deep")
        npc1 = _npc(db, "NPC1 Deep")
        pc2 = _full_pc(db, "PC2 Deep")
        pc3 = _full_pc(db, "PC3 Deep")
        loc_deep = _location(db, "Location Deep")

        _make_bond(db, "character", pc1.id, "character", npc1.id, bidirectional=True)
        _make_bond(db, "character", npc1.id, "character", pc2.id, bidirectional=True)
        _make_bond(db, "character", pc2.id, "character", pc3.id, bidirectional=True)
        _make_bond(db, "character", pc3.id, "location", loc_deep.id, bidirectional=False)

        result = get_locations_for_character(db, pc1.id)
        all_ids = _ids(result["common"]) | _ids(result["familiar"]) | _ids(result["known"])
        assert loc_deep.id not in all_ids


# ===========================================================================
# Tests — Traversal exclusions
# ===========================================================================


class TestTraversalExclusions:
    """Inactive bonds, deleted game objects, and trauma bonds are excluded."""

    def test_inactive_bond_excluded(self, db: Session) -> None:
        """Inactive bonds are not traversed."""
        pc = _full_pc(db, "PC Active")
        loc = _location(db, "Location via Inactive")
        npc = _npc(db, "NPC Bridge")

        # PC -> NPC (active)
        _make_bond(db, "character", pc.id, "character", npc.id, bidirectional=True)
        # NPC -> Location (INACTIVE)
        _make_bond(
            db, "character", npc.id, "location", loc.id,
            bidirectional=False, is_active=False,
        )

        result = get_locations_for_character(db, pc.id)
        all_ids = _ids(result["common"]) | _ids(result["familiar"]) | _ids(result["known"])
        assert loc.id not in all_ids

    def test_inactive_bond_to_intermediary_blocked(self, db: Session) -> None:
        """An inactive bond to an intermediary blocks the rest of the path."""
        pc = _full_pc(db, "PC Blocked")
        npc = _npc(db, "NPC Blocked")
        loc = _location(db, "Location Blocked")

        # PC -> NPC (INACTIVE)
        _make_bond(
            db, "character", pc.id, "character", npc.id,
            bidirectional=True, is_active=False,
        )
        # NPC -> Location (active, but unreachable because of inactive bridge)
        _make_bond(db, "character", npc.id, "location", loc.id, bidirectional=False)

        result = get_locations_for_character(db, pc.id)
        all_ids = _ids(result["common"]) | _ids(result["familiar"]) | _ids(result["known"])
        assert loc.id not in all_ids

    def test_soft_deleted_intermediary_is_dead_end(self, db: Session) -> None:
        """A soft-deleted Game Object is a dead end in traversal."""
        pc = _full_pc(db, "PC Deletion")
        npc = _npc(db, "NPC Deleted")
        loc = _location(db, "Location via Deleted")

        # Build bonds first (before deleting npc)
        _make_bond(db, "character", pc.id, "character", npc.id, bidirectional=True)
        _make_bond(db, "character", npc.id, "location", loc.id, bidirectional=False)

        # Now soft-delete the intermediary
        npc.is_deleted = True
        db.flush()

        result = get_locations_for_character(db, pc.id)
        all_ids = _ids(result["common"]) | _ids(result["familiar"]) | _ids(result["known"])
        assert loc.id not in all_ids

    def test_soft_deleted_target_location_excluded(self, db: Session) -> None:
        """A soft-deleted target location is not returned."""
        pc = _full_pc(db, "PC Del Loc")
        loc = _location(db, "Deleted Location")

        _make_bond(db, "character", pc.id, "location", loc.id, bidirectional=False)

        # Soft-delete the location AFTER creating the bond
        loc.is_deleted = True
        db.flush()

        result = get_locations_for_character(db, pc.id)
        assert loc.id not in _ids(result["common"])

    def test_trauma_bond_excluded(self, db: Session) -> None:
        """Trauma bonds (is_trauma=True, no target) are excluded from traversal."""
        pc = _full_pc(db, "PC Trauma")
        loc = _location(db, "Location Not via Trauma")

        # Create a trauma bond directly (no target)
        trauma_slot = Slot(
            slot_type="pc_bond",
            owner_type="character",
            owner_id=pc.id,
            target_type=None,
            target_id=None,
            name="Trauma",
            is_active=True,
            is_trauma=True,
            charges=5,
            degradations=0,
            bidirectional=False,
        )
        db.add(trauma_slot)
        db.flush()

        # Also create a normal bond to location for comparison
        _make_bond(db, "character", pc.id, "location", loc.id, bidirectional=False)

        result = get_locations_for_character(db, pc.id)
        # Only the normal bond's location appears; no crash from trauma slot
        assert loc.id in _ids(result["common"])


# ===========================================================================
# Tests — Character-intermediary constraint enforcement
# ===========================================================================


class TestCharacterIntermediaryConstraint:
    """Verify that non-Character → non-Character traversal is blocked."""

    def test_group_to_location_not_traversed_after_non_char(
        self, db: Session
    ) -> None:
        """After reaching a Group, the next hop can only go to a Character."""
        pc = _full_pc(db, "PC Constraint")
        npc = _npc(db, "NPC Constraint")
        group = _group(db, "Group Constraint")
        loc = _location(db, "Location via Group")

        # PC <-> NPC
        _make_bond(db, "character", pc.id, "character", npc.id, bidirectional=True)
        # NPC <-> Group (bidirectional)
        _make_bond(db, "character", npc.id, "group", group.id, bidirectional=True)
        # Group -> Location (holding, directional)
        _make_bond(db, "group", group.id, "location", loc.id, bidirectional=False)

        result = get_locations_for_character(db, pc.id)
        # Path: PC->NPC(1)->Group(2)->Location(3)
        # At Group (non-char), next hop MUST be a Character.
        # Location is NOT a Character → edge is BLOCKED.
        all_ids = _ids(result["common"]) | _ids(result["familiar"]) | _ids(result["known"])
        assert loc.id not in all_ids

    def test_first_hop_can_go_to_group(self, db: Session) -> None:
        """The first hop from the starting node can go to any type (Group ok)."""
        pc = _full_pc(db, "PC First Hop")
        group = _group(db, "Group First Hop")
        pc2 = _full_pc(db, "PC2 First Hop")
        loc = _location(db, "Loc via Group first hop")

        # PC -> Group (first hop — allowed to any type)
        _make_bond(db, "character", pc.id, "group", group.id, bidirectional=True)
        # PC2 <-> Group (bidirectional, so Group -> PC2 edge exists)
        _make_bond(db, "character", pc2.id, "group", group.id, bidirectional=True)
        # PC2 -> Location
        _make_bond(db, "character", pc2.id, "location", loc.id, bidirectional=False)

        result = get_locations_for_character(db, pc.id)
        # Path: PC->Group(1, non-char) must go to Character next
        # Group->PC2 (2-hop) — PC2 is Character, OK
        # PC2->Location (3-hop) — collecting location at hop 3 = known
        assert pc2.id not in _ids(result["common"])  # not collecting characters here
        # Location is collected at hop 3 = known
        assert loc.id in _ids(result["known"])

    def test_group_to_group_traversal_blocked(self, db: Session) -> None:
        """Group→Group traversal is blocked (both non-Character)."""
        pc = _full_pc(db, "PC G2G")
        npc = _npc(db, "NPC G2G")
        group1 = _group(db, "Group G2G 1")
        group2 = _group(db, "Group G2G 2")
        loc = _location(db, "Loc via G2G")

        # PC -> NPC (bidirectional)
        _make_bond(db, "character", pc.id, "character", npc.id, bidirectional=True)
        # NPC -> Group1 (bidirectional)
        _make_bond(db, "character", npc.id, "group", group1.id, bidirectional=True)
        # Group1 <-> Group2 (group_relation, bidirectional)
        _make_bond(db, "group", group1.id, "group", group2.id, bidirectional=True)
        # Some PC bonded to Group2 -> Location
        pc3 = _full_pc(db, "PC3 G2G")
        _make_bond(db, "character", pc3.id, "group", group2.id, bidirectional=True)
        _make_bond(db, "character", pc3.id, "location", loc.id, bidirectional=False)

        result = get_locations_for_character(db, pc.id)
        # Path: PC->NPC(1)->Group1(2)->Group2(3)
        # At Group1 (non-char), next hop must be Character. Group2 is NOT Character → BLOCKED.
        # Location is not reachable.
        all_ids = _ids(result["common"]) | _ids(result["familiar"]) | _ids(result["known"])
        assert loc.id not in all_ids


# ===========================================================================
# Tests — Bidirectionality
# ===========================================================================


class TestBidirectionality:
    """Verify bidirectional bonds create edges in both directions."""

    def test_bidirectional_bond_traversable_both_ways(self, db: Session) -> None:
        """A bidirectional bond between two characters is traversable from either side."""
        pc1 = _full_pc(db, "PC Bi 1")
        pc2 = _full_pc(db, "PC Bi 2")
        loc1 = _location(db, "Loc Bi 1")
        loc2 = _location(db, "Loc Bi 2")

        # PC1 <-> PC2 (bidirectional)
        _make_bond(db, "character", pc1.id, "character", pc2.id, bidirectional=True)
        # PC1 -> Loc1
        _make_bond(db, "character", pc1.id, "location", loc1.id, bidirectional=False)
        # PC2 -> Loc2
        _make_bond(db, "character", pc2.id, "location", loc2.id, bidirectional=False)

        # From PC1: loc1 common, loc2 familiar
        result1 = get_locations_for_character(db, pc1.id)
        assert loc1.id in _ids(result1["common"])
        assert loc2.id in _ids(result1["familiar"])

        # From PC2: loc2 common, loc1 familiar
        result2 = get_locations_for_character(db, pc2.id)
        assert loc2.id in _ids(result2["common"])
        assert loc1.id in _ids(result2["familiar"])

    def test_directional_bond_only_one_direction(self, db: Session) -> None:
        """A directional bond is NOT traversable in reverse."""
        pc = _full_pc(db, "PC Directional")
        loc = _location(db, "Loc Directional")

        # PC -> Loc (directional)
        _make_bond(db, "character", pc.id, "location", loc.id, bidirectional=False)

        # PC sees loc in common
        result_char = get_locations_for_character(db, pc.id)
        assert loc.id in _ids(result_char["common"])

        # Location does NOT see pc in its presence (directional bond, no reverse edge)
        result_loc = get_presence_for_location(db, loc.id)
        all_char_ids = (
            _ids(result_loc["common"])
            | _ids(result_loc["familiar"])
            | _ids(result_loc["known"])
        )
        assert pc.id not in all_char_ids


# ===========================================================================
# Tests — Result shape and metadata
# ===========================================================================


class TestResultShape:
    """Verify the structure and metadata of returned results."""

    def test_result_has_all_three_tiers(self, db: Session) -> None:
        """compute_presence always returns all three tier keys."""
        pc = _full_pc(db, "PC Shape")
        result = get_locations_for_character(db, pc.id)
        assert "common" in result
        assert "familiar" in result
        assert "known" in result

    def test_entity_ref_has_id_name_type(self, db: Session) -> None:
        """Each item in a tier has id, name, and type fields."""
        pc = _full_pc(db, "PC Ref")
        loc = _location(db, "Named Location")
        _make_bond(db, "character", pc.id, "location", loc.id, bidirectional=False)

        result = get_locations_for_character(db, pc.id)
        assert len(result["common"]) == 1
        item = result["common"][0]
        assert item["id"] == loc.id
        assert item["name"] == "Named Location"
        assert item["type"] == "location"


# ===========================================================================
# Tests — API endpoint integration
# ===========================================================================


class TestCharacterDetailAPIWithLocations:
    """Integration tests for GET /api/v1/characters/{id} — locations field."""

    def test_character_detail_includes_locations_field(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """GET /characters/{id} returns a locations field with three tiers."""
        auth_as(client, seed_data["gm"])
        pc1 = seed_data["pc1"]
        resp = client.get(f"/api/v1/characters/{pc1.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "locations" in data
        assert "common" in data["locations"]
        assert "familiar" in data["locations"]
        assert "known" in data["locations"]

    def test_character_detail_locations_are_lists(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """Each tier in locations is a list."""
        auth_as(client, seed_data["gm"])
        pc1 = seed_data["pc1"]
        resp = client.get(f"/api/v1/characters/{pc1.id}")
        data = resp.json()
        assert isinstance(data["locations"]["common"], list)
        assert isinstance(data["locations"]["familiar"], list)
        assert isinstance(data["locations"]["known"], list)

    def test_character_detail_locations_based_on_seed_data(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """npc1 is bonded to the region — region appears in npc1's common tier."""
        auth_as(client, seed_data["gm"])
        npc1 = seed_data["npc1"]
        region = seed_data["region"]
        resp = client.get(f"/api/v1/characters/{npc1.id}")
        assert resp.status_code == 200
        data = resp.json()
        common_ids = {item["id"] for item in data["locations"]["common"]}
        assert region.id in common_ids

    def test_character_not_found_still_404(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """Non-existent character still returns 404."""
        auth_as(client, seed_data["gm"])
        resp = client.get("/api/v1/characters/01JZZZZZZZZZZZZZZZZZZZZZZZ")
        assert resp.status_code == 404


class TestLocationDetailAPIWithPresence:
    """Integration tests for GET /api/v1/locations/{id} — presence field."""

    def test_location_detail_includes_presence_field(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """GET /locations/{id} returns a presence field with three tiers."""
        auth_as(client, seed_data["gm"])
        region = seed_data["region"]
        resp = client.get(f"/api/v1/locations/{region.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "presence" in data
        assert "common" in data["presence"]
        assert "familiar" in data["presence"]
        assert "known" in data["presence"]

    def test_location_detail_presence_are_lists(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """Each tier in presence is a list."""
        auth_as(client, seed_data["gm"])
        region = seed_data["region"]
        resp = client.get(f"/api/v1/locations/{region.id}")
        data = resp.json()
        assert isinstance(data["presence"]["common"], list)
        assert isinstance(data["presence"]["familiar"], list)
        assert isinstance(data["presence"]["known"], list)

    def test_location_not_found_still_404(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """Non-existent location still returns 404."""
        auth_as(client, seed_data["gm"])
        resp = client.get("/api/v1/locations/DOESNOTEXIST12345678901")
        assert resp.status_code == 404

    def test_location_with_bidirectional_bond_shows_character_presence(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """A location with a bidirectional bond to a character shows that character."""
        auth_as(client, seed_data["gm"])
        region = seed_data["region"]
        pc1 = seed_data["pc1"]

        # Create a bidirectional bond from pc1 to the region
        from wizards_engine.models.slot import Slot

        bond = Slot(
            slot_type="pc_bond",
            owner_type="character",
            owner_id=pc1.id,
            target_type="location",
            target_id=region.id,
            name="Home Region",
            is_active=True,
            bidirectional=True,
            charges=0,
            degradations=0,
            is_trauma=False,
        )
        db.add(bond)
        db.commit()

        resp = client.get(f"/api/v1/locations/{region.id}")
        assert resp.status_code == 200
        data = resp.json()
        common_ids = {item["id"] for item in data["presence"]["common"]}
        assert pc1.id in common_ids
