"""Service layer for Group CRUD operations.

All database interactions for the Group resource live here.  Route
handlers call these functions and handle HTTP-level concerns (status codes,
response shaping) separately.

Functions are stateless — each accepts a SQLAlchemy ``Session`` as its
first argument.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from wizards_engine.models.group import Group

__all__ = [
    "create_group",
    "get_group",
    "list_groups_query",
    "update_group",
    "delete_group",
]


def create_group(
    db: Session,
    *,
    name: str,
    tier: int,
    description: str | None = None,
    notes: str | None = None,
) -> Group:
    """Create a new Group and persist it.

    Args:
        db: Active SQLAlchemy session.
        name: Group name.  Must be non-empty (caller validates).
        tier: Power/influence level.  Must be >= 0 (caller validates).
        description: Optional freeform description.
        notes: Optional GM notes.

    Returns:
        The newly created and flushed :class:`~wizards_engine.models.group.Group`
        instance with its auto-generated ``id`` populated.
    """
    group = Group(
        name=name,
        tier=tier,
        description=description,
        notes=notes,
        is_deleted=False,
    )
    db.add(group)
    db.flush()
    db.refresh(group)
    return group


def get_group(db: Session, group_id: str) -> Group | None:
    """Retrieve a single Group by its ULID, including soft-deleted ones.

    Direct lookup by ID always returns the group regardless of the
    ``is_deleted`` flag.  The route layer surfaces ``is_deleted`` in the
    response so callers can see the deletion state.

    Args:
        db: Active SQLAlchemy session.
        group_id: ULID primary key.

    Returns:
        The :class:`~wizards_engine.models.group.Group` if found,
        or ``None`` if no row exists with that ID.
    """
    return db.get(Group, group_id)


_ALLOWED_SORT_COLS_GROUP = {
    "name": Group.name,
    "created_at": Group.created_at,
    "updated_at": Group.updated_at,
}


def list_groups_query(
    db: Session,
    *,
    include_deleted: bool = False,
    name: str | None = None,
    sort_by: str = "name",
    sort_dir: str = "asc",
):
    """Build a SQLAlchemy select statement for the Groups list with optional filters.

    The returned statement has *no* ``ORDER BY`` or ``LIMIT`` applied — the
    caller (``api.pagination.paginate``) adds those.

    Args:
        db: Active SQLAlchemy session.
        include_deleted: When ``True``, include soft-deleted groups.
            Defaults to ``False`` (exclude deleted).
        name: Case-insensitive partial match on the group name.
        sort_by: Column to sort by — ``"name"``, ``"created_at"``, or
            ``"updated_at"``.  Defaults to ``"name"``.
        sort_dir: Sort direction — ``"asc"`` or ``"desc"``.  Defaults to ``"asc"``.

    Returns:
        A 2-tuple of ``(Select statement, order_by expression)`` targeting
        :class:`~wizards_engine.models.group.Group`.
    """
    stmt = select(Group)

    if not include_deleted:
        stmt = stmt.where(Group.is_deleted.is_(False))

    if name is not None:
        stmt = stmt.where(func.lower(Group.name).contains(name.lower()))

    sort_col = _ALLOWED_SORT_COLS_GROUP.get(sort_by, Group.name)
    return stmt, sort_col, sort_dir


def update_group(
    db: Session,
    group: Group,
    updates: dict[str, Any],
) -> Group:
    """Apply a partial update to *group* and persist it.

    Only keys present in *updates* are applied.  The caller (route handler)
    is responsible for building *updates* using ``model_fields_set`` so that
    omitted PATCH fields are not overwritten.

    Args:
        db: Active SQLAlchemy session.
        group: The ORM instance to update.
        updates: Mapping of field names to new values.  Only ``name``,
            ``description``, and ``notes`` are permitted per the CRUD/GM
            action split.  ``tier`` is not accepted here.

    Returns:
        The updated :class:`~wizards_engine.models.group.Group`
        instance after flush.
    """
    for field, value in updates.items():
        setattr(group, field, value)
    db.flush()
    db.refresh(group)
    return group


def delete_group(db: Session, group: Group) -> None:
    """Soft-delete *group* by setting ``is_deleted = True``.

    The group row is never physically removed.  References (bonds, slots,
    etc.) continue to resolve to the deleted record.

    Args:
        db: Active SQLAlchemy session.
        group: The ORM instance to soft-delete.
    """
    group.is_deleted = True
    db.flush()
