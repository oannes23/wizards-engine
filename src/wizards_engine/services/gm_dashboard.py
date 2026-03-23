"""Service layer for GM dashboard aggregation queries.

All functions are stateless read-only queries.  They accept an injected
SQLAlchemy session and return lists of ORM instances for the route layer
to serialise.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from wizards_engine.models.character import Character
from wizards_engine.models.clock import Clock
from wizards_engine.models.event import Event, EventTarget
from wizards_engine.models.group import Group
from wizards_engine.models.proposal import Proposal
from wizards_engine.models.slot import Slot
from wizards_engine.services.proposal.constants import (
    FREE_TIME_MAX,
    GNOSIS_MAX,
    PLOT_MAX,
    STRESS_MAX,
)
from wizards_engine.services.shared import count_trauma_bonds

__all__ = [
    "get_pending_proposals",
    "get_pc_summaries",
    "get_near_completion_clocks",
    "get_stress_proximity",
    "get_low_charge_slots",
    "get_recent_events_for_target",
    "get_active_clocks_for_group",
    "get_queue_summary",
]


def get_pending_proposals(db: Session) -> list[Proposal]:
    """Return all pending proposals ordered system-origin first, then oldest first.

    Ordering rationale: ``"system" > "player"`` lexicographically, so
    ``ORDER BY origin DESC`` puts system proposals at the top.  Within each
    origin group, ULID order (ascending) gives oldest-first within the group.

    Args:
        db: An open SQLAlchemy session.

    Returns:
        A list of :class:`~wizards_engine.models.proposal.Proposal` instances
        with ``status == "pending"``.
    """
    stmt = (
        select(Proposal)
        .where(Proposal.status == "pending")
        .order_by(
            Proposal.origin.desc(),  # 'system' > 'player' → system first
            Proposal.id.asc(),       # ULID lexicographic = chronological
        )
    )
    return list(db.scalars(stmt).all())


def get_pc_summaries(db: Session) -> list[Character]:
    """Return all active full (PC-level) characters ordered alphabetically by name.

    Excludes soft-deleted characters and simplified (NPC) characters.

    Args:
        db: An open SQLAlchemy session.

    Returns:
        A list of :class:`~wizards_engine.models.character.Character` instances
        with ``detail_level == "full"`` and ``is_deleted == False``.
    """
    stmt = (
        select(Character)
        .where(
            Character.detail_level == "full",
            Character.is_deleted == False,  # noqa: E712
        )
        .order_by(Character.name.asc())
    )
    return list(db.scalars(stmt).all())


def get_near_completion_clocks(db: Session) -> list[Clock]:
    """Return clocks that are exactly one segment away from completion.

    A clock is "near completion" when ``progress == segments - 1``.  Completed
    clocks (``progress >= segments``) and deleted clocks are excluded.

    Args:
        db: An open SQLAlchemy session.

    Returns:
        A list of :class:`~wizards_engine.models.clock.Clock` instances ordered
        by ULID (oldest first).
    """
    stmt = (
        select(Clock)
        .where(
            Clock.is_deleted == False,  # noqa: E712
            Clock.progress >= Clock.segments - 1,
            Clock.progress < Clock.segments,
        )
        .order_by(Clock.id.asc())
    )
    return list(db.scalars(stmt).all())


def get_stress_proximity(db: Session) -> list[dict]:
    """Return PCs within 2 stress of their effective stress maximum.

    The effective stress maximum for a character is ``9 - trauma_bond_count``,
    where trauma bonds reduce the maximum stress a character can accumulate
    before the ``resolve_trauma`` proposal is generated.

    Args:
        db: An open SQLAlchemy session.

    Returns:
        A list of dicts (one per at-risk character) with the following keys:

        - ``character_id`` — ULID of the character.
        - ``character_name`` — display name.
        - ``current_stress`` — the character's current stress value.
        - ``effective_max`` — computed effective stress maximum (9 minus
          trauma bond count).
        - ``margin`` — how many stress points remain before the character
          hits their maximum (``effective_max - current_stress``).
    """
    characters = db.scalars(
        select(Character).where(
            Character.detail_level == "full",
            Character.is_deleted.is_(False),
        )
    ).all()

    results = []
    for char in characters:
        trauma_count = count_trauma_bonds(db, char.id)
        effective_max = STRESS_MAX - trauma_count
        current_stress = char.stress or 0
        if effective_max - current_stress <= 2:
            results.append({
                "character_id": char.id,
                "character_name": char.name,
                "current_stress": current_stress,
                "effective_max": effective_max,
                "margin": effective_max - current_stress,
            })
    return results


# ---------------------------------------------------------------------------
# Queue Summary helpers (GET /api/v1/gm/queue-summary)
# ---------------------------------------------------------------------------


def get_low_charge_slots(db: Session, character_id: str) -> list[Slot]:
    """Return active trait and non-trauma bond slots with a low charge value.

    Returns all active ``core_trait`` and ``role_trait`` slots whose
    ``charge`` is <= 2, and all active non-trauma ``pc_bond`` slots whose
    ``charges`` is <= 2.

    Uses the ``ix_slots_owner`` index (``owner_type``, ``owner_id``,
    ``slot_type``) for efficient lookups.

    Args:
        db: An open SQLAlchemy session.
        character_id: ULID of the character to inspect.

    Returns:
        A list of :class:`~wizards_engine.models.slot.Slot` instances.
        Traits (``core_trait``/``role_trait``) are included when
        ``charge <= 2``.  Bonds (``pc_bond``) are included when
        ``is_trauma`` is not True and ``charges <= 2``.
    """
    stmt = (
        select(Slot)
        .where(
            Slot.owner_type == "character",
            Slot.owner_id == character_id,
            Slot.is_active.is_(True),
            Slot.slot_type.in_(["core_trait", "role_trait", "pc_bond"]),
        )
        .order_by(Slot.slot_type.asc(), Slot.id.asc())
    )
    all_slots = list(db.scalars(stmt).all())

    low_charge: list[Slot] = []
    for slot in all_slots:
        if slot.slot_type in ("core_trait", "role_trait"):
            if (slot.charge or 0) <= 2:
                low_charge.append(slot)
        elif slot.slot_type == "pc_bond":
            if not slot.is_trauma and (slot.charges or 0) <= 2:
                low_charge.append(slot)
    return low_charge


def get_recent_events_for_target(
    db: Session,
    target_type: str,
    target_id: str,
    limit: int = 3,
) -> list[Event]:
    """Return the most recent events targeting a given Game Object.

    Joins ``event_targets`` to ``events`` using the ``ix_event_targets_target``
    index (``target_type``, ``target_id``) for efficient reverse lookup.

    Args:
        db: An open SQLAlchemy session.
        target_type: Polymorphic type tag, e.g. ``"character"`` or ``"group"``.
        target_id: ULID of the Game Object.
        limit: Maximum number of events to return (default 3).

    Returns:
        A list of :class:`~wizards_engine.models.event.Event` instances
        ordered by ``created_at`` descending (newest first), up to *limit*
        items.
    """
    stmt = (
        select(Event)
        .join(EventTarget, EventTarget.event_id == Event.id)
        .where(
            EventTarget.target_type == target_type,
            EventTarget.target_id == target_id,
        )
        .order_by(Event.created_at.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def get_active_clocks_for_group(db: Session, group_id: str) -> list[Clock]:
    """Return all active (non-completed, non-deleted) clocks for a group.

    A clock is considered active when ``progress < segments`` and
    ``is_deleted = False``.

    Args:
        db: An open SQLAlchemy session.
        group_id: ULID of the group.

    Returns:
        A list of :class:`~wizards_engine.models.clock.Clock` instances
        ordered by ULID (oldest first).
    """
    stmt = (
        select(Clock)
        .where(
            Clock.associated_type == "group",
            Clock.associated_id == group_id,
            Clock.is_deleted.is_(False),
            Clock.progress < Clock.segments,
        )
        .order_by(Clock.id.asc())
    )
    return list(db.scalars(stmt).all())


def get_queue_summary(db: Session) -> dict:
    """Assemble the full queue summary for all PCs and groups.

    For each active full character, computes:
    - Current meters with their maximums.
    - Low-charge traits (core/role traits with charge <= 2).
    - Low-charge bonds (non-trauma pc_bonds with charges <= 2).
    - Last 3 events targeting the character.

    For each active group, computes:
    - Active (non-completed, non-deleted) clocks associated with the group.
    - Last 3 events targeting the group.

    Groups are sorted by their most-recent-event timestamp descending.
    Groups with no events appear at the end.

    Args:
        db: An open SQLAlchemy session.

    Returns:
        A dict with keys ``"pc_cards"`` and ``"group_cards"``.  Each value
        is a list of dicts ready for schema serialisation.
    """
    # ------------------------------------------------------------------
    # PC cards
    # ------------------------------------------------------------------
    characters = list(
        db.scalars(
            select(Character)
            .where(
                Character.detail_level == "full",
                Character.is_deleted.is_(False),
            )
            .order_by(Character.name.asc())
        ).all()
    )

    pc_cards = []
    for char in characters:
        trauma_count = count_trauma_bonds(db, char.id)
        stress_max = STRESS_MAX - trauma_count

        low_slots = get_low_charge_slots(db, char.id)
        low_traits = [
            {
                "id": s.id,
                "name": s.name,
                "slot_type": s.slot_type,
                "charge": s.charge or 0,
            }
            for s in low_slots
            if s.slot_type in ("core_trait", "role_trait")
        ]
        low_bonds = [
            {
                "id": s.id,
                "name": s.name,
                "slot_type": s.slot_type,
                "charge": s.charges or 0,
            }
            for s in low_slots
            if s.slot_type == "pc_bond"
        ]

        recent = get_recent_events_for_target(db, "character", char.id)
        recent_events = [
            {"id": e.id, "type": e.type, "created_at": e.created_at}
            for e in recent
        ]

        pc_cards.append(
            {
                "id": char.id,
                "name": char.name,
                "stress": char.stress or 0,
                "stress_max": stress_max,
                "free_time": char.free_time or 0,
                "free_time_max": 20,
                "plot": char.plot or 0,
                "plot_max": 5,
                "gnosis": char.gnosis or 0,
                "gnosis_max": 23,
                "low_charge_traits": low_traits,
                "low_charge_bonds": low_bonds,
                "recent_events": recent_events,
            }
        )

    # ------------------------------------------------------------------
    # Group cards
    # ------------------------------------------------------------------
    groups = list(
        db.scalars(
            select(Group)
            .where(Group.is_deleted.is_(False))
            .order_by(Group.name.asc())
        ).all()
    )

    group_cards_unsorted = []
    for group in groups:
        clocks = get_active_clocks_for_group(db, group.id)
        active_clocks = [
            {
                "id": c.id,
                "name": c.name,
                "progress": c.progress,
                "segments": c.segments,
            }
            for c in clocks
        ]

        recent = get_recent_events_for_target(db, "group", group.id)
        recent_events = [
            {"id": e.id, "type": e.type, "created_at": e.created_at}
            for e in recent
        ]

        most_recent_at: datetime | None = (
            recent[0].created_at if recent else None
        )

        group_cards_unsorted.append(
            {
                "id": group.id,
                "name": group.name,
                "tier": group.tier,
                "active_clocks": active_clocks,
                "recent_events": recent_events,
                "most_recent_event_at": most_recent_at,
            }
        )

    # Sort: groups with events descending by timestamp, then groups without events.
    group_cards = sorted(
        group_cards_unsorted,
        key=lambda g: (
            g["most_recent_event_at"] is None,  # False (has events) sorts first
            -(g["most_recent_event_at"].timestamp() if g["most_recent_event_at"] else 0),
        ),
    )

    return {"pc_cards": pc_cards, "group_cards": group_cards}
