"""Service layer for Magic Effect lifecycle operations.

All database interactions for the MagicEffect resource live here.  Route
handlers call these functions and handle HTTP-level concerns separately.

Functions are stateless — each accepts a SQLAlchemy ``Session`` as its
first argument.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from wizards_engine.models.character import Character
from wizards_engine.models.magic_effect import MagicEffect

# Effect types that count toward the cap of 9.
_CAPPED_TYPES = frozenset({"charged", "permanent"})

# Maximum number of active (charged + permanent) effects per character.
EFFECT_CAP = 9


def _count_active_capped_effects(db: Session, character_id: str) -> int:
    """Return the number of active charged + permanent effects for a character.

    Args:
        db: Active SQLAlchemy session.
        character_id: ULID of the character.

    Returns:
        Count of active charged and permanent effects (excludes instants).
    """
    rows = (
        db.execute(
            select(MagicEffect).where(
                MagicEffect.character_id == character_id,
                MagicEffect.is_active.is_(True),
                MagicEffect.effect_type.in_(list(_CAPPED_TYPES)),
            )
        )
        .scalars()
        .all()
    )
    return len(rows)


def create_effect(
    db: Session,
    character_id: str,
    name: str,
    description: str,
    effect_type: str,
    power_level: int,
    charges_current: int | None = None,
    charges_max: int | None = None,
) -> MagicEffect:
    """Create a new Magic Effect on a character's sheet.

    Validates that the character exists and is full (``detail_level='full'``),
    that ``effect_type`` is one of ``'instant'``, ``'charged'``, or
    ``'permanent'``, that ``power_level`` is between 1 and 5, and that charged
    effects have both charge fields.  Charged and permanent effects count toward
    the cap of 9 active effects; instants do not.

    Args:
        db: Active SQLAlchemy session.
        character_id: ULID of the character to attach the effect to.
        name: Effect name.
        description: Effect description.
        effect_type: One of ``'instant'``, ``'charged'``, or ``'permanent'``.
        power_level: Effect power level (1–5).
        charges_current: Current charges (required for charged; must be None
            for instant/permanent).
        charges_max: Maximum charges (required for charged; must be None for
            instant/permanent).

    Returns:
        The newly created and flushed :class:`~wizards_engine.models.magic_effect.MagicEffect`.

    Raises:
        ValueError: If any validation rule is violated.
    """
    character = db.get(Character, character_id)
    if character is None:
        raise ValueError(f"Character '{character_id}' not found.")
    if character.detail_level != "full":
        raise ValueError(
            f"Character '{character_id}' is not a full character. "
            "Magic effects can only be added to full (PC) characters."
        )

    valid_types = {"instant", "charged", "permanent"}
    if effect_type not in valid_types:
        raise ValueError(
            f"Invalid effect_type '{effect_type}'. Must be one of: "
            + ", ".join(sorted(valid_types))
        )

    if not (1 <= power_level <= 5):
        raise ValueError(
            f"power_level must be between 1 and 5, got {power_level}."
        )

    if effect_type == "charged":
        if charges_current is None or charges_max is None:
            raise ValueError(
                "charges_current and charges_max are required for charged effects."
            )
    else:
        if charges_current is not None or charges_max is not None:
            raise ValueError(
                f"charges_current and charges_max must be None for '{effect_type}' effects."
            )

    # Enforce cap — only charged and permanent count toward the limit.
    if effect_type in _CAPPED_TYPES:
        current_count = _count_active_capped_effects(db, character_id)
        if current_count >= EFFECT_CAP:
            raise ValueError(
                f"Character '{character_id}' already has {current_count} active "
                f"charged/permanent effects (cap is {EFFECT_CAP}). "
                "Retire an existing effect before adding a new one."
            )

    effect = MagicEffect(
        character_id=character_id,
        name=name,
        description=description,
        effect_type=effect_type,
        power_level=power_level,
        charges_current=charges_current,
        charges_max=charges_max,
        is_active=True,
    )
    db.add(effect)
    db.flush()
    db.refresh(effect)
    return effect


def use_effect(
    db: Session,
    effect_id: str,
    narrative: str | None = None,
) -> MagicEffect:
    """Decrement the charges on a charged Magic Effect by 1.

    The ``narrative`` parameter is accepted for event-log purposes (deferred to
    a later epic) and is not stored on the effect itself.

    Args:
        db: Active SQLAlchemy session.
        effect_id: ULID of the MagicEffect to use.
        narrative: Optional freeform text describing the use (accepted,
            not stored on the effect record itself).

    Returns:
        The updated :class:`~wizards_engine.models.magic_effect.MagicEffect`.

    Raises:
        ValueError: If the effect does not exist, is not active, is not of
            type ``'charged'``, or has zero charges remaining.
    """
    effect = db.get(MagicEffect, effect_id)
    if effect is None:
        raise ValueError(f"Magic effect '{effect_id}' not found.")
    if not effect.is_active:
        raise ValueError(
            f"Magic effect '{effect_id}' is not active (it has been retired)."
        )
    if effect.effect_type != "charged":
        raise ValueError(
            f"Magic effect '{effect_id}' is of type '{effect.effect_type}'. "
            "Only charged effects can be used this way."
        )
    if effect.charges_current is None or effect.charges_current <= 0:
        raise ValueError(
            f"Magic effect '{effect_id}' has no charges remaining."
        )

    effect.charges_current -= 1
    db.flush()
    db.refresh(effect)
    return effect


def retire_effect(db: Session, effect_id: str) -> MagicEffect:
    """Set an effect's ``is_active`` flag to ``False``, moving it to Past.

    Freeing the cap space is automatic — the effect is no longer counted
    because the active-filter excludes it.

    Args:
        db: Active SQLAlchemy session.
        effect_id: ULID of the MagicEffect to retire.

    Returns:
        The updated :class:`~wizards_engine.models.magic_effect.MagicEffect`.

    Raises:
        ValueError: If the effect does not exist.
    """
    effect = db.get(MagicEffect, effect_id)
    if effect is None:
        raise ValueError(f"Magic effect '{effect_id}' not found.")

    effect.is_active = False
    db.flush()
    db.refresh(effect)
    return effect


def get_effect(db: Session, effect_id: str) -> MagicEffect | None:
    """Return a single MagicEffect by its ULID.

    Args:
        db: Active SQLAlchemy session.
        effect_id: ULID primary key.

    Returns:
        The :class:`~wizards_engine.models.magic_effect.MagicEffect` if found,
        or ``None`` if no row exists with that ID.
    """
    return db.get(MagicEffect, effect_id)


def get_effects_for_character(
    db: Session, character_id: str
) -> list[MagicEffect]:
    """Return all magic effects (active and retired) for a character.

    Results are ordered by creation time, oldest first.

    Args:
        db: Active SQLAlchemy session.
        character_id: ULID of the character.

    Returns:
        A list of :class:`~wizards_engine.models.magic_effect.MagicEffect`
        instances (may be empty).
    """
    return list(
        db.execute(
            select(MagicEffect)
            .where(MagicEffect.character_id == character_id)
            .order_by(MagicEffect.created_at)
        )
        .scalars()
        .all()
    )
