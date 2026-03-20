"""Tests for the bond-distance visibility filtering service (Story 4.1.3).

Exercises all 7 visibility levels:
- silent:   GM only; players always excluded
- gm_only:  GM only; players always excluded
- private:  actor's character + primary target owner (if PC) + GM
- bonded:   PCs with a direct bond (1-hop) to any event target + GM
- familiar: PCs within 2-hop Character-intermediary traversal + GM
- public:   PCs within 3-hop Character-intermediary traversal + GM
- global:   all players + GM

Also covers:
- get_reachable_nodes — BFS collecting all nodes by hop distance
- get_visible_character_ids — character-filtered reachability helper
- filter_events_for_user — bulk filter wrapper
- Edge cases: no targets, no bonds, missing actor, deleted intermediaries
"""

from __future__ import annotations

import secrets

import pytest
from sqlalchemy.orm import Session

from wizards_engine.models.character import Character
from wizards_engine.models.event import Event, EventTarget
from wizards_engine.models.group import Group
from wizards_engine.models.location import Location
from wizards_engine.models.slot import Slot
from wizards_engine.models.user import User
from wizards_engine.services.visibility import (
    can_user_see_event,
    filter_events_for_user,
    get_reachable_nodes,
    get_visible_character_ids,
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
    """Create and flush a Group."""
    g = Group(name=name, tier=1)
    db.add(g)
    db.flush()
    db.refresh(g)
    return g


def _location(db: Session, name: str) -> Location:
    """Create and flush a Location."""
    loc = Location(name=name)
    db.add(loc)
    db.flush()
    db.refresh(loc)
    return loc


def _player(db: Session, character: Character, name: str = "Player") -> User:
    """Create and flush a player User linked to *character*."""
    u = User(
        display_name=name,
        role="player",
        login_code=secrets.token_urlsafe(16),
        is_active=True,
        character_id=character.id,
    )
    db.add(u)
    db.flush()
    db.refresh(u)
    return u


def _gm(db: Session) -> User:
    """Create and flush a GM User (no character link)."""
    u = User(
        display_name="GM",
        role="gm",
        login_code=secrets.token_urlsafe(16),
        is_active=True,
    )
    db.add(u)
    db.flush()
    db.refresh(u)
    return u


def _bond(
    db: Session,
    owner_type: str,
    owner_id: str,
    target_type: str,
    target_id: str,
    *,
    bidirectional: bool = True,
    is_active: bool = True,
    slot_type: str | None = None,
) -> Slot:
    """Insert a bond slot directly."""
    if slot_type is None:
        if owner_type == "character":
            obj = db.get(Character, owner_id)
            slot_type = "pc_bond" if (obj and obj.detail_level == "full") else "npc_bond"
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
        name="test bond",
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


def _event(
    db: Session,
    visibility: str,
    *,
    actor_user: User | None = None,
    targets: list[tuple[str, str, bool]] | None = None,
) -> Event:
    """Create a minimal Event with the given visibility.

    Args:
        db: SQLAlchemy session.
        visibility: One of the 7 visibility level strings.
        actor_user: The User acting (sets actor_id and actor_type).
        targets: List of ``(target_type, target_id, is_primary)`` tuples.

    Returns:
        Flushed Event instance.
    """
    actor_type = "gm" if (actor_user and actor_user.role == "gm") else (
        "player" if actor_user else "system"
    )
    ev = Event(
        type="test.event",
        actor_type=actor_type,
        actor_id=actor_user.id if actor_user else None,
        changes={},
        visibility=visibility,
    )
    db.add(ev)
    db.flush()

    for (t_type, t_id, is_primary) in (targets or []):
        et = EventTarget(
            event_id=ev.id,
            target_type=t_type,
            target_id=t_id,
            is_primary=is_primary,
        )
        db.add(et)

    db.flush()
    db.refresh(ev)
    return ev


# ===========================================================================
# Tests — get_reachable_nodes
# ===========================================================================


class TestGetReachableNodes:
    """Tests for the low-level BFS reachability helper."""

    def test_returns_dict_keyed_by_hop(self, db: Session) -> None:
        """Result has integer keys 1 through max_hops."""
        pc = _full_pc(db, "PC Reach")
        result = get_reachable_nodes(db, "character", pc.id, max_hops=3)
        assert set(result.keys()) == {1, 2, 3}

    def test_empty_when_no_bonds(self, db: Session) -> None:
        """An isolated node has no reachable neighbours."""
        pc = _full_pc(db, "PC Isolated")
        result = get_reachable_nodes(db, "character", pc.id, max_hops=3)
        assert result[1] == set()
        assert result[2] == set()
        assert result[3] == set()

    def test_direct_bond_at_hop_1(self, db: Session) -> None:
        """A directly bonded node appears at hop 1."""
        pc = _full_pc(db, "PC Hop1")
        npc = _npc(db, "NPC Hop1")
        _bond(db, "character", pc.id, "character", npc.id, bidirectional=True)

        result = get_reachable_nodes(db, "character", pc.id, max_hops=1)
        assert ("character", npc.id) in result[1]

    def test_indirect_via_character_at_hop_2(self, db: Session) -> None:
        """Node reachable via one Character intermediary appears at hop 2."""
        pc = _full_pc(db, "PC Hop2 Start")
        npc = _npc(db, "NPC Hop2 Mid")
        loc = _location(db, "Loc Hop2 End")
        _bond(db, "character", pc.id, "character", npc.id, bidirectional=True)
        _bond(db, "character", npc.id, "location", loc.id, bidirectional=False)

        result = get_reachable_nodes(db, "character", pc.id, max_hops=2)
        assert ("location", loc.id) in result[2]

    def test_closest_hop_wins(self, db: Session) -> None:
        """A node reachable at hop 1 is not also in hop 2 set."""
        pc = _full_pc(db, "PC Close")
        npc = _npc(db, "NPC Close")
        _bond(db, "character", pc.id, "character", npc.id, bidirectional=True)
        # Add a second bond to npc from another intermediary to ensure
        # the npc is only listed once, at hop 1.
        pc2 = _full_pc(db, "PC2 Close")
        _bond(db, "character", pc.id, "character", pc2.id, bidirectional=True)
        _bond(db, "character", pc2.id, "character", npc.id, bidirectional=True)

        result = get_reachable_nodes(db, "character", pc.id, max_hops=3)
        assert ("character", npc.id) in result[1]
        assert ("character", npc.id) not in result[2]
        assert ("character", npc.id) not in result[3]

    def test_start_node_not_in_result(self, db: Session) -> None:
        """The starting node never appears in the result sets."""
        pc = _full_pc(db, "PC Self")
        npc = _npc(db, "NPC Neighbor")
        _bond(db, "character", pc.id, "character", npc.id, bidirectional=True)

        result = get_reachable_nodes(db, "character", pc.id, max_hops=2)
        for hop_set in result.values():
            assert ("character", pc.id) not in hop_set

    def test_character_intermediary_constraint_enforced(self, db: Session) -> None:
        """After a non-Character node the next hop must be a Character."""
        pc = _full_pc(db, "PC Constraint")
        npc = _npc(db, "NPC Constraint")
        grp = _group(db, "Group Constraint")
        loc = _location(db, "Loc Constraint")

        # pc -> npc -> group -> loc (group-to-location blocked by constraint)
        _bond(db, "character", pc.id, "character", npc.id, bidirectional=True)
        _bond(db, "character", npc.id, "group", grp.id, bidirectional=True)
        _bond(db, "group", grp.id, "location", loc.id, bidirectional=False)

        result = get_reachable_nodes(db, "character", pc.id, max_hops=3)
        all_nodes = result[1] | result[2] | result[3]
        assert ("location", loc.id) not in all_nodes

    def test_deleted_node_is_dead_end(self, db: Session) -> None:
        """A soft-deleted node is excluded and blocks further traversal."""
        pc = _full_pc(db, "PC Del BFS")
        npc = _npc(db, "NPC Del BFS")
        loc = _location(db, "Loc Del BFS")
        _bond(db, "character", pc.id, "character", npc.id, bidirectional=True)
        _bond(db, "character", npc.id, "location", loc.id, bidirectional=False)

        npc.is_deleted = True
        db.flush()

        result = get_reachable_nodes(db, "character", pc.id, max_hops=3)
        all_nodes = result[1] | result[2] | result[3]
        assert ("character", npc.id) not in all_nodes
        assert ("location", loc.id) not in all_nodes


# ===========================================================================
# Tests — get_visible_character_ids
# ===========================================================================


class TestGetVisibleCharacterIds:
    """Tests for the PC-reachability helper."""

    def test_returns_character_ids_only(self, db: Session) -> None:
        """Only Character IDs are returned; Groups/Locations are excluded."""
        pc = _full_pc(db, "PC Vis Char")
        npc = _npc(db, "NPC Vis Char")
        loc = _location(db, "Loc Vis Char")
        _bond(db, "character", pc.id, "character", npc.id, bidirectional=True)
        _bond(db, "character", pc.id, "location", loc.id, bidirectional=False)

        result = get_visible_character_ids(db, "character", pc.id, max_hops=1)
        assert npc.id in result
        assert loc.id not in result

    def test_accumulates_across_all_hops(self, db: Session) -> None:
        """Characters from hop 1 AND hop 2 are all in the result set."""
        pc = _full_pc(db, "PC Accum")
        npc1 = _npc(db, "NPC Accum 1")
        pc2 = _full_pc(db, "PC2 Accum")
        _bond(db, "character", pc.id, "character", npc1.id, bidirectional=True)
        _bond(db, "character", npc1.id, "character", pc2.id, bidirectional=True)

        result = get_visible_character_ids(db, "character", pc.id, max_hops=2)
        assert npc1.id in result
        assert pc2.id in result

    def test_empty_when_no_bonds(self, db: Session) -> None:
        """Isolated node returns empty set."""
        pc = _full_pc(db, "PC Isolated Char IDs")
        result = get_visible_character_ids(db, "character", pc.id, max_hops=3)
        assert result == set()


# ===========================================================================
# Tests — can_user_see_event: silent
# ===========================================================================


class TestSilentVisibility:
    """silent events: GM can see; players cannot."""

    def test_gm_sees_silent(self, db: Session) -> None:
        gm = _gm(db)
        ev = _event(db, "silent")
        assert can_user_see_event(db, gm, ev) is True

    def test_player_cannot_see_silent(self, db: Session) -> None:
        pc = _full_pc(db, "PC Silent")
        player = _player(db, pc)
        ev = _event(db, "silent")
        assert can_user_see_event(db, player, ev) is False

    def test_player_without_character_cannot_see_silent(self, db: Session) -> None:
        player = User(
            display_name="No Char Player",
            role="player",
            login_code=secrets.token_urlsafe(16),
            is_active=True,
        )
        db.add(player)
        db.flush()
        ev = _event(db, "silent")
        assert can_user_see_event(db, player, ev) is False


# ===========================================================================
# Tests — can_user_see_event: gm_only
# ===========================================================================


class TestGmOnlyVisibility:
    """gm_only events: GM can see; players cannot."""

    def test_gm_sees_gm_only(self, db: Session) -> None:
        gm = _gm(db)
        ev = _event(db, "gm_only")
        assert can_user_see_event(db, gm, ev) is True

    def test_player_cannot_see_gm_only(self, db: Session) -> None:
        pc = _full_pc(db, "PC GM Only")
        player = _player(db, pc)
        ev = _event(db, "gm_only")
        assert can_user_see_event(db, player, ev) is False


# ===========================================================================
# Tests — can_user_see_event: global
# ===========================================================================


class TestGlobalVisibility:
    """global events: all users (GM and players) can see."""

    def test_gm_sees_global(self, db: Session) -> None:
        gm = _gm(db)
        ev = _event(db, "global")
        assert can_user_see_event(db, gm, ev) is True

    def test_player_sees_global(self, db: Session) -> None:
        pc = _full_pc(db, "PC Global")
        player = _player(db, pc)
        ev = _event(db, "global")
        assert can_user_see_event(db, player, ev) is True

    def test_player_without_character_sees_global(self, db: Session) -> None:
        """A player without a linked character still sees global events."""
        player = User(
            display_name="No Char Global",
            role="player",
            login_code=secrets.token_urlsafe(16),
            is_active=True,
        )
        db.add(player)
        db.flush()
        ev = _event(db, "global")
        assert can_user_see_event(db, player, ev) is True


# ===========================================================================
# Tests — can_user_see_event: private
# ===========================================================================


class TestPrivateVisibility:
    """private events: actor's character + primary target owner (if PC) + GM."""

    def test_gm_sees_private(self, db: Session) -> None:
        gm = _gm(db)
        ev = _event(db, "private")
        assert can_user_see_event(db, gm, ev) is True

    def test_actor_player_sees_own_private_event(self, db: Session) -> None:
        pc = _full_pc(db, "PC Actor Private")
        player = _player(db, pc)
        ev = _event(db, "private", actor_user=player)
        assert can_user_see_event(db, player, ev) is True

    def test_uninvolved_player_cannot_see_private(self, db: Session) -> None:
        pc_actor = _full_pc(db, "PC Actor")
        player_actor = _player(db, pc_actor, "Actor Player")
        pc_other = _full_pc(db, "PC Other")
        player_other = _player(db, pc_other, "Other Player")
        ev = _event(db, "private", actor_user=player_actor)
        assert can_user_see_event(db, player_other, ev) is False

    def test_primary_target_owner_sees_private(self, db: Session) -> None:
        """The player whose character is the primary target sees private events."""
        pc_actor = _full_pc(db, "PC Actor Tgt")
        player_actor = _player(db, pc_actor, "Actor Tgt Player")
        pc_target = _full_pc(db, "PC Primary Target")
        player_target = _player(db, pc_target, "Target Player")
        ev = _event(
            db,
            "private",
            actor_user=player_actor,
            targets=[("character", pc_target.id, True)],
        )
        assert can_user_see_event(db, player_target, ev) is True

    def test_non_primary_target_cannot_see_private(self, db: Session) -> None:
        """A player whose character is a non-primary target does NOT see private."""
        pc_actor = _full_pc(db, "PC Actor NP")
        player_actor = _player(db, pc_actor, "Actor NP Player")
        pc_secondary = _full_pc(db, "PC Secondary")
        player_secondary = _player(db, pc_secondary, "Secondary Player")
        ev = _event(
            db,
            "private",
            actor_user=player_actor,
            targets=[("character", pc_secondary.id, False)],  # is_primary=False
        )
        assert can_user_see_event(db, player_secondary, ev) is False

    def test_private_no_primary_target_only_actor_and_gm_see(
        self, db: Session
    ) -> None:
        """Without a PC primary target, only actor + GM see the event."""
        pc_actor = _full_pc(db, "PC No Target")
        player_actor = _player(db, pc_actor, "No Target Actor")
        pc_other = _full_pc(db, "PC No Target Other")
        player_other = _player(db, pc_other, "No Target Other")
        # No targets at all.
        ev = _event(db, "private", actor_user=player_actor)
        assert can_user_see_event(db, player_actor, ev) is True
        assert can_user_see_event(db, player_other, ev) is False

    def test_private_with_group_primary_target_player_cannot_see(
        self, db: Session
    ) -> None:
        """Private event with a non-character primary target: only actor + GM."""
        pc_actor = _full_pc(db, "PC Group Target")
        player_actor = _player(db, pc_actor, "Group Target Actor")
        pc_other = _full_pc(db, "PC Uninvolved")
        player_other = _player(db, pc_other, "Uninvolved")
        grp = _group(db, "Group Target")
        ev = _event(
            db,
            "private",
            actor_user=player_actor,
            targets=[("group", grp.id, True)],
        )
        # Other player cannot see — group target has no PC owner.
        assert can_user_see_event(db, player_other, ev) is False
        # The actor can still see their own event.
        assert can_user_see_event(db, player_actor, ev) is True

    def test_player_without_character_cannot_see_private(self, db: Session) -> None:
        """A player with no character linked cannot see private events."""
        player = User(
            display_name="No Char",
            role="player",
            login_code=secrets.token_urlsafe(16),
            is_active=True,
        )
        db.add(player)
        db.flush()
        ev = _event(db, "private")
        assert can_user_see_event(db, player, ev) is False


# ===========================================================================
# Tests — can_user_see_event: bonded (1-hop)
# ===========================================================================


class TestBondedVisibility:
    """bonded events: PCs directly bonded (1-hop) to any target + GM."""

    def test_gm_sees_bonded(self, db: Session) -> None:
        gm = _gm(db)
        pc_target = _full_pc(db, "PC Bonded Target")
        ev = _event(db, "bonded", targets=[("character", pc_target.id, True)])
        assert can_user_see_event(db, gm, ev) is True

    def test_directly_bonded_player_sees_bonded_event(self, db: Session) -> None:
        pc_viewer = _full_pc(db, "PC Viewer Bonded")
        player = _player(db, pc_viewer)
        pc_target = _full_pc(db, "PC Bonded Target")
        _bond(db, "character", pc_viewer.id, "character", pc_target.id, bidirectional=True)
        ev = _event(db, "bonded", targets=[("character", pc_target.id, True)])
        assert can_user_see_event(db, player, ev) is True

    def test_unbonded_player_cannot_see_bonded_event(self, db: Session) -> None:
        pc_viewer = _full_pc(db, "PC Viewer Bonded X")
        player = _player(db, pc_viewer)
        pc_target = _full_pc(db, "PC Bonded Target X")
        # No bond between viewer and target.
        ev = _event(db, "bonded", targets=[("character", pc_target.id, True)])
        assert can_user_see_event(db, player, ev) is False

    def test_bonded_via_location_target_sees_event(self, db: Session) -> None:
        """Player bonded to a location that is the event target can see it."""
        pc_viewer = _full_pc(db, "PC Loc Viewer")
        player = _player(db, pc_viewer)
        loc = _location(db, "Bonded Location")
        _bond(db, "character", pc_viewer.id, "location", loc.id, bidirectional=True)
        ev = _event(db, "bonded", targets=[("location", loc.id, True)])
        assert can_user_see_event(db, player, ev) is True

    def test_bonded_player_without_character_cannot_see(self, db: Session) -> None:
        """A player with no character linked cannot match bond-graph checks."""
        player = User(
            display_name="No Char Bonded",
            role="player",
            login_code=secrets.token_urlsafe(16),
            is_active=True,
        )
        db.add(player)
        db.flush()
        pc_target = _full_pc(db, "PC Bonded No Char Target")
        ev = _event(db, "bonded", targets=[("character", pc_target.id, True)])
        assert can_user_see_event(db, player, ev) is False

    def test_bonded_event_with_no_targets_player_cannot_see(
        self, db: Session
    ) -> None:
        """An event with no targets: no bond traversal → player cannot see."""
        pc = _full_pc(db, "PC No Target Bonded")
        player = _player(db, pc)
        ev = _event(db, "bonded")  # no targets
        assert can_user_see_event(db, player, ev) is False

    def test_two_hop_character_cannot_see_bonded_event(self, db: Session) -> None:
        """A PC two hops away from the target cannot see a bonded event."""
        pc_viewer = _full_pc(db, "PC 2-hop Bonded")
        player = _player(db, pc_viewer)
        npc = _npc(db, "NPC 2-hop Bonded")
        pc_target = _full_pc(db, "PC Target 2-hop Bonded")
        _bond(db, "character", pc_viewer.id, "character", npc.id, bidirectional=True)
        _bond(db, "character", npc.id, "character", pc_target.id, bidirectional=True)
        ev = _event(db, "bonded", targets=[("character", pc_target.id, True)])
        # bonded = 1-hop only; pc_viewer is 2 hops away from pc_target via npc.
        assert can_user_see_event(db, player, ev) is False


# ===========================================================================
# Tests — can_user_see_event: familiar (2-hop)
# ===========================================================================


class TestFamiliarVisibility:
    """familiar events: PCs within 2-hop Character-intermediary traversal + GM."""

    def test_gm_sees_familiar(self, db: Session) -> None:
        gm = _gm(db)
        pc_target = _full_pc(db, "PC Familiar Target")
        ev = _event(db, "familiar", targets=[("character", pc_target.id, True)])
        assert can_user_see_event(db, gm, ev) is True

    def test_directly_bonded_sees_familiar(self, db: Session) -> None:
        """1-hop (direct bond) is within the 2-hop familiar range."""
        pc_viewer = _full_pc(db, "PC 1-hop Familiar")
        player = _player(db, pc_viewer)
        pc_target = _full_pc(db, "PC Target 1-hop Familiar")
        _bond(db, "character", pc_viewer.id, "character", pc_target.id, bidirectional=True)
        ev = _event(db, "familiar", targets=[("character", pc_target.id, True)])
        assert can_user_see_event(db, player, ev) is True

    def test_two_hop_character_sees_familiar(self, db: Session) -> None:
        """A PC two hops away via a Character intermediary can see familiar events."""
        pc_viewer = _full_pc(db, "PC 2-hop Familiar Viewer")
        player = _player(db, pc_viewer)
        npc = _npc(db, "NPC 2-hop Familiar Mid")
        pc_target = _full_pc(db, "PC 2-hop Familiar Target")
        _bond(db, "character", pc_viewer.id, "character", npc.id, bidirectional=True)
        _bond(db, "character", npc.id, "character", pc_target.id, bidirectional=True)
        ev = _event(db, "familiar", targets=[("character", pc_target.id, True)])
        assert can_user_see_event(db, player, ev) is True

    def test_three_hop_cannot_see_familiar(self, db: Session) -> None:
        """A PC three hops away cannot see a familiar event."""
        pc_viewer = _full_pc(db, "PC 3-hop Familiar Viewer")
        player = _player(db, pc_viewer)
        npc1 = _npc(db, "NPC 3-hop Mid1")
        npc2 = _npc(db, "NPC 3-hop Mid2")
        pc_target = _full_pc(db, "PC 3-hop Familiar Target")
        _bond(db, "character", pc_viewer.id, "character", npc1.id, bidirectional=True)
        _bond(db, "character", npc1.id, "character", npc2.id, bidirectional=True)
        _bond(db, "character", npc2.id, "character", pc_target.id, bidirectional=True)
        ev = _event(db, "familiar", targets=[("character", pc_target.id, True)])
        assert can_user_see_event(db, player, ev) is False

    def test_familiar_via_group_target(self, db: Session) -> None:
        """PC bonded to a Group that is the event target sees the familiar event."""
        pc_viewer = _full_pc(db, "PC Grp Familiar Viewer")
        player = _player(db, pc_viewer)
        grp = _group(db, "Familiar Group")
        _bond(db, "character", pc_viewer.id, "group", grp.id, bidirectional=True)
        ev = _event(db, "familiar", targets=[("group", grp.id, True)])
        assert can_user_see_event(db, player, ev) is True


# ===========================================================================
# Tests — can_user_see_event: public (3-hop)
# ===========================================================================


class TestPublicVisibility:
    """public events: PCs within 3-hop Character-intermediary traversal + GM."""

    def test_gm_sees_public(self, db: Session) -> None:
        gm = _gm(db)
        pc_target = _full_pc(db, "PC Public Target")
        ev = _event(db, "public", targets=[("character", pc_target.id, True)])
        assert can_user_see_event(db, gm, ev) is True

    def test_one_hop_sees_public(self, db: Session) -> None:
        """A directly bonded PC is within 3 hops."""
        pc_viewer = _full_pc(db, "PC 1-hop Public Viewer")
        player = _player(db, pc_viewer)
        pc_target = _full_pc(db, "PC 1-hop Public Target")
        _bond(db, "character", pc_viewer.id, "character", pc_target.id, bidirectional=True)
        ev = _event(db, "public", targets=[("character", pc_target.id, True)])
        assert can_user_see_event(db, player, ev) is True

    def test_three_hop_sees_public(self, db: Session) -> None:
        """A PC three hops away (via two Character intermediaries) sees public events."""
        pc_viewer = _full_pc(db, "PC 3-hop Public Viewer")
        player = _player(db, pc_viewer)
        npc1 = _npc(db, "NPC 3-hop Public Mid1")
        npc2 = _npc(db, "NPC 3-hop Public Mid2")
        pc_target = _full_pc(db, "PC 3-hop Public Target")
        _bond(db, "character", pc_viewer.id, "character", npc1.id, bidirectional=True)
        _bond(db, "character", npc1.id, "character", npc2.id, bidirectional=True)
        _bond(db, "character", npc2.id, "character", pc_target.id, bidirectional=True)
        ev = _event(db, "public", targets=[("character", pc_target.id, True)])
        assert can_user_see_event(db, player, ev) is True

    def test_four_hop_cannot_see_public(self, db: Session) -> None:
        """A PC four hops away cannot see a public event."""
        pc_viewer = _full_pc(db, "PC 4-hop Public Viewer")
        player = _player(db, pc_viewer)
        npc1 = _npc(db, "NPC 4-hop Mid1")
        npc2 = _npc(db, "NPC 4-hop Mid2")
        npc3 = _npc(db, "NPC 4-hop Mid3")
        pc_target = _full_pc(db, "PC 4-hop Public Target")
        _bond(db, "character", pc_viewer.id, "character", npc1.id, bidirectional=True)
        _bond(db, "character", npc1.id, "character", npc2.id, bidirectional=True)
        _bond(db, "character", npc2.id, "character", npc3.id, bidirectional=True)
        _bond(db, "character", npc3.id, "character", pc_target.id, bidirectional=True)
        ev = _event(db, "public", targets=[("character", pc_target.id, True)])
        assert can_user_see_event(db, player, ev) is False

    def test_public_with_multiple_targets_any_match_sufficient(
        self, db: Session
    ) -> None:
        """A PC bonded to ANY of the event's targets can see a public event."""
        pc_viewer = _full_pc(db, "PC Multi Target Viewer")
        player = _player(db, pc_viewer)
        pc_close = _full_pc(db, "PC Close Multi")
        pc_far = _full_pc(db, "PC Far Multi")
        # Viewer is bonded to pc_close but not pc_far.
        _bond(db, "character", pc_viewer.id, "character", pc_close.id, bidirectional=True)
        # Event targets both characters.
        ev = _event(
            db,
            "public",
            targets=[
                ("character", pc_close.id, True),
                ("character", pc_far.id, False),
            ],
        )
        # Viewer can see because they're bonded to pc_close (1-hop ≤ 3).
        assert can_user_see_event(db, player, ev) is True


# ===========================================================================
# Tests — filter_events_for_user
# ===========================================================================


class TestFilterEventsForUser:
    """Tests for the bulk filter_events_for_user wrapper."""

    def test_empty_list_returns_empty(self, db: Session) -> None:
        gm = _gm(db)
        assert filter_events_for_user(db, gm, []) == []

    def test_gm_sees_all_non_silent(self, db: Session) -> None:
        """GM sees gm_only, private, bonded, familiar, public, global."""
        gm = _gm(db)
        events = [
            _event(db, "gm_only"),
            _event(db, "private"),
            _event(db, "bonded"),
            _event(db, "familiar"),
            _event(db, "public"),
            _event(db, "global"),
        ]
        result = filter_events_for_user(db, gm, events)
        assert len(result) == 6

    def test_gm_sees_silent_via_filter(self, db: Session) -> None:
        """filter_events_for_user includes silent events for GM (silent feed uses this)."""
        gm = _gm(db)
        ev = _event(db, "silent")
        result = filter_events_for_user(db, gm, [ev])
        assert len(result) == 1

    def test_player_sees_global_only_when_unbonded(self, db: Session) -> None:
        """An unbonded player with no relevant connections only sees global events."""
        pc = _full_pc(db, "PC Filter Test")
        player = _player(db, pc)
        events = [
            _event(db, "silent"),
            _event(db, "gm_only"),
            _event(db, "global"),
        ]
        result = filter_events_for_user(db, player, events)
        assert len(result) == 1
        assert result[0].visibility == "global"

    def test_order_preserved(self, db: Session) -> None:
        """Filtered results preserve the input list order."""
        gm = _gm(db)
        ev1 = _event(db, "global")
        ev2 = _event(db, "gm_only")
        ev3 = _event(db, "global")
        result = filter_events_for_user(db, gm, [ev1, ev2, ev3])
        assert [e.id for e in result] == [ev1.id, ev2.id, ev3.id]

    def test_mixed_events_player_sees_subset(self, db: Session) -> None:
        """Player sees global + events they have bond-graph access to."""
        pc_viewer = _full_pc(db, "PC Filter Mixed")
        player = _player(db, pc_viewer)
        pc_target = _full_pc(db, "PC Filter Mixed Target")
        _bond(db, "character", pc_viewer.id, "character", pc_target.id, bidirectional=True)

        ev_global = _event(db, "global")
        ev_bonded_visible = _event(
            db, "bonded", targets=[("character", pc_target.id, True)]
        )
        ev_bonded_invisible = _event(db, "bonded")  # no targets → invisible
        ev_gm_only = _event(db, "gm_only")

        all_events = [ev_global, ev_bonded_visible, ev_bonded_invisible, ev_gm_only]
        result = filter_events_for_user(db, player, all_events)
        result_ids = {e.id for e in result}
        assert ev_global.id in result_ids
        assert ev_bonded_visible.id in result_ids
        assert ev_bonded_invisible.id not in result_ids
        assert ev_gm_only.id not in result_ids


# ===========================================================================
# Tests — seed_data integration (uses conftest fixtures)
# ===========================================================================


class TestSeedDataIntegration:
    """Smoke tests against the standard canonical seed data."""

    def test_gm_sees_global_from_seed(self, db: Session, seed_data: dict) -> None:
        gm = seed_data["gm"]
        ev = _event(db, "global")
        assert can_user_see_event(db, gm, ev) is True

    def test_player1_sees_global_from_seed(self, db: Session, seed_data: dict) -> None:
        player1 = seed_data["player1"]
        ev = _event(db, "global")
        assert can_user_see_event(db, player1, ev) is True

    def test_player1_cannot_see_gm_only_from_seed(
        self, db: Session, seed_data: dict
    ) -> None:
        player1 = seed_data["player1"]
        ev = _event(db, "gm_only")
        assert can_user_see_event(db, player1, ev) is False

    def test_player1_sees_bonded_event_on_group_from_seed(
        self, db: Session, seed_data: dict
    ) -> None:
        """player1 has a bond to The Syndicate group — bonded event on it is visible."""
        player1 = seed_data["player1"]
        grp = seed_data["group"]
        ev = _event(db, "bonded", targets=[("group", grp.id, True)])
        assert can_user_see_event(db, player1, ev) is True

    def test_player3_cannot_see_bonded_event_on_group_from_seed(
        self, db: Session, seed_data: dict
    ) -> None:
        """player3 has no bond to The Syndicate — cannot see bonded event on it."""
        player3 = seed_data["player3"]
        grp = seed_data["group"]
        ev = _event(db, "bonded", targets=[("group", grp.id, True)])
        assert can_user_see_event(db, player3, ev) is False

    def test_player1_sees_own_private_event_from_seed(
        self, db: Session, seed_data: dict
    ) -> None:
        player1 = seed_data["player1"]
        ev = _event(db, "private", actor_user=player1)
        assert can_user_see_event(db, player1, ev) is True

    def test_player2_cannot_see_player1_private_event_from_seed(
        self, db: Session, seed_data: dict
    ) -> None:
        player1 = seed_data["player1"]
        player2 = seed_data["player2"]
        ev = _event(db, "private", actor_user=player1)
        assert can_user_see_event(db, player2, ev) is False


# ===========================================================================
# Tests — inactive bonds excluded
# ===========================================================================


class TestInactiveBondExclusion:
    """Inactive bonds are excluded from BFS traversal."""

    def test_inactive_bond_not_traversed_by_get_reachable_nodes(
        self, db: Session
    ) -> None:
        """An inactive bond between two characters is NOT traversed."""
        pc = _full_pc(db, "PC Inactive Bond Start")
        npc = _npc(db, "NPC Inactive Bond End")
        _bond(db, "character", pc.id, "character", npc.id, bidirectional=True, is_active=False)

        result = get_reachable_nodes(db, "character", pc.id, max_hops=1)
        assert ("character", npc.id) not in result[1]

    def test_inactive_bond_blocks_further_traversal(self, db: Session) -> None:
        """Nodes only reachable via an inactive bond are unreachable."""
        pc = _full_pc(db, "PC Inactive Block Start")
        npc = _npc(db, "NPC Inactive Block Mid")
        loc = _location(db, "Loc Inactive Block End")
        # pc -> npc via active bond, npc -> loc via INACTIVE bond
        _bond(db, "character", pc.id, "character", npc.id, bidirectional=True, is_active=True)
        _bond(db, "character", npc.id, "location", loc.id, bidirectional=False, is_active=False)

        result = get_reachable_nodes(db, "character", pc.id, max_hops=2)
        all_nodes = result[1] | result[2]
        assert ("character", npc.id) in all_nodes  # active bond, still reachable
        assert ("location", loc.id) not in all_nodes  # inactive bond, not reachable

    def test_player_cannot_see_bonded_event_via_inactive_bond(
        self, db: Session
    ) -> None:
        """An inactive bond does not grant bonded-level visibility."""
        pc_viewer = _full_pc(db, "PC Inactive Viewer")
        player = _player(db, pc_viewer)
        pc_target = _full_pc(db, "PC Inactive Target")
        # Bond exists but is inactive.
        _bond(db, "character", pc_viewer.id, "character", pc_target.id, bidirectional=True, is_active=False)
        ev = _event(db, "bonded", targets=[("character", pc_target.id, True)])
        assert can_user_see_event(db, player, ev) is False


# ===========================================================================
# Tests — private: primary target is character with no owning user
# ===========================================================================


class TestPrivateNoOwningUser:
    """private: character primary target with no linked User grants no extra access."""

    def test_unowned_character_primary_target_does_not_widen_private(
        self, db: Session
    ) -> None:
        """If the primary-target character has no owning User, only actor+GM see it."""
        pc_actor = _full_pc(db, "PC Actor Unowned Target")
        player_actor = _player(db, pc_actor, "Actor Unowned")
        # Character exists but no User references it.
        orphan_char = _full_pc(db, "Orphan Character")
        pc_uninvolved = _full_pc(db, "PC Uninvolved Unowned")
        player_uninvolved = _player(db, pc_uninvolved, "Uninvolved Unowned")

        ev = _event(
            db,
            "private",
            actor_user=player_actor,
            targets=[("character", orphan_char.id, True)],
        )
        # Actor can see.
        assert can_user_see_event(db, player_actor, ev) is True
        # Uninvolved player cannot see.
        assert can_user_see_event(db, player_uninvolved, ev) is False


# ===========================================================================
# Tests — bonded: multiple targets, viewer bonded to non-primary target
# ===========================================================================


class TestBondedMultipleTargets:
    """bonded events: viewer bonded to ANY target (primary or not) can see the event."""

    def test_viewer_bonded_to_non_primary_target_sees_bonded_event(
        self, db: Session
    ) -> None:
        """Being bonded to a secondary (non-primary) target is sufficient for bonded."""
        pc_viewer = _full_pc(db, "PC Viewer Multi Bonded")
        player = _player(db, pc_viewer)
        pc_primary = _full_pc(db, "PC Primary Target Multi")
        pc_secondary = _full_pc(db, "PC Secondary Target Multi")

        # Viewer is bonded to secondary, NOT primary.
        _bond(db, "character", pc_viewer.id, "character", pc_secondary.id, bidirectional=True)

        ev = _event(
            db,
            "bonded",
            targets=[
                ("character", pc_primary.id, True),
                ("character", pc_secondary.id, False),
            ],
        )
        assert can_user_see_event(db, player, ev) is True


# ===========================================================================
# Tests — familiar: deleted intermediary blocks traversal
# ===========================================================================


class TestFamiliarDeletedIntermediary:
    """familiar: soft-deleted intermediary nodes block further traversal."""

    def test_deleted_character_intermediary_blocks_familiar_visibility(
        self, db: Session
    ) -> None:
        """If the 1-hop intermediary is deleted, the 2-hop target is unreachable."""
        pc_viewer = _full_pc(db, "PC Viewer Del Int")
        player = _player(db, pc_viewer)
        npc_mid = _npc(db, "NPC Del Int Mid")
        pc_target = _full_pc(db, "PC Target Del Int")

        _bond(db, "character", pc_viewer.id, "character", npc_mid.id, bidirectional=True)
        _bond(db, "character", npc_mid.id, "character", pc_target.id, bidirectional=True)

        # Soft-delete the intermediary.
        npc_mid.is_deleted = True
        db.flush()

        ev = _event(db, "familiar", targets=[("character", pc_target.id, True)])
        # The path via npc_mid is blocked; pc_target is unreachable.
        assert can_user_see_event(db, player, ev) is False
