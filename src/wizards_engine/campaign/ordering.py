"""Import ordering constants and location topological sort.

Defines the 6-phase import order that ensures foreign key dependencies
are satisfied before dependent entities are created.  Also provides a
topological sort for locations that honours their parent-child hierarchy.

Import phase overview
---------------------
Phase 1: ``trait_templates``, ``locations``
    No dependencies on other campaign entities.  Locations use a
    topological sort so parents are always created before children.

Phase 2: ``groups``, ``characters``
    Core fields only — no slots yet.  Groups and characters have no
    cross-dependencies (they can be created in any order within the
    phase).

Phase 3: ``slots`` (traits, bonds, features, relations, holdings),
         ``magic_effects``
    Slots require their owner (character, group, location) to exist.
    Bond slots require their target to exist.  Magic effects require
    their character to exist.

Phase 4: ``clocks``
    Clocks optionally reference a game object as ``associated_with``.
    All game objects must already exist.

Phase 5: ``users``
    Users have an optional FK to characters (``character_id``), so
    characters must exist first.

Phase 6: ``sessions``, ``stories``
    Sessions reference participants (characters must exist).
    Stories reference owners, authors, and session links (everything
    must exist).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Phase constants
# ---------------------------------------------------------------------------

#: Phase 1 entity types — no incoming FK dependencies.
PHASE_1: tuple[str, ...] = ("trait_templates", "locations")

#: Phase 2 entity types — core object creation (no slots yet).
PHASE_2: tuple[str, ...] = ("groups", "characters")

#: Phase 3 entity types — slots and sub-objects that hang off game objects.
PHASE_3: tuple[str, ...] = ("slots", "magic_effects")

#: Phase 4 entity types — clocks optionally reference game objects.
PHASE_4: tuple[str, ...] = ("clocks",)

#: Phase 5 entity types — users require characters for the character FK.
PHASE_5: tuple[str, ...] = ("users",)

#: Phase 6 entity types — sessions and stories reference everything.
PHASE_6: tuple[str, ...] = ("sessions", "stories")

#: Ordered tuple of all phases for iterating the full import sequence.
IMPORT_PHASES: tuple[tuple[str, ...], ...] = (
    PHASE_1,
    PHASE_2,
    PHASE_3,
    PHASE_4,
    PHASE_5,
    PHASE_6,
)


# ---------------------------------------------------------------------------
# Location topological sort
# ---------------------------------------------------------------------------


def topological_sort_locations(
    locations: list[dict],
) -> list[dict]:
    """Sort a flat list of location dicts so parents always precede children.

    Each dict must contain at least a ``"name"`` key and an optional
    ``"parent"`` key whose value is the ``name`` of the parent location
    (or ``None`` / absent for root locations).

    The algorithm is a standard iterative Kahn's algorithm (BFS over
    zero-in-degree nodes).

    Parameters
    ----------
    locations:
        List of location dicts.  Each dict must have a ``"name"``
        field.  The ``"parent"`` field is optional; omitted or ``None``
        means a root location.

    Returns
    -------
    list[dict]
        The same dicts reordered so that every location appears after
        its parent.

    Raises
    ------
    ValueError
        If a cycle is detected (circular parent chain) or if a
        ``"parent"`` value references a name not present in the list.
    """
    if not locations:
        return []

    # Build name → dict mapping.
    by_name: dict[str, dict] = {}
    for loc in locations:
        name = loc["name"]
        if name in by_name:
            raise ValueError(
                f"Duplicate location name in topological sort: {name!r}"
            )
        by_name[name] = loc

    # Validate parent references before sorting.
    for loc in locations:
        parent = loc.get("parent")
        if parent is not None and parent not in by_name:
            raise ValueError(
                f"Location {loc['name']!r} references unknown parent {parent!r}"
            )

    # Build adjacency and in-degree counts.
    # Edge: parent → child (parent must come first).
    children_of: dict[str, list[str]] = {name: [] for name in by_name}
    in_degree: dict[str, int] = {name: 0 for name in by_name}

    for loc in locations:
        parent = loc.get("parent")
        if parent is not None:
            children_of[parent].append(loc["name"])
            in_degree[loc["name"]] += 1

    # Kahn's algorithm — process nodes with in_degree == 0 first.
    queue: list[str] = [name for name, deg in in_degree.items() if deg == 0]
    # Sort roots alphabetically for deterministic output.
    queue.sort()
    result: list[dict] = []

    while queue:
        current = queue.pop(0)
        result.append(by_name[current])
        # Reduce in-degree for all children; add newly free nodes.
        newly_free: list[str] = []
        for child in children_of[current]:
            in_degree[child] -= 1
            if in_degree[child] == 0:
                newly_free.append(child)
        newly_free.sort()  # keep deterministic ordering within each level
        queue.extend(newly_free)

    if len(result) != len(locations):
        # Some nodes were never reached — cycle detected.
        sorted_names = {loc["name"] for loc in result}
        cycle_nodes = [loc["name"] for loc in locations if loc["name"] not in sorted_names]
        raise ValueError(
            f"Cycle detected in location parent hierarchy involving: "
            f"{sorted(cycle_nodes)}"
        )

    return result
