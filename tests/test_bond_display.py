"""Tests for Story 2.3.2 — Bond Display on Game Object Detail.

Verifies that GET detail endpoints for characters, groups, and locations
return correct bond information with perspective-normalized labels.

Covers:
- CharacterDetailResponse includes bonds grouped by active/past
- Bidirectional inbound bonds appear on the target's bond list
- Perspective normalization: source sees source_label, target sees target_label
- GroupDetailResponse includes traits, bonds (flat list), and derived members
- LocationDetailResponse includes traits and bonds
- Edge cases: no bonds, past bonds, directional bonds not in target list
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import auth_as
from tests.fixtures import seed_data as _seed_data_fn
from wizards_engine.models.character import Character
from wizards_engine.models.group import Group
from wizards_engine.models.location import Location
from wizards_engine.models.slot import Slot
from wizards_engine.services.bond import (
    build_bond_display,
    create_bond,
    get_bonds_display_for_entity,
    get_group_members,
    get_traits_for_owner,
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


def _group_trait(db: Session, group: Group, name: str, description: str | None = None) -> Slot:
    """Create and flush a group_trait slot."""
    slot = Slot(
        slot_type="group_trait",
        owner_type="group",
        owner_id=group.id,
        name=name,
        description=description,
        is_active=True,
    )
    db.add(slot)
    db.flush()
    db.refresh(slot)
    return slot


def _feature_trait(db: Session, location: Location, name: str, description: str | None = None) -> Slot:
    """Create and flush a feature_trait slot."""
    slot = Slot(
        slot_type="feature_trait",
        owner_type="location",
        owner_id=location.id,
        name=name,
        description=description,
        is_active=True,
    )
    db.add(slot)
    db.flush()
    db.refresh(slot)
    return slot


# ===========================================================================
# Service-layer: build_bond_display perspective normalization
# ===========================================================================


class TestBuildBondDisplay:
    """Unit tests for perspective-normalized bond display at the service layer."""

    def test_outbound_bond_shows_source_label(self, db: Session) -> None:
        """From the source's perspective, label = source_label."""
        pc_a = _full_pc(db, "A")
        pc_b = _full_pc(db, "B")
        bond = create_bond(
            db,
            "character",
            pc_a.id,
            "character",
            pc_b.id,
            source_label="Old Friend",
            target_label="Rival",
        ).bond

        display = build_bond_display(db, bond, "character", pc_a.id)
        assert display.label == "Old Friend"

    def test_outbound_bond_target_is_the_actual_target(self, db: Session) -> None:
        """From the source's perspective, target_id/target_type point to the actual target."""
        pc_a = _full_pc(db, "A")
        pc_b = _full_pc(db, "B")
        bond = create_bond(db, "character", pc_a.id, "character", pc_b.id).bond

        display = build_bond_display(db, bond, "character", pc_a.id)
        assert display.target_id == pc_b.id
        assert display.target_type == "character"
        assert display.target_name == "B"

    def test_inbound_bond_shows_target_label(self, db: Session) -> None:
        """From the target's perspective on a bidirectional bond, label = target_label."""
        pc_a = _full_pc(db, "A")
        pc_b = _full_pc(db, "B")
        bond = create_bond(
            db,
            "character",
            pc_a.id,
            "character",
            pc_b.id,
            source_label="Friend from A",
            target_label="Friend from B",
        ).bond
        assert bond.bidirectional is True

        display = build_bond_display(db, bond, "character", pc_b.id)
        assert display.label == "Friend from B"

    def test_inbound_bond_target_points_to_source(self, db: Session) -> None:
        """From the target's perspective, target_id/target_type point to the bond's owner (the source)."""
        pc_a = _full_pc(db, "A")
        pc_b = _full_pc(db, "B")
        bond = create_bond(db, "character", pc_a.id, "character", pc_b.id).bond

        # B is the "target" of this bond record; from B's perspective the other end is A.
        display = build_bond_display(db, bond, "character", pc_b.id)
        assert display.target_id == pc_a.id
        assert display.target_type == "character"
        assert display.target_name == "A"

    def test_outbound_bond_empty_label_defaults_to_empty_string(self, db: Session) -> None:
        """When source_label is None, label is empty string."""
        pc = _full_pc(db)
        target = _full_pc(db, "T")
        bond = create_bond(db, "character", pc.id, "character", target.id).bond

        display = build_bond_display(db, bond, "character", pc.id)
        assert display.label == ""

    def test_pc_bond_includes_mechanical_fields(self, db: Session) -> None:
        """PC bonds include charges/degradations/is_trauma (charges starts at 5)."""
        pc = _full_pc(db)
        target = _full_pc(db, "T")
        bond = create_bond(db, "character", pc.id, "character", target.id).bond

        display = build_bond_display(db, bond, "character", pc.id)
        assert display.charges == 5  # PC bonds start at full charges (5)
        assert display.degradations == 0
        assert display.is_trauma is False

    def test_npc_bond_has_null_mechanical_fields(self, db: Session) -> None:
        """NPC bonds have charges/degradations/is_trauma = None."""
        npc = _npc(db)
        target = _full_pc(db, "T")
        bond = create_bond(db, "character", npc.id, "character", target.id).bond

        display = build_bond_display(db, bond, "character", npc.id)
        assert display.charges is None
        assert display.degradations is None
        assert display.is_trauma is None

    def test_group_bond_inbound_from_character(self, db: Session) -> None:
        """Group sees inbound character bond; target_id shows the character."""
        pc = _full_pc(db, "Member PC")
        group = _group(db, "The Org")
        bond = create_bond(
            db,
            "character",
            pc.id,
            "group",
            group.id,
            source_label="Member",
            target_label="They belong to us",
        ).bond
        assert bond.bidirectional is True

        display = build_bond_display(db, bond, "group", group.id)
        assert display.label == "They belong to us"
        assert display.target_id == pc.id
        assert display.target_name == "Member PC"


# ===========================================================================
# Service-layer: get_bonds_display_for_entity
# ===========================================================================


class TestGetBondsDisplayForEntity:
    """Tests for the combined active/past bond display aggregation."""

    def test_active_outbound_bond_in_active_list(self, db: Session) -> None:
        pc = _full_pc(db, "PC")
        target = _full_pc(db, "T")
        create_bond(db, "character", pc.id, "character", target.id)

        result = get_bonds_display_for_entity(db, "character", pc.id)
        assert len(result["active"]) == 1
        assert len(result["past"]) == 0

    def test_inactive_bond_in_past_list(self, db: Session) -> None:
        pc = _full_pc(db, "PC")
        target = _full_pc(db, "T")
        bond = create_bond(db, "character", pc.id, "character", target.id).bond
        bond.is_active = False
        db.flush()

        result = get_bonds_display_for_entity(db, "character", pc.id)
        assert len(result["active"]) == 0
        assert len(result["past"]) == 1

    def test_bidirectional_bond_appears_on_target_list(self, db: Session) -> None:
        """Inbound bidirectional bonds show up on the target's bond list."""
        pc_a = _full_pc(db, "A")
        pc_b = _full_pc(db, "B")
        create_bond(db, "character", pc_a.id, "character", pc_b.id)

        # B does not own this bond but should see it as inbound.
        result = get_bonds_display_for_entity(db, "character", pc_b.id)
        assert len(result["active"]) == 1

    def test_directional_bond_does_not_appear_on_target_list(self, db: Session) -> None:
        """Directional bonds are not included in the target's bond list."""
        pc = _full_pc(db)
        loc = _location(db, "A Place")
        create_bond(db, "character", pc.id, "location", loc.id)

        # The location should have no inbound bonds (directional).
        result = get_bonds_display_for_entity(db, "location", loc.id)
        assert len(result["active"]) == 0

    def test_no_duplicate_bonds_in_merged_list(self, db: Session) -> None:
        """A bond should appear exactly once even if merged from both owned and inbound queries."""
        pc_a = _full_pc(db, "A")
        pc_b = _full_pc(db, "B")
        bond = create_bond(db, "character", pc_a.id, "character", pc_b.id).bond

        # A owns the bond — check from A's side.
        result = get_bonds_display_for_entity(db, "character", pc_a.id)
        bond_ids = [b.id for b in result["active"]]
        assert bond_ids.count(bond.id) == 1

    def test_empty_when_no_bonds(self, db: Session) -> None:
        pc = _full_pc(db)
        result = get_bonds_display_for_entity(db, "character", pc.id)
        assert result["active"] == []
        assert result["past"] == []

    def test_both_active_and_past_populated(self, db: Session) -> None:
        pc = _full_pc(db, "PC")
        t1 = _full_pc(db, "T1")
        t2 = _full_pc(db, "T2")
        create_bond(db, "character", pc.id, "character", t1.id)
        old_bond = create_bond(db, "character", pc.id, "character", t2.id).bond
        old_bond.is_active = False
        db.flush()

        result = get_bonds_display_for_entity(db, "character", pc.id)
        assert len(result["active"]) == 1
        assert len(result["past"]) == 1


# ===========================================================================
# Service-layer: get_traits_for_owner
# ===========================================================================


class TestGetTraitsForOwner:
    """Tests for the trait query helper."""

    def test_returns_active_group_traits(self, db: Session) -> None:
        group = _group(db, "G")
        t1 = _group_trait(db, group, "Ruthless")
        t2 = _group_trait(db, group, "Well-Connected")

        traits = get_traits_for_owner(db, "group", group.id, "group_trait")
        ids = [t.id for t in traits]
        assert t1.id in ids
        assert t2.id in ids

    def test_excludes_inactive_traits(self, db: Session) -> None:
        group = _group(db)
        active = _group_trait(db, group, "Active Trait")
        inactive = _group_trait(db, group, "Old Trait")
        inactive.is_active = False
        db.flush()

        traits = get_traits_for_owner(db, "group", group.id, "group_trait")
        ids = [t.id for t in traits]
        assert active.id in ids
        assert inactive.id not in ids

    def test_returns_active_feature_traits(self, db: Session) -> None:
        loc = _location(db, "The Keep")
        t1 = _feature_trait(db, loc, "Ancient Walls")
        t2 = _feature_trait(db, loc, "Defensible Position")

        traits = get_traits_for_owner(db, "location", loc.id, "feature_trait")
        ids = [t.id for t in traits]
        assert t1.id in ids
        assert t2.id in ids

    def test_returns_empty_when_no_traits(self, db: Session) -> None:
        group = _group(db)
        traits = get_traits_for_owner(db, "group", group.id, "group_trait")
        assert traits == []

    def test_does_not_cross_contaminate_owners(self, db: Session) -> None:
        g1 = _group(db, "G1")
        g2 = _group(db, "G2")
        _group_trait(db, g1, "G1 Trait")
        t2 = _group_trait(db, g2, "G2 Trait")

        traits = get_traits_for_owner(db, "group", g2.id, "group_trait")
        assert len(traits) == 1
        assert traits[0].id == t2.id


# ===========================================================================
# Service-layer: get_group_members
# ===========================================================================


class TestGetGroupMembers:
    """Tests for the derived group membership query."""

    def test_pc_bonded_to_group_is_member(self, db: Session) -> None:
        pc = _full_pc(db, "A PC")
        group = _group(db, "The Party")
        create_bond(db, "character", pc.id, "group", group.id)

        members = get_group_members(db, group.id)
        member_ids = [m.id for m in members]
        assert pc.id in member_ids

    def test_npc_bonded_to_group_is_member(self, db: Session) -> None:
        npc = _npc(db, "An NPC")
        group = _group(db, "The Faction")
        create_bond(db, "character", npc.id, "group", group.id)

        members = get_group_members(db, group.id)
        assert npc.id in [m.id for m in members]

    def test_retired_bond_does_not_confer_membership(self, db: Session) -> None:
        pc = _full_pc(db, "Former Member")
        group = _group(db)
        bond = create_bond(db, "character", pc.id, "group", group.id).bond
        bond.is_active = False
        db.flush()

        members = get_group_members(db, group.id)
        assert pc.id not in [m.id for m in members]

    def test_returns_empty_when_no_members(self, db: Session) -> None:
        group = _group(db)
        members = get_group_members(db, group.id)
        assert members == []

    def test_multiple_members_all_returned(self, db: Session) -> None:
        pc1 = _full_pc(db, "PC 1")
        pc2 = _full_pc(db, "PC 2")
        npc = _npc(db, "NPC")
        group = _group(db, "The Crew")
        create_bond(db, "character", pc1.id, "group", group.id)
        create_bond(db, "character", pc2.id, "group", group.id)
        create_bond(db, "character", npc.id, "group", group.id)

        members = get_group_members(db, group.id)
        member_ids = {m.id for m in members}
        assert {pc1.id, pc2.id, npc.id} == member_ids


# ===========================================================================
# HTTP: GET /characters/{id} — bond display
# ===========================================================================


class TestCharacterDetailBonds:
    """Tests for bond fields in the GET /characters/{id} response."""

    def test_character_detail_has_bonds_field(self, client: TestClient, seed_data: dict) -> None:
        """GET /characters/{id} response includes a 'bonds' field."""
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/characters/{seed_data['pc1'].id}")
        assert response.status_code == 200
        data = response.json()
        assert "bonds" in data

    def test_character_bonds_has_active_and_past_keys(self, client: TestClient, seed_data: dict) -> None:
        """The bonds field contains 'active' and 'past' lists."""
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/characters/{seed_data['pc1'].id}")
        bonds = response.json()["bonds"]
        assert "active" in bonds
        assert "past" in bonds

    def test_pc1_active_bond_to_group_appears(self, client: TestClient, seed_data: dict) -> None:
        """pc1's bond to The Syndicate appears in its active bond list."""
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/characters/{seed_data['pc1'].id}")
        active_bonds = response.json()["bonds"]["active"]
        target_ids = [b["target_id"] for b in active_bonds]
        assert seed_data["group"].id in target_ids

    def test_active_bond_has_expected_fields(self, client: TestClient, seed_data: dict) -> None:
        """Each bond in the list has all required fields."""
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/characters/{seed_data['pc1'].id}")
        bond = response.json()["bonds"]["active"][0]
        required_fields = {
            "id", "slot_type", "target_type", "target_id", "target_name",
            "label", "description", "is_active", "bidirectional",
            "charges", "degradations", "is_trauma",
        }
        assert required_fields.issubset(set(bond.keys()))

    def test_pc_bond_shows_correct_slot_type(self, client: TestClient, seed_data: dict) -> None:
        """pc_bond slot_type appears in pc1's bond list."""
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/characters/{seed_data['pc1'].id}")
        active_bonds = response.json()["bonds"]["active"]
        slot_types = [b["slot_type"] for b in active_bonds]
        assert "pc_bond" in slot_types

    def test_character_with_no_bonds_has_empty_lists(self, client: TestClient, seed_data: dict) -> None:
        """pc3 has no bonds in seed_data — active and past should be empty."""
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/characters/{seed_data['pc3'].id}")
        bonds = response.json()["bonds"]
        assert bonds["active"] == []
        assert bonds["past"] == []

    def test_retired_bond_appears_in_past_list(self, client: TestClient, seed_data: dict, db: Session) -> None:
        """After retiring a bond, it moves from active to past."""
        pc = seed_data["pc3"]
        group = seed_data["group"]
        bond = create_bond(db, "character", pc.id, "group", group.id).bond
        db.commit()

        # Retire the bond.
        bond.is_active = False
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/characters/{pc.id}")
        bonds = response.json()["bonds"]
        assert bonds["active"] == []
        assert len(bonds["past"]) == 1
        assert bonds["past"][0]["is_active"] is False

    def test_inbound_bidirectional_bond_appears_on_target(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """A bidirectional bond from pc_a to pc_b shows up on pc_b's bond list."""
        pc_a = seed_data["pc1"]
        pc_b = seed_data["pc3"]
        create_bond(
            db,
            "character",
            pc_a.id,
            "character",
            pc_b.id,
            source_label="Ally",
            target_label="Partner",
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/characters/{pc_b.id}")
        active_bonds = response.json()["bonds"]["active"]
        target_ids = [b["target_id"] for b in active_bonds]
        # pc_b should see pc_a as "the other end" of this inbound bond.
        assert pc_a.id in target_ids

    def test_inbound_bond_label_is_target_label(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """The inbound bond's label on pc_b is the target_label, not source_label."""
        pc_a = seed_data["pc1"]
        pc_b = seed_data["pc3"]
        create_bond(
            db,
            "character",
            pc_a.id,
            "character",
            pc_b.id,
            source_label="My Rival",
            target_label="Their Rival",
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/characters/{pc_b.id}")
        active_bonds = response.json()["bonds"]["active"]
        # Find the bond where pc_a is the other end.
        bond_from_pc_a = next(b for b in active_bonds if b["target_id"] == pc_a.id)
        assert bond_from_pc_a["label"] == "Their Rival"

    def test_character_detail_still_includes_standard_fields(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """Bond display doesn't break existing character fields."""
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/characters/{seed_data['pc1'].id}")
        data = response.json()
        assert data["id"] == seed_data["pc1"].id
        assert data["name"] == seed_data["pc1"].name
        assert "detail_level" in data

    def test_list_endpoint_does_not_include_bonds(self, client: TestClient, seed_data: dict) -> None:
        """GET /characters (list) should not include bonds field."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/characters")
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) > 0
        # List items should not have 'bonds' field.
        assert "bonds" not in items[0]


# ===========================================================================
# HTTP: GET /groups/{id} — traits, bonds, members
# ===========================================================================


class TestGroupDetailBonds:
    """Tests for traits, bonds, and members in the GET /groups/{id} response."""

    def test_group_detail_has_traits_bonds_members_fields(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """GET /groups/{id} response includes 'traits', 'bonds', and 'members' fields."""
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/groups/{seed_data['group'].id}")
        assert response.status_code == 200
        data = response.json()
        assert "traits" in data
        assert "bonds" in data
        assert "members" in data

    def test_group_with_no_traits_returns_empty_list(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """The Syndicate has no traits in seed_data — traits list is empty."""
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/groups/{seed_data['group'].id}")
        assert response.json()["traits"] == []

    def test_group_traits_returned_correctly(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Group traits added to a group appear in the traits list."""
        group = seed_data["group"]
        trait = _group_trait(db, group, "Ruthless", "They show no mercy.")
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/groups/{group.id}")
        traits = response.json()["traits"]
        assert len(traits) == 1
        assert traits[0]["name"] == "Ruthless"
        assert traits[0]["description"] == "They show no mercy."

    def test_group_trait_has_required_fields(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Each trait entry has id, name, description."""
        group = seed_data["group"]
        _group_trait(db, group, "Influence", "Political reach.")
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/groups/{group.id}")
        trait = response.json()["traits"][0]
        assert "id" in trait
        assert "name" in trait
        assert "description" in trait

    def test_group_members_derived_from_bonds(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """pc1 and pc2 both have bonds to The Syndicate — they appear as members."""
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/groups/{seed_data['group'].id}")
        members = response.json()["members"]
        member_ids = [m["id"] for m in members]
        assert seed_data["pc1"].id in member_ids
        assert seed_data["pc2"].id in member_ids

    def test_group_member_has_required_fields(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """Each member entry has id, name, detail_level."""
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/groups/{seed_data['group'].id}")
        member = response.json()["members"][0]
        assert "id" in member
        assert "name" in member
        assert "detail_level" in member

    def test_group_with_no_members_returns_empty_list(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """A newly created group with no bonds has an empty members list."""
        new_group = _group(db, "New Empty Group")
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/groups/{new_group.id}")
        assert response.json()["members"] == []

    def test_group_bonds_flat_list(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Group bonds returned as a flat list (not grouped by active/past)."""
        group = seed_data["group"]
        peer = _group(db, "Peer Group")
        create_bond(db, "group", group.id, "group", peer.id)
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/groups/{group.id}")
        bonds = response.json()["bonds"]
        assert "active" in bonds
        assert "past" in bonds

    def test_group_relation_appears_in_bonds(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """An outbound group_relation bond appears in the group's bonds list."""
        group = seed_data["group"]
        peer = _group(db, "Peer Org")
        create_bond(db, "group", group.id, "group", peer.id)
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/groups/{group.id}")
        bonds = response.json()["bonds"]["active"]
        slot_types = [b["slot_type"] for b in bonds]
        assert "group_relation" in slot_types

    def test_group_bond_has_required_fields(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Each bond entry on a group has the required display fields."""
        group = seed_data["group"]
        peer = _group(db, "Ally Group")
        create_bond(db, "group", group.id, "group", peer.id, source_label="Ally")
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/groups/{group.id}")
        bond = response.json()["bonds"]["active"][0]
        required = {"id", "slot_type", "target_type", "target_id", "target_name", "label", "is_active"}
        assert required.issubset(set(bond.keys()))

    def test_group_list_endpoint_does_not_include_bonds(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """GET /groups (list) should not include bonds field."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/groups")
        items = response.json()["items"]
        assert len(items) > 0
        assert "bonds" not in items[0]


# ===========================================================================
# HTTP: GET /locations/{id} — traits, bonds
# ===========================================================================


class TestLocationDetailBonds:
    """Tests for traits and bonds in the GET /locations/{id} response."""

    def test_location_detail_has_traits_and_bonds_fields(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """GET /locations/{id} includes 'traits' and 'bonds' fields."""
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/locations/{seed_data['region'].id}")
        assert response.status_code == 200
        data = response.json()
        assert "traits" in data
        assert "bonds" in data

    def test_location_with_no_traits_returns_empty_list(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """The Shattered Coast has no traits in seed_data — traits list is empty."""
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/locations/{seed_data['region'].id}")
        assert response.json()["traits"] == []

    def test_location_traits_returned_correctly(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Feature traits added to a location appear in the traits list."""
        region = seed_data["region"]
        trait = _feature_trait(db, region, "Treacherous Cliffs", "Jagged rocks below.")
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/locations/{region.id}")
        traits = response.json()["traits"]
        assert len(traits) == 1
        assert traits[0]["name"] == "Treacherous Cliffs"
        assert traits[0]["description"] == "Jagged rocks below."

    def test_location_trait_has_required_fields(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Each trait entry has id, name, description."""
        region = seed_data["region"]
        _feature_trait(db, region, "Ancient Ruin")
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/locations/{region.id}")
        trait = response.json()["traits"][0]
        assert "id" in trait
        assert "name" in trait
        assert "description" in trait

    def test_location_bonds_grouped_by_status(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """Location bonds returned as active/past groups."""
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/locations/{seed_data['region'].id}")
        bonds = response.json()["bonds"]
        assert "active" in bonds
        assert "past" in bonds

    def test_location_bond_appears_in_bonds(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """An outbound location_bond appears in the location's bonds list."""
        region = seed_data["region"]
        pc = seed_data["pc3"]
        create_bond(
            db, "location", region.id, "character", pc.id,
            source_label="Notable inhabitant",
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/locations/{region.id}")
        bonds = response.json()["bonds"]["active"]
        assert len(bonds) >= 1
        bond_slot_types = [b["slot_type"] for b in bonds]
        assert "location_bond" in bond_slot_types

    def test_location_bond_has_required_fields(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Each bond entry has the required display fields."""
        region = seed_data["region"]
        pc = seed_data["pc3"]
        create_bond(db, "location", region.id, "character", pc.id)
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/locations/{region.id}")
        bond = response.json()["bonds"]["active"][0]
        required = {"id", "slot_type", "target_type", "target_id", "target_name", "label", "is_active"}
        assert required.issubset(set(bond.keys()))

    def test_location_list_endpoint_does_not_include_bonds(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """GET /locations (list) should not include bonds or traits fields."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/locations")
        items = response.json()["items"]
        assert len(items) > 0
        assert "bonds" not in items[0]
        assert "traits" not in items[0]

    def test_location_detail_still_includes_standard_fields(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """Bond/trait display doesn't break existing location fields."""
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/locations/{seed_data['region'].id}")
        data = response.json()
        assert data["id"] == seed_data["region"].id
        assert data["name"] == seed_data["region"].name
        assert "parent_id" in data


# ===========================================================================
# Cross-entity: perspective normalization round-trip
# ===========================================================================


class TestPerspectiveNormalizationRoundTrip:
    """Bidirectional bond labels appear correctly from both endpoints."""

    def test_bidirectional_bond_different_labels_each_side(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """A bidirectional bond between two PCs shows different labels from each side."""
        pc_a = seed_data["pc1"]
        pc_b = seed_data["pc3"]
        create_bond(
            db,
            "character",
            pc_a.id,
            "character",
            pc_b.id,
            source_label="My Rival",
            target_label="Their Rival",
        )
        db.commit()

        auth_as(client, seed_data["gm"])

        # From pc_a's side: label = "My Rival", target = pc_b
        resp_a = client.get(f"/api/v1/characters/{pc_a.id}")
        a_bonds = resp_a.json()["bonds"]["active"]
        bond_a = next(b for b in a_bonds if b["target_id"] == pc_b.id)
        assert bond_a["label"] == "My Rival"

        # From pc_b's side: label = "Their Rival", target = pc_a
        resp_b = client.get(f"/api/v1/characters/{pc_b.id}")
        b_bonds = resp_b.json()["bonds"]["active"]
        bond_b = next(b for b in b_bonds if b["target_id"] == pc_a.id)
        assert bond_b["label"] == "Their Rival"

    def test_group_group_bond_bidirectional_both_see_it(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """A bidirectional group-group bond appears on both groups' bond lists."""
        group = seed_data["group"]
        peer = _group(db, "Rival Syndicate")
        create_bond(
            db,
            "group",
            group.id,
            "group",
            peer.id,
            source_label="Rivals",
            target_label="Competitors",
        )
        db.commit()

        auth_as(client, seed_data["gm"])

        resp_group = client.get(f"/api/v1/groups/{group.id}")
        group_bonds = resp_group.json()["bonds"]["active"]
        # Group should see the bond with peer as target
        peer_bond_on_group = next(
            (b for b in group_bonds if b["target_id"] == peer.id), None
        )
        assert peer_bond_on_group is not None
        assert peer_bond_on_group["label"] == "Rivals"

        resp_peer = client.get(f"/api/v1/groups/{peer.id}")
        peer_bonds = resp_peer.json()["bonds"]["active"]
        # Peer should see the bond with group as "target" (the other end from peer's view)
        group_bond_on_peer = next(
            (b for b in peer_bonds if b["target_id"] == group.id), None
        )
        assert group_bond_on_peer is not None
        assert group_bond_on_peer["label"] == "Competitors"
