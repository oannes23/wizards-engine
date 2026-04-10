"""Bond-distance visibility filtering for Events (and future feed items).

Implements the unified 7-level visibility model defined in
spec/domains/feed.md and spec/domains/events.md.

The 7 levels, in order of increasing scope:

- ``silent``  — GM only (excluded from normal queries; silent-feed only)
- ``gm_only`` — GM only (appears in the GM's normal feed)
- ``private`` — actor's character + primary target's owner (if PC) + GM
- ``bonded``  — PCs with a direct bond (1-hop) to any event target + GM
- ``familiar``— PCs within 2-hop Character-intermediary traversal + GM
- ``public``  — PCs within 3-hop Character-intermediary traversal + GM
- ``global``  — all players + GM

All visibility is **computed on read**.  No caching — SQLite performance
is fine for 4–6 players.

The bond-graph BFS traversal is shared with the presence service.  Rather
than duplicating the algorithm, this module imports the low-level helpers
``load_active_bonds`` and ``build_adjacency`` from
``wizards_engine.services.presence``.
"""

from __future__ import annotations

from collections import deque

from sqlalchemy import select
from sqlalchemy.orm import Session

from wizards_engine.models.event import Event, EventTarget
from wizards_engine.models.story import Story
from wizards_engine.models.user import User
from wizards_engine.roles import Role, has_full_visibility
from wizards_engine.services.presence import (
    AdjList,
    NodeKey,
    build_adjacency,
    is_deleted,
    load_active_bonds,
)

__all__ = [
    "get_reachable_nodes",
    "get_visible_character_ids",
    "get_bond_distance_for_user",
    "can_user_see_event",
    "filter_events_for_user",
    "can_user_see_story",
    "filter_stories_for_user",
]


# ---------------------------------------------------------------------------
# Core BFS helper — reachable nodes grouped by hop distance
# ---------------------------------------------------------------------------


def get_reachable_nodes(
    db: Session,
    start_type: str,
    start_id: str,
    max_hops: int,
) -> dict[int, set[NodeKey]]:
    """BFS from *start* through the bond graph up to *max_hops*.

    Applies the same Character-intermediary constraint as the presence
    service:

    - After a non-Character node (Group or Location), the next hop **must**
      go to a Character node.
    - After a Character node, the next hop can go to any type.
    - The first hop from the starting node can go to any type.
    - Inactive and trauma bonds are excluded (via ``load_active_bonds``).
    - Soft-deleted Game Objects are treated as dead ends.

    The starting node itself is **not** included in the result.

    Args:
        db: Active SQLAlchemy session.
        start_type: Type of the origin node (``"character"``,
            ``"group"``, or ``"location"``).
        start_id: ULID of the origin node.
        max_hops: Maximum hop distance to traverse (inclusive).

    Returns:
        A dict mapping hop distance (1-indexed integer) to the set of
        :data:`~wizards_engine.services.presence.NodeKey` values reached
        at exactly that distance.  Keys present for each hop from 1 through
        *max_hops* (even if the set is empty).
    """
    bonds = load_active_bonds(db)
    adj: AdjList = build_adjacency(bonds)

    start_node: NodeKey = (start_type, start_id)

    visited: set[NodeKey] = {start_node}
    queue: deque[tuple[NodeKey, int]] = deque()

    # Seed the queue with direct neighbours of the start node (hop 1).
    for neighbour in adj.get(start_node, []):
        if neighbour not in visited:
            nb_type, nb_id = neighbour
            if not is_deleted(db, nb_type, nb_id):
                visited.add(neighbour)
                queue.append((neighbour, 1))

    result: dict[int, set[NodeKey]] = {hop: set() for hop in range(1, max_hops + 1)}

    while queue:
        node, hop = queue.popleft()

        if hop > max_hops:
            continue

        result[hop].add(node)

        if hop < max_hops:
            n_type, _n_id = node
            for neighbour in adj.get(node, []):
                if neighbour in visited:
                    continue
                nb_type, nb_id = neighbour

                if is_deleted(db, nb_type, nb_id):
                    continue

                # Character-intermediary constraint: after a non-Character
                # node the next hop must land on a Character.
                if n_type != "character" and nb_type != "character":
                    continue

                visited.add(neighbour)
                queue.append((neighbour, hop + 1))

    return result


# ---------------------------------------------------------------------------
# PC-reachability helper
# ---------------------------------------------------------------------------


def get_visible_character_ids(
    db: Session,
    target_type: str,
    target_id: str,
    max_hops: int,
) -> set[str]:
    """Return all Character IDs reachable from *target* within *max_hops*.

    This is the core building block for the ``bonded`` (1-hop),
    ``familiar`` (2-hop), and ``public`` (3-hop) visibility levels.

    Starting from the given target Game Object, traverse the bond graph
    outward up to *max_hops*.  Collect the IDs of all **Character** nodes
    reached (at any hop up to and including the limit).

    Note that "character" here means any Character (PC or NPC).  The
    caller is responsible for narrowing down to PC-owning users if needed.

    Args:
        db: Active SQLAlchemy session.
        target_type: Type of the starting node.
        target_id: ULID of the starting node.
        max_hops: Maximum number of hops to traverse.

    Returns:
        Set of Character ULIDs reachable within *max_hops*.
    """
    reachable = get_reachable_nodes(db, target_type, target_id, max_hops)
    character_ids: set[str] = set()
    for _hop, nodes in reachable.items():
        for node_type, node_id in nodes:
            if node_type == "character":
                character_ids.add(node_id)
    return character_ids


# ---------------------------------------------------------------------------
# Bond-distance helper for detail responses
# ---------------------------------------------------------------------------


def get_bond_distance_for_user(
    db: Session, user: User, entity_type: str, entity_id: str
) -> int | None:
    """Return the bond-graph hop distance from *user*'s character to an entity.

    Computes how far (in bond-graph hops) the requesting player's character is
    from the viewed entity.  Used to populate the ``bond_distance`` field in
    detail responses.

    | Value | Meaning                                                        |
    |-------|----------------------------------------------------------------|
    | None  | Caller is GM, Viewer, or has no character — full detail always |
    | 0     | Entity is the caller's own character                           |
    | 1     | 1-hop (bonded)                                                 |
    | 2     | 2-hop (familiar)                                               |
    | 3     | 3-hop (public)                                                 |
    | 4     | Beyond 3 hops (unreachable in bond graph)                      |

    Args:
        db: Active SQLAlchemy session.
        user: The requesting user.
        entity_type: Type of the target entity — ``"character"``, ``"group"``,
            or ``"location"``.
        entity_id: ULID of the target entity.

    Returns:
        An integer hop distance (0–4) or ``None`` for privileged users and
        users without a linked character.
    """
    # GMs and Viewers always receive full detail — distance is not applicable.
    if has_full_visibility(user):
        return None

    # Players without a linked character also receive full detail.
    if user.character_id is None:
        return None

    # The entity *is* the caller's own character.
    if entity_type == "character" and entity_id == user.character_id:
        return 0

    # BFS outward from the caller's character up to 3 hops.
    reachable = get_reachable_nodes(db, "character", user.character_id, max_hops=3)

    for hop in (1, 2, 3):
        if (entity_type, entity_id) in reachable[hop]:
            return hop

    # Entity is not reachable within 3 hops.
    return 4


# ---------------------------------------------------------------------------
# Private-visibility helpers
# ---------------------------------------------------------------------------


def _actor_character_id(db: Session, event: Event) -> str | None:
    """Return the character_id of the user who acted, or ``None``.

    Returns ``None`` when:
    - The event has no ``actor_id`` (system events).
    - The actor User has no linked character (GM without a character).

    Args:
        db: Active SQLAlchemy session.
        event: The event whose actor we want to resolve.

    Returns:
        A Character ULID, or ``None``.
    """
    if event.actor_id is None:
        return None
    actor_user = db.get(User, event.actor_id)
    if actor_user is None:
        return None
    return actor_user.character_id


def _primary_target_owner_character_id(db: Session, event: Event) -> str | None:
    """Return the character_id of the primary target's owning user, or ``None``.

    Walks the ``event.targets`` relationship to find the ``is_primary``
    target.  If that target is a Character with a linked User, returns that
    User's ``character_id``.

    Returns ``None`` when:
    - The event has no primary target.
    - The primary target is not a Character.
    - No User has that character_id linked.

    Args:
        db: Active SQLAlchemy session.
        event: The event whose primary target owner we want to resolve.

    Returns:
        A Character ULID, or ``None``.
    """
    primary: EventTarget | None = None
    for target in event.targets:
        if target.is_primary:
            primary = target
            break

    if primary is None:
        return None

    if primary.target_type != "character":
        return None

    # Find the User who owns this Character.
    stmt = select(User).where(User.character_id == primary.target_id)
    owner = db.execute(stmt).scalar_one_or_none()
    if owner is None:
        return None

    return owner.character_id


# ---------------------------------------------------------------------------
# Primary visibility predicate
# ---------------------------------------------------------------------------


def can_user_see_event(db: Session, user: User, event: Event) -> bool:
    """Check whether *user* can see *event* under the unified visibility model.

    Implements the 7-level visibility rules from spec/domains/feed.md:

    - ``silent``  — GM only.  Always excluded from normal queries; this
      function returns ``True`` for the GM so that the silent-feed endpoint
      can use it directly, but callers that build a normal feed must
      pre-filter ``silent`` events out themselves.
    - ``gm_only`` — GM only.
    - ``private`` — actor's character + primary target's owner (if PC) + GM.
    - ``bonded``  — PCs with a direct bond (1-hop) to any event target + GM.
    - ``familiar``— PCs within 2-hop traversal of any event target + GM.
    - ``public``  — PCs within 3-hop traversal of any event target + GM.
    - ``global``  — all players + GM.

    Args:
        db: Active SQLAlchemy session.
        user: The requesting user (Player or GM).
        event: The event being accessed.

    Returns:
        ``True`` if the user may see the event; ``False`` otherwise.
    """
    visibility = event.visibility

    # GM and Viewer have full visibility, with one exception: Viewers are
    # excluded from ``silent`` events (system plumbing the GM sees only).
    if has_full_visibility(user):
        if user.role == Role.VIEWER and visibility == "silent":
            return False
        return True

    # Players never see gm_only events.
    if visibility == "gm_only":
        return False

    # silent: GM only — players excluded.
    if visibility == "silent":
        return False

    # global: every authenticated user sees it.
    if visibility == "global":
        return True

    # private: actor's character OR primary target owner, plus GM (above).
    if visibility == "private":
        char_id = user.character_id
        if char_id is None:
            return False
        actor_char = _actor_character_id(db, event)
        if actor_char == char_id:
            return True
        primary_owner_char = _primary_target_owner_character_id(db, event)
        if primary_owner_char == char_id:
            return True
        return False

    # bonded / familiar / public: bond-graph traversal from event targets.
    if visibility in ("bonded", "familiar", "public"):
        hop_limit = {"bonded": 1, "familiar": 2, "public": 3}[visibility]
        char_id = user.character_id
        if char_id is None:
            return False
        for target in event.targets:
            reachable = get_visible_character_ids(
                db, target.target_type, target.target_id, hop_limit
            )
            if char_id in reachable:
                return True
        return False

    # Unknown visibility level — deny by default.
    return False


# ---------------------------------------------------------------------------
# Bulk filter
# ---------------------------------------------------------------------------


def filter_events_for_user(
    db: Session, user: User, events: list[Event]
) -> list[Event]:
    """Filter *events* to only those visible to *user*.

    Convenience wrapper around :func:`can_user_see_event` that processes
    a list in one pass.

    Note: ``silent`` events are included here if the GM is the requesting
    user, consistent with :func:`can_user_see_event`.  Callers building
    a **normal** (non-silent) feed must exclude ``silent`` events from the
    input list before calling this function.

    Args:
        db: Active SQLAlchemy session.
        user: The requesting user.
        events: The candidate event list to filter.

    Returns:
        A new list containing only the events the user may see, preserving
        input order.
    """
    return [e for e in events if can_user_see_event(db, user, e)]


# ---------------------------------------------------------------------------
# Story visibility predicate
# ---------------------------------------------------------------------------

#: Hop-count mapping for the bond-graph visibility levels.
_STORY_HOP_LIMIT: dict[str, int] = {
    "bonded": 1,
    "familiar": 2,
    "public": 3,
}


def can_user_see_story(db: Session, user: User, story: Story) -> bool:
    """Check whether *user* can see *story* under the unified visibility model.

    Implements the Story visibility rules from spec/domains/feed.md:

    1. GM always sees every Story.
    2. If *user*'s ID is in ``story.visibility_overrides`` → visible.
    3. If *user*'s ``character_id`` matches any PC owner → visible (owner rule).
    4. Derive the effective visibility level (``story.visibility_level`` or
       ``"familiar"`` by default) and apply bond-graph traversal from each owner.
    5. ``gm_only`` / ``silent`` → GM only (players denied).
    6. ``private`` → owner-scoped (only PC owners and GM; non-PC owners give GM-only).
    7. ``global`` → all players.
    8. ``bonded`` / ``familiar`` / ``public`` → bond-graph traversal.

    Note: Step 3 (PC-owner check) runs *before* the level check so that a PC
    owner always has access even if the level would otherwise exclude them.

    Args:
        db: Active SQLAlchemy session.
        user: The requesting user (Player or GM).
        story: The Story being accessed.

    Returns:
        ``True`` if the user may see the story; ``False`` otherwise.
    """
    # 1. GM and Viewer see all Stories.
    if has_full_visibility(user):
        return True

    # 2. Check visibility_overrides (list of user IDs).
    overrides: list[str] = story.visibility_overrides or []
    if user.id in overrides:
        return True

    # Get the effective visibility level (nullable → default familiar).
    level: str = story.visibility_level or "familiar"

    # 3. gm_only / silent → players never see.
    if level in ("gm_only", "silent"):
        return False

    # 4. global → all authenticated players.
    if level == "global":
        return True

    # 5. PC-owner check — a user whose character is a Story owner always sees it.
    char_id = user.character_id
    if char_id is not None:
        for owner in story.owners:
            if owner.owner_type == "character" and owner.owner_id == char_id:
                return True

    # 6. private → only PC owners (handled above) + GM (handled above).
    if level == "private":
        return False

    # 7. bonded / familiar / public → bond-graph traversal from each owner.
    if level in _STORY_HOP_LIMIT:
        hop_limit = _STORY_HOP_LIMIT[level]
        if char_id is None:
            return False
        for owner in story.owners:
            reachable = get_visible_character_ids(
                db, owner.owner_type, owner.owner_id, hop_limit
            )
            if char_id in reachable:
                return True
        return False

    # Unknown level — deny by default.
    return False


# ---------------------------------------------------------------------------
# Story bulk filter
# ---------------------------------------------------------------------------


def filter_stories_for_user(
    db: Session, user: User, stories: list[Story]
) -> list[Story]:
    """Filter *stories* to only those visible to *user*.

    Convenience wrapper around :func:`can_user_see_story` that processes
    a list in one pass.

    Args:
        db: Active SQLAlchemy session.
        user: The requesting user.
        stories: Candidate story list to filter.

    Returns:
        A new list containing only the stories the user may see, preserving
        input order.
    """
    return [s for s in stories if can_user_see_story(db, user, s)]
