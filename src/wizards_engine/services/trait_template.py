"""Service layer for Trait Template CRUD operations.

All database interactions for the TraitTemplate resource live here.  Route
handlers call these functions and handle HTTP-level concerns (status codes,
response shaping) separately.

Functions are stateless — each accepts a SQLAlchemy ``Session`` as its
first argument.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from wizards_engine.models.slot import TraitTemplate

__all__ = [
    "create_trait_template",
    "get_trait_template",
    "list_trait_templates_query",
    "update_trait_template",
    "delete_trait_template",
]


def create_trait_template(
    db: Session,
    *,
    name: str,
    description: str,
    template_type: str,
) -> TraitTemplate:
    """Create a new TraitTemplate and persist it.

    Args:
        db: Active SQLAlchemy session.
        name: Template name.  Must be non-empty (caller validates).
        description: Freeform trait description.  Must be non-empty (caller validates).
        template_type: Either ``"core"`` or ``"role"``.  Immutable after creation.

    Returns:
        The newly created and flushed :class:`~wizards_engine.models.slot.TraitTemplate`
        instance with its auto-generated ``id`` populated.
    """
    template = TraitTemplate(
        name=name,
        description=description,
        type=template_type,
        is_deleted=False,
    )
    db.add(template)
    db.flush()
    db.refresh(template)
    return template


def get_trait_template(db: Session, template_id: str) -> TraitTemplate | None:
    """Retrieve a single TraitTemplate by its ULID, including soft-deleted ones.

    Direct lookup by ID always returns the template regardless of the
    ``is_deleted`` flag.  This is intentional — soft-deleted templates must
    still resolve for trait instance display on character sheets.

    Args:
        db: Active SQLAlchemy session.
        template_id: ULID primary key.

    Returns:
        The :class:`~wizards_engine.models.slot.TraitTemplate` if found,
        or ``None`` if no row exists with that ID.
    """
    return db.get(TraitTemplate, template_id)


def list_trait_templates_query(
    db: Session,
    *,
    template_type: str | None = None,
    include_deleted: bool = False,
):
    """Build a SQLAlchemy select statement for the TraitTemplates list with optional filters.

    The returned statement has *no* ``ORDER BY`` or ``LIMIT`` applied — the
    caller (``api.pagination.paginate``) adds those.

    Args:
        db: Active SQLAlchemy session.
        template_type: Optional filter — ``"core"`` or ``"role"``.
        include_deleted: When ``True``, include soft-deleted templates.
            Defaults to ``False`` (exclude deleted).

    Returns:
        A SQLAlchemy ``Select`` statement targeting
        :class:`~wizards_engine.models.slot.TraitTemplate`.
    """
    stmt = select(TraitTemplate)

    if not include_deleted:
        stmt = stmt.where(TraitTemplate.is_deleted.is_(False))

    if template_type is not None:
        stmt = stmt.where(TraitTemplate.type == template_type)

    return stmt


def update_trait_template(
    db: Session,
    template: TraitTemplate,
    updates: dict[str, Any],
) -> TraitTemplate:
    """Apply a partial update to *template* and persist it.

    Only keys present in *updates* are applied.  The caller (route handler)
    is responsible for building *updates* using ``model_fields_set`` so that
    omitted PATCH fields are not overwritten.

    Note: ``type`` is never accepted in *updates* — it is immutable after
    creation.  The route layer is responsible for rejecting PATCH requests
    that include ``type``.

    Args:
        db: Active SQLAlchemy session.
        template: The ORM instance to update.
        updates: Mapping of field names to new values.  Only ``name`` and
            ``description`` are permitted per the spec.

    Returns:
        The updated :class:`~wizards_engine.models.slot.TraitTemplate`
        instance after flush.
    """
    for field, value in updates.items():
        setattr(template, field, value)
    db.flush()
    db.refresh(template)
    return template


def delete_trait_template(db: Session, template: TraitTemplate) -> None:
    """Soft-delete *template* by setting ``is_deleted = True``.

    The template row is never physically removed.  Existing trait instances
    that reference this template via ``slots.template_id`` are NOT affected —
    they continue to function normally.  The template is hidden from list
    results but remains resolvable by direct GET for instance display.

    Args:
        db: Active SQLAlchemy session.
        template: The ORM instance to soft-delete.
    """
    template.is_deleted = True
    db.flush()
