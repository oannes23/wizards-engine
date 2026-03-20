"""Validation and calculation logic for all proposal action types.

Covers ``use_skill``, ``use_magic``, ``charge_magic``, and the 5 downtime
action types (``regain_gnosis``, ``work_on_project``, ``rest``,
``new_trait``, ``new_bond``).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from wizards_engine.models.character import Character
from wizards_engine.models.magic_effect import MagicEffect
from wizards_engine.models.slot import Slot, TraitTemplate
from wizards_engine.services.exceptions import BusinessRuleViolation

from .constants import (
    CANONICAL_MAGIC_STATS,
    CANONICAL_SKILLS,
    DOWNTIME_ACTION_TYPES,
    MAGIC_STAT_KEYS,
    PC_BOND_LIMIT,
    TRAIT_LIMITS,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _raise_validation(field: str, message: str) -> None:
    """Raise a :class:`BusinessRuleViolation` for a field-level validation error.

    Args:
        field: The field name to attribute the error to.
        message: Human-readable error message.

    Raises:
        BusinessRuleViolation: Always.
    """
    raise BusinessRuleViolation.field_error(field, message)


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
        BusinessRuleViolation: If the slot does not exist, does not belong to
            the character, has the wrong slot_type, is inactive, or has 0 charges.
    """
    field = (
        "modifiers.core_trait_id"
        if expected_slot_type == "core_trait"
        else "modifiers.role_trait_id"
    )
    slot: Slot | None = db.get(Slot, trait_id)
    if slot is None:
        _raise_validation(field, f"Trait '{trait_id}' not found")
    if slot.owner_id != character_id:
        _raise_validation(field, f"Trait '{trait_id}' does not belong to this character")
    if slot.slot_type != expected_slot_type:
        _raise_validation(
            field,
            f"Trait '{trait_id}' is a {slot.slot_type}, expected {expected_slot_type}",
        )
    if not slot.is_active:
        _raise_validation(field, f"Trait '{trait_id}' is not active")
    if (slot.charge or 0) < 1:
        _raise_validation(field, f"Trait '{trait_id}' has 0 charges and cannot be invoked")
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
        BusinessRuleViolation: If the slot does not exist, does not belong to
            the character, is not a ``pc_bond``, or is inactive.
    """
    slot: Slot | None = db.get(Slot, bond_id)
    if slot is None:
        _raise_validation("modifiers.bond_id", f"Bond '{bond_id}' not found")
    if slot.owner_id != character_id:
        _raise_validation(
            "modifiers.bond_id", f"Bond '{bond_id}' does not belong to this character"
        )
    if slot.slot_type != "pc_bond":
        _raise_validation(
            "modifiers.bond_id",
            f"Bond '{bond_id}' is a {slot.slot_type}, expected pc_bond",
        )
    if not slot.is_active:
        _raise_validation("modifiers.bond_id", f"Bond '{bond_id}' is not active")
    return slot  # type: ignore[return-value]


def _check_free_time(character: Character) -> None:
    """Raise BusinessRuleViolation if the character has less than 1 Free Time.

    Args:
        character: The Character to check.

    Raises:
        BusinessRuleViolation: If ``character.free_time < 1``.
    """
    if (character.free_time or 0) < 1:
        _raise_validation(
            "free_time",
            "Character must have at least 1 Free Time to submit a downtime action",
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
    against the character's current state.

    Args:
        db: Active SQLAlchemy session.
        character_id: ULID of the character submitting the proposal.
        selections: The ``selections`` dict from the proposal request.

    Returns:
        A ``calculated_effect`` dict with dice_pool, skill, modifiers, costs.

    Raises:
        BusinessRuleViolation: If skill is invalid, a referenced trait/bond is
            missing, not owned, inactive, has 0 charges, or Plot is insufficient.
    """
    skill = selections.get("skill")
    if not skill:
        _raise_validation("skill", "skill is required for use_skill proposals")
    if skill not in CANONICAL_SKILLS:
        _raise_validation(
            "skill",
            f"skill must be one of: {sorted(CANONICAL_SKILLS)}",
        )

    character: Character | None = db.get(Character, character_id)
    if character is None:
        _raise_validation("character_id", f"Character '{character_id}' not found")

    skill_level: int = (character.skills or {}).get(skill, 0)

    # Modifier validation
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

    # Plot spend validation
    plot_spend: int = int(selections.get("plot_spend") or 0)
    if plot_spend < 0:
        _raise_validation("plot_spend", "plot_spend must be >= 0")
    if (character.plot or 0) < plot_spend:
        _raise_validation(
            "plot_spend",
            f"Character has {character.plot or 0} Plot but {plot_spend} was requested",
        )

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
    """
    stats: dict[str, Any] = character.magic_stats or {}
    if not stats:
        return 0
    return min(v.get("level", 0) for v in stats.values())


def _gnosis_equiv_to_sacrifice_dice(total_gnosis: int) -> int:
    """Convert a total Gnosis equivalent to the number of sacrifice dice.

    Uses the triangular-number tiered formula: N dice costs N*(N+1)/2 Gnosis.
    Returns the maximum N such that N*(N+1)/2 <= total_gnosis.
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
    cost summary.  ``"other"`` entries always get 0 Gnosis equivalent
    (GM sets value in overrides).

    Returns:
        A 2-tuple: (sacrifice_details, costs).

    Raises:
        BusinessRuleViolation: For invalid sacrifice entries.
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
                _raise_validation("sacrifice.gnosis", "Gnosis sacrifice amount must be >= 0")
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
                _raise_validation("sacrifice.stress", "Stress sacrifice amount must be >= 0")
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
                _raise_validation("sacrifice.free_time", "Free Time sacrifice amount must be >= 0")
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
                _raise_validation("sacrifice.bond", "Bond sacrifice requires a target_id")
            slot: Slot | None = db.get(Slot, target_id)
            if slot is None:
                _raise_validation("sacrifice.bond", f"Bond '{target_id}' not found")
            if slot.owner_id != character.id:
                _raise_validation("sacrifice.bond", f"Bond '{target_id}' does not belong to this character")
            if slot.slot_type != "pc_bond":
                _raise_validation("sacrifice.bond", f"Slot '{target_id}' is not a pc_bond")
            if not slot.is_active:
                _raise_validation("sacrifice.bond", f"Bond '{target_id}' is not active")
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
                _raise_validation("sacrifice.trait", "Trait sacrifice requires a target_id")
            slot = db.get(Slot, target_id)
            if slot is None:
                _raise_validation("sacrifice.trait", f"Trait '{target_id}' not found")
            if slot.owner_id != character.id:
                _raise_validation("sacrifice.trait", f"Trait '{target_id}' does not belong to this character")
            if slot.slot_type not in ("core_trait", "role_trait"):
                _raise_validation("sacrifice.trait", f"Slot '{target_id}' is not a core_trait or role_trait")
            if not slot.is_active:
                _raise_validation("sacrifice.trait", f"Trait '{target_id}' is not active")
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
            _raise_validation(
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

    Returns:
        A 2-tuple: (active_modifiers, trait_charges_costs).

    Raises:
        BusinessRuleViolation: For any invalid modifier reference.
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

    Raises:
        BusinessRuleViolation: For any validation failure.
    """
    suggested_stat: str | None = selections.get("suggested_stat")
    if not suggested_stat:
        _raise_validation("suggested_stat", "suggested_stat is required for use_magic proposals")
    if suggested_stat not in CANONICAL_MAGIC_STATS:
        _raise_validation(
            "suggested_stat",
            f"suggested_stat must be one of: {sorted(CANONICAL_MAGIC_STATS)}",
        )

    character: Character | None = db.get(Character, character_id)
    if character is None:
        _raise_validation("character_id", f"Character '{character_id}' not found")

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

    # Plot spend validation
    plot_spend: int = int(selections.get("plot_spend") or 0)
    if plot_spend < 0:
        _raise_validation("plot_spend", "plot_spend must be >= 0")
    if (character.plot or 0) < plot_spend:
        _raise_validation(
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

    Raises:
        BusinessRuleViolation: For any validation failure.
    """
    effect_id: str | None = selections.get("effect_id")
    if not effect_id:
        _raise_validation("effect_id", "effect_id is required for charge_magic proposals")

    effect: MagicEffect | None = db.get(MagicEffect, effect_id)
    if effect is None:
        _raise_validation("effect_id", f"Magic effect '{effect_id}' not found")
    if effect.character_id != character_id:
        _raise_validation("effect_id", f"Magic effect '{effect_id}' does not belong to this character")
    if not effect.is_active:
        _raise_validation("effect_id", f"Magic effect '{effect_id}' is not active")
    if effect.effect_type not in ("charged", "permanent"):
        _raise_validation(
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
# Downtime action calculations
# ---------------------------------------------------------------------------


def calculate_regain_gnosis(
    db: Session,
    character: Character,
    selections: dict[str, Any],
) -> dict[str, Any]:
    """Validate and compute the ``calculated_effect`` for a ``regain_gnosis`` proposal.

    Gnosis gained = 3 + lowest magic stat level + modifier count (max +3).

    Raises:
        BusinessRuleViolation: If FT is insufficient or modifier validation fails.
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


def calculate_work_on_project(
    db: Session,
    character: Character,
    selections: dict[str, Any],
) -> dict[str, Any]:
    """Validate and compute the ``calculated_effect`` for a ``work_on_project`` proposal.

    Raises:
        BusinessRuleViolation: If FT is insufficient, story_id or entry_text
            are missing, or the story does not exist.
    """
    from wizards_engine.models.story import Story  # noqa: PLC0415

    _check_free_time(character)

    story_id: str | None = selections.get("story_id")
    if not story_id:
        _raise_validation("story_id", "story_id is required for work_on_project proposals")

    entry_text: str | None = selections.get("entry_text")
    if not entry_text:
        _raise_validation("entry_text", "entry_text is required for work_on_project proposals")

    story = db.get(Story, story_id)
    if story is None or story.is_deleted:
        _raise_validation("story_id", f"Story '{story_id}' not found")

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

    Stress healed = 3 + modifier count (max +3).

    Raises:
        BusinessRuleViolation: If FT is insufficient or modifier validation fails.
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

    Raises:
        BusinessRuleViolation: If FT is insufficient, slot_type is invalid,
            template/name validation fails, or retire_trait_id is missing when
            required.
    """
    _check_free_time(character)

    slot_type: str | None = selections.get("slot_type")
    if slot_type not in ("core_trait", "role_trait"):
        _raise_validation("slot_type", "slot_type must be 'core_trait' or 'role_trait'")

    template_id: str | None = selections.get("template_id")
    proposed_name: str | None = selections.get("proposed_name")
    proposed_description: str | None = selections.get("proposed_description")
    retire_trait_id: str | None = selections.get("retire_trait_id")

    # Either template_id or proposed_name+description must be provided.
    if template_id is None and not proposed_name:
        _raise_validation(
            "template_id",
            "Either template_id or proposed_name + proposed_description must be provided",
        )
    if proposed_name and not proposed_description:
        _raise_validation(
            "proposed_description",
            "proposed_description is required when proposed_name is provided",
        )

    # Validate template if provided.
    if template_id is not None:
        tmpl: TraitTemplate | None = db.get(TraitTemplate, template_id)
        if tmpl is None or tmpl.is_deleted:
            _raise_validation("template_id", f"Trait template '{template_id}' not found")
        required_type = "core" if slot_type == "core_trait" else "role"
        if tmpl.type != required_type:
            _raise_validation(
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
        _raise_validation(
            "retire_trait_id",
            f"Character is at the {slot_type} limit ({limit}). "
            "retire_trait_id is required to retire an existing trait.",
        )

    # Validate retire_trait_id if provided.
    if retire_trait_id is not None:
        rslot: Slot | None = db.get(Slot, retire_trait_id)
        if rslot is None:
            _raise_validation("retire_trait_id", f"Trait '{retire_trait_id}' not found")
        if rslot.owner_id != character.id:
            _raise_validation(
                "retire_trait_id",
                f"Trait '{retire_trait_id}' does not belong to this character",
            )
        if not rslot.is_active:
            _raise_validation("retire_trait_id", f"Trait '{retire_trait_id}' is not active")
        if rslot.slot_type != slot_type:
            _raise_validation(
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

    Raises:
        BusinessRuleViolation: If FT is insufficient, target is not found,
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
        _raise_validation("target_type", "target_type is required for new_bond proposals")
    if not target_id:
        _raise_validation("target_id", "target_id is required for new_bond proposals")

    _nb_model_map: dict[str, type] = {
        "character": Character,
        "group": Group,
        "location": Location,
    }
    model_cls = _nb_model_map.get(target_type)
    if model_cls is None:
        _raise_validation(
            "target_type",
            f"target_type must be 'character', 'group', or 'location', got '{target_type}'",
        )

    target_obj = db.get(model_cls, target_id)
    if target_obj is None or getattr(target_obj, "is_deleted", False):
        _raise_validation("target_id", f"{target_type.capitalize()} '{target_id}' not found")

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
        _raise_validation(
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
        _raise_validation(
            "retire_bond_id",
            f"Character is at the pc_bond limit ({PC_BOND_LIMIT}). "
            "retire_bond_id is required to retire an existing bond.",
        )

    # Validate retire_bond_id if provided.
    if retire_bond_id is not None:
        rb_slot: Slot | None = db.get(Slot, retire_bond_id)
        if rb_slot is None:
            _raise_validation("retire_bond_id", f"Bond '{retire_bond_id}' not found")
        if rb_slot.owner_id != character.id:
            _raise_validation(
                "retire_bond_id",
                f"Bond '{retire_bond_id}' does not belong to this character",
            )
        if not rb_slot.is_active:
            _raise_validation("retire_bond_id", f"Bond '{retire_bond_id}' is not active")
        if rb_slot.slot_type != "pc_bond":
            _raise_validation(
                "retire_bond_id",
                f"Bond '{retire_bond_id}' is a {rb_slot.slot_type}, expected pc_bond",
            )
        if rb_slot.is_trauma:
            _raise_validation("retire_bond_id", "Cannot retire a trauma bond")

    return {
        "target_type": target_type,
        "target_id": target_id,
        "retire_bond_id": retire_bond_id,
        "costs": {"free_time": 1},
    }
