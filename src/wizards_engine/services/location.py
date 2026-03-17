"""Service layer for Location CRUD operations.

All database interactions for the Location resource live here.  Route
handlers call these functions and handle HTTP-level concerns (status codes,
response shaping) separately.

Functions are stateless — each accepts a SQLAlchemy ``Session`` as its
first argument.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from wizards_engine.models.location import Location


def create_location(
    db: Session,
    *,
    name: str,
    description: str | None = None,
    parent_id: str | None = None,
    notes: str | None = None,
) -> Location:
    """Create a new Location and persist it.

    Args:
        db: Active SQLAlchemy session.
        name: Location name.  Must be non-empty (caller validates).
        description: Optional freeform description.
        parent_id: Optional ULID of the parent location.  Caller must
            validate that this references an existing location.
        notes: Optional GM notes.

    Returns:
        The newly created and flushed :class:`~wizards_engine.models.location.Location`
        instance with its auto-generated ``id`` populated.
    """
    location = Location(
        name=name,
        description=description,
        parent_id=parent_id,
        notes=notes,
        is_deleted=False,
    )
    db.add(location)
    db.flush()
    db.refresh(location)
    return location


def get_location(db: Session, location_id: str) -> Location | None:
    """Retrieve a single Location by its ULID, including soft-deleted ones.

    Direct lookup by ID always returns the location regardless of the
    ``is_deleted`` flag.  The route layer surfaces ``is_deleted`` in the
    response so callers can see the deletion state.

    Args:
        db: Active SQLAlchemy session.
        location_id: ULID primary key.

    Returns:
        The :class:`~wizards_engine.models.location.Location` if found,
        or ``None`` if no row exists with that ID.
    """
    return db.get(Location, location_id)


def list_locations_query(
    db: Session,
    *,
    parent_id: str | None = None,
    include_deleted: bool = False,
):
    """Build a SQLAlchemy select statement for the Locations list with optional filters.

    The returned statement has *no* ``ORDER BY`` or ``LIMIT`` applied — the
    caller (``api.pagination.paginate``) adds those.

    Args:
        db: Active SQLAlchemy session.
        parent_id: When provided, return only direct children of this
            location (not recursive).  ``None`` skips the filter.
        include_deleted: When ``True``, include soft-deleted locations.
            Defaults to ``False`` (exclude deleted).

    Returns:
        A SQLAlchemy ``Select`` statement targeting :class:`~wizards_engine.models.location.Location`.
    """
    stmt = select(Location)

    if not include_deleted:
        stmt = stmt.where(Location.is_deleted.is_(False))

    if parent_id is not None:
        stmt = stmt.where(Location.parent_id == parent_id)

    return stmt


def update_location(
    db: Session,
    location: Location,
    updates: dict[str, Any],
) -> Location:
    """Apply a partial update to *location* and persist it.

    Only keys present in *updates* are applied.  The caller (route handler)
    is responsible for building *updates* using ``model_fields_set`` so that
    omitted PATCH fields are not overwritten.

    Args:
        db: Active SQLAlchemy session.
        location: The ORM instance to update.
        updates: Mapping of field names to new values.  Only ``name``,
            ``description``, and ``notes`` are permitted per the CRUD/GM
            action split.  ``parent_id`` changes come via GM actions.

    Returns:
        The updated :class:`~wizards_engine.models.location.Location`
        instance after flush.
    """
    for field, value in updates.items():
        setattr(location, field, value)
    db.flush()
    db.refresh(location)
    return location


def delete_location(db: Session, location: Location) -> None:
    """Soft-delete *location* by setting ``is_deleted = True``.

    The location row is never physically removed.  References (bonds,
    story entries, etc.) continue to resolve to the deleted record.

    Args:
        db: Active SQLAlchemy session.
        location: The ORM instance to soft-delete.
    """
    location.is_deleted = True
    db.flush()
