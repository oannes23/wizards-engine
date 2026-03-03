# Traits — Domain Specification

**Status**: 🟢 Complete
**Last interrogated**: 2026-02-26
**Last verified**: —
**Depends on**: [character-core](character-core.md)
**Depended on by**: [proposals](proposals.md), [downtime](downtime.md)

---

## Overview

Traits represent a character's defining qualities (Core Traits) and learned abilities (Role Traits). They provide a +1d bonus to dice pools when relevant and use a charge mechanic to gate their usage. Traits can be referenced narratively at no cost; only the +1d mechanical bonus spends a charge.

Traits share a unified architecture with Bonds — see [bonds.md](bonds.md) for the full Trait/Bond instance model.

---

## Core Concepts

### Unified Trait/Bond Architecture

Traits and Bonds share a common two-layer architecture:

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
- Charges are **replenished** during downtime via the "Reset Trait Charges" activity (fully restores one trait per activity, costs Free Time)

### Trait Slots and Blank Slots

Characters have fixed trait **slots** (2 Core, 3 Role) but slots may be **blank** — not yet filled with a trait. Characters don't need all 5 traits immediately; the intent is to fill them quickly during early play.

### Past/Retired Traits

When a trait is replaced (via "New Trait" downtime action or GM action), the old Trait Instance is marked `is_active = false`. It remains on the character sheet in a **"Past" section**:
- Full event history preserved and viewable
- Cannot be selected for proposals (+1d bonus)
- Serves as a narrative record of the character's trait history

This applies equally to retired Bonds — see [bonds.md](bonds.md).

### Trait Lifecycle

1. **Created**: GM adds traits via direct action (post character creation), selecting from the Trait Template catalog. New traits start at full charge (5).
2. **Active**: Trait is available for use in proposals and downtime.
3. **Replaced**: Player submits "New Trait" downtime action to replace an existing trait or fill a blank slot. Old trait moves to Past.
4. **Retired/Past**: `is_active = false`. Viewable history, no mechanical use.
5. **GM edit**: GM can edit any trait's name/description/charge via admin CRUD at any time.

---

## Decisions

### Unified Trait/Bond Architecture

- **Decision**: Core Traits, Role Traits, and Bonds share a unified two-layer architecture: Trait Templates (definition catalog) and Trait Instances (per-character state). Core/Role Traits link to Trait Templates; Bonds link to game objects.
- **Rationale**: Unifying the model reduces complexity. All three types occupy slots on the character sheet, can be active or retired, and have event history streams.
- **Implications**: Single instance model with a slot type discriminator. See [bonds.md](bonds.md) for Bond-specific fields.

### Trait Template Catalog

- **Decision**: Trait Templates are a GM-created shared catalog. Characters pick from the catalog when adding traits. Multiple characters can share the same Trait Template. Editing a template propagates changes to all characters referencing it.
- **Rationale**: A shared catalog allows trait reuse and provides a consistent library for the GM to manage. Propagating edits keeps the template as the single source of truth for a trait's identity.
- **Implications**: Need a Trait Template CRUD for the GM. Templates exist independently of characters.

### Template Type Binding

- **Decision**: Trait Template type (`core` or `role`) is fixed on the template. Core templates can only fill Core slots; Role templates can only fill Role slots.
- **Rationale**: Clear categorization. The distinction between defining qualities (Core) and learned abilities (Role) is fundamental to the design.
- **Implications**: Template creation requires specifying a type. Slot assignment validates type match.

### No Duplicate Templates per Character

- **Decision**: A character can only have one active instance of a given Trait Template. No assigning the same template to multiple slots.
- **Rationale**: Each trait should be narratively distinct on a character. Duplicates would be mechanically redundant.

### Fixed Trait Slot Counts

- **Decision**: Characters have exactly 2 Core Trait slots and 3 Role Trait slots. Slots may be blank.
- **Rationale**: Fixed slot counts keep characters focused. Blank slots allow gradual discovery of character identity during play.
- **Implications**: Trait creation fills a slot. Trait replacement swaps within a slot. No trait addition beyond the fixed 5 slots.

### Charge Range

- **Decision**: Charge range is 0–5 for all traits.
- **Rationale**: Provides enough uses between downtimes without being unlimited.
- **Implications**: Downtime "Reset Trait Charges" activity restores charges.

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

- **Decision**: The "Reset Trait Charges" downtime activity fully restores one trait to 5 charges. Player chooses which trait. Costs Free Time.
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

Traits are managed via Trait Template catalog (GM), GM direct action, and downtime proposals:

- `GET /api/v1/characters/{id}` — full sheet includes all trait slots (active, blank, and past/retired)
- Trait Template CRUD: GM manages the shared catalog of trait definitions
- GM direct action: assign/update/remove trait instances on a character (standard GM bypass)
- "New Trait" downtime action: submitted as a proposal via `POST /api/v1/proposals`
- "Reset Trait Charges" downtime action: submitted as a proposal via `POST /api/v1/proposals`

No dedicated trait instance endpoints for players — all player-initiated trait changes go through proposals.

---

## Implications for Other Specs

| Spec | Implication |
|------|-------------|
| [bonds](bonds.md) | Unified Trait/Bond architecture — shared instance model. Bonds are a slot type alongside Core/Role. |
| [proposals](proposals.md) | Modifier selection: max 1 Core + 1 Role + 1 Bond per proposal. Each gives +1d. Charge spend happens on approval. |
| [downtime](downtime.md) | Two trait-related downtime activities: "Reset Trait Charges" (full restore, one trait) and "New Trait" (replace/fill a slot). Both cost Free Time. |
| [character-core](character-core.md) | Traits are sub-entities of the Character sheet, displayed in full-sheet endpoint. Past/retired traits shown separately. |
| [events](events.md) | Charge changes, trait replacements, and retirements are logged as events. Per-instance event history stream. |
| [architecture/data-model](../architecture/data-model.md) | Trait Template catalog + Trait Instance model. Shared with Bonds. |

---

_Last updated: 2026-02-26_
