"""Service layer for Character CRUD operations.

All database interactions for the Character resource live here.  Route
handlers call these functions and handle HTTP-level concerns (status codes,
response shaping) separately.

Functions are stateless — each accepts a SQLAlchemy ``Session`` as its
first argument.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from wizards_engine.models.character import Character
from wizards_engine.models.user import User

__all__ = [
    "create_character",
    "get_character",
    "list_characters_query",
    "update_character",
    "delete_character",
    "reset_stress",
]


def create_character(
    db: Session,
    *,
    name: str,
    description: str | None = None,
    notes: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> Character:
    """Create a new simplified (NPC-level) Character and persist it.

    GM-created characters always have ``detail_level = 'simplified'``.
    Full-level characters are only created via the player invite flow.

    Args:
        db: Active SQLAlchemy session.
        name: Character name.  Must be non-empty (caller validates).
        description: Optional freeform description.
        notes: Optional GM notes.
        attributes: Optional freeform JSON blob for NPC mechanical data.

    Returns:
        The newly created and flushed :class:`~wizards_engine.models.character.Character`
        instance with its auto-generated ``id`` populated.
    """
    character = Character(
        name=name,
        description=description,
        notes=notes,
        attributes=attributes,
        detail_level="simplified",
        is_deleted=False,
    )
    db.add(character)
    db.flush()
    db.refresh(character)
    return character


def get_character(db: Session, character_id: str) -> Character | None:
    """Retrieve a single Character by its ULID, including soft-deleted ones.

    Direct lookup by ID always returns the character regardless of the
    ``is_deleted`` flag.  The route layer surfaces ``is_deleted`` in the
    response so callers can see the deletion state.

    Args:
        db: Active SQLAlchemy session.
        character_id: ULID primary key.

    Returns:
        The :class:`~wizards_engine.models.character.Character` if found,
        or ``None`` if no row exists with that ID.
    """
    return db.get(Character, character_id)


_ALLOWED_SORT_COLS_CHARACTER = {
    "name": Character.name,
    "created_at": Character.created_at,
    "updated_at": Character.updated_at,
}


def list_characters_query(
    db: Session,
    *,
    detail_level: str | None = None,
    has_player: bool | None = None,
    include_deleted: bool = False,
    name: str | None = None,
    sort_by: str = "name",
    sort_dir: str = "asc",
):
    """Build a SQLAlchemy select statement for the Characters list with optional filters.

    The returned statement has *no* ``ORDER BY`` or ``LIMIT`` applied — the
    caller (``api.pagination.paginate``) adds those.

    Args:
        db: Active SQLAlchemy session.
        detail_level: Filter to ``"full"`` or ``"simplified"`` characters.
        has_player: When ``True``, return only characters linked to a User.
            When ``False``, return only characters without a linked User.
            ``None`` skips the filter.
        include_deleted: When ``True``, include soft-deleted characters.
            Defaults to ``False`` (exclude deleted).
        name: Case-insensitive partial match on the character name.
        sort_by: Column to sort by — ``"name"``, ``"created_at"``, or
            ``"updated_at"``.  Defaults to ``"name"``.
        sort_dir: Sort direction — ``"asc"`` or ``"desc"``.  Defaults to ``"asc"``.

    Returns:
        A 3-tuple of ``(Select statement, sort_col, sort_dir)`` where
        ``sort_col`` is a SQLAlchemy column object for use with the
        ``sort_col`` parameter of :func:`~wizards_engine.api.pagination.paginate`.
    """
    stmt = select(Character)

    if not include_deleted:
        stmt = stmt.where(Character.is_deleted.is_(False))

    if detail_level is not None:
        stmt = stmt.where(Character.detail_level == detail_level)

    if has_player is True:
        # Only characters that have a User pointing at them.
        stmt = stmt.where(
            Character.id.in_(
                select(User.character_id).where(User.character_id.is_not(None))
            )
        )
    elif has_player is False:
        # Only characters with no linked User.
        stmt = stmt.where(
            ~Character.id.in_(
                select(User.character_id).where(User.character_id.is_not(None))
            )
        )

    if name is not None:
        stmt = stmt.where(func.lower(Character.name).contains(name.lower()))

    sort_col = _ALLOWED_SORT_COLS_CHARACTER.get(sort_by, Character.name)
    return stmt, sort_col, sort_dir


def update_character(
    db: Session,
    character: Character,
    updates: dict[str, Any],
) -> Character:
    """Apply a partial update to *character* and persist it.

    Only keys present in *updates* are applied.  The caller (route handler)
    is responsible for building *updates* using ``model_fields_set`` so that
    omitted PATCH fields are not overwritten.

    Args:
        db: Active SQLAlchemy session.
        character: The ORM instance to update.
        updates: Mapping of field names to new values.  Only ``name``,
            ``description``, and ``notes`` are permitted per the CRUD/GM
            action split.

    Returns:
        The updated :class:`~wizards_engine.models.character.Character`
        instance after flush.
    """
    for field, value in updates.items():
        setattr(character, field, value)
    db.flush()
    db.refresh(character)
    return character


def delete_character(db: Session, character: Character) -> None:
    """Soft-delete *character* by setting ``is_deleted = True``.

    The character row is never physically removed.  References (bonds,
    story entries, etc.) continue to resolve to the deleted record.

    Args:
        db: Active SQLAlchemy session.
        character: The ORM instance to soft-delete.
    """
    character.is_deleted = True
    db.flush()


def reset_stress(db: Session, character_id: str) -> Character:
    """Reset a full character's stress meter to 0.

    This is called as part of the Trauma compound operation — when a character
    takes a Trauma (bond retired, trauma bond created), their Stress resets to 0
    to give them breathing room after the consequence.

    Args:
        db: Active SQLAlchemy session.
        character_id: ULID of the character whose stress should be reset.

    Returns:
        The updated :class:`~wizards_engine.models.character.Character` instance.

    Raises:
        ValueError: If the character does not exist or is not a full (PC) character.
    """
    character = db.get(Character, character_id)
    if character is None:
        raise ValueError(f"Character '{character_id}' not found.")
    if character.detail_level != "full":
        raise ValueError(
            f"Character '{character_id}' is simplified (NPC). "
            "Stress mechanics apply to full (PC) characters only."
        )
    character.stress = 0
    db.flush()
    db.refresh(character)
    return character
