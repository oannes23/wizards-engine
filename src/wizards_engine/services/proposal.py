"""Service layer for Proposal creation and retrieval.

Proposals are the player-facing workflow for submitting intended actions.
Each proposal passes through ``pending`` → (``approved`` | ``rejected``)
states.  The GM reviews and approves or rejects proposals.

Functions are stateless — each accepts a SQLAlchemy ``Session`` as its
first argument.

Key decisions:
- Only the owning player or the GM can read/edit/delete a proposal.
- System action types (``resolve_clock``, ``resolve_trauma``) are
  created internally, never via the player submission path.
- When a rejected proposal is revised (PATCH), it transitions back to
  ``pending`` and a ``proposal.revised`` event is recorded.
- ``use_skill`` proposals have their ``calculated_effect`` populated on
  creation and on revision.  The calculation validates skill, trait
  modifiers, bond modifier, and Plot spend, raising ``ValueError`` for
  any affordability or ownership violation.
- All 7 downtime action types auto-cost 1 FT (deducted on approval).
  Affordability check (FT >= 1) is performed on submission.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from wizards_engine.models.character import Character
from wizards_engine.models.magic_effect import MagicEffect
from wizards_engine.models.proposal import Proposal
from wizards_engine.models.slot import Slot, TraitTemplate
from wizards_engine.services.event import create_event
from wizards_engine.services.magic_effect import create_effect as _create_magic_effect

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: The 8 canonical skill names accepted in ``use_skill`` proposals.
CANONICAL_SKILLS: frozenset[str] = frozenset(
    {
        "awareness",
        "composure",
        "influence",
        "finesse",
        "speed",
        "power",
        "knowledge",
        "technology",
    }
)

#: The 5 canonical magic stat names accepted in ``use_magic`` / ``charge_magic`` proposals.
CANONICAL_MAGIC_STATS: frozenset[str] = frozenset(
    {
        "being",
        "wyrding",
        "summoning",
        "enchanting",
        "dreaming",
    }
)

#: The 5 magic stat keys used for ``regain_gnosis`` lowest-stat calculation.
MAGIC_STAT_KEYS: tuple[str, ...] = (
    "being",
    "wyrding",
    "summoning",
    "enchanting",
    "dreaming",
)

#: Maximum gnosis value (cap applied on approval).
GNOSIS_MAX: int = 23

#: Maximum free_time value.
FREE_TIME_MAX: int = 20

#: Hard PC bond slot limit.
PC_BOND_LIMIT: int = 8

#: Hard active trait limits per slot_type.
TRAIT_LIMITS: dict[str, int] = {
    "core_trait": 2,
    "role_trait": 3,
}

#: Downtime action types that auto-cost 1 FT (proposal-based only).
#: ``recharge_trait`` and ``maintain_bond`` were promoted to direct player
#: actions in Phase 5.5 and are no longer valid proposal action types.
DOWNTIME_ACTION_TYPES: frozenset[str] = frozenset(
    {
        "regain_gnosis",
        "work_on_project",
        "rest",
        "new_trait",
        "new_bond",
    }
)


# ---------------------------------------------------------------------------
# use_skill calculation
# ---------------------------------------------------------------------------


def calculate_use_skill(
    db: Session,
    *,
    character_id: str,
    selections: dict[str, Any],
) -> dict[str, Any]:
    """Validate and compute the ``calculated_effect`` for a ``use_skill`` proposal.

    Validates the skill name, optional trait/bond modifiers, and Plot spend
    against the character's current state.  Raises ``HTTPException(422)`` for
    any validation failure.

    Args:
        db: Active SQLAlchemy session.
        character_id: ULID of the character submitting the proposal.
        selections: The ``selections`` dict from the proposal request, expected to
            contain:

            - ``skill`` (str): one of the 8 canonical skill names.
            - ``modifiers`` (dict, optional): mapping with optional keys
              ``core_trait_id``, ``role_trait_id``, ``bond_id``.
            - ``plot_spend`` (int, optional): number of Plot points to spend
              (default 0).

    Returns:
        A ``calculated_effect`` dict with the shape::

            {
                "dice_pool": int,
                "skill": str,
                "skill_level": int,
                "modifiers": [
                    {"type": str, "id": str, "name": str, "bonus": 1},
                    ...
                ],
                "plot_spend": int,
                "costs": {
                    "trait_charges": [{"trait_id": str, "cost": 1}, ...],
                    "plot": int,
                }
            }

    Raises:
        HTTPException(422): If skill is invalid, a referenced trait/bond is
            missing, not owned by the character, inactive, has 0 charges (traits),
            or the character lacks sufficient Plot.
    """
    # ------------------------------------------------------------------
    # Skill validation
    # ------------------------------------------------------------------
    skill = selections.get("skill")
    if not skill:
        _raise_422("skill", "skill is required for use_skill proposals")
    if skill not in CANONICAL_SKILLS:
        _raise_422(
            "skill",
            f"skill must be one of: {sorted(CANONICAL_SKILLS)}",
        )

    character: Character | None = db.get(Character, character_id)
    if character is None:
        # Character was already validated by the route; this is a guard.
        _raise_422("character_id", f"Character '{character_id}' not found")

    skill_level: int = (character.skills or {}).get(skill, 0)

    # ------------------------------------------------------------------
    # Modifier validation
    # ------------------------------------------------------------------
    modifiers_input: dict[str, Any] = selections.get("modifiers") or {}
    core_trait_id: str | None = modifiers_input.get("core_trait_id")
    role_trait_id: str | None = modifiers_input.get("role_trait_id")
    bond_id: str | None = modifiers_input.get("bond_id")

    active_modifiers: list[dict[str, Any]] = []
    trait_charges_costs: list[dict[str, Any]] = []

    if core_trait_id is not None:
        slot = _validate_trait_modifier(db, character_id, core_trait_id, "core_trait")
        active_modifiers.append(
            {"type": "core_trait", "id": slot.id, "name": slot.name, "bonus": 1}
        )
        trait_charges_costs.append({"trait_id": slot.id, "cost": 1})

    if role_trait_id is not None:
        slot = _validate_trait_modifier(db, character_id, role_trait_id, "role_trait")
        active_modifiers.append(
            {"type": "role_trait", "id": slot.id, "name": slot.name, "bonus": 1}
        )
        trait_charges_costs.append({"trait_id": slot.id, "cost": 1})

    if bond_id is not None:
        bond_slot = _validate_bond_modifier(db, character_id, bond_id)
        active_modifiers.append(
            {"type": "bond", "id": bond_slot.id, "name": bond_slot.name, "bonus": 1}
        )

    # ------------------------------------------------------------------
    # Plot spend validation
    # ------------------------------------------------------------------
    plot_spend: int = int(selections.get("plot_spend") or 0)
    if plot_spend < 0:
        _raise_422("plot_spend", "plot_spend must be >= 0")
    if (character.plot or 0) < plot_spend:
        _raise_422(
            "plot_spend",
            f"Character has {character.plot or 0} Plot but {plot_spend} was requested",
        )

    # ------------------------------------------------------------------
    # Dice pool
    # Dice pool = skill level + number of active modifiers.
    # Plot spend provides guaranteed 6s, NOT extra dice.
    # ------------------------------------------------------------------
    dice_pool: int = skill_level + len(active_modifiers)

    return {
        "dice_pool": dice_pool,
        "skill": skill,
        "skill_level": skill_level,
        "modifiers": active_modifiers,
        "plot_spend": plot_spend,
        "costs": {
            "trait_charges": trait_charges_costs,
            "plot": plot_spend,
        },
    }


# ---------------------------------------------------------------------------
# Magic action helpers — sacrifice processing and tiered dice conversion
# ---------------------------------------------------------------------------


def _lowest_magic_stat(character: Character) -> int:
    """Return the lowest level across all 5 magic stats for *character*.

    Returns 0 if the character has no magic stats defined.

    Args:
        character: The character whose magic stats are inspected.

    Returns:
        The minimum level value (0–5).
    """
    stats: dict[str, Any] = character.magic_stats or {}
    if not stats:
        return 0
    return min(v.get("level", 0) for v in stats.values())


def _gnosis_equiv_to_sacrifice_dice(total_gnosis: int) -> int:
    """Convert a total Gnosis equivalent to the number of sacrifice dice.

    Uses the triangular-number tiered formula: N dice costs N*(N+1)/2 Gnosis.
    Returns the maximum N such that N*(N+1)/2 <= total_gnosis.

    Args:
        total_gnosis: Total Gnosis equivalent from all sacrifices.

    Returns:
        Number of dice (0 or more).
    """
    if total_gnosis <= 0:
        return 0
    n = 0
    while (n + 1) * (n + 2) // 2 <= total_gnosis:
        n += 1
    return n


def _process_sacrifice_list(
    db: Session,
    character: Character,
    sacrifice: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Process a list of sacrifice entries and return detailed info and cost summary.

    Converts each sacrifice entry to its Gnosis equivalent and builds the
    cost summary.  Raises ``HTTPException(422)`` for any invalid entry
    (missing bond/trait, not owned, not active).  ``"other"`` entries always
    get 0 Gnosis equivalent (GM sets value in overrides).

    Args:
        db: Active SQLAlchemy session.
        character: The character performing the sacrifice.
        sacrifice: A list of dicts, each with ``type`` and optionally ``amount``,
            ``target_id``, ``description``.

    Returns:
        A 2-tuple:
        - ``sacrifice_details``: list of per-entry dicts with ``gnosis_equivalent`` added.
        - ``costs``: summary dict with ``gnosis``, ``stress``, ``free_time``,
          ``bond_sacrifices``, ``trait_sacrifices``.

    Raises:
        HTTPException(422): For invalid sacrifice entries.
    """
    lowest_stat = _lowest_magic_stat(character)
    sacrifice_details: list[dict[str, Any]] = []
    costs: dict[str, Any] = {
        "gnosis": 0,
        "stress": 0,
        "free_time": 0,
        "bond_sacrifices": [],
        "trait_sacrifices": [],
    }

    for entry in sacrifice:
        stype = entry.get("type")

        if stype == "gnosis":
            amount: int = int(entry.get("amount") or 0)
            if amount < 0:
                _raise_422("sacrifice.gnosis", "Gnosis sacrifice amount must be >= 0")
            gnosis_equiv = amount
            costs["gnosis"] += amount
            sacrifice_details.append({
                "type": "gnosis",
                "amount": amount,
                "gnosis_equivalent": gnosis_equiv,
            })

        elif stype == "stress":
            amount = int(entry.get("amount") or 0)
            if amount < 0:
                _raise_422("sacrifice.stress", "Stress sacrifice amount must be >= 0")
            gnosis_equiv = amount * 2
            costs["stress"] += amount
            sacrifice_details.append({
                "type": "stress",
                "amount": amount,
                "gnosis_equivalent": gnosis_equiv,
            })

        elif stype == "free_time":
            amount = int(entry.get("amount") or 0)
            if amount < 0:
                _raise_422("sacrifice.free_time", "Free Time sacrifice amount must be >= 0")
            gnosis_equiv = amount * (3 + lowest_stat)
            costs["free_time"] += amount
            sacrifice_details.append({
                "type": "free_time",
                "amount": amount,
                "gnosis_equivalent": gnosis_equiv,
            })

        elif stype == "bond":
            target_id: str | None = entry.get("target_id")
            if not target_id:
                _raise_422("sacrifice.bond", "Bond sacrifice requires a target_id")
            slot: Slot | None = db.get(Slot, target_id)
            if slot is None:
                _raise_422("sacrifice.bond", f"Bond '{target_id}' not found")
            if slot.owner_id != character.id:
                _raise_422("sacrifice.bond", f"Bond '{target_id}' does not belong to this character")
            if slot.slot_type != "pc_bond":
                _raise_422("sacrifice.bond", f"Slot '{target_id}' is not a pc_bond")
            if not slot.is_active:
                _raise_422("sacrifice.bond", f"Bond '{target_id}' is not active")
            gnosis_equiv = 10
            costs["bond_sacrifices"].append({"bond_id": target_id, "name": slot.name})
            sacrifice_details.append({
                "type": "bond",
                "target_id": target_id,
                "name": slot.name,
                "gnosis_equivalent": gnosis_equiv,
            })

        elif stype == "trait":
            target_id = entry.get("target_id")
            if not target_id:
                _raise_422("sacrifice.trait", "Trait sacrifice requires a target_id")
            slot = db.get(Slot, target_id)
            if slot is None:
                _raise_422("sacrifice.trait", f"Trait '{target_id}' not found")
            if slot.owner_id != character.id:
                _raise_422("sacrifice.trait", f"Trait '{target_id}' does not belong to this character")
            if slot.slot_type not in ("core_trait", "role_trait"):
                _raise_422("sacrifice.trait", f"Slot '{target_id}' is not a core_trait or role_trait")
            if not slot.is_active:
                _raise_422("sacrifice.trait", f"Trait '{target_id}' is not active")
            gnosis_equiv = 10
            costs["trait_sacrifices"].append({"trait_id": target_id, "name": slot.name})
            sacrifice_details.append({
                "type": "trait",
                "target_id": target_id,
                "name": slot.name,
                "gnosis_equivalent": gnosis_equiv,
            })

        elif stype == "other":
            description: str = entry.get("description") or ""
            gnosis_equiv = 0  # GM assigns value in overrides
            sacrifice_details.append({
                "type": "other",
                "description": description,
                "gnosis_equivalent": gnosis_equiv,
            })

        else:
            _raise_422(
                "sacrifice",
                f"Unknown sacrifice type '{stype}'. Must be one of: "
                "gnosis, stress, free_time, bond, trait, other",
            )

    return sacrifice_details, costs


def _validate_magic_modifiers(
    db: Session,
    character_id: str,
    modifiers_input: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Validate the optional modifier entries for a magic action.

    Same stacking rules as ``use_skill``: 1 core trait, 1 role trait, 1 bond.
    Trait modifiers cost 1 charge each; bond modifiers have no charge cost.

    Args:
        db: Active SQLAlchemy session.
        character_id: ULID of the owning character.
        modifiers_input: Dict with optional keys ``core_trait_id``,
            ``role_trait_id``, ``bond_id``.

    Returns:
        A 2-tuple:
        - ``active_modifiers``: list of modifier dicts for ``calculated_effect``.
        - ``trait_charges_costs``: list of ``{trait_id, cost}`` dicts.

    Raises:
        HTTPException(422): For any invalid modifier reference.
    """
    core_trait_id: str | None = modifiers_input.get("core_trait_id")
    role_trait_id: str | None = modifiers_input.get("role_trait_id")
    bond_id: str | None = modifiers_input.get("bond_id")

    active_modifiers: list[dict[str, Any]] = []
    trait_charges_costs: list[dict[str, Any]] = []

    if core_trait_id is not None:
        slot = _validate_trait_modifier(db, character_id, core_trait_id, "core_trait")
        active_modifiers.append(
            {"type": "core_trait", "id": slot.id, "name": slot.name, "bonus": 1}
        )
        trait_charges_costs.append({"trait_id": slot.id, "cost": 1})

    if role_trait_id is not None:
        slot = _validate_trait_modifier(db, character_id, role_trait_id, "role_trait")
        active_modifiers.append(
            {"type": "role_trait", "id": slot.id, "name": slot.name, "bonus": 1}
        )
        trait_charges_costs.append({"trait_id": slot.id, "cost": 1})

    if bond_id is not None:
        bond_slot = _validate_bond_modifier(db, character_id, bond_id)
        active_modifiers.append(
            {"type": "bond", "id": bond_slot.id, "name": bond_slot.name, "bonus": 1}
        )

    return active_modifiers, trait_charges_costs


# ---------------------------------------------------------------------------
# use_magic calculation
# ---------------------------------------------------------------------------


def calculate_use_magic(
    db: Session,
    *,
    character_id: str,
    selections: dict[str, Any],
) -> dict[str, Any]:
    """Validate and compute the ``calculated_effect`` for a ``use_magic`` proposal.

    Validates the suggested stat, sacrifice entries, and optional modifiers.
    Computes total Gnosis equivalent from all sacrifices, converts to sacrifice
    dice via the tiered formula, and builds the full dice pool.

    Args:
        db: Active SQLAlchemy session.
        character_id: ULID of the character submitting the proposal.
        selections: The ``selections`` dict, expected to contain:

            - ``suggested_stat`` (str): one of the 5 canonical magic stat names.
            - ``sacrifice`` (list, optional): sacrifice entries (see spec).
            - ``modifiers`` (dict, optional): ``core_trait_id``, ``role_trait_id``,
              ``bond_id``.
            - ``plot_spend`` (int, optional): number of Plot points to spend
              (default 0).

    Returns:
        A ``calculated_effect`` dict with the shape::

            {
                "suggested_stat": str,
                "stat_level": int,
                "dice_pool": int,
                "sacrifice_dice": int,
                "total_gnosis_equivalent": int,
                "sacrifice_details": [...],
                "modifiers": [...],
                "plot_spend": int,
                "costs": {
                    "gnosis": int,
                    "stress": int,
                    "free_time": int,
                    "bond_sacrifices": [...],
                    "trait_sacrifices": [...],
                    "trait_charges": [...],
                    "plot": int,
                }
            }

    Raises:
        HTTPException(422): For any validation failure.
    """
    suggested_stat: str | None = selections.get("suggested_stat")
    if not suggested_stat:
        _raise_422("suggested_stat", "suggested_stat is required for use_magic proposals")
    if suggested_stat not in CANONICAL_MAGIC_STATS:
        _raise_422(
            "suggested_stat",
            f"suggested_stat must be one of: {sorted(CANONICAL_MAGIC_STATS)}",
        )

    character: Character | None = db.get(Character, character_id)
    if character is None:
        _raise_422("character_id", f"Character '{character_id}' not found")

    stat_level: int = (character.magic_stats or {}).get(suggested_stat, {}).get("level", 0)

    # Process sacrifice entries.
    sacrifice_list: list[dict[str, Any]] = selections.get("sacrifice") or []
    sacrifice_details, costs = _process_sacrifice_list(db, character, sacrifice_list)

    # Total Gnosis equivalent from sacrifice.
    total_gnosis_equiv: int = sum(s["gnosis_equivalent"] for s in sacrifice_details)

    # Convert to sacrifice dice.
    sacrifice_dice: int = _gnosis_equiv_to_sacrifice_dice(total_gnosis_equiv)

    # Validate modifiers.
    modifiers_input: dict[str, Any] = selections.get("modifiers") or {}
    active_modifiers, trait_charges_costs = _validate_magic_modifiers(
        db, character_id, modifiers_input
    )

    # ------------------------------------------------------------------
    # Plot spend validation
    # ------------------------------------------------------------------
    plot_spend: int = int(selections.get("plot_spend") or 0)
    if plot_spend < 0:
        _raise_422("plot_spend", "plot_spend must be >= 0")
    if (character.plot or 0) < plot_spend:
        _raise_422(
            "plot_spend",
            f"Character has {character.plot or 0} Plot but {plot_spend} was requested",
        )

    # Build full dice pool.
    dice_pool: int = stat_level + sacrifice_dice + len(active_modifiers)

    costs["trait_charges"] = trait_charges_costs
    costs["plot"] = plot_spend

    return {
        "suggested_stat": suggested_stat,
        "stat_level": stat_level,
        "dice_pool": dice_pool,
        "sacrifice_dice": sacrifice_dice,
        "total_gnosis_equivalent": total_gnosis_equiv,
        "sacrifice_details": sacrifice_details,
        "modifiers": active_modifiers,
        "plot_spend": plot_spend,
        "costs": costs,
    }


# ---------------------------------------------------------------------------
# charge_magic calculation
# ---------------------------------------------------------------------------


def calculate_charge_magic(
    db: Session,
    *,
    character_id: str,
    selections: dict[str, Any],
) -> dict[str, Any]:
    """Validate and compute the ``calculated_effect`` for a ``charge_magic`` proposal.

    Same structure as ``use_magic`` but also validates the target Magic Effect.
    Only ``charged`` and ``permanent`` effects can be targeted (not ``instant``).

    Args:
        db: Active SQLAlchemy session.
        character_id: ULID of the character submitting the proposal.
        selections: The ``selections`` dict, expected to contain:

            - ``effect_id`` (str): ULID of the target MagicEffect.
            - ``suggested_stat`` (str): one of the 5 canonical magic stat names.
            - ``sacrifice`` (list, optional): sacrifice entries.
            - ``modifiers`` (dict, optional): ``core_trait_id``, ``role_trait_id``,
              ``bond_id``.

    Returns:
        A ``calculated_effect`` dict (same structure as ``use_magic``) plus
        a ``target_effect`` key with ``{id, name, effect_type, power_level,
        charges_current, charges_max}``.

    Raises:
        HTTPException(422): For any validation failure.
    """
    effect_id: str | None = selections.get("effect_id")
    if not effect_id:
        _raise_422("effect_id", "effect_id is required for charge_magic proposals")

    effect: MagicEffect | None = db.get(MagicEffect, effect_id)
    if effect is None:
        _raise_422("effect_id", f"Magic effect '{effect_id}' not found")
    if effect.character_id != character_id:
        _raise_422("effect_id", f"Magic effect '{effect_id}' does not belong to this character")
    if not effect.is_active:
        _raise_422("effect_id", f"Magic effect '{effect_id}' is not active")
    if effect.effect_type not in ("charged", "permanent"):
        _raise_422(
            "effect_id",
            f"Magic effect '{effect_id}' is of type '{effect.effect_type}'; "
            "only charged and permanent effects can be targeted by charge_magic",
        )

    # Use the same core calculation as use_magic.
    base_calc = calculate_use_magic(db, character_id=character_id, selections=selections)

    # Attach target effect details.
    base_calc["target_effect"] = {
        "id": effect.id,
        "name": effect.name,
        "effect_type": effect.effect_type,
        "power_level": effect.power_level,
        "charges_current": effect.charges_current,
        "charges_max": effect.charges_max,
    }

    return base_calc


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _raise_422(field: str, message: str) -> None:
    """Raise an HTTP 422 with a structured validation error.

    Args:
        field: The field name to attribute the error to.
        message: Human-readable error message.

    Raises:
        HTTPException(422): Always.
    """
    raise HTTPException(
        status_code=422,
        detail={
            "error": {
                "code": "validation_error",
                "message": "Validation failed",
                "details": {"fields": {field: message}},
            }
        },
    )


def _validate_trait_modifier(
    db: Session,
    character_id: str,
    trait_id: str,
    expected_slot_type: str,
) -> Slot:
    """Validate a trait modifier for a ``use_skill`` proposal.

    Args:
        db: Active SQLAlchemy session.
        character_id: ULID of the owning character.
        trait_id: ULID of the trait slot to validate.
        expected_slot_type: ``"core_trait"`` or ``"role_trait"``.

    Returns:
        The validated :class:`~wizards_engine.models.slot.Slot`.

    Raises:
        HTTPException(422): If the slot does not exist, does not belong to the
            character, has the wrong slot_type, is inactive, or has 0 charges.
    """
    field = (
        "modifiers.core_trait_id"
        if expected_slot_type == "core_trait"
        else "modifiers.role_trait_id"
    )
    slot: Slot | None = db.get(Slot, trait_id)
    if slot is None:
        _raise_422(field, f"Trait '{trait_id}' not found")
    if slot.owner_id != character_id:
        _raise_422(field, f"Trait '{trait_id}' does not belong to this character")
    if slot.slot_type != expected_slot_type:
        _raise_422(
            field,
            f"Trait '{trait_id}' is a {slot.slot_type}, expected {expected_slot_type}",
        )
    if not slot.is_active:
        _raise_422(field, f"Trait '{trait_id}' is not active")
    if (slot.charge or 0) < 1:
        _raise_422(field, f"Trait '{trait_id}' has 0 charges and cannot be invoked")
    return slot  # type: ignore[return-value]


def _validate_bond_modifier(
    db: Session,
    character_id: str,
    bond_id: str,
) -> Slot:
    """Validate a bond modifier for a ``use_skill`` proposal.

    Bonds provide +1d at no charge cost — only active ``pc_bond`` slots
    are accepted.

    Args:
        db: Active SQLAlchemy session.
        character_id: ULID of the owning character.
        bond_id: ULID of the bond slot to validate.

    Returns:
        The validated :class:`~wizards_engine.models.slot.Slot`.

    Raises:
        HTTPException(422): If the slot does not exist, does not belong to the
            character, is not a ``pc_bond``, or is inactive.
    """
    slot: Slot | None = db.get(Slot, bond_id)
    if slot is None:
        _raise_422("modifiers.bond_id", f"Bond '{bond_id}' not found")
    if slot.owner_id != character_id:
        _raise_422(
            "modifiers.bond_id", f"Bond '{bond_id}' does not belong to this character"
        )
    if slot.slot_type != "pc_bond":
        _raise_422(
            "modifiers.bond_id",
            f"Bond '{bond_id}' is a {slot.slot_type}, expected pc_bond",
        )
    if not slot.is_active:
        _raise_422("modifiers.bond_id", f"Bond '{bond_id}' is not active")
    return slot  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Downtime action calculations
# ---------------------------------------------------------------------------


def _check_free_time(character: Character) -> None:
    """Raise HTTPException(422) if the character has less than 1 Free Time.

    Args:
        character: The Character to check.

    Raises:
        HTTPException(422): If ``character.free_time < 1``.
    """
    if (character.free_time or 0) < 1:
        _raise_422(
            "free_time",
            "Character must have at least 1 Free Time to submit a downtime action",
        )


def calculate_regain_gnosis(
    db: Session,
    character: Character,
    selections: dict[str, Any],
) -> dict[str, Any]:
    """Validate and compute the ``calculated_effect`` for a ``regain_gnosis`` proposal.

    Gnosis gained = 3 + lowest magic stat level + modifier count (max +3 from
    1 core_trait + 1 role_trait + 1 bond modifier).

    Args:
        db: Active SQLAlchemy session.
        character: The character submitting the proposal.
        selections: Expected key: ``modifiers`` (optional dict with
            ``core_trait_id``, ``role_trait_id``, ``bond_id``).

    Returns:
        A ``calculated_effect`` dict::

            {
                "gnosis_gained": int,
                "costs": {
                    "free_time": 1,
                    "trait_charges": [{"trait_id": str, "cost": 1}, ...]
                }
            }

    Raises:
        HTTPException(422): If FT is insufficient or modifier validation fails.
    """
    _check_free_time(character)

    magic_stats: dict[str, Any] = character.magic_stats or {}
    lowest_magic_level: int = min(
        (magic_stats.get(stat) or {}).get("level", 0)
        for stat in MAGIC_STAT_KEYS
    )

    modifiers_input: dict[str, Any] = selections.get("modifiers") or {}
    core_trait_id: str | None = modifiers_input.get("core_trait_id")
    role_trait_id: str | None = modifiers_input.get("role_trait_id")
    bond_id: str | None = modifiers_input.get("bond_id")

    trait_charges_costs: list[dict[str, Any]] = []
    modifier_count: int = 0

    if core_trait_id is not None:
        slot = _validate_trait_modifier(db, character.id, core_trait_id, "core_trait")
        trait_charges_costs.append({"trait_id": slot.id, "cost": 1})
        modifier_count += 1

    if role_trait_id is not None:
        slot = _validate_trait_modifier(db, character.id, role_trait_id, "role_trait")
        trait_charges_costs.append({"trait_id": slot.id, "cost": 1})
        modifier_count += 1

    if bond_id is not None:
        _validate_bond_modifier(db, character.id, bond_id)
        modifier_count += 1

    gnosis_gained: int = 3 + lowest_magic_level + modifier_count

    return {
        "gnosis_gained": gnosis_gained,
        "costs": {
            "free_time": 1,
            "trait_charges": trait_charges_costs,
        },
    }


def calculate_recharge_trait(
    db: Session,
    character: Character,
    selections: dict[str, Any],
) -> dict[str, Any]:
    """Validate and compute the ``calculated_effect`` for a ``recharge_trait`` proposal.

    Args:
        db: Active SQLAlchemy session.
        character: The character submitting the proposal.
        selections: Expected key: ``trait_id`` (str, required).

    Returns:
        A ``calculated_effect`` dict::

            {
                "trait_id": str,
                "charges_restored": 5,
                "costs": {"free_time": 1}
            }

    Raises:
        HTTPException(422): If FT is insufficient, trait_id is missing, the
            trait is not found, not owned by this character, not a core/role
            trait, or is inactive.
    """
    _check_free_time(character)

    trait_id: str | None = selections.get("trait_id")
    if not trait_id:
        _raise_422("trait_id", "trait_id is required for recharge_trait proposals")

    slot: Slot | None = db.get(Slot, trait_id)
    if slot is None:
        _raise_422("trait_id", f"Trait '{trait_id}' not found")
    if slot.owner_id != character.id:
        _raise_422("trait_id", f"Trait '{trait_id}' does not belong to this character")
    if slot.slot_type not in ("core_trait", "role_trait"):
        _raise_422(
            "trait_id",
            f"Trait '{trait_id}' is a {slot.slot_type}, expected core_trait or role_trait",
        )
    if not slot.is_active:
        _raise_422("trait_id", f"Trait '{trait_id}' is not active")

    return {
        "trait_id": slot.id,
        "charges_restored": 5,
        "costs": {"free_time": 1},
    }


def calculate_maintain_bond(
    db: Session,
    character: Character,
    selections: dict[str, Any],
) -> dict[str, Any]:
    """Validate and compute the ``calculated_effect`` for a ``maintain_bond`` proposal.

    Args:
        db: Active SQLAlchemy session.
        character: The character submitting the proposal.
        selections: Expected key: ``bond_id`` (str, required).

    Returns:
        A ``calculated_effect`` dict::

            {
                "bond_id": str,
                "stress_healed": int,
                "costs": {"free_time": 1}
            }

    Raises:
        HTTPException(422): If FT is insufficient, bond_id is missing, the
            bond is not found, not owned by this character, not a pc_bond,
            or is inactive.
    """
    _check_free_time(character)

    bond_id: str | None = selections.get("bond_id")
    if not bond_id:
        _raise_422("bond_id", "bond_id is required for maintain_bond proposals")

    slot: Slot | None = db.get(Slot, bond_id)
    if slot is None:
        _raise_422("bond_id", f"Bond '{bond_id}' not found")
    if slot.owner_id != character.id:
        _raise_422("bond_id", f"Bond '{bond_id}' does not belong to this character")
    if slot.slot_type != "pc_bond":
        _raise_422(
            "bond_id",
            f"Bond '{bond_id}' is a {slot.slot_type}, expected pc_bond",
        )
    if not slot.is_active:
        _raise_422("bond_id", f"Bond '{bond_id}' is not active")

    return {
        "bond_id": slot.id,
        "stress_healed": slot.stress or 0,
        "costs": {"free_time": 1},
    }


def calculate_work_on_project(
    db: Session,
    character: Character,
    selections: dict[str, Any],
) -> dict[str, Any]:
    """Validate and compute the ``calculated_effect`` for a ``work_on_project`` proposal.

    Args:
        db: Active SQLAlchemy session.
        character: The character submitting the proposal.
        selections: Expected keys: ``story_id`` (str, required),
            ``entry_text`` (str, required).

    Returns:
        A ``calculated_effect`` dict::

            {
                "story_id": str,
                "costs": {"free_time": 1}
            }

    Raises:
        HTTPException(422): If FT is insufficient, story_id or entry_text
            are missing, or the story does not exist.
    """
    from wizards_engine.models.story import Story  # noqa: PLC0415

    _check_free_time(character)

    story_id: str | None = selections.get("story_id")
    if not story_id:
        _raise_422("story_id", "story_id is required for work_on_project proposals")

    entry_text: str | None = selections.get("entry_text")
    if not entry_text:
        _raise_422("entry_text", "entry_text is required for work_on_project proposals")

    story = db.get(Story, story_id)
    if story is None or story.is_deleted:
        _raise_422("story_id", f"Story '{story_id}' not found")

    return {
        "story_id": story_id,
        "entry_text": entry_text,
        "costs": {"free_time": 1},
    }


def calculate_rest(
    db: Session,
    character: Character,
    selections: dict[str, Any],
) -> dict[str, Any]:
    """Validate and compute the ``calculated_effect`` for a ``rest`` proposal.

    Stress healed = 3 + modifier count (max +3 from 1 core_trait + 1 role_trait
    + 1 bond modifier).

    Args:
        db: Active SQLAlchemy session.
        character: The character submitting the proposal.
        selections: Expected key: ``modifiers`` (optional dict with
            ``core_trait_id``, ``role_trait_id``, ``bond_id``).

    Returns:
        A ``calculated_effect`` dict::

            {
                "stress_healed": int,
                "costs": {
                    "free_time": 1,
                    "trait_charges": [{"trait_id": str, "cost": 1}, ...]
                }
            }

    Raises:
        HTTPException(422): If FT is insufficient or modifier validation fails.
    """
    _check_free_time(character)

    modifiers_input: dict[str, Any] = selections.get("modifiers") or {}
    core_trait_id: str | None = modifiers_input.get("core_trait_id")
    role_trait_id: str | None = modifiers_input.get("role_trait_id")
    bond_id: str | None = modifiers_input.get("bond_id")

    trait_charges_costs: list[dict[str, Any]] = []
    modifier_count: int = 0

    if core_trait_id is not None:
        slot = _validate_trait_modifier(db, character.id, core_trait_id, "core_trait")
        trait_charges_costs.append({"trait_id": slot.id, "cost": 1})
        modifier_count += 1

    if role_trait_id is not None:
        slot = _validate_trait_modifier(db, character.id, role_trait_id, "role_trait")
        trait_charges_costs.append({"trait_id": slot.id, "cost": 1})
        modifier_count += 1

    if bond_id is not None:
        _validate_bond_modifier(db, character.id, bond_id)
        modifier_count += 1

    stress_healed: int = 3 + modifier_count

    return {
        "stress_healed": stress_healed,
        "costs": {
            "free_time": 1,
            "trait_charges": trait_charges_costs,
        },
    }


def calculate_new_trait(
    db: Session,
    character: Character,
    selections: dict[str, Any],
) -> dict[str, Any]:
    """Validate and compute the ``calculated_effect`` for a ``new_trait`` proposal.

    Either ``template_id`` or both ``proposed_name`` + ``proposed_description``
    must be provided.  If at the active-count limit for the given slot_type,
    ``retire_trait_id`` is required.

    Args:
        db: Active SQLAlchemy session.
        character: The character submitting the proposal.
        selections: Expected keys:

            - ``slot_type`` (str, required): ``"core_trait"`` or ``"role_trait"``.
            - ``template_id`` (str, optional): ULID of an existing TraitTemplate.
            - ``proposed_name`` (str, optional): Name for a new catalog entry.
            - ``proposed_description`` (str, optional): Description for new
              catalog entry. Required when ``proposed_name`` is provided.
            - ``retire_trait_id`` (str, optional): ULID of active trait to
              retire. Required when at the slot limit.

    Returns:
        A ``calculated_effect`` dict::

            {
                "slot_type": str,
                "template_id": str | None,
                "proposed_name": str | None,
                "proposed_description": str | None,
                "retire_trait_id": str | None,
                "costs": {"free_time": 1}
            }

    Raises:
        HTTPException(422): If FT is insufficient, slot_type is invalid,
            template/name validation fails, or retire_trait_id is missing when
            required.
    """
    _check_free_time(character)

    slot_type: str | None = selections.get("slot_type")
    if slot_type not in ("core_trait", "role_trait"):
        _raise_422("slot_type", "slot_type must be 'core_trait' or 'role_trait'")

    template_id: str | None = selections.get("template_id")
    proposed_name: str | None = selections.get("proposed_name")
    proposed_description: str | None = selections.get("proposed_description")
    retire_trait_id: str | None = selections.get("retire_trait_id")

    # Either template_id or proposed_name+description must be provided.
    if template_id is None and not proposed_name:
        _raise_422(
            "template_id",
            "Either template_id or proposed_name + proposed_description must be provided",
        )
    if proposed_name and not proposed_description:
        _raise_422(
            "proposed_description",
            "proposed_description is required when proposed_name is provided",
        )

    # Validate template if provided.
    if template_id is not None:
        tmpl: TraitTemplate | None = db.get(TraitTemplate, template_id)
        if tmpl is None or tmpl.is_deleted:
            _raise_422("template_id", f"Trait template '{template_id}' not found")
        required_type = "core" if slot_type == "core_trait" else "role"
        if tmpl.type != required_type:
            _raise_422(
                "template_id",
                f"Template '{template_id}' has type '{tmpl.type}', "
                f"but slot_type '{slot_type}' requires a '{required_type}' template",
            )

    # Check active slot count to determine if retirement is required.
    limit: int = TRAIT_LIMITS[slot_type]  # type: ignore[index]
    active_nt_stmt = select(Slot).where(
        and_(
            Slot.owner_type == "character",
            Slot.owner_id == character.id,
            Slot.slot_type == slot_type,
            Slot.is_active.is_(True),
        )
    )
    active_count: int = len(db.execute(active_nt_stmt).scalars().all())

    if active_count >= limit and retire_trait_id is None:
        _raise_422(
            "retire_trait_id",
            f"Character is at the {slot_type} limit ({limit}). "
            "retire_trait_id is required to retire an existing trait.",
        )

    # Validate retire_trait_id if provided.
    if retire_trait_id is not None:
        rslot: Slot | None = db.get(Slot, retire_trait_id)
        if rslot is None:
            _raise_422("retire_trait_id", f"Trait '{retire_trait_id}' not found")
        if rslot.owner_id != character.id:
            _raise_422(
                "retire_trait_id",
                f"Trait '{retire_trait_id}' does not belong to this character",
            )
        if not rslot.is_active:
            _raise_422("retire_trait_id", f"Trait '{retire_trait_id}' is not active")
        if rslot.slot_type != slot_type:
            _raise_422(
                "retire_trait_id",
                f"Trait '{retire_trait_id}' is a {rslot.slot_type}, "
                f"expected {slot_type}",
            )

    return {
        "slot_type": slot_type,
        "template_id": template_id,
        "proposed_name": proposed_name,
        "proposed_description": proposed_description,
        "retire_trait_id": retire_trait_id,
        "costs": {"free_time": 1},
    }


def calculate_new_bond(
    db: Session,
    character: Character,
    selections: dict[str, Any],
) -> dict[str, Any]:
    """Validate and compute the ``calculated_effect`` for a ``new_bond`` proposal.

    Args:
        db: Active SQLAlchemy session.
        character: The character submitting the proposal.
        selections: Expected keys:

            - ``target_type`` (str, required): ``"character"``, ``"group"``,
              or ``"location"``.
            - ``target_id`` (str, required): ULID of the target Game Object.
            - ``retire_bond_id`` (str, optional): ULID of active pc_bond to
              retire. Required when at the 8-bond limit.

    Returns:
        A ``calculated_effect`` dict::

            {
                "target_type": str,
                "target_id": str,
                "retire_bond_id": str | None,
                "costs": {"free_time": 1}
            }

    Raises:
        HTTPException(422): If FT is insufficient, target is not found,
            duplicate active bond exists, or retire_bond_id is missing when
            required.
    """
    from wizards_engine.models.group import Group  # noqa: PLC0415
    from wizards_engine.models.location import Location  # noqa: PLC0415

    _check_free_time(character)

    target_type: str | None = selections.get("target_type")
    target_id: str | None = selections.get("target_id")
    retire_bond_id: str | None = selections.get("retire_bond_id")

    if not target_type:
        _raise_422("target_type", "target_type is required for new_bond proposals")
    if not target_id:
        _raise_422("target_id", "target_id is required for new_bond proposals")

    _nb_model_map: dict[str, type] = {
        "character": Character,
        "group": Group,
        "location": Location,
    }
    model_cls = _nb_model_map.get(target_type)
    if model_cls is None:
        _raise_422(
            "target_type",
            f"target_type must be 'character', 'group', or 'location', got '{target_type}'",
        )

    target_obj = db.get(model_cls, target_id)
    if target_obj is None or getattr(target_obj, "is_deleted", False):
        _raise_422("target_id", f"{target_type.capitalize()} '{target_id}' not found")

    # No duplicate active bond to same target.
    dup_stmt = select(Slot).where(
        and_(
            Slot.owner_type == "character",
            Slot.owner_id == character.id,
            Slot.target_type == target_type,
            Slot.target_id == target_id,
            Slot.is_active.is_(True),
        )
    )
    if db.execute(dup_stmt).scalars().first() is not None:
        _raise_422(
            "target_id",
            f"Character already has an active bond to {target_type} '{target_id}'",
        )

    # Check active pc_bond count.
    nb_count_stmt = select(Slot).where(
        and_(
            Slot.owner_type == "character",
            Slot.owner_id == character.id,
            Slot.slot_type == "pc_bond",
            Slot.is_active.is_(True),
        )
    )
    active_bond_count: int = len(db.execute(nb_count_stmt).scalars().all())

    if active_bond_count >= PC_BOND_LIMIT and retire_bond_id is None:
        _raise_422(
            "retire_bond_id",
            f"Character is at the pc_bond limit ({PC_BOND_LIMIT}). "
            "retire_bond_id is required to retire an existing bond.",
        )

    # Validate retire_bond_id if provided.
    if retire_bond_id is not None:
        rb_slot: Slot | None = db.get(Slot, retire_bond_id)
        if rb_slot is None:
            _raise_422("retire_bond_id", f"Bond '{retire_bond_id}' not found")
        if rb_slot.owner_id != character.id:
            _raise_422(
                "retire_bond_id",
                f"Bond '{retire_bond_id}' does not belong to this character",
            )
        if not rb_slot.is_active:
            _raise_422("retire_bond_id", f"Bond '{retire_bond_id}' is not active")
        if rb_slot.slot_type != "pc_bond":
            _raise_422(
                "retire_bond_id",
                f"Bond '{retire_bond_id}' is a {rb_slot.slot_type}, expected pc_bond",
            )
        if rb_slot.is_trauma:
            _raise_422("retire_bond_id", "Cannot retire a trauma bond")

    return {
        "target_type": target_type,
        "target_id": target_id,
        "retire_bond_id": retire_bond_id,
        "costs": {"free_time": 1},
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_proposal(
    db: Session,
    *,
    character_id: str,
    action_type: str,
    narrative: str | None,
    selections: dict[str, Any],
    actor_id: str,
) -> Proposal:
    """Create a new player-submitted proposal in ``pending`` status.

    For ``use_skill`` proposals, computes and stores the ``calculated_effect``
    immediately.  For all other action types, ``calculated_effect`` is set to
    ``{}`` (deferred to later stories).

    Args:
        db: Active SQLAlchemy session.
        character_id: ULID of the submitting character.
        action_type: One of the 10 player-submittable action types.
        narrative: Player-written description of the intended action.  May be
            ``None`` for session action types (``use_skill``, ``use_magic``,
            ``charge_magic``).
        selections: Type-specific input dict (validated at the API layer).
        actor_id: ULID of the authenticated user (for event creation).

    Returns:
        The newly created and flushed :class:`~wizards_engine.models.proposal.Proposal`
        instance.
    """
    calculated_effect: dict[str, Any] = {}
    if action_type == "use_skill":
        calculated_effect = calculate_use_skill(
            db, character_id=character_id, selections=selections
        )
    elif action_type == "use_magic":
        calculated_effect = calculate_use_magic(
            db, character_id=character_id, selections=selections
        )
    elif action_type == "charge_magic":
        calculated_effect = calculate_charge_magic(
            db, character_id=character_id, selections=selections
        )
    elif action_type in DOWNTIME_ACTION_TYPES:
        character: Character | None = db.get(Character, character_id)
        if character is not None:
            if action_type == "regain_gnosis":
                calculated_effect = calculate_regain_gnosis(db, character, selections)
            elif action_type == "recharge_trait":
                calculated_effect = calculate_recharge_trait(db, character, selections)
            elif action_type == "maintain_bond":
                calculated_effect = calculate_maintain_bond(db, character, selections)
            elif action_type == "work_on_project":
                calculated_effect = calculate_work_on_project(db, character, selections)
            elif action_type == "rest":
                calculated_effect = calculate_rest(db, character, selections)
            elif action_type == "new_trait":
                calculated_effect = calculate_new_trait(db, character, selections)
            elif action_type == "new_bond":
                calculated_effect = calculate_new_bond(db, character, selections)

    proposal = Proposal(
        character_id=character_id,
        action_type=action_type,
        origin="player",
        narrative=narrative,
        selections=selections,
        calculated_effect=calculated_effect,
        status="pending",
    )
    db.add(proposal)
    db.flush()
    db.refresh(proposal)
    return proposal


def get_proposal(db: Session, proposal_id: str) -> Proposal | None:
    """Retrieve a single proposal by ULID, or ``None`` if not found.

    Args:
        db: Active SQLAlchemy session.
        proposal_id: ULID of the proposal to retrieve.

    Returns:
        The :class:`~wizards_engine.models.proposal.Proposal` instance,
        or ``None`` if no row exists with that ID.
    """
    return db.get(Proposal, proposal_id)


def list_proposals_query(
    db: Session,
    *,
    character_id: str | None = None,
    status: str | None = None,
    action_type: str | None = None,
    owner_character_id: str | None = None,
):
    """Build a SQLAlchemy select query for proposals with optional filters.

    Does not execute the query.  The caller is responsible for applying
    pagination and executing.

    Args:
        db: Active SQLAlchemy session (unused here but kept for consistency).
        character_id: Optional filter — only proposals for this character ULID.
        status: Optional filter — ``"pending"``, ``"approved"``, or ``"rejected"``.
        action_type: Optional filter — exact match on action_type.
        owner_character_id: When set, restricts results to proposals whose
            ``character_id`` matches this value.  Used to enforce player
            visibility (players see only their own proposals).  When a
            ``character_id`` filter is also provided and it does not match
            ``owner_character_id``, the result will be empty (the player can
            only query their own proposals).

    Returns:
        A SQLAlchemy ``Select`` statement ready for pagination.
    """
    q = select(Proposal)

    # Ownership restriction: players can only see their own proposals.
    if owner_character_id is not None:
        q = q.where(Proposal.character_id == owner_character_id)
    # Explicit character_id filter: only applied when there is no ownership
    # restriction (i.e., GM callers).
    elif character_id is not None:
        q = q.where(Proposal.character_id == character_id)

    if status is not None:
        q = q.where(Proposal.status == status)

    if action_type is not None:
        q = q.where(Proposal.action_type == action_type)

    return q


def update_proposal(
    db: Session,
    proposal: Proposal,
    *,
    narrative: str | None = None,
    selections: dict[str, Any] | None = None,
    actor_id: str,
    actor_type: str,
) -> Proposal:
    """Apply a partial update to a proposal.

    If the proposal was previously ``rejected``, changes its status back to
    ``pending`` and creates a ``proposal.revised`` event with ``private``
    visibility.

    Args:
        db: Active SQLAlchemy session.
        proposal: The :class:`~wizards_engine.models.proposal.Proposal` to update.
        narrative: New narrative text.  ``None`` leaves the field unchanged.
        selections: New selections dict.  ``None`` leaves the field unchanged.
        actor_id: ULID of the user performing the update.
        actor_type: ``"player"`` or ``"gm"``.

    Returns:
        The updated and refreshed Proposal instance.
    """
    was_rejected = proposal.status == "rejected"

    if narrative is not None:
        proposal.narrative = narrative

    if selections is not None:
        proposal.selections = selections

    # Recalculate effect whenever selections change (or on revision).
    if proposal.action_type == "use_skill" and (
        selections is not None or was_rejected
    ):
        proposal.calculated_effect = calculate_use_skill(
            db,
            character_id=proposal.character_id,
            selections=proposal.selections,
        )
    elif proposal.action_type == "use_magic" and (
        selections is not None or was_rejected
    ):
        proposal.calculated_effect = calculate_use_magic(
            db,
            character_id=proposal.character_id,
            selections=proposal.selections,
        )
    elif proposal.action_type == "charge_magic" and (
        selections is not None or was_rejected
    ):
        proposal.calculated_effect = calculate_charge_magic(
            db,
            character_id=proposal.character_id,
            selections=proposal.selections,
        )
    elif proposal.action_type in DOWNTIME_ACTION_TYPES and (
        selections is not None or was_rejected
    ):
        dt_character: Character | None = db.get(Character, proposal.character_id)
        if dt_character is not None:
            if proposal.action_type == "regain_gnosis":
                proposal.calculated_effect = calculate_regain_gnosis(
                    db, dt_character, proposal.selections
                )
            elif proposal.action_type == "recharge_trait":
                proposal.calculated_effect = calculate_recharge_trait(
                    db, dt_character, proposal.selections
                )
            elif proposal.action_type == "maintain_bond":
                proposal.calculated_effect = calculate_maintain_bond(
                    db, dt_character, proposal.selections
                )
            elif proposal.action_type == "work_on_project":
                proposal.calculated_effect = calculate_work_on_project(
                    db, dt_character, proposal.selections
                )
            elif proposal.action_type == "rest":
                proposal.calculated_effect = calculate_rest(
                    db, dt_character, proposal.selections
                )
            elif proposal.action_type == "new_trait":
                proposal.calculated_effect = calculate_new_trait(
                    db, dt_character, proposal.selections
                )
            elif proposal.action_type == "new_bond":
                proposal.calculated_effect = calculate_new_bond(
                    db, dt_character, proposal.selections
                )

    if was_rejected:
        proposal.status = "pending"

    db.flush()

    if was_rejected:
        revised_targets: list[dict] = []
        if proposal.character_id is not None:
            revised_targets = [
                {
                    "target_type": "character",
                    "target_id": proposal.character_id,
                    "is_primary": True,
                }
            ]
        create_event(
            db,
            type="proposal.revised",
            actor_type=actor_type,
            actor_id=actor_id,
            visibility="private",
            proposal_id=proposal.id,
            targets=revised_targets,
        )

    db.refresh(proposal)
    return proposal


def delete_proposal(db: Session, proposal: Proposal) -> None:
    """Hard-delete a proposal from the database.

    Args:
        db: Active SQLAlchemy session.
        proposal: The :class:`~wizards_engine.models.proposal.Proposal` to delete.

    Returns:
        ``None``.
    """
    db.delete(proposal)
    db.flush()


# ---------------------------------------------------------------------------
# Approval helpers — action-type-specific resource deduction
# ---------------------------------------------------------------------------


def _apply_use_skill(
    db: Session,
    character: Character,
    effective_effect: dict[str, Any],
    gm_overrides: dict[str, Any],
) -> dict[str, Any]:
    """Deduct resources for a ``use_skill`` approval and return the changes dict.

    Deducts trait charges for each trait modifier and deducts Plot if a
    ``plot_spend`` was recorded.  If ``gm_overrides["bond_strained"]`` is
    ``True``, adds +1 stress to the modifier bond and handles the
    stress-at-max boundary (reset + increment degradations).

    Args:
        db: Active SQLAlchemy session.
        character: The character whose resources are deducted.
        effective_effect: The final ``calculated_effect`` after GM overrides
            have been merged in.
        gm_overrides: The raw GM overrides dict from the request.

    Returns:
        A ``changes`` dict keyed by fully-qualified change keys (e.g.
        ``"slot.<id>.charge"``) with ``{op, before, after}`` entries.
    """
    changes: dict[str, Any] = {}
    costs: dict[str, Any] = effective_effect.get("costs") or {}

    # ------------------------------------------------------------------
    # Trait charge deductions
    # ------------------------------------------------------------------
    for charge_cost in costs.get("trait_charges") or []:
        trait_id: str = charge_cost["trait_id"]
        slot: Slot | None = db.get(Slot, trait_id)
        if slot is not None:
            before = slot.charge or 0
            after = max(0, before - 1)
            slot.charge = after
            changes[f"slot.{slot.id}.charge"] = {
                "op": "meter.delta",
                "before": before,
                "after": after,
            }
    db.flush()

    # ------------------------------------------------------------------
    # Plot deduction
    # ------------------------------------------------------------------
    plot_cost: int = int(costs.get("plot") or 0)
    if plot_cost > 0:
        before_plot = character.plot or 0
        after_plot = max(0, before_plot - plot_cost)
        character.plot = after_plot
        changes[f"character.{character.id}.plot"] = {
            "op": "meter.delta",
            "before": before_plot,
            "after": after_plot,
        }
        db.flush()

    # ------------------------------------------------------------------
    # Bond strain (optional, GM flag)
    # ------------------------------------------------------------------
    bond_strained: bool = bool((gm_overrides or {}).get("bond_strained", False))
    if bond_strained:
        # Find the bond modifier from the effect modifiers list.
        bond_mod = next(
            (m for m in (effective_effect.get("modifiers") or []) if m["type"] == "bond"),
            None,
        )
        if bond_mod is not None:
            bond_slot: Slot | None = db.get(Slot, bond_mod["id"])
            if bond_slot is not None:
                degradations: int = bond_slot.stress_degradations or 0
                max_stress: int = 5 - degradations
                before_stress = bond_slot.stress or 0
                new_stress = before_stress + 1

                if new_stress >= max_stress:
                    # Hit the boundary: reset stress, increment degradations.
                    bond_slot.stress = 0
                    bond_slot.stress_degradations = degradations + 1
                    changes[f"slot.{bond_slot.id}.stress"] = {
                        "op": "meter.set",
                        "before": before_stress,
                        "after": 0,
                    }
                    changes[f"slot.{bond_slot.id}.stress_degradations"] = {
                        "op": "meter.delta",
                        "before": degradations,
                        "after": degradations + 1,
                    }
                else:
                    bond_slot.stress = new_stress
                    changes[f"slot.{bond_slot.id}.stress"] = {
                        "op": "meter.delta",
                        "before": before_stress,
                        "after": new_stress,
                    }
                db.flush()

    return changes


def _count_trauma_bonds(db: Session, character_id: str) -> int:
    """Return the count of active trauma bonds for a character.

    Mirrors the helper in :mod:`wizards_engine.services.gm_actions`.

    Args:
        db: Active SQLAlchemy session.
        character_id: ULID of the character to inspect.

    Returns:
        Number of active trauma bonds (``pc_bond`` slots with ``is_trauma=True``).
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


def _has_pending_resolve_trauma(db: Session, character_id: str) -> bool:
    """Return ``True`` if a pending ``resolve_trauma`` proposal already exists.

    Used for idempotency — only one pending trauma proposal per character.

    Args:
        db: Active SQLAlchemy session.
        character_id: ULID of the character to check.

    Returns:
        ``True`` if a pending ``resolve_trauma`` proposal exists.
    """
    result = db.scalars(
        select(Proposal).where(
            Proposal.character_id == character_id,
            Proposal.action_type == "resolve_trauma",
            Proposal.status == "pending",
        )
    ).first()
    return result is not None


def _apply_sacrifice_resources(
    db: Session,
    character: Character,
    effective_effect: dict[str, Any],
    approval_event_id: str,
    changes: dict[str, Any],
) -> None:
    """Apply all sacrifice-based resource deductions for a magic action approval.

    Deducts Gnosis, applies Stress, deducts Free Time, retires sacrificed
    bonds/traits, and deducts trait modifier charges.  If Stress sacrifice
    pushes the character to their effective stress max, a ``resolve_trauma``
    proposal is auto-generated (idempotent) and a rider event is created.

    Mutates *character* and *changes* in-place.

    Args:
        db: Active SQLAlchemy session.
        character: The character whose resources are deducted.
        effective_effect: The final ``calculated_effect`` (after GM overrides).
        approval_event_id: ID of the parent approval event (for rider events).
        changes: The changes dict to populate with before/after records.
    """
    costs: dict[str, Any] = effective_effect.get("costs") or {}

    # ------------------------------------------------------------------
    # Gnosis deduction
    # ------------------------------------------------------------------
    gnosis_cost: int = int(costs.get("gnosis") or 0)
    if gnosis_cost > 0:
        before_gnosis = character.gnosis or 0
        after_gnosis = max(0, before_gnosis - gnosis_cost)
        character.gnosis = after_gnosis
        changes[f"character.{character.id}.gnosis"] = {
            "op": "meter.delta",
            "before": before_gnosis,
            "after": after_gnosis,
        }
        db.flush()

    # ------------------------------------------------------------------
    # Stress sacrifice
    # ------------------------------------------------------------------
    stress_cost: int = int(costs.get("stress") or 0)
    if stress_cost > 0:
        trauma_count = _count_trauma_bonds(db, character.id)
        effective_max = 9 - trauma_count
        before_stress = character.stress or 0
        new_stress = before_stress + stress_cost
        clamped = new_stress >= effective_max
        after_stress = min(new_stress, effective_max)
        character.stress = after_stress
        stress_entry: dict[str, Any] = {
            "op": "meter.delta",
            "before": before_stress,
            "after": after_stress,
        }
        if clamped:
            stress_entry["clamped"] = True
        changes[f"character.{character.id}.stress"] = stress_entry
        db.flush()

        # Auto-generate resolve_trauma proposal if stress hits effective max.
        if after_stress >= effective_max and not _has_pending_resolve_trauma(db, character.id):
            trauma_proposal = Proposal(
                character_id=character.id,
                action_type="resolve_trauma",
                origin="system",
                narrative="",
                selections={},
                status="pending",
            )
            db.add(trauma_proposal)
            db.flush()
            create_event(
                db,
                type="character.resolve_trauma_generated",
                actor_type="system",
                actor_id=None,
                changes={},
                visibility="silent",
                parent_event_id=approval_event_id,
                targets=[
                    {
                        "target_type": "character",
                        "target_id": character.id,
                        "is_primary": True,
                    }
                ],
                metadata={"proposal_id": trauma_proposal.id},
            )

    # ------------------------------------------------------------------
    # Free Time deduction
    # ------------------------------------------------------------------
    ft_cost: int = int(costs.get("free_time") or 0)
    if ft_cost > 0:
        before_ft = character.free_time or 0
        after_ft = max(0, before_ft - ft_cost)
        character.free_time = after_ft
        changes[f"character.{character.id}.free_time"] = {
            "op": "meter.delta",
            "before": before_ft,
            "after": after_ft,
        }
        db.flush()

    # ------------------------------------------------------------------
    # Trait modifier charge deductions
    # ------------------------------------------------------------------
    for charge_cost in costs.get("trait_charges") or []:
        trait_id: str = charge_cost["trait_id"]
        slot: Slot | None = db.get(Slot, trait_id)
        if slot is not None:
            before = slot.charge or 0
            after = max(0, before - 1)
            slot.charge = after
            changes[f"slot.{slot.id}.charge"] = {
                "op": "meter.delta",
                "before": before,
                "after": after,
            }
    db.flush()

    # ------------------------------------------------------------------
    # Bond sacrifices — retire (set is_active = False)
    # ------------------------------------------------------------------
    for bond_sac in costs.get("bond_sacrifices") or []:
        bond_id: str = bond_sac["bond_id"]
        bond_slot: Slot | None = db.get(Slot, bond_id)
        if bond_slot is not None and bond_slot.is_active:
            bond_slot.is_active = False
            changes[f"slot.{bond_slot.id}.is_active"] = {
                "op": "field.set",
                "before": True,
                "after": False,
            }
    db.flush()

    # ------------------------------------------------------------------
    # Trait sacrifices — retire (set is_active = False)
    # ------------------------------------------------------------------
    for trait_sac in costs.get("trait_sacrifices") or []:
        trait_id = trait_sac["trait_id"]
        trait_slot: Slot | None = db.get(Slot, trait_id)
        if trait_slot is not None and trait_slot.is_active:
            trait_slot.is_active = False
            changes[f"slot.{trait_slot.id}.is_active"] = {
                "op": "field.set",
                "before": True,
                "after": False,
            }
    db.flush()


def _apply_use_magic(
    db: Session,
    character: Character,
    effective_effect: dict[str, Any],
    gm_overrides: dict[str, Any],
) -> dict[str, Any]:
    """Deduct resources for a ``use_magic`` approval and return the changes dict.

    Applies all sacrifice costs (Gnosis, Stress, Free Time, bond/trait
    retirements) and modifier trait charges.  If Stress sacrifice pushes the
    character to their effective stress max, a ``resolve_trauma`` proposal is
    auto-generated.  If ``gm_overrides["effect_details"]`` is provided, creates
    a new MagicEffect on the character's sheet.

    Args:
        db: Active SQLAlchemy session.
        character: The character whose resources are deducted.
        effective_effect: The final ``calculated_effect`` after GM overrides.
        gm_overrides: The raw GM overrides dict.  Recognised keys:
            ``effect_details`` (dict) — fields for a new MagicEffect to create.

    Returns:
        A ``changes`` dict keyed by fully-qualified change keys.
    """
    changes: dict[str, Any] = {}

    # We need the approval event ID to attach rider events; use a sentinel for
    # now — the actual ID is injected after the approval event is created.
    # The handler is called before event creation, so we pass None and the
    # caller attaches rider events independently.  To work around this, we
    # use the pattern established by gm_actions: pass the parent_event_id
    # after the fact.  For stress sacrifice, the rider event is deferred to
    # a post-approval step.

    # Sacrifice resource deductions (no approval_event_id available here;
    # stress boundary rider is created in the post-apply step).
    costs: dict[str, Any] = effective_effect.get("costs") or {}

    # Gnosis
    gnosis_cost: int = int(costs.get("gnosis") or 0)
    if gnosis_cost > 0:
        before_gnosis = character.gnosis or 0
        after_gnosis = max(0, before_gnosis - gnosis_cost)
        character.gnosis = after_gnosis
        changes[f"character.{character.id}.gnosis"] = {
            "op": "meter.delta",
            "before": before_gnosis,
            "after": after_gnosis,
        }
        db.flush()

    # Stress
    stress_cost: int = int(costs.get("stress") or 0)
    if stress_cost > 0:
        trauma_count = _count_trauma_bonds(db, character.id)
        effective_max = 9 - trauma_count
        before_stress = character.stress or 0
        new_stress = before_stress + stress_cost
        after_stress = min(new_stress, effective_max)
        stress_entry: dict[str, Any] = {
            "op": "meter.delta",
            "before": before_stress,
            "after": after_stress,
        }
        if new_stress >= effective_max:
            stress_entry["clamped"] = True
        character.stress = after_stress
        changes[f"character.{character.id}.stress"] = stress_entry
        db.flush()

    # Free Time
    ft_cost: int = int(costs.get("free_time") or 0)
    if ft_cost > 0:
        before_ft = character.free_time or 0
        after_ft = max(0, before_ft - ft_cost)
        character.free_time = after_ft
        changes[f"character.{character.id}.free_time"] = {
            "op": "meter.delta",
            "before": before_ft,
            "after": after_ft,
        }
        db.flush()

    # Trait modifier charge deductions
    for charge_cost in costs.get("trait_charges") or []:
        trait_id: str = charge_cost["trait_id"]
        slot: Slot | None = db.get(Slot, trait_id)
        if slot is not None:
            before = slot.charge or 0
            after = max(0, before - 1)
            slot.charge = after
            changes[f"slot.{slot.id}.charge"] = {
                "op": "meter.delta",
                "before": before,
                "after": after,
            }
    db.flush()

    # ------------------------------------------------------------------
    # Plot deduction
    # ------------------------------------------------------------------
    plot_cost: int = int(costs.get("plot") or 0)
    if plot_cost > 0:
        before_plot = character.plot or 0
        after_plot = max(0, before_plot - plot_cost)
        character.plot = after_plot
        changes[f"character.{character.id}.plot"] = {
            "op": "meter.delta",
            "before": before_plot,
            "after": after_plot,
        }
        db.flush()

    # ------------------------------------------------------------------
    # Bond strain (optional, GM flag)
    # ------------------------------------------------------------------
    bond_strained: bool = bool((gm_overrides or {}).get("bond_strained", False))
    if bond_strained:
        bond_mod = next(
            (m for m in (effective_effect.get("modifiers") or []) if m["type"] == "bond"),
            None,
        )
        if bond_mod is not None:
            bond_slot_s: Slot | None = db.get(Slot, bond_mod["id"])
            if bond_slot_s is not None:
                degradations_s: int = bond_slot_s.stress_degradations or 0
                max_stress_s: int = 5 - degradations_s
                before_stress_s = bond_slot_s.stress or 0
                new_stress_s = before_stress_s + 1

                if new_stress_s >= max_stress_s:
                    bond_slot_s.stress = 0
                    bond_slot_s.stress_degradations = degradations_s + 1
                    changes[f"slot.{bond_slot_s.id}.stress"] = {
                        "op": "meter.set",
                        "before": before_stress_s,
                        "after": 0,
                    }
                    changes[f"slot.{bond_slot_s.id}.stress_degradations"] = {
                        "op": "meter.delta",
                        "before": degradations_s,
                        "after": degradations_s + 1,
                    }
                else:
                    bond_slot_s.stress = new_stress_s
                    changes[f"slot.{bond_slot_s.id}.stress"] = {
                        "op": "meter.delta",
                        "before": before_stress_s,
                        "after": new_stress_s,
                    }
                db.flush()

    # Bond sacrifices — retire
    for bond_sac in costs.get("bond_sacrifices") or []:
        bond_id: str = bond_sac["bond_id"]
        bond_slot: Slot | None = db.get(Slot, bond_id)
        if bond_slot is not None and bond_slot.is_active:
            bond_slot.is_active = False
            changes[f"slot.{bond_slot.id}.is_active"] = {
                "op": "field.set",
                "before": True,
                "after": False,
            }
    db.flush()

    # Trait sacrifices — retire
    for trait_sac in costs.get("trait_sacrifices") or []:
        trait_id = trait_sac["trait_id"]
        trait_slot: Slot | None = db.get(Slot, trait_id)
        if trait_slot is not None and trait_slot.is_active:
            trait_slot.is_active = False
            changes[f"slot.{trait_slot.id}.is_active"] = {
                "op": "field.set",
                "before": True,
                "after": False,
            }
    db.flush()

    # ------------------------------------------------------------------
    # Create MagicEffect if GM provided effect_details
    # ------------------------------------------------------------------
    effect_details: dict[str, Any] | None = (gm_overrides or {}).get("effect_details")
    if effect_details:
        try:
            new_effect = _create_magic_effect(
                db,
                character_id=character.id,
                name=effect_details.get("name", ""),
                description=effect_details.get("description", ""),
                effect_type=effect_details.get("effect_type", "instant"),
                power_level=int(effect_details.get("power_level", 1)),
                charges_current=effect_details.get("charges_current"),
                charges_max=effect_details.get("charges_max"),
            )
            changes[f"magic_effect.{new_effect.id}.created"] = {
                "op": "entity.created",
                "before": None,
                "after": {
                    "id": new_effect.id,
                    "name": new_effect.name,
                    "effect_type": new_effect.effect_type,
                    "power_level": new_effect.power_level,
                    "charges_current": new_effect.charges_current,
                    "charges_max": new_effect.charges_max,
                },
            }
        except ValueError as exc:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=422,
                detail={
                    "error": {
                        "code": "validation_error",
                        "message": str(exc),
                        "details": {"fields": {"effect_details": str(exc)}},
                    }
                },
            ) from exc

    return changes


def _apply_charge_magic(
    db: Session,
    character: Character,
    effective_effect: dict[str, Any],
    gm_overrides: dict[str, Any],
) -> dict[str, Any]:
    """Deduct resources for a ``charge_magic`` approval and return the changes dict.

    Applies sacrifice costs identically to ``_apply_use_magic``, then applies
    the GM-determined charge/power boost to the target Magic Effect.

    For ``charged`` effects, ``gm_overrides["charges_added"]`` increases
    ``charges_current`` by that amount; if the new current would exceed
    ``charges_max``, ``charges_max`` grows to match.

    For ``permanent`` effects, ``gm_overrides["power_boost"]`` increases
    ``power_level`` by that amount (clamped at 5).

    Args:
        db: Active SQLAlchemy session.
        character: The character whose resources are deducted.
        effective_effect: The final ``calculated_effect`` after GM overrides.
        gm_overrides: The raw GM overrides dict.  Recognised keys:
            ``charges_added`` (int) — for charged target effects;
            ``power_boost`` (int) — for permanent target effects.

    Returns:
        A ``changes`` dict keyed by fully-qualified change keys.
    """
    changes: dict[str, Any] = {}

    # Apply sacrifice resources (same as use_magic, no effect creation here).
    costs: dict[str, Any] = effective_effect.get("costs") or {}

    # Gnosis
    gnosis_cost: int = int(costs.get("gnosis") or 0)
    if gnosis_cost > 0:
        before_gnosis = character.gnosis or 0
        after_gnosis = max(0, before_gnosis - gnosis_cost)
        character.gnosis = after_gnosis
        changes[f"character.{character.id}.gnosis"] = {
            "op": "meter.delta",
            "before": before_gnosis,
            "after": after_gnosis,
        }
        db.flush()

    # Stress
    stress_cost: int = int(costs.get("stress") or 0)
    if stress_cost > 0:
        trauma_count = _count_trauma_bonds(db, character.id)
        effective_max = 9 - trauma_count
        before_stress = character.stress or 0
        new_stress = before_stress + stress_cost
        after_stress = min(new_stress, effective_max)
        stress_entry: dict[str, Any] = {
            "op": "meter.delta",
            "before": before_stress,
            "after": after_stress,
        }
        if new_stress >= effective_max:
            stress_entry["clamped"] = True
        character.stress = after_stress
        changes[f"character.{character.id}.stress"] = stress_entry
        db.flush()

    # Free Time
    ft_cost: int = int(costs.get("free_time") or 0)
    if ft_cost > 0:
        before_ft = character.free_time or 0
        after_ft = max(0, before_ft - ft_cost)
        character.free_time = after_ft
        changes[f"character.{character.id}.free_time"] = {
            "op": "meter.delta",
            "before": before_ft,
            "after": after_ft,
        }
        db.flush()

    # Trait modifier charge deductions
    for charge_cost in costs.get("trait_charges") or []:
        trait_id: str = charge_cost["trait_id"]
        slot: Slot | None = db.get(Slot, trait_id)
        if slot is not None:
            before = slot.charge or 0
            after = max(0, before - 1)
            slot.charge = after
            changes[f"slot.{slot.id}.charge"] = {
                "op": "meter.delta",
                "before": before,
                "after": after,
            }
    db.flush()

    # ------------------------------------------------------------------
    # Plot deduction
    # ------------------------------------------------------------------
    plot_cost_cm: int = int(costs.get("plot") or 0)
    if plot_cost_cm > 0:
        before_plot_cm = character.plot or 0
        after_plot_cm = max(0, before_plot_cm - plot_cost_cm)
        character.plot = after_plot_cm
        changes[f"character.{character.id}.plot"] = {
            "op": "meter.delta",
            "before": before_plot_cm,
            "after": after_plot_cm,
        }
        db.flush()

    # ------------------------------------------------------------------
    # Bond strain (optional, GM flag)
    # ------------------------------------------------------------------
    bond_strained_cm: bool = bool((gm_overrides or {}).get("bond_strained", False))
    if bond_strained_cm:
        bond_mod_cm = next(
            (m for m in (effective_effect.get("modifiers") or []) if m["type"] == "bond"),
            None,
        )
        if bond_mod_cm is not None:
            bond_slot_cm: Slot | None = db.get(Slot, bond_mod_cm["id"])
            if bond_slot_cm is not None:
                degradations_cm: int = bond_slot_cm.stress_degradations or 0
                max_stress_cm: int = 5 - degradations_cm
                before_stress_cm = bond_slot_cm.stress or 0
                new_stress_cm = before_stress_cm + 1

                if new_stress_cm >= max_stress_cm:
                    bond_slot_cm.stress = 0
                    bond_slot_cm.stress_degradations = degradations_cm + 1
                    changes[f"slot.{bond_slot_cm.id}.stress"] = {
                        "op": "meter.set",
                        "before": before_stress_cm,
                        "after": 0,
                    }
                    changes[f"slot.{bond_slot_cm.id}.stress_degradations"] = {
                        "op": "meter.delta",
                        "before": degradations_cm,
                        "after": degradations_cm + 1,
                    }
                else:
                    bond_slot_cm.stress = new_stress_cm
                    changes[f"slot.{bond_slot_cm.id}.stress"] = {
                        "op": "meter.delta",
                        "before": before_stress_cm,
                        "after": new_stress_cm,
                    }
                db.flush()

    # Bond sacrifices — retire
    for bond_sac in costs.get("bond_sacrifices") or []:
        bond_id: str = bond_sac["bond_id"]
        bond_slot: Slot | None = db.get(Slot, bond_id)
        if bond_slot is not None and bond_slot.is_active:
            bond_slot.is_active = False
            changes[f"slot.{bond_slot.id}.is_active"] = {
                "op": "field.set",
                "before": True,
                "after": False,
            }
    db.flush()

    # Trait sacrifices — retire
    for trait_sac in costs.get("trait_sacrifices") or []:
        trait_id = trait_sac["trait_id"]
        trait_slot: Slot | None = db.get(Slot, trait_id)
        if trait_slot is not None and trait_slot.is_active:
            trait_slot.is_active = False
            changes[f"slot.{trait_slot.id}.is_active"] = {
                "op": "field.set",
                "before": True,
                "after": False,
            }
    db.flush()

    # ------------------------------------------------------------------
    # Apply charge or power boost to the target effect
    # ------------------------------------------------------------------
    target_effect_data: dict[str, Any] = effective_effect.get("target_effect") or {}
    effect_id: str | None = target_effect_data.get("id")
    if effect_id:
        target: MagicEffect | None = db.get(MagicEffect, effect_id)
        if target is not None:
            if target.effect_type == "charged":
                charges_added: int = int((gm_overrides or {}).get("charges_added") or 0)
                if charges_added > 0:
                    before_current = target.charges_current or 0
                    before_max = target.charges_max or 0
                    after_current = before_current + charges_added
                    after_max = max(before_max, after_current)
                    target.charges_current = after_current
                    target.charges_max = after_max
                    changes[f"magic_effect.{target.id}.charges_current"] = {
                        "op": "meter.delta",
                        "before": before_current,
                        "after": after_current,
                    }
                    if after_max != before_max:
                        changes[f"magic_effect.{target.id}.charges_max"] = {
                            "op": "meter.delta",
                            "before": before_max,
                            "after": after_max,
                        }
                    db.flush()

            elif target.effect_type == "permanent":
                power_boost: int = int((gm_overrides or {}).get("power_boost") or 0)
                if power_boost > 0:
                    before_power = target.power_level or 1
                    after_power = min(5, before_power + power_boost)
                    target.power_level = after_power
                    changes[f"magic_effect.{target.id}.power_level"] = {
                        "op": "meter.delta",
                        "before": before_power,
                        "after": after_power,
                    }
                    db.flush()

    return changes


def _apply_downtime_ft_cost(
    db: Session,
    character: Character,
    changes: dict[str, Any],
) -> None:
    """Deduct 1 Free Time from *character* and record the change.

    Mutates *character* and *changes* in-place.

    Args:
        db: Active SQLAlchemy session.
        character: The character whose Free Time is deducted.
        changes: The changes dict to populate with before/after record.
    """
    before_ft = character.free_time or 0
    after_ft = max(0, before_ft - 1)
    character.free_time = after_ft
    changes[f"character.{character.id}.free_time"] = {
        "op": "meter.delta",
        "before": before_ft,
        "after": after_ft,
    }
    db.flush()


def _apply_downtime_trait_charges(
    db: Session,
    effective_effect: dict[str, Any],
    changes: dict[str, Any],
) -> None:
    """Deduct trait charges for any trait modifiers in *effective_effect*.

    Mutates *changes* in-place.

    Args:
        db: Active SQLAlchemy session.
        effective_effect: The final ``calculated_effect``.
        changes: The changes dict to populate with before/after records.
    """
    costs: dict[str, Any] = effective_effect.get("costs") or {}
    for charge_cost in costs.get("trait_charges") or []:
        trait_id: str = charge_cost["trait_id"]
        slot: Slot | None = db.get(Slot, trait_id)
        if slot is not None:
            before = slot.charge or 0
            after = max(0, before - 1)
            slot.charge = after
            changes[f"slot.{slot.id}.charge"] = {
                "op": "meter.delta",
                "before": before,
                "after": after,
            }
    db.flush()


def _apply_regain_gnosis(
    db: Session,
    character: Character,
    effective_effect: dict[str, Any],
    gm_overrides: dict[str, Any],
) -> dict[str, Any]:
    """Deduct resources and add Gnosis for a ``regain_gnosis`` approval.

    Adds ``gnosis_gained`` to the character (capped at ``GNOSIS_MAX``),
    deducts 1 Free Time, and deducts any modifier trait charges.

    Args:
        db: Active SQLAlchemy session.
        character: The character whose resources are changed.
        effective_effect: The final ``calculated_effect`` after GM overrides.
        gm_overrides: The raw GM overrides dict (unused for this action type).

    Returns:
        A ``changes`` dict keyed by fully-qualified change keys.
    """
    changes: dict[str, Any] = {}

    gnosis_gained: int = int(effective_effect.get("gnosis_gained") or 0)
    if gnosis_gained > 0:
        before_gnosis = character.gnosis or 0
        after_gnosis = min(GNOSIS_MAX, before_gnosis + gnosis_gained)
        character.gnosis = after_gnosis
        changes[f"character.{character.id}.gnosis"] = {
            "op": "meter.delta",
            "before": before_gnosis,
            "after": after_gnosis,
        }
        db.flush()

    _apply_downtime_ft_cost(db, character, changes)
    _apply_downtime_trait_charges(db, effective_effect, changes)

    return changes


def _apply_recharge_trait(
    db: Session,
    character: Character,
    effective_effect: dict[str, Any],
    gm_overrides: dict[str, Any],
) -> dict[str, Any]:
    """Set a trait's charge to 5 and deduct 1 Free Time.

    Args:
        db: Active SQLAlchemy session.
        character: The character whose resources are changed.
        effective_effect: The final ``calculated_effect`` after GM overrides.
        gm_overrides: The raw GM overrides dict (unused for this action type).

    Returns:
        A ``changes`` dict keyed by fully-qualified change keys.
    """
    changes: dict[str, Any] = {}

    trait_id: str | None = effective_effect.get("trait_id")
    if trait_id:
        slot: Slot | None = db.get(Slot, trait_id)
        if slot is not None:
            before_charge = slot.charge or 0
            slot.charge = 5
            changes[f"slot.{slot.id}.charge"] = {
                "op": "meter.set",
                "before": before_charge,
                "after": 5,
            }
            db.flush()

    _apply_downtime_ft_cost(db, character, changes)

    return changes


def _apply_maintain_bond(
    db: Session,
    character: Character,
    effective_effect: dict[str, Any],
    gm_overrides: dict[str, Any],
) -> dict[str, Any]:
    """Reset a bond's stress to 0 and deduct 1 Free Time.

    Note: Only resets stress (bond charges); does not reverse degradations.

    Args:
        db: Active SQLAlchemy session.
        character: The character whose resources are changed.
        effective_effect: The final ``calculated_effect`` after GM overrides.
        gm_overrides: The raw GM overrides dict (unused for this action type).

    Returns:
        A ``changes`` dict keyed by fully-qualified change keys.
    """
    changes: dict[str, Any] = {}

    bond_id: str | None = effective_effect.get("bond_id")
    if bond_id:
        bond_slot: Slot | None = db.get(Slot, bond_id)
        if bond_slot is not None:
            before_stress = bond_slot.stress or 0
            if before_stress != 0:
                bond_slot.stress = 0
                changes[f"slot.{bond_slot.id}.stress"] = {
                    "op": "meter.set",
                    "before": before_stress,
                    "after": 0,
                }
                db.flush()

    _apply_downtime_ft_cost(db, character, changes)

    return changes


def _apply_work_on_project(
    db: Session,
    character: Character,
    effective_effect: dict[str, Any],
    gm_overrides: dict[str, Any],
) -> dict[str, Any]:
    """Create a story entry and deduct 1 Free Time.

    The ``entry_text`` is read from *effective_effect* (stored there at
    calculation time).  The ``author_id`` is resolved by looking up the
    ``User`` whose ``character_id`` matches this character.

    Args:
        db: Active SQLAlchemy session.
        character: The character whose resources are changed.
        effective_effect: The final ``calculated_effect`` after GM overrides.
            Must contain ``story_id`` and ``entry_text``.
        gm_overrides: The raw GM overrides dict (unused for this action type).

    Returns:
        A ``changes`` dict keyed by fully-qualified change keys.
    """
    from wizards_engine.models.user import User  # noqa: PLC0415
    from wizards_engine.services.story import create_story_entry  # noqa: PLC0415

    changes: dict[str, Any] = {}

    story_id: str | None = effective_effect.get("story_id")
    entry_text: str | None = effective_effect.get("entry_text")

    if story_id and entry_text:
        # Resolve the author (user linked to this character).
        owning_user = db.execute(
            select(User).where(User.character_id == character.id)  # type: ignore[attr-defined]
        ).scalars().first()
        author_id: str = owning_user.id if owning_user is not None else character.id

        create_story_entry(
            db,
            story_id=story_id,
            text=entry_text,
            author_id=author_id,
            character_id=character.id,
        )
        changes[f"story.{story_id}.entry_added"] = {
            "op": "entity.created",
            "before": None,
            "after": {"story_id": story_id},
        }

    _apply_downtime_ft_cost(db, character, changes)

    return changes


def _apply_rest(
    db: Session,
    character: Character,
    effective_effect: dict[str, Any],
    gm_overrides: dict[str, Any],
) -> dict[str, Any]:
    """Reduce character stress and deduct 1 Free Time and any modifier trait charges.

    Args:
        db: Active SQLAlchemy session.
        character: The character whose resources are changed.
        effective_effect: The final ``calculated_effect`` after GM overrides.
        gm_overrides: The raw GM overrides dict (unused for this action type).

    Returns:
        A ``changes`` dict keyed by fully-qualified change keys.
    """
    changes: dict[str, Any] = {}

    stress_healed: int = int(effective_effect.get("stress_healed") or 0)
    if stress_healed > 0:
        before_stress = character.stress or 0
        after_stress = max(0, before_stress - stress_healed)
        if after_stress != before_stress:
            character.stress = after_stress
            changes[f"character.{character.id}.stress"] = {
                "op": "meter.delta",
                "before": before_stress,
                "after": after_stress,
            }
            db.flush()

    _apply_downtime_ft_cost(db, character, changes)
    _apply_downtime_trait_charges(db, effective_effect, changes)

    return changes


def _apply_new_trait(
    db: Session,
    character: Character,
    effective_effect: dict[str, Any],
    gm_overrides: dict[str, Any],
) -> dict[str, Any]:
    """Optionally create a TraitTemplate, retire an old trait, create a new trait, and deduct 1 FT.

    If ``proposed_name`` is set in *effective_effect*, a new TraitTemplate is
    created first.  If ``retire_trait_id`` is set, the old trait is retired.
    Then a new trait instance is created with ``charge=5``.

    Args:
        db: Active SQLAlchemy session.
        character: The character whose resources are changed.
        effective_effect: The final ``calculated_effect`` after GM overrides.
        gm_overrides: The raw GM overrides dict (unused for this action type).

    Returns:
        A ``changes`` dict keyed by fully-qualified change keys.
    """
    from wizards_engine.services.trait import (  # noqa: PLC0415
        create_trait_instance,
        retire_trait_instance,
    )
    from wizards_engine.services.trait_template import (  # noqa: PLC0415
        create_trait_template,
    )

    changes: dict[str, Any] = {}

    slot_type: str = effective_effect.get("slot_type", "")
    template_id: str | None = effective_effect.get("template_id")
    proposed_name: str | None = effective_effect.get("proposed_name")
    proposed_description: str | None = effective_effect.get("proposed_description")
    retire_trait_id: str | None = effective_effect.get("retire_trait_id")

    # Create TraitTemplate if proposed_name provided.
    if proposed_name and not template_id:
        tmpl_type = "core" if slot_type == "core_trait" else "role"
        new_tmpl = create_trait_template(
            db,
            name=proposed_name,
            description=proposed_description or "",
            template_type=tmpl_type,
        )
        template_id = new_tmpl.id
        changes[f"trait_template.{new_tmpl.id}.created"] = {
            "op": "entity.created",
            "before": None,
            "after": {"id": new_tmpl.id, "name": new_tmpl.name},
        }

    # Retire old trait if requested.
    if retire_trait_id:
        old_slot: Slot | None = db.get(Slot, retire_trait_id)
        if old_slot is not None and old_slot.is_active:
            retire_trait_instance(db, retire_trait_id)
            changes[f"slot.{retire_trait_id}.is_active"] = {
                "op": "field.set",
                "before": True,
                "after": False,
            }

    # Create new trait instance.
    if template_id and slot_type:
        new_slot = create_trait_instance(db, character.id, slot_type, template_id)
        changes[f"slot.{new_slot.id}.created"] = {
            "op": "entity.created",
            "before": None,
            "after": {
                "id": new_slot.id,
                "name": new_slot.name,
                "slot_type": new_slot.slot_type,
                "charge": new_slot.charge,
            },
        }

    _apply_downtime_ft_cost(db, character, changes)

    return changes


def _apply_new_bond(
    db: Session,
    character: Character,
    effective_effect: dict[str, Any],
    gm_overrides: dict[str, Any],
) -> dict[str, Any]:
    """Optionally retire an old bond, create a new PC bond, and deduct 1 FT.

    Args:
        db: Active SQLAlchemy session.
        character: The character whose resources are changed.
        effective_effect: The final ``calculated_effect`` after GM overrides.
        gm_overrides: The raw GM overrides dict (unused for this action type).

    Returns:
        A ``changes`` dict keyed by fully-qualified change keys.
    """
    from wizards_engine.services.bond import create_bond  # noqa: PLC0415

    changes: dict[str, Any] = {}

    target_type: str | None = effective_effect.get("target_type")
    target_id: str | None = effective_effect.get("target_id")
    retire_bond_id: str | None = effective_effect.get("retire_bond_id")

    # Retire old bond if requested.
    if retire_bond_id:
        old_bond: Slot | None = db.get(Slot, retire_bond_id)
        if old_bond is not None and old_bond.is_active:
            old_bond.is_active = False
            changes[f"slot.{retire_bond_id}.is_active"] = {
                "op": "field.set",
                "before": True,
                "after": False,
            }
            db.flush()

    # Create new bond.
    if target_type and target_id:
        result = create_bond(
            db,
            source_type="character",
            source_id=character.id,
            target_type=target_type,
            target_id=target_id,
        )
        new_bond_slot = result.bond
        changes[f"slot.{new_bond_slot.id}.created"] = {
            "op": "entity.created",
            "before": None,
            "after": {
                "id": new_bond_slot.id,
                "name": new_bond_slot.name,
                "slot_type": new_bond_slot.slot_type,
            },
        }

    _apply_downtime_ft_cost(db, character, changes)

    return changes


#: Registry mapping action_type → apply function.
#: Each function has the signature:
#:   (db, character, effective_effect, gm_overrides) -> changes dict
_APPLY_HANDLERS: dict = {
    "use_skill": _apply_use_skill,
    "use_magic": _apply_use_magic,
    "charge_magic": _apply_charge_magic,
    "regain_gnosis": _apply_regain_gnosis,
    "recharge_trait": _apply_recharge_trait,
    "maintain_bond": _apply_maintain_bond,
    "work_on_project": _apply_work_on_project,
    "rest": _apply_rest,
    "new_trait": _apply_new_trait,
    "new_bond": _apply_new_bond,
}


def _merge_overrides(
    calculated_effect: dict[str, Any],
    gm_overrides: dict[str, Any],
) -> dict[str, Any]:
    """Merge ``gm_overrides`` into ``calculated_effect`` (shallow top-level merge,
    deep merge one level for nested dicts like ``costs``).

    Args:
        calculated_effect: The system-computed effect dict.
        gm_overrides: GM-supplied replacement values.

    Returns:
        The merged effective effect.
    """
    if not gm_overrides:
        return dict(calculated_effect)

    merged = dict(calculated_effect)
    for key, value in gm_overrides.items():
        if key in ("bond_strained", "force", "effect_details", "charges_added", "power_boost", "actual_stat", "style_bonus"):
            # These are control flags or magic-action GM fields — skip merging into effect.
            continue
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            # Deep merge one level (e.g., "costs").
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value
    return merged


def _check_affordability(
    db: Session,
    character: Character,
    effective_effect: dict[str, Any],
) -> dict[str, str]:
    """Check whether the character can still afford the costs in ``effective_effect``.

    Args:
        db: Active SQLAlchemy session.
        character: The character being checked.
        effective_effect: The final effect (after GM overrides applied).

    Returns:
        A dict mapping field name → reason string for each insufficient resource.
        Empty dict means all resources are available.
    """
    insufficient: dict[str, str] = {}
    costs: dict[str, Any] = effective_effect.get("costs") or {}

    # Trait charges
    for charge_cost in costs.get("trait_charges") or []:
        trait_id: str = charge_cost["trait_id"]
        slot: Slot | None = db.get(Slot, trait_id)
        if slot is None or (slot.charge or 0) < 1:
            name = slot.name if slot else trait_id
            insufficient[f"trait.{trait_id}"] = (
                f"Trait '{name}' has 0 charges and cannot be invoked"
            )

    # Plot spend
    plot_cost: int = int(costs.get("plot") or 0)
    if plot_cost > 0 and (character.plot or 0) < plot_cost:
        insufficient["plot"] = (
            f"Character has {character.plot or 0} Plot but {plot_cost} was requested"
        )

    # Gnosis cost (magic actions): only block if character has 0 and cost > 0.
    # Sacrifice amounts above current Gnosis are clamped on approval — see _apply_use_magic.
    gnosis_cost: int = int(costs.get("gnosis") or 0)
    if gnosis_cost > 0 and (character.gnosis or 0) == 0:
        insufficient["gnosis"] = (
            "Character has 0 Gnosis and cannot sacrifice Gnosis"
        )

    # Stress cost (magic sacrifice): only block if already at effective max.
    # Going to or over effective_max triggers a Trauma proposal — that is allowed.
    # Block only when already at max and ANY stress sacrifice is requested.
    stress_cost: int = int(costs.get("stress") or 0)
    if stress_cost > 0:
        trauma_count_af: int = _count_trauma_bonds(db, character.id)
        effective_stress_max: int = 9 - trauma_count_af
        current_stress: int = character.stress or 0
        if current_stress >= effective_stress_max:
            insufficient["stress"] = (
                f"Character is already at effective stress maximum ({effective_stress_max}) "
                "and cannot take additional stress sacrifice"
            )

    # Free Time (downtime actions all cost 1 FT)
    ft_cost: int = int(costs.get("free_time") or 0)
    if ft_cost > 0 and (character.free_time or 0) < ft_cost:
        insufficient["free_time"] = (
            f"Character has {character.free_time or 0} Free Time but {ft_cost} was required"
        )

    return insufficient


# ---------------------------------------------------------------------------
# Approve / reject
# ---------------------------------------------------------------------------


def approve_proposal(
    db: Session,
    proposal: Proposal,
    *,
    actor_id: str,
    narrative: str | None = None,
    gm_overrides: dict[str, Any] | None = None,
    rider_event_payload: dict[str, Any] | None = None,
) -> Proposal:
    """Approve a pending proposal, deduct resources, and create events.

    Validates affordability at approval time.  If resources are insufficient
    the caller must pass ``gm_overrides={"force": True}`` to bypass.

    For ``use_skill`` proposals, deducts trait charges and Plot.  If
    ``gm_overrides["bond_strained"]`` is ``True``, strains the modifier bond.

    Creates a ``proposal.approved`` event recording all resource changes.
    Optionally creates a rider event in the same transaction.

    Args:
        db: Active SQLAlchemy session.
        proposal: The :class:`~wizards_engine.models.proposal.Proposal` to
            approve.  Must have ``status = "pending"``.
        actor_id: ULID of the GM user performing the approval.
        narrative: GM narrative override for the event.  If ``None``, the
            proposal's own narrative is used.
        gm_overrides: Optional dict of fields that replace corresponding
            entries in ``calculated_effect``.  Special keys:
            ``bond_strained`` (bool) — strain the modifier bond;
            ``force`` (bool) — bypass re-validation.
        rider_event_payload: Optional dict with keys ``type``, ``targets``,
            ``changes``, ``narrative``, ``visibility`` for a rider event.

    Returns:
        The updated and refreshed Proposal (status = ``"approved"``).

    Raises:
        HTTPException(409): If the proposal is not ``pending``.
        HTTPException(409): If resources are insufficient and ``force`` is not
            set in ``gm_overrides``.
    """
    from fastapi import HTTPException

    if proposal.status != "pending":
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "proposal_not_pending",
                    "message": "Only pending proposals can be approved.",
                }
            },
        )

    gm_overrides = gm_overrides or {}
    force: bool = bool(gm_overrides.get("force", False))

    # Compute the effective effect: calculated_effect + gm_overrides.
    calculated_effect: dict[str, Any] = proposal.calculated_effect or {}
    effective_effect = _merge_overrides(calculated_effect, gm_overrides)

    # Re-validate affordability (resources may have changed since submission).
    if not force and proposal.character_id is not None:
        character: Character | None = db.get(Character, proposal.character_id)
        if character is not None:
            insufficient = _check_affordability(db, character, effective_effect)
            if insufficient:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error": {
                            "code": "insufficient_resources",
                            "message": "Character no longer has sufficient resources.",
                            "details": insufficient,
                        }
                    },
                )

    # Apply action-type-specific resource deduction.
    changes: dict[str, Any] = {}
    if proposal.character_id is not None:
        character = db.get(Character, proposal.character_id)
        if character is not None:
            handler = _APPLY_HANDLERS.get(proposal.action_type)
            if handler is not None:
                changes = handler(db, character, effective_effect, gm_overrides)

    # Persist gm_overrides on the proposal (store the raw overrides as supplied).
    proposal.gm_overrides = gm_overrides if gm_overrides else None

    # Determine event narrative.
    event_narrative = narrative if narrative is not None else proposal.narrative

    # Build targets for the approval event.
    targets: list[dict[str, Any]] = []
    if proposal.character_id is not None:
        targets.append(
            {
                "target_type": "character",
                "target_id": proposal.character_id,
                "is_primary": True,
            }
        )

    # Create the approval event.
    approval_event = create_event(
        db,
        type="proposal.approved",
        actor_type="gm",
        actor_id=actor_id,
        changes=changes,
        narrative=event_narrative,
        visibility="bonded",
        targets=targets,
        proposal_id=proposal.id,
    )

    # ------------------------------------------------------------------
    # Magic action: stress boundary check (auto-generate resolve_trauma).
    # Must run after approval event creation so we have a parent_event_id.
    # ------------------------------------------------------------------
    if proposal.action_type in ("use_magic", "charge_magic") and proposal.character_id is not None:
        character = db.get(Character, proposal.character_id)
        if character is not None and character.stress is not None:
            _stress_change_key = f"character.{character.id}.stress"
            if _stress_change_key in changes:
                trauma_count = _count_trauma_bonds(db, character.id)
                effective_stress_max = 9 - trauma_count
                if character.stress >= effective_stress_max and not _has_pending_resolve_trauma(
                    db, character.id
                ):
                    trauma_proposal = Proposal(
                        character_id=character.id,
                        action_type="resolve_trauma",
                        origin="system",
                        narrative="",
                        selections={},
                        status="pending",
                    )
                    db.add(trauma_proposal)
                    db.flush()
                    create_event(
                        db,
                        type="character.resolve_trauma_generated",
                        actor_type="system",
                        actor_id=None,
                        changes={},
                        visibility="silent",
                        parent_event_id=approval_event.id,
                        targets=[
                            {
                                "target_type": "character",
                                "target_id": character.id,
                                "is_primary": True,
                            }
                        ],
                        metadata={"proposal_id": trauma_proposal.id},
                    )

    # Create rider event if provided.
    rider_event_id: str | None = None
    if rider_event_payload is not None:
        rider_event = create_event(
            db,
            type=rider_event_payload.get("type", "rider.event"),
            actor_type="gm",
            actor_id=actor_id,
            changes=rider_event_payload.get("changes") or {},
            narrative=rider_event_payload.get("narrative"),
            visibility=rider_event_payload.get("visibility", "bonded"),
            targets=rider_event_payload.get("targets") or [],
            parent_event_id=approval_event.id,
            metadata=rider_event_payload.get("metadata"),
        )
        rider_event_id = rider_event.id

    # Update proposal state.
    proposal.status = "approved"
    proposal.event_id = approval_event.id
    if rider_event_id is not None:
        proposal.rider_event_id = rider_event_id

    db.flush()
    db.refresh(proposal)
    return proposal


def reject_proposal(
    db: Session,
    proposal: Proposal,
    *,
    actor_id: str,
    rejection_note: str | None = None,
) -> Proposal:
    """Reject a pending proposal with an optional rejection note.

    Sets the proposal's status to ``"rejected"`` and records the note in
    ``gm_notes``.  Creates a ``proposal.rejected`` event with
    ``private`` visibility.

    Args:
        db: Active SQLAlchemy session.
        proposal: The :class:`~wizards_engine.models.proposal.Proposal` to
            reject.  Must have ``status = "pending"``.
        actor_id: ULID of the GM user performing the rejection.
        rejection_note: Optional GM-written reason for rejection.  Stored in
            ``proposal.gm_notes``.

    Returns:
        The updated and refreshed Proposal (status = ``"rejected"``).

    Raises:
        HTTPException(409): If the proposal is not ``pending``.
    """
    from fastapi import HTTPException

    if proposal.status != "pending":
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "proposal_not_pending",
                    "message": "Only pending proposals can be rejected.",
                }
            },
        )

    proposal.status = "rejected"
    if rejection_note is not None:
        proposal.gm_notes = rejection_note

    db.flush()

    # Build targets.
    targets: list[dict[str, Any]] = []
    if proposal.character_id is not None:
        targets.append(
            {
                "target_type": "character",
                "target_id": proposal.character_id,
                "is_primary": True,
            }
        )

    create_event(
        db,
        type="proposal.rejected",
        actor_type="gm",
        actor_id=actor_id,
        visibility="private",
        narrative=rejection_note,
        targets=targets,
        proposal_id=proposal.id,
    )

    db.refresh(proposal)
    return proposal
