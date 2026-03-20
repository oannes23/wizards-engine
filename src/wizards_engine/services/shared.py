"""Shared service helpers used across multiple service modules.

Consolidates duplicated logic that appeared in ``proposal.py``,
``gm_actions.py``, ``bond.py``, ``story.py``, ``event.py``, and
``session.py``.
"""

from __future__ import annotations

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

__all__ = [
    "GAME_OBJECT_MODEL_MAP",
    "get_game_object",
    "count_trauma_bonds",
    "has_pending_resolve_trauma",
    "get_active_session",
    "get_active_session_id",
]

from wizards_engine.models.character import Character
from wizards_engine.models.group import Group
from wizards_engine.models.location import Location
from wizards_engine.models.proposal import Proposal
from wizards_engine.models.session import Session as SessionModel
from wizards_engine.models.slot import Slot


# ---------------------------------------------------------------------------
# Game Object model mapping
# ---------------------------------------------------------------------------

#: Canonical mapping from Game Object type string to ORM model class.
GAME_OBJECT_MODEL_MAP: dict[str, type] = {
    "character": Character,
    "group": Group,
    "location": Location,
}


def get_game_object(
    db: Session,
    object_type: str,
    object_id: str,
) -> Character | Group | Location | None:
    """Return the active (non-deleted) Game Object, or ``None``.

    Args:
        db: Active SQLAlchemy session.
        object_type: One of ``"character"``, ``"group"``, ``"location"``.
        object_id: ULID of the Game Object.

    Returns:
        The ORM instance if found and not soft-deleted, else ``None``.
    """
    model = GAME_OBJECT_MODEL_MAP.get(object_type)
    if model is None:
        return None
    obj = db.get(model, object_id)
    if obj is None or obj.is_deleted:
        return None
    return obj


# ---------------------------------------------------------------------------
# Trauma bond helpers (shared by proposal approval + gm_actions)
# ---------------------------------------------------------------------------


def count_trauma_bonds(db: Session, character_id: str) -> int:
    """Return the count of active trauma bonds for a character.

    A trauma bond is a ``pc_bond`` slot owned by the character where
    ``is_trauma = True`` and ``is_active = True``.

    Args:
        db: Active SQLAlchemy session.
        character_id: ULID of the character to inspect.

    Returns:
        Number of active trauma bonds.
    """
    rows = (
        db.execute(
            select(Slot).where(
                and_(
                    Slot.owner_type == "character",
                    Slot.owner_id == character_id,
                    Slot.slot_type == "pc_bond",
                    Slot.is_trauma.is_(True),
                    Slot.is_active.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    return len(rows)


def has_pending_resolve_trauma(db: Session, character_id: str) -> bool:
    """Return ``True`` if a pending ``resolve_trauma`` proposal exists.

    Used to ensure idempotency — only one pending trauma proposal per
    character at a time.

    Args:
        db: Active SQLAlchemy session.
        character_id: ULID of the character to check.

    Returns:
        ``True`` if a pending ``resolve_trauma`` proposal exists for
        this character.
    """
    result = db.scalars(
        select(Proposal).where(
            Proposal.character_id == character_id,
            Proposal.action_type == "resolve_trauma",
            Proposal.status == "pending",
        )
    ).first()
    return result is not None


# ---------------------------------------------------------------------------
# Active session helpers (shared by event, story, session services)
# ---------------------------------------------------------------------------


def get_active_session(db: Session) -> SessionModel | None:
    """Return the currently active session, or ``None`` if none exists.

    Args:
        db: Active SQLAlchemy session.

    Returns:
        The :class:`~wizards_engine.models.session.Session` with
        ``status = "active"``, or ``None``.
    """
    return db.scalars(
        select(SessionModel).where(SessionModel.status == "active")
    ).first()


def get_active_session_id(db: Session) -> str | None:
    """Return the ID of the currently active session, or ``None``.

    Args:
        db: Active SQLAlchemy session.

    Returns:
        The ULID of the active session, or ``None`` if no active session
        exists.
    """
    result = db.execute(
        select(SessionModel.id).where(SessionModel.status == "active")
    ).first()
    return result[0] if result else None
