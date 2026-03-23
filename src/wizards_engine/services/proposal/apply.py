"""Action-type-specific resource deduction handlers for proposal approval.

Each ``_apply_*`` function is called when a proposal of the corresponding
action type is approved.  It mutates character state, deducts resources,
and returns a ``changes`` dict recording all before/after values.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from wizards_engine.models.character import Character
from wizards_engine.models.magic_effect import MagicEffect
from wizards_engine.models.proposal import Proposal
from wizards_engine.models.slot import Slot
from wizards_engine.services.event import create_event
from wizards_engine.services.exceptions import BusinessRuleViolation
from wizards_engine.services.magic_effect import create_effect as _create_magic_effect
from wizards_engine.services.shared import count_trauma_bonds, has_pending_resolve_trauma

from .constants import GNOSIS_MAX, STRESS_MAX


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _apply_bond_strain_to_slot(
    db: Session,
    bond_slot: Slot,
    changes: dict[str, Any],
) -> None:
    """Decrement a bond's charges by 1, applying degradation if charges hit 0.

    Mutates *bond_slot* and *changes* in place.
    """
    degradations: int = bond_slot.degradations or 0
    effective_max: int = 5 - degradations
    before_charges = bond_slot.charges or 0
    new_charges = before_charges - 1

    if new_charges <= 0:
        # Hit the boundary: charges depleted — apply degradation and reset.
        degradations += 1
        bond_slot.degradations = degradations
        new_effective_max = max(0, 5 - degradations)
        bond_slot.charges = new_effective_max
        changes[f"slot.{bond_slot.id}.charges"] = {
            "op": "meter.set",
            "before": before_charges,
            "after": new_effective_max,
        }
        changes[f"slot.{bond_slot.id}.degradations"] = {
            "op": "meter.delta",
            "before": degradations - 1,
            "after": degradations,
        }
    else:
        bond_slot.charges = new_charges
        changes[f"slot.{bond_slot.id}.charges"] = {
            "op": "meter.delta",
            "before": before_charges,
            "after": new_charges,
        }
    db.flush()


def _apply_downtime_ft_cost(
    db: Session,
    character: Character,
    changes: dict[str, Any],
) -> None:
    """Deduct 1 Free Time from *character* and record the change."""
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
    """Deduct trait charges for any trait modifiers in *effective_effect*."""
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


# ---------------------------------------------------------------------------
# Session action handlers
# ---------------------------------------------------------------------------


def _apply_use_skill(
    db: Session,
    character: Character,
    effective_effect: dict[str, Any],
    gm_overrides: dict[str, Any],
) -> dict[str, Any]:
    """Deduct resources for a ``use_skill`` approval and return the changes dict."""
    changes: dict[str, Any] = {}
    costs: dict[str, Any] = effective_effect.get("costs") or {}

    # Trait charge deductions
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

    # Plot deduction
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

    # Bond strain (optional, GM flag)
    bond_strained: bool = bool((gm_overrides or {}).get("bond_strained", False))
    if bond_strained:
        bond_mod = next(
            (m for m in (effective_effect.get("modifiers") or []) if m["type"] == "bond"),
            None,
        )
        if bond_mod is not None:
            bond_slot: Slot | None = db.get(Slot, bond_mod["id"])
            if bond_slot is not None:
                _apply_bond_strain_to_slot(db, bond_slot, changes)

    return changes


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
    """
    costs: dict[str, Any] = effective_effect.get("costs") or {}

    # Gnosis deduction
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

    # Stress sacrifice
    stress_cost: int = int(costs.get("stress") or 0)
    if stress_cost > 0:
        trauma_count = count_trauma_bonds(db, character.id)
        effective_max = STRESS_MAX - trauma_count
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
        if after_stress >= effective_max and not has_pending_resolve_trauma(db, character.id):
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

    # Free Time deduction
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

    # Bond sacrifices — retire (set is_active = False)
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

    # Trait sacrifices — retire (set is_active = False)
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
    """Deduct resources for a ``use_magic`` approval and return the changes dict."""
    changes: dict[str, Any] = {}
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
        trauma_count = count_trauma_bonds(db, character.id)
        effective_max = STRESS_MAX - trauma_count
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

    # Plot deduction
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

    # Bond strain (optional, GM flag)
    bond_strained: bool = bool((gm_overrides or {}).get("bond_strained", False))
    if bond_strained:
        bond_mod = next(
            (m for m in (effective_effect.get("modifiers") or []) if m["type"] == "bond"),
            None,
        )
        if bond_mod is not None:
            bond_slot_s: Slot | None = db.get(Slot, bond_mod["id"])
            if bond_slot_s is not None:
                _apply_bond_strain_to_slot(db, bond_slot_s, changes)

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

    # Create MagicEffect if GM provided effect_details
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
            raise BusinessRuleViolation(
                "validation_error",
                str(exc),
                {"fields": {"effect_details": str(exc)}},
            ) from exc

    return changes


def _apply_charge_magic(
    db: Session,
    character: Character,
    effective_effect: dict[str, Any],
    gm_overrides: dict[str, Any],
) -> dict[str, Any]:
    """Deduct resources for a ``charge_magic`` approval and return the changes dict."""
    changes: dict[str, Any] = {}
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
        trauma_count = count_trauma_bonds(db, character.id)
        effective_max = STRESS_MAX - trauma_count
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

    # Plot deduction
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

    # Bond strain (optional, GM flag)
    bond_strained_cm: bool = bool((gm_overrides or {}).get("bond_strained", False))
    if bond_strained_cm:
        bond_mod_cm = next(
            (m for m in (effective_effect.get("modifiers") or []) if m["type"] == "bond"),
            None,
        )
        if bond_mod_cm is not None:
            bond_slot_cm: Slot | None = db.get(Slot, bond_mod_cm["id"])
            if bond_slot_cm is not None:
                _apply_bond_strain_to_slot(db, bond_slot_cm, changes)

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

    # Apply charge or power boost to the target effect
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


# ---------------------------------------------------------------------------
# Downtime action handlers
# ---------------------------------------------------------------------------


def _apply_regain_gnosis(
    db: Session,
    character: Character,
    effective_effect: dict[str, Any],
    gm_overrides: dict[str, Any],
) -> dict[str, Any]:
    """Deduct resources and add Gnosis for a ``regain_gnosis`` approval."""
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


def _apply_work_on_project(
    db: Session,
    character: Character,
    effective_effect: dict[str, Any],
    gm_overrides: dict[str, Any],
) -> dict[str, Any]:
    """Create a story entry and deduct 1 Free Time."""
    from wizards_engine.models.user import User  # noqa: PLC0415
    from wizards_engine.services.story import create_story_entry  # noqa: PLC0415

    changes: dict[str, Any] = {}

    story_id: str | None = effective_effect.get("story_id")
    entry_text: str | None = effective_effect.get("entry_text")

    if story_id and entry_text:
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
    """Reduce character stress and deduct 1 Free Time and any modifier trait charges."""
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
    """Optionally create a TraitTemplate, retire an old trait, create a new trait, and deduct 1 FT."""
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
    """Optionally retire an old bond, create a new PC bond, and deduct 1 FT."""
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
APPLY_HANDLERS: dict = {
    "use_skill": _apply_use_skill,
    "use_magic": _apply_use_magic,
    "charge_magic": _apply_charge_magic,
    "regain_gnosis": _apply_regain_gnosis,
    "work_on_project": _apply_work_on_project,
    "rest": _apply_rest,
    "new_trait": _apply_new_trait,
    "new_bond": _apply_new_bond,
}


# ---------------------------------------------------------------------------
# Override merging + affordability check
# ---------------------------------------------------------------------------


def merge_overrides(
    calculated_effect: dict[str, Any],
    gm_overrides: dict[str, Any],
) -> dict[str, Any]:
    """Merge ``gm_overrides`` into ``calculated_effect`` (shallow top-level merge,
    deep merge one level for nested dicts like ``costs``)."""
    if not gm_overrides:
        return dict(calculated_effect)

    merged = dict(calculated_effect)
    for key, value in gm_overrides.items():
        if key in ("bond_strained", "force", "effect_details", "charges_added", "power_boost", "actual_stat", "style_bonus"):
            # These are control flags or magic-action GM fields — skip merging into effect.
            continue
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value
    return merged


def check_affordability(
    db: Session,
    character: Character,
    effective_effect: dict[str, Any],
) -> dict[str, str]:
    """Check whether the character can still afford the costs in ``effective_effect``.

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

    # Gnosis cost (magic actions)
    gnosis_cost: int = int(costs.get("gnosis") or 0)
    if gnosis_cost > 0 and (character.gnosis or 0) == 0:
        insufficient["gnosis"] = (
            "Character has 0 Gnosis and cannot sacrifice Gnosis"
        )

    # Stress cost (magic sacrifice)
    stress_cost: int = int(costs.get("stress") or 0)
    if stress_cost > 0:
        trauma_count_af: int = count_trauma_bonds(db, character.id)
        effective_stress_max: int = STRESS_MAX - trauma_count_af
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
