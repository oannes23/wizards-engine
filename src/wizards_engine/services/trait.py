"""Service layer for PC Trait Instance operations.

Manages Core and Role trait instances on full (PC-level) Characters.  Trait
instances live in the unified ``slots`` table with ``slot_type`` of
``"core_trait"`` or ``"role_trait"``.

No HTTP concerns live here.  Route handlers (and, later, GM action handlers)
call these functions and handle HTTP-level status codes and response shaping
separately.

Functions are stateless — each accepts a SQLAlchemy ``Session`` as its first
argument.

Key design notes (from spec/domains/traits.md):
- Core Traits: max 2 active per character.
- Role Traits: max 3 active per character.
- Template type must match slot type: ``core`` template → ``core_trait`` slot.
- A character can hold only one active instance per template (no duplicates).
- New trait instances always start at charge = 5 (full).
- Retirement sets ``is_active = False`` without deleting the row.
- Charge range is 0–5; decrement never goes below 0; recharge resets to 5.
"""

from __future__ import annotations

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from wizards_engine.models.character import Character
from wizards_engine.models.slot import Slot, TraitTemplate


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SLOT_LIMITS: dict[str, int] = {
    "core_trait": 2,
    "role_trait": 3,
}

# Maps slot_type → the template type required for that slot.
_REQUIRED_TEMPLATE_TYPE: dict[str, str] = {
    "core_trait": "core",
    "role_trait": "role",
}

_FULL_CHARGE = 5


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_active_character(db: Session, character_id: str) -> Character:
    """Return the non-deleted Character with the given ID.

    Args:
        db: Active SQLAlchemy session.
        character_id: ULID of the Character.

    Returns:
        The :class:`~wizards_engine.models.character.Character` instance.

    Raises:
        ValueError: If the character does not exist or has been soft-deleted.
    """
    character = db.get(Character, character_id)
    if character is None or character.is_deleted:
        raise ValueError(
            f"Character '{character_id}' not found or has been deleted."
        )
    return character


def _get_active_template(db: Session, template_id: str) -> TraitTemplate:
    """Return the non-deleted TraitTemplate with the given ID.

    Args:
        db: Active SQLAlchemy session.
        template_id: ULID of the TraitTemplate.

    Returns:
        The :class:`~wizards_engine.models.slot.TraitTemplate` instance.

    Raises:
        ValueError: If the template does not exist or has been soft-deleted.
    """
    template = db.get(TraitTemplate, template_id)
    if template is None:
        raise ValueError(f"Trait template '{template_id}' not found.")
    if template.is_deleted:
        raise ValueError(
            f"Trait template '{template_id}' has been deleted and cannot be "
            "assigned to new trait instances."
        )
    return template


def _count_active_traits(db: Session, character_id: str, slot_type: str) -> int:
    """Count active trait instances of the given slot_type for a character.

    Args:
        db: Active SQLAlchemy session.
        character_id: ULID of the Character.
        slot_type: ``"core_trait"`` or ``"role_trait"``.

    Returns:
        Integer count of active trait slots.
    """
    stmt = select(Slot).where(
        and_(
            Slot.owner_type == "character",
            Slot.owner_id == character_id,
            Slot.slot_type == slot_type,
            Slot.is_active.is_(True),
        )
    )
    return len(db.execute(stmt).scalars().all())


def _has_active_template_instance(
    db: Session, character_id: str, template_id: str
) -> bool:
    """Return ``True`` if the character already has an active instance of the template.

    Args:
        db: Active SQLAlchemy session.
        character_id: ULID of the Character.
        template_id: ULID of the TraitTemplate.

    Returns:
        ``True`` if an active slot with this template_id exists.
    """
    stmt = select(Slot).where(
        and_(
            Slot.owner_type == "character",
            Slot.owner_id == character_id,
            Slot.template_id == template_id,
            Slot.is_active.is_(True),
        )
    )
    return db.execute(stmt).scalars().first() is not None


def _get_slot_or_raise(db: Session, slot_id: str) -> Slot:
    """Return the Slot with the given ID.

    Args:
        db: Active SQLAlchemy session.
        slot_id: ULID of the Slot.

    Returns:
        The :class:`~wizards_engine.models.slot.Slot` instance.

    Raises:
        ValueError: If no slot with this ID exists.
    """
    slot = db.get(Slot, slot_id)
    if slot is None:
        raise ValueError(f"Trait instance '{slot_id}' not found.")
    return slot


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_trait_instance(
    db: Session,
    character_id: str,
    slot_type: str,
    template_id: str,
) -> Slot:
    """Create a new trait instance on a full Character.

    Validates all preconditions before creating the slot:
    - Character must exist, not be soft-deleted, and have ``detail_level="full"``.
    - Template must exist and not be soft-deleted.
    - Template type must match slot type (``core`` template → ``core_trait``,
      ``role`` template → ``role_trait``).
    - Active slot count must be below the limit (2 for core_trait, 3 for role_trait).
    - Character must not already have an active instance of the same template.

    New trait instances always start at ``charge = 5`` (full) and
    ``is_active = True``.

    Args:
        db: Active SQLAlchemy session.
        character_id: ULID of the Character to receive the trait.
        slot_type: ``"core_trait"`` or ``"role_trait"``.
        template_id: ULID of the TraitTemplate to link.

    Returns:
        The newly created and flushed :class:`~wizards_engine.models.slot.Slot`
        instance.

    Raises:
        ValueError: If any validation condition is not met.
    """
    if slot_type not in _SLOT_LIMITS:
        raise ValueError(
            f"Invalid slot_type '{slot_type}'. Must be 'core_trait' or 'role_trait'."
        )

    character = _get_active_character(db, character_id)

    if character.detail_level != "full":
        raise ValueError(
            f"Character '{character_id}' is a simplified (NPC) character. "
            "Trait instances can only be created on full (PC-level) characters."
        )

    template = _get_active_template(db, template_id)

    required_type = _REQUIRED_TEMPLATE_TYPE[slot_type]
    if template.type != required_type:
        raise ValueError(
            f"Template '{template_id}' has type '{template.type}', but slot_type "
            f"'{slot_type}' requires a '{required_type}' template. "
            "Core templates fill core_trait slots; role templates fill role_trait slots."
        )

    limit = _SLOT_LIMITS[slot_type]
    current_count = _count_active_traits(db, character_id, slot_type)
    if current_count >= limit:
        raise ValueError(
            f"Character '{character_id}' already has {current_count} active "
            f"{slot_type} instances (limit: {limit}). Retire an existing trait "
            "before adding a new one."
        )

    if _has_active_template_instance(db, character_id, template_id):
        raise ValueError(
            f"Character '{character_id}' already has an active trait instance for "
            f"template '{template_id}'. A character can only have one active instance "
            "per template."
        )

    slot = Slot(
        slot_type=slot_type,
        owner_type="character",
        owner_id=character_id,
        template_id=template_id,
        name=template.name,
        description=template.description,
        charge=_FULL_CHARGE,
        is_active=True,
    )
    db.add(slot)
    db.flush()
    db.refresh(slot)
    return slot


def retire_trait_instance(db: Session, slot_id: str) -> Slot:
    """Retire a trait instance by setting ``is_active = False``.

    The slot row is not deleted.  The retired instance remains on the
    character's "Past" section and its event history is preserved.

    Args:
        db: Active SQLAlchemy session.
        slot_id: ULID of the trait instance (Slot) to retire.

    Returns:
        The updated :class:`~wizards_engine.models.slot.Slot` instance.

    Raises:
        ValueError: If the slot does not exist or is not a trait slot.
    """
    slot = _get_slot_or_raise(db, slot_id)

    if slot.slot_type not in _SLOT_LIMITS:
        raise ValueError(
            f"Slot '{slot_id}' has type '{slot.slot_type}', which is not a "
            "trait slot. Only 'core_trait' and 'role_trait' slots can be retired "
            "via this function."
        )

    slot.is_active = False
    db.flush()
    db.refresh(slot)
    return slot


def replace_trait_instance(
    db: Session,
    character_id: str,
    retire_slot_id: str,
    slot_type: str,
    template_id: str,
) -> Slot:
    """Atomically retire an old trait and create a replacement.

    Validates that the old slot exists, belongs to the given character, and
    matches the given slot_type.  Then retires it and creates the new instance
    in one operation.

    This is the service-layer implementation of the "New Trait" downtime action
    when the player is replacing an existing (non-blank) trait.

    Args:
        db: Active SQLAlchemy session.
        character_id: ULID of the Character.
        retire_slot_id: ULID of the existing trait instance to retire.
        slot_type: ``"core_trait"`` or ``"role_trait"`` — must match the old slot.
        template_id: ULID of the TraitTemplate for the new instance.

    Returns:
        The newly created :class:`~wizards_engine.models.slot.Slot` (the
        replacement), after flush.

    Raises:
        ValueError: If the old slot does not exist, does not belong to the
            character, has a mismatched slot_type, or if the new instance
            fails validation.
    """
    old_slot = _get_slot_or_raise(db, retire_slot_id)

    if old_slot.owner_type != "character" or old_slot.owner_id != character_id:
        raise ValueError(
            f"Slot '{retire_slot_id}' does not belong to character '{character_id}'."
        )

    if old_slot.slot_type != slot_type:
        raise ValueError(
            f"Slot '{retire_slot_id}' has type '{old_slot.slot_type}', but "
            f"slot_type '{slot_type}' was expected. The replacement slot_type must "
            "match the slot being retired."
        )

    # Retire first so the slot count check in create_trait_instance sees a free slot.
    old_slot.is_active = False
    db.flush()

    new_slot = create_trait_instance(db, character_id, slot_type, template_id)
    return new_slot


def decrement_charge(db: Session, slot_id: str) -> Slot:
    """Decrement the charge on a trait instance by 1 (minimum 0).

    This is the service-layer implementation of spending a charge when a trait
    is invoked for the +1d bonus in an approved proposal.

    Args:
        db: Active SQLAlchemy session.
        slot_id: ULID of the trait instance (Slot).

    Returns:
        The updated :class:`~wizards_engine.models.slot.Slot` instance.

    Raises:
        ValueError: If the slot does not exist or is not a trait slot.
    """
    slot = _get_slot_or_raise(db, slot_id)

    if slot.slot_type not in _SLOT_LIMITS:
        raise ValueError(
            f"Slot '{slot_id}' has type '{slot.slot_type}', which is not a "
            "trait slot. Charge management applies to 'core_trait' and 'role_trait' "
            "slots only."
        )

    current_charge = slot.charge if slot.charge is not None else 0
    slot.charge = max(0, current_charge - 1)

    db.flush()
    db.refresh(slot)
    return slot


def recharge_trait(db: Session, slot_id: str) -> Slot:
    """Reset a trait instance's charge to 5 (full).

    This is the service-layer implementation of the "Recharge Trait" downtime
    activity.

    Args:
        db: Active SQLAlchemy session.
        slot_id: ULID of the trait instance (Slot).

    Returns:
        The updated :class:`~wizards_engine.models.slot.Slot` instance.

    Raises:
        ValueError: If the slot does not exist or is not a trait slot.
    """
    slot = _get_slot_or_raise(db, slot_id)

    if slot.slot_type not in _SLOT_LIMITS:
        raise ValueError(
            f"Slot '{slot_id}' has type '{slot.slot_type}', which is not a "
            "trait slot. Charge management applies to 'core_trait' and 'role_trait' "
            "slots only."
        )

    slot.charge = _FULL_CHARGE

    db.flush()
    db.refresh(slot)
    return slot


def get_trait_instance(db: Session, slot_id: str) -> Slot | None:
    """Return the Slot with the given ID, or ``None`` if it does not exist.

    Args:
        db: Active SQLAlchemy session.
        slot_id: ULID of the slot to retrieve.

    Returns:
        The :class:`~wizards_engine.models.slot.Slot` instance, or ``None``.
    """
    return db.get(Slot, slot_id)


def get_active_traits(
    db: Session,
    character_id: str,
    slot_type: str,
) -> list[Slot]:
    """Return all active trait instances of a given slot_type for a character.

    Only active (``is_active = True``) slots are returned.  Retired/past
    traits are excluded.

    Args:
        db: Active SQLAlchemy session.
        character_id: ULID of the Character.
        slot_type: ``"core_trait"`` or ``"role_trait"``.

    Returns:
        Ordered list of :class:`~wizards_engine.models.slot.Slot` instances,
        sorted by creation time (ascending).
    """
    stmt = (
        select(Slot)
        .where(
            and_(
                Slot.owner_type == "character",
                Slot.owner_id == character_id,
                Slot.slot_type == slot_type,
                Slot.is_active.is_(True),
            )
        )
        .order_by(Slot.created_at)
    )
    return list(db.execute(stmt).scalars().all())
