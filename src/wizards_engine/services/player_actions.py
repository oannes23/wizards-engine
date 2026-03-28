"""Service layer for player direct actions.

Implements stateless business logic for the three player direct action
endpoints that do not require GM approval:

- ``execute_find_time``: Convert 3 Plot → 1 Free Time.
- ``execute_recharge_trait``: Spend 1 Free Time to restore a Core/Role trait to 5 charges.
- ``execute_maintain_bond``: Spend 1 Free Time to restore a PC bond to its effective max charges.

Each function: fetches → validates → mutates → creates event → returns result.
Routes call these functions and handle auth/ownership checks before the call.

Domain exceptions from :mod:`wizards_engine.services.exceptions` are raised
in preference to HTTP-layer exceptions so the service layer remains testable
independent of FastAPI.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from wizards_engine.models.character import Character
from wizards_engine.models.slot import Slot
from wizards_engine.models.user import User
from wizards_engine.schemas.character import CharacterResponse
from wizards_engine.roles import actor_type_for
from wizards_engine.services.event import create_event
from wizards_engine.services.exceptions import (
    BusinessRuleViolation,
    InsufficientResources,
    NotFoundError,
)
from wizards_engine.services.proposal.constants import FREE_TIME_MAX

__all__ = [
    "execute_find_time",
    "execute_recharge_trait",
    "execute_maintain_bond",
]


# ---------------------------------------------------------------------------
# find-time
# ---------------------------------------------------------------------------


class FindTimeResult:
    """Result of a successful find-time action.

    Attributes
    ----------
    id:
        ULID of the character.
    plot:
        Updated plot value after spending 3.
    free_time:
        Updated free_time value after gaining 1.
    """

    def __init__(self, id: str, plot: int, free_time: int) -> None:
        self.id = id
        self.plot = plot
        self.free_time = free_time


def execute_find_time(
    db: Session,
    character_id: str,
    actor_user: User,
) -> FindTimeResult:
    """Convert 3 Plot into 1 Free Time for a full (PC) character.

    Validates the character exists, is a full PC, has at least 3 Plot, and
    has fewer than 20 Free Time.  Then applies the conversion and creates an
    event in the append-only log.

    Args:
        db: Active SQLAlchemy session.
        character_id: ULID of the target character.
        actor_user: The authenticated user performing the action.

    Returns:
        :class:`FindTimeResult` with the updated ``plot`` and ``free_time`` values.

    Raises:
        NotFoundError: If the character does not exist or is deleted.
        BusinessRuleViolation: If the character is not a full PC, has fewer
            than 3 Plot (``insufficient_plot``), or Free Time is already at
            the cap of 20 (``free_time_at_cap``).
    """
    character: Character | None = db.get(Character, character_id)
    if character is None or character.is_deleted:
        raise NotFoundError("Character", character_id)

    if character.detail_level != "full":
        raise BusinessRuleViolation(
            "not_a_pc",
            "Only full (PC-level) characters can use find-time.",
        )

    plot_before: int = character.plot or 0
    if plot_before < 3:
        raise InsufficientResources(
            "insufficient_plot",
            "Character does not have enough Plot (requires 3).",
        )

    ft_before: int = character.free_time or 0
    if ft_before >= FREE_TIME_MAX:
        raise InsufficientResources(
            "free_time_at_cap",
            "Character's Free Time is already at the cap of 20.",
        )

    plot_after = plot_before - 3
    ft_after = ft_before + 1

    character.plot = plot_after
    character.free_time = ft_after
    db.flush()

    create_event(
        db,
        type="player.find_time",
        actor_type=actor_type_for(actor_user),
        actor_id=actor_user.id,
        visibility="private",
        changes={
            f"character.{character_id}.plot": {
                "op": "meter.delta",
                "before": plot_before,
                "after": plot_after,
            },
            f"character.{character_id}.free_time": {
                "op": "meter.delta",
                "before": ft_before,
                "after": ft_after,
            },
        },
        targets=[
            {
                "target_type": "character",
                "target_id": character_id,
                "is_primary": True,
            }
        ],
    )

    db.refresh(character)
    return FindTimeResult(
        id=character.id,
        plot=character.plot,
        free_time=character.free_time,
    )


# ---------------------------------------------------------------------------
# recharge-trait
# ---------------------------------------------------------------------------


def execute_recharge_trait(
    db: Session,
    character_id: str,
    slot_id: str,
    narrative: str,
    actor_user: User,
) -> CharacterResponse:
    """Spend 1 Free Time to restore a Core or Role trait to full charges (5).

    Validates character exists and is a full PC, narrative is non-empty,
    slot exists and belongs to the character, slot is active, slot type is
    ``core_trait`` or ``role_trait``, trait is not already at 5 charges, and
    character has at least 1 Free Time.

    Args:
        db: Active SQLAlchemy session.
        character_id: ULID of the target character.
        slot_id: ULID of the Slot record representing the trait to recharge.
        narrative: Player-written description (must be non-empty).
        actor_user: The authenticated user performing the action.

    Returns:
        :class:`~wizards_engine.schemas.character.CharacterResponse` with the
        character's current state after the action.

    Raises:
        NotFoundError: If the character is not found, or the trait slot is
            not found.
        BusinessRuleViolation: If the character is not a full PC, the
            narrative is empty, the slot does not belong to the character,
            the slot is not active, or the slot type is not a trait type.
        InsufficientResources: If the trait is already at max charges
            (``trait_already_full``) or the character has no Free Time
            (``insufficient_free_time``).
    """
    character: Character | None = db.get(Character, character_id)
    if character is None or character.is_deleted:
        raise NotFoundError("Character", character_id)

    if character.detail_level != "full":
        raise BusinessRuleViolation(
            "not_a_pc",
            "Only full (PC-level) characters can use recharge-trait.",
        )

    if not narrative or not narrative.strip():
        raise BusinessRuleViolation(
            "narrative_required",
            "A non-empty narrative is required for this action.",
        )

    slot: Slot | None = db.get(Slot, slot_id)
    if slot is None:
        raise NotFoundError("Trait slot", slot_id, code="trait_not_found")

    if slot.owner_id != character_id:
        raise BusinessRuleViolation(
            "trait_not_owned",
            "This trait slot does not belong to the specified character.",
        )

    if not slot.is_active:
        raise BusinessRuleViolation(
            "trait_not_active",
            "Only active traits can be recharged.",
        )

    if slot.slot_type not in ("core_trait", "role_trait"):
        raise BusinessRuleViolation(
            "not_a_trait",
            "Only core_trait and role_trait slots can be recharged.",
        )

    charge_before: int = slot.charge if slot.charge is not None else 0
    if charge_before >= 5:
        raise InsufficientResources(
            "trait_already_full",
            "This trait's charges are already at the maximum of 5.",
        )

    ft_before: int = character.free_time or 0
    if ft_before < 1:
        raise InsufficientResources(
            "insufficient_free_time",
            "Character does not have enough Free Time (requires 1).",
        )

    ft_after = ft_before - 1
    slot.charge = 5
    character.free_time = ft_after
    db.flush()

    create_event(
        db,
        type="player.recharge_trait",
        actor_type=actor_type_for(actor_user),
        actor_id=actor_user.id,
        visibility="private",
        narrative=narrative,
        changes={
            f"slot.{slot_id}.charge": {
                "op": "meter.set",
                "before": charge_before,
                "after": 5,
            },
            f"character.{character_id}.free_time": {
                "op": "meter.delta",
                "before": ft_before,
                "after": ft_after,
            },
        },
        targets=[
            {
                "target_type": "character",
                "target_id": character_id,
                "is_primary": True,
            }
        ],
    )

    db.refresh(character)
    return CharacterResponse.model_validate(character)


# ---------------------------------------------------------------------------
# maintain-bond
# ---------------------------------------------------------------------------


def execute_maintain_bond(
    db: Session,
    character_id: str,
    slot_id: str,
    narrative: str,
    actor_user: User,
) -> CharacterResponse:
    """Spend 1 Free Time to restore a PC bond to its effective maximum charges.

    The effective maximum is ``5 - degradations``.  Validates character exists
    and is a full PC, narrative is non-empty, slot exists and belongs to the
    character, slot is active, slot type is ``pc_bond``, bond is not a trauma
    bond, bond is not already at effective max, and character has at least 1
    Free Time.

    Args:
        db: Active SQLAlchemy session.
        character_id: ULID of the target character.
        slot_id: ULID of the Slot record representing the bond to maintain.
        narrative: Player-written description (must be non-empty).
        actor_user: The authenticated user performing the action.

    Returns:
        :class:`~wizards_engine.schemas.character.CharacterResponse` with the
        character's current state after the action.

    Raises:
        NotFoundError: If the character is not found, or the bond slot is not found.
        BusinessRuleViolation: If the character is not a full PC, the narrative
            is empty, the slot does not belong to the character, the slot is not
            active, the slot type is not ``pc_bond``, or the bond is a trauma bond.
        InsufficientResources: If the bond is already at its effective maximum
            charges (``bond_already_maintained``) or the character has no Free
            Time (``insufficient_free_time``).
    """
    character: Character | None = db.get(Character, character_id)
    if character is None or character.is_deleted:
        raise NotFoundError("Character", character_id)

    if character.detail_level != "full":
        raise BusinessRuleViolation(
            "not_a_pc",
            "Only full (PC-level) characters can use maintain-bond.",
        )

    if not narrative or not narrative.strip():
        raise BusinessRuleViolation(
            "narrative_required",
            "A non-empty narrative is required for this action.",
        )

    slot: Slot | None = db.get(Slot, slot_id)
    if slot is None:
        raise NotFoundError("Bond slot", slot_id, code="bond_not_found")

    if slot.owner_id != character_id:
        raise BusinessRuleViolation(
            "bond_not_owned",
            "This bond slot does not belong to the specified character.",
        )

    if not slot.is_active:
        raise BusinessRuleViolation(
            "bond_not_active",
            "Only active bonds can be maintained.",
        )

    if slot.slot_type != "pc_bond":
        raise BusinessRuleViolation(
            "not_a_pc_bond",
            "Only pc_bond slots can be maintained.",
        )

    if slot.is_trauma is True:
        raise BusinessRuleViolation(
            "cannot_maintain_trauma",
            "Trauma bonds cannot be maintained.",
        )

    effective_max: int = 5 - (slot.degradations or 0)
    charges_before: int = slot.charges if slot.charges is not None else 0

    if charges_before >= effective_max:
        raise InsufficientResources(
            "bond_already_maintained",
            "This bond's charges are already at the effective maximum.",
        )

    ft_before: int = character.free_time or 0
    if ft_before < 1:
        raise InsufficientResources(
            "insufficient_free_time",
            "Character does not have enough Free Time (requires 1).",
        )

    ft_after = ft_before - 1
    slot.charges = effective_max
    character.free_time = ft_after
    db.flush()

    create_event(
        db,
        type="player.maintain_bond",
        actor_type=actor_type_for(actor_user),
        actor_id=actor_user.id,
        visibility="private",
        narrative=narrative,
        changes={
            f"slot.{slot_id}.charges": {
                "op": "meter.set",
                "before": charges_before,
                "after": effective_max,
            },
            f"character.{character_id}.free_time": {
                "op": "meter.delta",
                "before": ft_before,
                "after": ft_after,
            },
        },
        targets=[
            {
                "target_type": "character",
                "target_id": character_id,
                "is_primary": True,
            }
        ],
    )

    db.refresh(character)
    return CharacterResponse.model_validate(character)
