"""Bond-graph BFS traversal for bond-distance presence computation.

Implements the Character-intermediary traversal algorithm described in
spec/domains/bonds.md (Bond-Distance Presence section).

The same traversal drives two computed systems:
- Bond-Distance Presence  (Character ↔ Location proximity tiers)
- Unified Visibility       (who can see which events — Epic 4.1)

Both computed on read; no caching.  SQLite performance is fine for 4–6 players.

Traversal rules (spec/domains/bonds.md — Character-intermediary constraint):
- After a non-Character node (Group or Location), the next hop MUST go to a
  Character node.
- After a Character node, the next hop can go to any type.
- First hop from the starting node can go to any type.
- Only active bonds (``is_active = True``) are traversed.
- Trauma bonds (``is_trauma = True``) are excluded (dead ends, no target).
- Soft-deleted Game Objects (``is_deleted = True``) are dead ends.
"""

from __future__ import annotations

from collections import deque

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from wizards_engine.models.character import Character
from wizards_engine.models.group import Group
from wizards_engine.models.location import Location
from wizards_engine.models.slot import Slot

__all__ = [
    "NodeKey",
    "AdjList",
    "load_active_bonds",
    "build_adjacency",
    "is_deleted",
    "compute_presence",
    "get_locations_for_character",
    "get_presence_for_location",
]


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

# Node identity — (type_string, id_string)
NodeKey = tuple[str, str]

# Each entry in the adjacency list: a list of neighbour NodeKeys.
AdjList = dict[NodeKey, list[NodeKey]]

# Presence tier names in hop order.
_TIER_NAMES = ["common", "familiar", "known"]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def load_active_bonds(db: Session) -> list[Slot]:
    """Load all active, non-trauma bonds where neither endpoint is deleted.

    This is the full bond graph used for traversal.  We load it entirely into
    memory because the dataset is tiny (4–6 players, dozens of bonds total).

    Args:
        db: Active SQLAlchemy session.

    Returns:
        List of active :class:`~wizards_engine.models.slot.Slot` instances
        for all bond-type slots.
    """
    bond_types = [
        "pc_bond",
        "npc_bond",
        "group_relation",
        "group_holding",
        "location_bond",
    ]
    stmt = select(Slot).where(
        and_(
            Slot.slot_type.in_(bond_types),
            Slot.is_active.is_(True),
            # Trauma bonds have no target — skip them.
            or_(Slot.is_trauma.is_(False), Slot.is_trauma.is_(None)),
            # Must have a target to be traversable.
            Slot.target_id.is_not(None),
            Slot.target_type.is_not(None),
        )
    )
    return list(db.execute(stmt).scalars().all())


def is_deleted(db: Session, node_type: str, node_id: str) -> bool:
    """Return True if the Game Object is soft-deleted (or doesn't exist).

    Args:
        db: Active SQLAlchemy session.
        node_type: ``"character"``, ``"group"``, or ``"location"``.
        node_id: ULID of the entity.

    Returns:
        ``True`` when the entity is deleted or not found; ``False`` otherwise.
    """
    model_map: dict[str, type] = {
        "character": Character,
        "group": Group,
        "location": Location,
    }
    model = model_map.get(node_type)
    if model is None:
        return True
    obj = db.get(model, node_id)
    if obj is None:
        return True
    return bool(obj.is_deleted)


def build_adjacency(bonds: list[Slot]) -> AdjList:
    """Build an adjacency list from the loaded bond list.

    Directional bonds create one directed edge (source → target).
    Bidirectional bonds create two edges (source ↔ target).

    Args:
        bonds: All active, non-trauma bonds (pre-loaded from DB).

    Returns:
        Dict mapping each :data:`NodeKey` to a list of neighbour NodeKeys.
    """
    adj: AdjList = {}

    for bond in bonds:
        src: NodeKey = (bond.owner_type, bond.owner_id)
        tgt: NodeKey = (bond.target_type, bond.target_id)

        adj.setdefault(src, [])
        adj.setdefault(tgt, [])

        adj[src].append(tgt)
        if bond.bidirectional:
            adj[tgt].append(src)

    return adj


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_presence(
    db: Session,
    start_type: str,
    start_id: str,
    collect_type: str,
    max_hops: int = 3,
) -> dict[str, list[dict]]:
    """BFS from *start* through the bond graph, collecting nodes of *collect_type*.

    Implements the Character-intermediary traversal constraint:
    - After visiting a non-Character node, the next hop MUST go to a Character.
    - After visiting a Character node, the next hop can go to any type.
    - First hop can go to any type.

    Deleted Game Objects are treated as dead ends and are not traversed.

    Args:
        db: Active SQLAlchemy session.
        start_type: Type of the starting entity (``"character"`` or
            ``"location"``).
        start_id: ULID of the starting entity.
        collect_type: Type of nodes to collect into result tiers (``"location"``
            or ``"character"``).
        max_hops: Maximum number of hops from the start node (default 3).

    Returns:
        A dict with keys ``"common"``, ``"familiar"``, ``"known"`` (one per hop
        tier, 1-indexed).  Each value is a list of ``{id, name, type}`` dicts
        for nodes of *collect_type* found at that hop distance.  Nodes
        reachable at multiple distances are placed in the closest tier only.
    """
    # Load the full bond graph once.
    bonds = load_active_bonds(db)
    adj = build_adjacency(bonds)

    start_node: NodeKey = (start_type, start_id)

    # BFS state:
    # - visited: set of NodeKeys already processed (to avoid cycles / re-entry)
    # - queue: deque of (node_key, hop_distance)
    visited: set[NodeKey] = {start_node}
    queue: deque[tuple[NodeKey, int]] = deque()

    # Enqueue immediate neighbours of the start node (hop 1).
    for neighbour in adj.get(start_node, []):
        if neighbour not in visited:
            n_type, n_id = neighbour
            # Skip deleted nodes immediately.
            if not is_deleted(db, n_type, n_id):
                visited.add(neighbour)
                queue.append((neighbour, 1))

    # Collect results keyed by tier name.
    results: dict[str, list[dict]] = {name: [] for name in _TIER_NAMES}

    # Pre-load entity names for the collect_type to avoid N+1 lookups.
    # We'll fetch names on-demand and cache them.
    name_cache: dict[NodeKey, str] = {}

    def _get_name(node_type: str, node_id: str) -> str:
        key: NodeKey = (node_type, node_id)
        if key not in name_cache:
            model_map: dict[str, type] = {
                "character": Character,
                "group": Group,
                "location": Location,
            }
            model = model_map.get(node_type)
            if model is None:
                return node_id
            obj = db.get(model, node_id)
            name_cache[key] = obj.name if obj is not None else node_id
        return name_cache[key]

    while queue:
        node, hop = queue.popleft()
        n_type, n_id = node

        if hop > max_hops:
            continue

        # Collect this node if it matches the target type.
        if n_type == collect_type:
            tier = _TIER_NAMES[hop - 1]
            results[tier].append(
                {"id": n_id, "name": _get_name(n_type, n_id), "type": n_type}
            )

        # Expand neighbours only if we haven't hit the hop limit yet.
        if hop < max_hops:
            for neighbour in adj.get(node, []):
                if neighbour in visited:
                    continue
                nb_type, nb_id = neighbour

                # Skip deleted nodes.
                if is_deleted(db, nb_type, nb_id):
                    continue

                # Character-intermediary constraint:
                # After a non-Character node, the next hop MUST be a Character.
                if n_type != "character" and nb_type != "character":
                    continue

                visited.add(neighbour)
                queue.append((neighbour, hop + 1))

    return results


def get_locations_for_character(
    db: Session,
    character_id: str,
) -> dict[str, list[dict]]:
    """Return locations reachable from *character_id* grouped by proximity tier.

    Uses :func:`compute_presence` with a 3-hop limit collecting Location nodes.

    Tiers:
    - ``common``   (1-hop): Locations the Character is directly bonded to.
    - ``familiar`` (2-hop): Locations through one Character intermediary.
    - ``known``    (3-hop): Locations through two intermediaries.

    Args:
        db: Active SQLAlchemy session.
        character_id: ULID of the Character.

    Returns:
        ``{"common": [...], "familiar": [...], "known": [...]}`` where each
        entry is a ``{id, name, type}`` dict.
    """
    return compute_presence(
        db,
        start_type="character",
        start_id=character_id,
        collect_type="location",
        max_hops=3,
    )


def get_presence_for_location(
    db: Session,
    location_id: str,
) -> dict[str, list[dict]]:
    """Return Characters reachable from *location_id* grouped by proximity tier.

    Uses :func:`compute_presence` with a 3-hop limit collecting Character nodes.

    Tiers:
    - ``common``   (1-hop): Characters directly bonded to the Location.
    - ``familiar`` (2-hop): Characters through one Character intermediary.
    - ``known``    (3-hop): Characters through two intermediaries.

    Args:
        db: Active SQLAlchemy session.
        location_id: ULID of the Location.

    Returns:
        ``{"common": [...], "familiar": [...], "known": [...]}`` where each
        entry is a ``{id, name, type}`` dict.
    """
    return compute_presence(
        db,
        start_type="location",
        start_id=location_id,
        collect_type="character",
        max_hops=3,
    )
