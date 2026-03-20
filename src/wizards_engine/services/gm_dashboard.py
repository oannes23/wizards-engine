"""Service layer for GM dashboard aggregation queries.

All functions are stateless read-only queries.  They accept an injected
SQLAlchemy session and return lists of ORM instances for the route layer
to serialise.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from wizards_engine.models.character import Character
from wizards_engine.models.clock import Clock
from wizards_engine.models.proposal import Proposal
from wizards_engine.services.shared import count_trauma_bonds

__all__ = [
    "get_pending_proposals",
    "get_pc_summaries",
    "get_near_completion_clocks",
    "get_stress_proximity",
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
        effective_max = 9 - trauma_count
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
