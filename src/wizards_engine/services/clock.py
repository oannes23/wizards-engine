"""Service layer for Clock CRUD operations.

All database interactions for the Clock resource live here.  Route
handlers call these functions and handle HTTP-level concerns (status
codes, response shaping) separately.

Functions are stateless — each accepts a SQLAlchemy ``Session`` as its
first argument.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from wizards_engine.models.character import Character
from wizards_engine.models.clock import Clock
from wizards_engine.models.group import Group
from wizards_engine.models.location import Location

# Mapping from associated_type value to the ORM model class.
_ASSOCIATED_TYPE_MAP: dict[str, type] = {
    "character": Character,
    "group": Group,
    "location": Location,
}


def resolve_associated_object(
    db: Session,
    associated_type: str,
    associated_id: str,
) -> bool:
    """Check whether the referenced Game Object exists (not soft-deleted).

    Args:
        db: Active SQLAlchemy session.
        associated_type: One of ``"character"``, ``"group"``, ``"location"``.
        associated_id: ULID of the referenced Game Object.

    Returns:
        ``True`` if the object exists and is not deleted; ``False`` otherwise.
    """
    model_cls = _ASSOCIATED_TYPE_MAP.get(associated_type)
    if model_cls is None:
        return False
    obj = db.get(model_cls, associated_id)
    return obj is not None and not obj.is_deleted


def create_clock(
    db: Session,
    *,
    name: str,
    segments: int = 5,
    associated_type: str | None = None,
    associated_id: str | None = None,
    notes: str | None = None,
) -> Clock:
    """Create a new Clock and persist it.

    Progress defaults to 0.  ``segments`` must be > 0 (caller validates).
    Association is optional; if provided, both ``associated_type`` and
    ``associated_id`` must be supplied together (caller validates).

    Args:
        db: Active SQLAlchemy session.
        name: Clock name.  Must be non-empty (caller validates).
        segments: Total segments.  Any positive integer; defaults to 5.
        associated_type: Optional Game Object type (``"character"``,
            ``"group"``, or ``"location"``).
        associated_id: Optional ID of the associated Game Object.
        notes: Optional freeform notes.

    Returns:
        The newly created and flushed :class:`~wizards_engine.models.clock.Clock`
        instance with its auto-generated ``id`` populated.
    """
    clock = Clock(
        name=name,
        segments=segments,
        progress=0,
        associated_type=associated_type,
        associated_id=associated_id,
        notes=notes,
        is_deleted=False,
    )
    db.add(clock)
    db.flush()
    db.refresh(clock)
    return clock


def get_clock(db: Session, clock_id: str) -> Clock | None:
    """Retrieve a single Clock by its ULID, including soft-deleted ones.

    Direct lookup by ID always returns the clock regardless of the
    ``is_deleted`` flag.

    Args:
        db: Active SQLAlchemy session.
        clock_id: ULID primary key.

    Returns:
        The :class:`~wizards_engine.models.clock.Clock` if found,
        or ``None`` if no row exists with that ID.
    """
    return db.get(Clock, clock_id)


def list_clocks_query(
    db: Session,
    *,
    associated_type: str | None = None,
    associated_id: str | None = None,
    include_deleted: bool = False,
):
    """Build a SQLAlchemy select statement for the Clocks list with optional filters.

    The returned statement has no ``ORDER BY`` or ``LIMIT`` applied — the
    caller (``api.pagination.paginate``) adds those.

    Args:
        db: Active SQLAlchemy session.
        associated_type: Filter to clocks with this association type.
        associated_id: Filter to clocks associated with this specific object ID.
        include_deleted: When ``True``, include soft-deleted clocks.
            Defaults to ``False`` (exclude deleted).

    Returns:
        A SQLAlchemy ``Select`` statement targeting :class:`~wizards_engine.models.clock.Clock`.
    """
    stmt = select(Clock)

    if not include_deleted:
        stmt = stmt.where(Clock.is_deleted.is_(False))

    if associated_type is not None:
        stmt = stmt.where(Clock.associated_type == associated_type)

    if associated_id is not None:
        stmt = stmt.where(Clock.associated_id == associated_id)

    return stmt


def update_clock(
    db: Session,
    clock: Clock,
    updates: dict[str, Any],
) -> Clock:
    """Apply a partial update to *clock* and persist it.

    Only keys present in *updates* are applied.  The caller is responsible
    for building *updates* using ``model_fields_set`` so that omitted PATCH
    fields are not overwritten.

    Only ``name``, ``notes``, and ``segments`` are permitted.  ``progress``,
    ``associated_type``, and ``associated_id`` cannot be changed via PATCH
    (caller enforces this).

    Args:
        db: Active SQLAlchemy session.
        clock: The ORM instance to update.
        updates: Mapping of field names to new values.

    Returns:
        The updated :class:`~wizards_engine.models.clock.Clock` instance after flush.
    """
    for field, value in updates.items():
        setattr(clock, field, value)
    db.flush()
    db.refresh(clock)
    return clock


def delete_clock(db: Session, clock: Clock) -> None:
    """Soft-delete *clock* by setting ``is_deleted = True``.

    The clock row is never physically removed.

    Args:
        db: Active SQLAlchemy session.
        clock: The ORM instance to soft-delete.
    """
    clock.is_deleted = True
    db.flush()
