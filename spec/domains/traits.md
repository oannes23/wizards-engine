# Traits — Domain Specification

**Status**: 🟢 Complete
**Last interrogated**: 2026-03-13
**Last verified**: 2026-03-16
**Depends on**: [character-core](character-core.md), [game-objects](game-objects.md)
**Depended on by**: [proposals](proposals.md), [downtime](downtime.md)

---

## Overview

**This is the authoritative spec for all trait types in the system.** Traits exist on three Game Object types with varying mechanical depth:

- **PC Traits** (Core 2 + Role 3): Mechanical — charges (0–5), +1d bonus on proposals, Trait Template catalog, Past/Retired lifecycle.
- **Group Traits** (10 slots): Descriptive — freeform name + description, no charges, no dice bonuses, simple replace lifecycle.
- **Location Feature Traits** (5 slots): Descriptive — freeform name + description, no charges, no dice bonuses, simple replace lifecycle.

All trait types live in the unified table with Bonds (see [bonds.md](bonds.md)), distinguished by `slot_type`.

---

## PC Traits (Full Characters Only)

### Unified Trait/Bond Architecture

PC Traits and Bonds share a common two-layer architecture:

1. **Trait Template** (definition layer): A GM-created catalog entry with name, description, and type (`core` or `role`). The type is fixed — Core templates fill Core slots, Role templates fill Role slots. Multiple characters can share the same Trait Template. Editing a template propagates changes to all characters referencing it. Bonds use game objects as their "template" instead — see [bonds.md](bonds.md).
2. **Trait Instance** (character layer): A per-character record linking to a Trait Template. Holds character-specific state: charges, `is_active` flag, and an event history stream. A character can only have one active instance of a given template (no duplicates).

### Core Traits (2 slots per Character)

Each Trait Instance links to a Trait Template and has:
- `charge`: meter, 0–5
- `is_active`: boolean (active vs retired/past)

Core Traits represent the character's defining qualities — fundamental aspects of who they are.

### Role Traits (3 slots per Character)

Same structure as Core Traits. Role Traits represent learned skills, professional abilities, or situational expertise.

### +1d Bonus Mechanic

When a Trait is relevant to an action, the player can spend 1 charge to add **+1d** to the related dice pool. This is selected during proposal submission. A trait with 0 charges cannot be selected for the mechanical bonus.

Players can reference traits narratively in their proposal fiction for flavor without spending a charge — the charge cost is only for the +1d bonus.

### Proposal Modifier Stacking

Per proposal, a player may select at most:
- **1 Core Trait** (+1d, costs 1 charge)
- **1 Role Trait** (+1d, costs 1 charge)
- **1 Bond** (+1d, no charge — see [bonds.md](bonds.md))

Maximum modifier bonus: **+3d** on top of the base skill dice pool.

### Charge Economy

- New traits start at **full charge (5)**
- Charges are **spent** (1 per invocation) when a trait is selected for the +1d bonus in an approved proposal
- Charges are **replenished** during downtime via the "Recharge Trait" activity (fully restores one trait per activity, costs 1 FT)

### Trait Slots and Blank Slots

Characters have fixed trait **slots** (2 Core, 3 Role) but slots may be **blank** — not yet filled with a trait. Characters don't need all 5 traits immediately; the intent is to fill them quickly during early play.

### Past/Retired Traits

When a PC trait is replaced (via "New Trait" downtime action or GM action), the old Trait Instance is marked `is_active = false`. It remains on the character sheet in a **"Past" section**:
- Full event history preserved and viewable
- Cannot be selected for proposals (+1d bonus)
- Serves as a narrative record of the character's trait history

This applies equally to retired Bonds — see [bonds.md](bonds.md).

### PC Trait Lifecycle

1. **Created**: GM adds traits via direct action (post character creation), selecting from the Trait Template catalog. New traits start at full charge (5).
2. **Active**: Trait is available for use in proposals and downtime.
3. **Replaced**: Player submits "New Trait" downtime action to replace an existing trait or fill a blank slot. Old trait moves to Past.
4. **Retired/Past**: `is_active = false`. Viewable history, no mechanical use.
5. **GM edit**: GM can edit any trait's name/description/charge via admin CRUD at any time.

---

## Group Traits (Descriptive)

Groups have **10 descriptive trait slots** — freeform name + description, no categories enforced. These represent the group's culture, training, assets, reputation, or any other defining characteristic the GM wants to track.

### Key Properties

- **Freeform**: No Trait Template catalog. GM types name + description directly.
- **No mechanics**: No charges, no dice bonuses, no stacking rules.
- **Simple replace**: GM can overwrite or clear any slot directly. No Past/Retired lifecycle — old values are not preserved on the entity.
- **Event-logged**: Changes are recorded in the event log with before/after values, providing history via events even without the Past/Retired pattern.
- **Player influence via work_on_project**: Players who are members of a Group can propose trait changes by submitting a `work_on_project` downtime action targeting the Group's Story/Arc. The GM resolves the trait change as the project outcome.

### Group Trait Lifecycle

1. **Created**: GM adds a descriptive trait to a Group slot (direct action).
2. **Active**: Visible on the Group detail endpoint.
3. **Replaced/Cleared**: GM overwrites with a new trait or clears the slot. Change logged as an event.

---

## Location Feature Traits (Descriptive)

Locations have **5 descriptive Feature trait slots** — freeform name + description representing physical characteristics, atmosphere, dangers, notable qualities, or any other defining feature.

### Key Properties

- **Freeform**: No Trait Template catalog. GM types name + description directly.
- **No mechanics**: No charges, no dice bonuses.
- **Interchangeable**: All 5 slots are generic. Categories (atmosphere, danger, etc.) are naming conventions, not enforced.
- **Simple replace**: Same as Group traits — GM overwrites or clears directly. No Past/Retired lifecycle.
- **Event-logged**: Changes recorded in the event log with before/after values.
- **Player influence via work_on_project**: Players bonded to a Location can propose Feature trait changes by submitting a `work_on_project` downtime action targeting a Story/Arc associated with the Location. The GM resolves the trait change as the project outcome.

### Location Feature Trait Lifecycle

1. **Created**: GM adds a descriptive Feature trait to a Location slot (direct action).
2. **Active**: Visible on the Location detail endpoint.
3. **Replaced/Cleared**: GM overwrites with a new trait or clears the slot. Change logged as an event.

---

## Unified Table

All trait types live in the unified table alongside Bonds, distinguished by `slot_type`:

| Slot Type | Owner | Slots | Mechanical | Template? |
|-----------|-------|-------|------------|-----------|
| `core_trait` | Full Character | 2 | Yes (charges, +1d) | Trait Template catalog |
| `role_trait` | Full Character | 3 | Yes (charges, +1d) | Trait Template catalog |
| `group_trait` | Group | 10 | No (descriptive) | Freeform |
| `feature_trait` | Location | 5 | No (descriptive) | Freeform |

Bond slot types are defined in [bonds.md](bonds.md).

The complete column layout and nullable field rules are specified in [data-model.md](../architecture/data-model.md).

---

## Decisions

### traits.md Is the Authoritative Trait Spec

- **Decision**: This document is the single source of truth for all trait types — PC Core/Role, Group descriptive, and Location Feature traits.
- **Rationale**: Traits are a cross-cutting concept. Having one authoritative reference prevents fragmentation.
- **Implications**: game-objects.md references this spec for Group/Location trait details.

### Unified Trait/Bond Architecture

- **Decision**: Core Traits, Role Traits, and Bonds share a unified two-layer architecture: Trait Templates (definition catalog) and Trait Instances (per-character state). Core/Role Traits link to Trait Templates; Bonds link to game objects. Group/Location traits are freeform (no templates).
- **Rationale**: Unifying the model reduces complexity. All types occupy slots, can be active or retired (PC) or simply replaced (Group/Location), and live in one table.
- **Implications**: Single table with a `slot_type` discriminator. See [bonds.md](bonds.md) for Bond-specific fields.

### Trait Template Catalog (PC Traits Only)

- **Decision**: Trait Templates are a GM-created shared catalog for Core and Role traits only. Group and Location traits are freeform — no catalog, no reuse mechanism.
- **Rationale**: PC traits benefit from reuse (multiple characters can share "Brave") and catalog management. Group/Location traits are more situational and don't need the overhead.
- **Implications**: Trait Template CRUD is for PC traits only. Group/Location trait creation is inline.

### Group Traits — Flat Descriptive Slots

- **Decision**: Groups have 10 descriptive trait slots with no enforced categories. Replaces the previous Culture (2) / Training (3) / Asset (5) structure.
- **Rationale**: Categories added complexity without clear benefit. The GM can name traits however they want — a "Culture" trait vs a "Training" trait is a naming convention, not a system distinction.
- **Implications**: Single `group_trait` slot_type in the unified table. Previous culture_trait, training_trait, asset_trait types removed.

### Location Feature Traits — Interchangeable Slots

- **Decision**: Locations have 5 generic Feature trait slots. All interchangeable — no typed sub-slots (atmosphere, danger, etc.).
- **Rationale**: Enforcing sub-types constrains the GM without adding value. 5 slots is enough for most Locations.
- **Implications**: Single `feature_trait` slot_type.

### Group/Location Traits Are Freeform

- **Decision**: Group and Location traits are name + description, typed directly by the GM. No Trait Template catalog or reuse mechanism.
- **Rationale**: These are world-building flavor text. A shared catalog adds overhead without meaningful benefit — each Group/Location is unique enough that reuse is rare.
- **Implications**: No template_id on Group/Location trait records. Just name + description.

### Simple Replace Lifecycle (Group/Location)

- **Decision**: Group and Location traits use a simple replace model — GM can overwrite or clear a slot directly. No Past/Retired pattern. Old values are captured in the event log (before/after), not on the entity itself.
- **Rationale**: These are descriptive flavor with no mechanical stakes. Full history tracking adds overhead for no gameplay benefit. The event log provides audit trail if ever needed.
- **Implications**: No `is_active` flag needed for Group/Location traits (they're always active or absent). Past/Retired only applies to PC traits and Bonds.

### Player Influence on Group/Location Traits

- **Decision**: Players can propose Group trait changes (for Groups they're members of) and Location Feature trait changes (for Locations they're bonded to) via the `work_on_project` downtime action. The player targets a Story/Arc associated with the Group or Location. The GM resolves the trait change as the project outcome.
- **Rationale**: No new proposal types needed — `work_on_project` already covers narrative-driven changes. Players discuss desired changes at the table, formalize via proposal, GM makes the actual edit.
- **Implications**: No new proposal types. GM direct action is the actual mechanism for the trait change; the proposal is the player's request and narrative contribution.

### Template Type Binding

- **Decision**: Trait Template type (`core` or `role`) is fixed on the template. Core templates can only fill Core slots; Role templates can only fill Role slots.
- **Rationale**: Clear categorization. The distinction between defining qualities (Core) and learned abilities (Role) is fundamental to the design.
- **Implications**: Template creation requires specifying a type. Slot assignment validates type match. Type is immutable after creation — PATCH only allows name/description.

### Trait Template Propagation

- **Decision**: Editing a Trait Template's name or description propagates to all characters referencing it (via `slots.template_id`). Type is immutable — cannot be changed after creation. Soft-deleting a template does NOT cascade to instances — existing trait instances keep their `template_id` reference and remain functional, but the template is hidden from the catalog browse endpoint.
- **Rationale**: Name/description propagation keeps the catalog consistent. Type immutability prevents breaking slot assignments. Orphaning (not cascading) on soft-delete avoids unexpected trait loss on active characters.
- **Implications**: PATCH on trait templates only accepts name/description. Soft-deleted templates still resolve when fetched by ID (for instance display) but are excluded from catalog lists.

### Auto-Catalog on New Trait Approval

- **Decision**: When the GM approves a `new_trait` downtime proposal that includes a proposed name/description (not referencing an existing template), the system automatically creates a new Trait Template in the catalog and links the new trait instance to it.
- **Rationale**: Reduces GM friction. The approval itself is the endorsement of the new trait concept. Auto-cataloging makes it immediately reusable for other characters.
- **Implications**: The `new_trait` proposal's `selections` can include either `template_id` (existing) or `proposed_name` + `proposed_description` (new). On approval with proposed fields, system creates template → links instance.

### No Duplicate Templates per Character

- **Decision**: A character can only have one active instance of a given Trait Template. No assigning the same template to multiple slots.
- **Rationale**: Each trait should be narratively distinct on a character. Duplicates would be mechanically redundant.

### Count-Based Trait Slots

- **Decision**: Characters have a maximum of 2 active Core Traits and 3 active Role Traits. Groups have 10 descriptive trait slots. Locations have 5 Feature trait slots. All counts are fixed maximums. Slots are count-based, not indexed — traits are referenced by ID, not by position. Blank slots are allowed (not all positions must be filled).
- **Rationale**: Count-based is simpler than indexed positions and consistent with the bond model. Traits are naturally referenced by their unique ID. Display ordering is by creation time.
- **Implications**: `new_trait` proposal uses `{slot_type, template_id?, retire_trait_id?}` — no `slot_index`. When at max active count for that slot_type, `retire_trait_id` is required. See [actions.md](actions.md).

### Charge Range

- **Decision**: Charge range is 0–5 for all PC traits.
- **Rationale**: Provides enough uses between downtimes without being unlimited.
- **Implications**: Downtime "Recharge Trait" activity restores charges.

### Charge Cost

- **Decision**: Invoking a trait for the +1d bonus always costs exactly 1 charge.
- **Rationale**: Simple and predictable. No variable costs to track or explain.
- **Implications**: At 5 charges, a trait can be invoked 5 times between resets.

### Initial Charge Value

- **Decision**: New traits (whether created at character setup or via downtime replacement) start at full charge (5).
- **Rationale**: New traits should be immediately usable. No penalty for gaining a new trait.
- **Implications**: The "New Trait" downtime action effectively also resets charges on that slot.

### Narrative vs Mechanical Invocation

- **Decision**: Players can reference traits narratively in proposal fiction without spending a charge. Only the +1d mechanical bonus costs a charge.
- **Rationale**: Encourages players to weave traits into their narrative without punishing them mechanically for good storytelling.
- **Implications**: The system only tracks mechanical invocations (charge spend). Narrative references are just flavor text.

### Modifier Stacking Rule

- **Decision**: Per proposal, a player may select at most 1 Core Trait, 1 Role Trait, and 1 Bond. Each provides +1d. Maximum modifier bonus is +3d.
- **Rationale**: Bounded dice pools (skill 0–3 + modifiers 0–3 = max 6d) keep the system predictable. One-of-each forces meaningful choice about which trait to activate.
- **Implications**: Affects proposals spec — modifier selection UI/validation must enforce the 1-of-each-type rule. Bonds provide flat +1d (no bond level — see [bonds.md](bonds.md)).

### Charge Reset Mechanic

- **Decision**: The "Recharge Trait" downtime activity fully restores one trait to 5 charges. Player chooses which trait. Costs 1 FT.
- **Rationale**: Per-trait reset creates meaningful resource decisions during downtime — which trait do you need most?
- **Implications**: A player with 5 depleted traits needs 5 separate downtime activities (and Free Time) to fully recharge.

### Trait Replacement via Downtime

- **Decision**: Players can replace an existing trait (or fill a blank slot) via the "New Trait" downtime action. Player selects the target slot, either picks an existing Trait Template from the catalog or proposes a new one (name/description), and writes narrative fiction explaining the change. Submitted as a proposal for GM approval. If a new template is proposed and approved, it's added to the catalog. Blank slots are the default selection.
- **Rationale**: Allows character growth and evolution while keeping it deliberate (costs Free Time, requires GM approval). Catalog grows organically from player proposals.
- **Implications**: New traits start at full charge (5). The replaced trait moves to Past (`is_active = false`, event history preserved). This is a downtime activity, so it follows the proposal workflow.

### Trait Setup

- **Decision**: Traits are added after character creation via GM direct action. Not part of the character creation payload.
- **Rationale**: Keeps the character creation endpoint simple. Trait setup is a separate step — consistent with how Bonds are also set up separately.
- **Implications**: A newly created character has blank trait slots until the GM fills them.

---

## API Endpoints

### Trait Template Catalog (GM-only CRUD)

- `GET /api/v1/trait-templates` — list all templates (filters: `?type=core|role`, `?is_deleted=false` default)
- `POST /api/v1/trait-templates` — create a new template (GM). Body: `{name, description, type}`.
- `GET /api/v1/trait-templates/{id}` — template detail
- `PATCH /api/v1/trait-templates/{id}` — update name/description only (GM). Type is immutable.
- `DELETE /api/v1/trait-templates/{id}` — soft delete (GM). Existing trait instances keep their `template_id` reference but the template is hidden from the catalog. Instances remain functional.

### PC Trait Management

- `GET /api/v1/characters/{id}` — full sheet includes all trait slots (active, blank, and past/retired)
- GM trait management (assign/update/remove instances): via `POST /api/v1/gm/actions` with action types `create_trait`, `modify_trait`, `retire_trait`. See [actions.md](actions.md).
- "New Trait" downtime action: submitted as a proposal via `POST /api/v1/proposals`
- "Recharge Trait" downtime action: submitted as a proposal via `POST /api/v1/proposals`

No dedicated trait instance endpoints for players — all player-initiated trait changes go through proposals.

### Group/Location Trait Management

- `GET /api/v1/groups/{id}` — Group detail includes all descriptive trait slots
- `GET /api/v1/locations/{id}` — Location detail includes all Feature trait slots
- GM trait management (create/update/clear descriptive traits on Groups and Locations): via `POST /api/v1/gm/actions` with action types `create_trait`, `modify_trait`, `retire_trait`. See [actions.md](actions.md).
- Player influence: `work_on_project` proposal targeting a Group/Location Story/Arc → GM resolves trait change

---

## Implications for Other Specs

| Spec | Implication |
|------|-------------|
| [bonds](bonds.md) | Unified table architecture — shared with all trait types. Bond slot types defined in bonds.md. |
| [game-objects](game-objects.md) | 🔄 Group traits simplified: 10 flat descriptive slots (no Culture/Training/Asset categories). Location Feature traits: 5 interchangeable slots. Both reference traits.md as authoritative. |
| [actions](actions.md) | PC modifier selection: max 1 Core + 1 Role + 1 Bond per proposal. Each gives +1d. Charge spend happens on approval. Group/Location trait changes via work_on_project (no new proposal types). `new_trait` uses count-based slots with `retire_trait_id`. GM trait management via `POST /gm/actions`. |
| [downtime](downtime.md) | Two PC trait activities: "Recharge Trait" (full restore, one trait) and "New Trait" (replace/fill a slot). Both cost 1 FT. |
| [character-core](character-core.md) | PC traits are sub-entities of the Character sheet. Past/retired traits shown separately. |
| [events](events.md) | All trait changes logged: PC charge changes, replacements, retirements, AND Group/Location trait overwrites (before/after). |
| [architecture/data-model](../architecture/data-model.md) | 🔄 Trait Template catalog (PC only) + unified table. `group_trait` replaces culture/training/asset types. `feature_trait` for Locations. Nullable mechanical fields. |

---

## Open Questions

_All resolved._

1. ~~**Trait Template CRUD endpoints**~~: **Resolved** — Standard REST CRUD: `GET/POST /api/v1/trait-templates`, `GET/PATCH/DELETE /api/v1/trait-templates/{id}`. All GM-only. Soft delete. PATCH accepts name/description only (type is immutable).
2. ~~**GM trait direct action endpoints**~~: **Resolved** — All GM trait management (assign/update/remove instances on Characters, create/update/clear descriptive traits on Groups/Locations) via `POST /api/v1/gm/actions` with action types `create_trait`, `modify_trait`, `retire_trait`. No sub-resource endpoints. See [actions.md](actions.md).
3. ~~**Group/Location trait management endpoints**~~: **Resolved** — Same as #2. All via `POST /api/v1/gm/actions`. No sub-resource endpoints on Groups or Locations for traits.
4. ~~**`new_trait` with proposed template**~~: **Resolved** — Auto-add on approval. When GM approves a `new_trait` proposal with proposed name/description, system automatically creates a Trait Template and links the instance.

---

_Last updated: 2026-03-13 (interrogation — resolved all open questions: trait template CRUD endpoints, auto-catalog on new_trait approval, template propagation semantics, template type immutability)_
