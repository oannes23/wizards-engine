# Bonds — Domain Specification

**Status**: 🟢 Complete
**Last interrogated**: 2026-02-26
**Last verified**: —
**Depends on**: [game-objects](game-objects.md), [character-core](character-core.md)
**Depended on by**: [proposals](proposals.md), [downtime](downtime.md)

---

## Overview

Bonds represent meaningful relationships between a Character and other game objects (PCs, NPCs, Groups, Locations, etc.). They provide a flat +1d bonus when invoked in proposals and have their own stress/degradation mechanic that mirrors character Stress/Trauma. Bonds are a type of Trait Instance — they share the unified Trait/Bond architecture but reference a game object as their "template" (inheriting its name and description).

---

## Core Concepts

### Unified Trait/Bond Architecture

Bonds, Core Traits, and Role Traits share a common architecture:

1. **Trait Template** (definition layer): A GM-created catalog entry with name, description, and type. For Core/Role Traits only — Bonds use a game object as their "template" instead.
2. **Trait Instance** (character layer): A per-character record that links to either a Trait Template (Core/Role) or a game object (Bond). Holds character-specific state: charges (Core/Role) or stress (Bonds), `is_active` flag, and an event history stream.

This means Bonds are a **slot type** on the character sheet, alongside Core and Role Trait slots, all managed through the same instance model.

### Bond Structure

Each Character has **7 Bond slots**. An active Bond instance has:
- `target`: polymorphic reference to a game object (PC, NPC, Group, Location, etc.)
- `name`: inherited from target game object
- `description`: inherited from target game object
- `stress`: current bond stress (0 to effective max)
- `stress_degradations`: count of max reductions (effective max = `5 - stress_degradations`)
- `is_active`: boolean (active vs retired/past)
- `is_trauma`: boolean (true if this slot holds a Trauma)

Bond slots may be **blank** — not yet filled. Characters don't need all 7 bonds at creation.

**No Bond level.** The meaningful measure of a bond is its accumulated fiction — the stream of event paragraphs from actions involving the bond.

### Bond Stress Mechanic

Bond stress mirrors the character Stress/Trauma pattern:

- **Range**: 0 to effective max (starts at 5, decreases with degradations)
- **Gains stress from**: GM narrative actions, or +1 when GM decides a proposal bond use strains it
- **At max stress**: GM resets stress to 0, increments `stress_degradations` by 1 (effective max decreases), and narrates a bad consequence in the relationship
- **Healing**: "Heal Bond Stress" downtime activity fully restores current stress to 0. Costs Free Time.
- **Degradation reversal**: GM can reverse a degradation via direct action (decrement `stress_degradations`, restoring +1 to effective max)
- **At 0 effective max** (5 degradations): GM handles narratively — no additional mechanical rule

### +1d Bonus on Proposals

When a Bond is selected on a proposal, it provides a flat **+1d** to the dice pool. No charge cost — Bonds don't use the charge mechanic.

Per the Modifier Stacking rule (see [traits.md](traits.md)), a proposal can include at most 1 Core Trait + 1 Role Trait + 1 Bond = max +3d.

If the GM decides the bond use strains the relationship, +1 bond stress is applied.

### Trauma

When a character's Stress hits max, they gain a Trauma which occupies a Bond slot:

1. The existing Bond in the chosen slot is **retired** (`is_active = false`) and moves to the "Past" section of the character sheet. Its full event history is preserved.
2. A new Bond instance is created in the slot with `is_trauma = true`, a trauma-specific name and description (negotiated between GM and player), no target reference, and fresh stress/degradation values (stress = 0, degradations = 0).
3. Character Stress resets to 0.
4. Character effective Stress max decreases by 1 (computed: `9 - count(active trauma bonds)`).

**Fixing Trauma**: GM direct action. The GM chooses what happens — can blank the slot, create a new bond, etc. No automatic restoration of the original bond.

### Past/Retired Bonds

When a Bond is replaced (by Trauma, "New Bond" downtime action, or GM action), the old Bond instance is marked `is_active = false`. It remains on the character sheet in a "Past" section:
- Full event history preserved and viewable
- Cannot be selected for proposals (+1d bonus)
- Serves as a narrative record of the character's relationship history

This applies equally to retired Core/Role Traits — see [traits.md](traits.md).

### Bond Lifecycle

1. **Created**: GM adds a bond via direct action (post character creation), pointing to a game object target. Starts with stress = 0, degradations = 0.
2. **Active**: Bond is available for use in proposals. Stress accumulates from narrative events and proposal use.
3. **Stressed**: Bond stress at max triggers degradation (GM action). Stress resets, max decreases.
4. **Replaced**: Player submits "New Bond" downtime action or bond becomes Trauma. Old bond retires to Past.
5. **Retired/Past**: `is_active = false`. Viewable history, no mechanical use.
6. **Trauma**: `is_trauma = true`. Occupies a slot, reduces character Stress max, fixable via GM action.

---

## Decisions

### No Bond Level

- **Decision**: Bond level is removed from the model. Bonds provide a flat +1d on proposals regardless of any "strength" metric.
- **Rationale**: The meaningful depth of a bond is captured by its accumulated fiction — the stream of narrative paragraphs from actions involving the bond. A numeric level would be redundant and misleading.
- **Implications**: Simplifies the model. Bond "strength" is emergent from play, not tracked numerically.

### Bond Stress Range and Degradation

- **Decision**: Bond stress range is 0 to effective max (base 5, minus degradation count). At max stress: GM resets to 0, increments degradation, narrates consequence. At 0 effective max (5 degradations): GM handles narratively.
- **Rationale**: Mirrors the character Stress/Trauma pattern at the bond level. Creates a consistent degradation mechanic across the system.
- **Implications**: Bond model needs `stress` and `stress_degradations` fields. Effective max is computed.

### Bond Stress Sources

- **Decision**: Bond stress comes from GM narrative actions and optionally from proposal bond use (+1 stress when GM decides the use strains the bond).
- **Rationale**: GM retains control over when bonds are strained. The +1 per proposal use is a risk/reward tradeoff, but only when the GM deems it appropriate.
- **Implications**: Proposal approval may include a "strain bond" flag or the GM applies stress as a separate action after approval.

### Bond Stress Healing

- **Decision**: "Heal Bond Stress" downtime activity fully restores current bond stress to 0. Costs Free Time. Does not reverse degradations.
- **Rationale**: Full heal keeps the downtime action simple and impactful. Degradation reversal is a separate GM-controlled action.
- **Implications**: Downtime spec needs this activity. GM can separately reverse degradation via direct action.

### Blank Bond Slots

- **Decision**: Bond slots can be blank. Characters don't need all 7 bonds at creation.
- **Rationale**: Mirrors trait slots. Allows bonds to form organically during play.
- **Implications**: Bond setup is via GM direct action post-creation. Players fill bonds via "New Bond" downtime action.

### Bond CRUD Pattern

- **Decision**: Same pattern as traits. GM creates bonds via direct action. Players replace/fill bonds via "New Bond" downtime action (costs Free Time, proposal workflow for GM approval).
- **Rationale**: Consistent with the unified Trait/Bond architecture. All player-initiated changes go through proposals.
- **Implications**: No dedicated bond CRUD endpoints for players.

### Bonds as Trait Instances

- **Decision**: Bonds are a type of Trait Instance in the unified architecture. They share the same instance model as Core/Role Traits but reference a game object (instead of a Trait Template) and use stress (instead of charges).
- **Rationale**: Unifying the model reduces complexity. All three types (Core, Role, Bond) occupy slots on the character sheet, can be active or retired, and have event history streams.
- **Implications**: Single instance table/model with a slot type discriminator. Bond-specific fields (stress, stress_degradations, target, is_trauma) may be nullable or in a subtype.

### Trauma Creates New Instance

- **Decision**: When Trauma occurs, the old bond retires to Past (is_active = false, full history preserved) and a new trauma instance is created in the slot. Fresh stress/degradation values.
- **Rationale**: Preserves the narrative history of the original bond. The trauma is a distinct entity, not a mutation of the old bond.
- **Implications**: "Past" section of the character sheet shows all retired bonds/traits with their event histories.

### Trauma Fix

- **Decision**: GM chooses what happens when fixing Trauma — can blank the slot, create a new bond, or anything else. No automatic restoration of the original bond.
- **Rationale**: Flexibility for the GM. The original bond exists in Past for reference but the fiction may have moved on.
- **Implications**: Fixing Trauma is a GM direct action. The trauma instance retires to Past, slot becomes blank (or GM fills it immediately).

### Polymorphic Targets

- **Decision**: Bond targets can reference any game object type (PC, NPC, Group, Location, etc.).
- **Rationale**: Relationships aren't limited to other characters — bonds with groups, locations, and NPCs are narratively important.
- **Implications**: Requires a polymorphic reference pattern in the data model (target_type + target_id, or similar). Bond inherits name/description from target.

### Fixed Bond Slot Count

- **Decision**: Characters have exactly 7 Bond slots.
- **Rationale**: Fixed count ensures a consistent relationship web across characters.
- **Implications**: Trauma can consume at most 7 slots. Character Stress max can decrease by at most 7 (from 9 to 2).

---

## API Endpoints

Bonds are sub-resources of Characters, managed via GM direct action and downtime proposals:

- `GET /api/v1/characters/{id}` — full sheet includes all bond slots (active, blank, trauma, and past/retired)
- GM direct action: create/update/delete bonds on a character (standard GM bypass)
- "New Bond" downtime action: submitted as a proposal via `POST /api/v1/proposals`
- "Heal Bond Stress" downtime action: submitted as a proposal via `POST /api/v1/proposals`

No dedicated bond CRUD endpoints for players — all player-initiated bond changes go through proposals.

---

## Implications for Other Specs

| Spec | Implication |
|------|-------------|
| [traits](traits.md) | 🔄 Unified Trait/Bond architecture: shared instance model, Trait Template catalog, `is_active` for Past section. Replaced traits also go to Past. |
| [proposals](proposals.md) | Bond provides flat +1d. GM may optionally apply +1 bond stress on approval. Modifier stacking: max 1 Bond per proposal. |
| [downtime](downtime.md) | Two bond-related downtime activities: "Heal Bond Stress" (full restore) and "New Bond" (replace/fill slot). Both cost Free Time. |
| [game-objects](game-objects.md) | Bond targets reference game objects via polymorphic ref. Bond inherits name/description from target. |
| [character-core](character-core.md) | Bonds are sub-entities of the Character sheet. Trauma occupies bond slots. Effective Stress max computed from trauma bond count. |
| [events](events.md) | Bond stress changes, degradations, replacements, and trauma events are logged. Event history stream per bond instance. |
| [architecture/data-model](../architecture/data-model.md) | 🔄 Unified Trait/Bond instance model. Trait Template catalog. Polymorphic refs for bond targets. |

---

_Last updated: 2026-02-26_
