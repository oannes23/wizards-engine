# Actions — Domain Specification

**Status**: 🟢 Complete
**Last interrogated**: 2026-03-10
**Last verified**: 2026-03-16
**Depends on**: [character-core](character-core.md), [traits](traits.md), [bonds](bonds.md), [magic-system](magic-system.md), [game-objects](game-objects.md), [events](events.md)
**Depended on by**: [downtime](downtime.md), [events](events.md)

*Renamed from proposals.md — expanded to cover the unified action system.*

---

## Overview

The **action system** is the unified mechanism through which all actors (players, GM, system) change game state. Every state change is an **action** — a typed, validated input that produces an **event** (the structured output recording what changed).

Actions vary by **actor** and **resolution path**:

- **Player Proposal Actions**: Mechanically significant player actions that require GM approval. Submit → calculate → GM review → approve/reject → event. Three sub-categories: Actions (session play), Downtime Actions (auto-cost 1 FT), and System Proposals (auto-generated).
- **Player Direct Actions**: Low-stakes player actions that bypass proposals and create events immediately. Examples: Find Time, Use Magic Effect, Retire Magic Effect, editing notes/description.
- **GM Actions**: GM direct actions that validate, apply changes, and create events immediately via `POST /api/v1/gm/actions`. The GM has more and higher-power action types but the underlying system is the same — structured input, validated, event output.

All paths produce identical **Event** rows. The proposal workflow is an approval gate, not a fundamentally different system.

The system does **not** record dice results. Dice are rolled at the physical table; the GM writes what happened in narrative. The system tracks the mechanical state changes, not the roll outcomes.

---

## Core Concepts

### Proposal Workflow

1. **Player submits**: selects an action type, writes narrative describing their action, selects modifiers and any type-specific details. System validates affordability (rejects immediately if resources insufficient).

2. **System calculates**: computes the `calculated_effect` — a typed structure including both outcome (dice pool, effect value) and all costs (trait charges, FT, Plot, etc.). Stores on the proposal.

3. **GM reviews**: GM sees the proposal with player-written narrative, selections, and calculated effect (outcome + costs). Rolls dice at the physical table.

4. **GM approves**: GM provides narrative outcome (or accepts the player's narrative as-is), optional overrides to any calculated values, and any type-specific outcome data (e.g., Magic Effect details). Optionally attaches one **rider event** for side effects. System auto-applies all mechanical consequences.

5. **GM rejects**: No state changes. GM provides a rejection note. Player can revise (mutate in place) and resubmit.

### Action Types

Three categories, 10 proposal types total (plus 2 former downtime types promoted to direct actions — see Player Direct Actions below):

**Actions** (session play):

| Type | Description | Base | Supports Modifiers | Supports Plot |
|------|-------------|------|-------------------|---------------|
| `use_skill` | Standard action using a Skill | Skill level (0–3) | Yes | Yes |
| `use_magic` | Freeform magic (see [magic-system](magic-system.md)) | Magic Stat level (0–5) + sacrifice dice | Yes | Yes |
| `charge_magic` | Recharge/boost an existing Magic Effect | Magic Stat level (0–5) + sacrifice dice | Yes | Yes |

**Downtime Actions** (between sessions, all auto-cost 1 Free Time):

| Type | Description | Calculated Effect | Supports Modifiers |
|------|-------------|------------------|-------------------|
| `regain_gnosis` | Study/meditate to regain Gnosis | 3 + lowest Magic Stat + modifiers (up to +3) | Yes |
| `work_on_project` | Advance a personal project (Story/Arc) | Narrative note added | No |
| `rest` | Heal accumulated Stress | 3 + modifiers (up to +3) | Yes |
| `new_trait` | Replace a trait or fill a blank slot | Structural change | No |
| `new_bond` | Replace a bond or fill a blank slot | Structural change | No |

**System Proposals** (auto-generated):

| Type | Description | Trigger |
|------|-------------|---------|
| `resolve_clock` | Resolve a completed clock | Clock reaches completion (progress >= segments) |
| `resolve_trauma` | Resolve a Trauma event | Character Stress hits effective max |

**Downtime structural rule**: All Downtime Action proposals automatically cost 1 Free Time, deducted on approval. This cost is implicit — not specified by the player. The two direct downtime actions (`recharge_trait`, `maintain_bond`) also cost 1 FT, deducted immediately on execution.

**Skill training**: Increasing a Skill level is a project — players use `work_on_project` targeting a Story/Arc for the skill they're training. GM resolves when the narrative warrants it.

### Proposal Data Model

**Common fields** (all proposals):

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| id | string | yes | Primary key (ULID) |
| character_id | ref → Character | no | Submitting character. Null for system-generated proposals. |
| action_type | enum | yes | One of the 10 proposal types |
| origin | enum | yes | `player` or `system`. Distinguishes player-submitted from system-generated. |
| narrative | text | conditional | Player's description of their action (player-written). GM can edit on approval. **Required for downtime actions; optional (nullable) for session actions** (`use_skill`, `use_magic`, `charge_magic`). Players can PATCH narrative onto pending proposals. |
| modifiers | JSON | no | `{core_trait_id?, role_trait_id?, bond_id?}` — up to 1 of each |
| plot_spend | integer | no | Number of Plot points spent (default 0) |
| details | JSON | no | Type-specific data (see below) |
| calculated_effect | JSON | no | Typed per action type — includes outcome AND costs (see below) |
| status | enum | yes | `pending`, `approved`, `rejected` |
| gm_narrative | text | no | GM's outcome narrative (set on approval). If null, the player's narrative is used as the event narrative. |
| gm_overrides | JSON | no | GM-modified values that **replace** corresponding fields in calculated_effect |
| rejection_note | text | no | GM's reason for rejection |
| rider_event_id | ref → events | no | FK to rider event, if one was created on approval (see below) |
| created_at | datetime | yes | Auto |
| updated_at | datetime | yes | Auto |

**Type-specific `details` JSON**:

| Action Type | Details Fields |
|-------------|---------------|
| `use_skill` | `{skill: string}` — which of the 8 hardcoded skills |
| `use_magic` | `{intention: string, symbolism: string, sacrifice_list: [{type, amount, target_id?}], suggested_stat: string}` |
| `charge_magic` | `{intention: string, symbolism: string, sacrifice_list: [...], suggested_stat: string, target_effect_id: string}` |
| `regain_gnosis` | `{}` — no extra details |
| `work_on_project` | `{story_id: string}` — which Story/Arc to progress |
| `rest` | `{}` — no extra details |
| `new_trait` | `{slot_type: "core"\|"role", template_id?: string, proposed_name?: string, proposed_description?: string, retire_trait_id?: string}` — retire_trait_id required when at max active count for that slot_type |
| `new_bond` | `{target_type: string, target_id: string, retire_bond_id?: string}` — retire_bond_id required when at max active bond count |
| `resolve_clock` | `{clock_id: string, associated_object_type: string, associated_object_id: string}` — auto-populated by the system |
| `resolve_trauma` | `{character_id: string}` — auto-populated by the system |

### Typed Calculated Effect Schemas

The `calculated_effect` field is a **typed structure per action type**, including both the computed outcome and all resource costs. The GM can override any field via `gm_overrides` (replacement semantics — overridden values replace calculated values).

**Action types** (dice-based):

```
use_skill: {
  dice_pool: int,           // Skill level + modifier count
  skill: str,               // The skill name
  skill_level: int,         // The character's level in that skill
  modifiers: [{id, type, name, bonus: 1}],  // Which traits/bonds selected
  plot_spend: int,
  costs: {
    trait_charges: [{trait_id, cost: 1}],  // Per invoked trait
    plot: int               // Plot points consumed
  }
}

use_magic: {
  suggested_stat: str,      // Magic stat the player suggested
  stat_level: int,          // Character's level in that stat
  dice_pool: int,           // Magic Stat + sacrifice dice + modifier count
  sacrifice_dice: int,      // Dice from sacrifice (after tiered conversion)
  total_gnosis_equivalent: int,  // Total Gnosis equivalent from all sacrifices
  sacrifice_details: [...], // Per-entry sacrifice breakdown with gnosis_equivalent
  modifiers: [{id, type, name, bonus: 1}],
  costs: {
    gnosis: int,            // Gnosis directly spent as sacrifice
    stress: int,            // Stress from sacrifice (if any)
    free_time: int,         // FT from sacrifice (if any)
    bond_sacrifices: [{bond_id, name}],    // Bonds sacrificed (→ Past)
    trait_sacrifices: [{trait_id, name}],  // Traits sacrificed (→ Past)
    trait_charges: [{trait_id, cost: 1}],  // Per invoked trait modifier
    plot: int
  }
}

charge_magic: {
  // Same shape as use_magic, plus:
  suggested_stat: str,
  stat_level: int,
  dice_pool: int,
  sacrifice_dice: int,
  total_gnosis_equivalent: int,
  sacrifice_details: [...],
  modifiers: [{id, type, name, bonus: 1}],
  target_effect: {id, name, effect_type, power_level, charges_current, charges_max},
  costs: {
    gnosis: int,
    stress: int,
    free_time: int,
    bond_sacrifices: [{bond_id, name}],
    trait_sacrifices: [{trait_id, name}],
    trait_charges: [{trait_id, cost: 1}],
    plot: int
  }
}
```

**Downtime types** (formula-based):

```
regain_gnosis: {
  gnosis_gained: int,       // 3 + lowest Magic Stat + modifiers
  costs: {
    free_time: 1,
    trait_charges: [{trait_id, cost: 1}]
  }
}

rest: {
  stress_healed: int,       // 3 + modifiers
  costs: {
    free_time: 1,
    trait_charges: [{trait_id, cost: 1}]
  }
}

work_on_project: {
  target_story_id: string,
  costs: { free_time: 1 }
}

new_trait: {
  slot_type: "core" | "role",
  replacing: {trait_id, name} | null,  // Null if filling blank slot
  costs: { free_time: 1 }
}

new_bond: {
  target: {type, id},               // The new bond target
  replacing: {bond_id, name} | null, // Null if filling blank slot
  costs: { free_time: 1 }
}
```

**System types**:

```
resolve_clock: {}  // No calculation — GM fills in narrative and outcome
resolve_trauma: {}  // No calculation — GM fills in trauma details
```

### Narrative Requirements

**Session actions** (`use_skill`, `use_magic`, `charge_magic`): Narrative is **optional** on submission. Players can PATCH narrative onto pending proposals after the fact. This supports fast table flow — the verbal description at the table is the primary narrative, and typed text can be added later.

**Downtime actions** (`regain_gnosis`, `work_on_project`, `rest`, `new_trait`, `new_bond`): Narrative is **required** on submission. These actions happen between sessions where there's time to write.

**Direct actions** (`recharge_trait`, `maintain_bond`): Narrative is **required**. These bypass GM approval but still need fiction grounding.

### Player-Written Narratives

Players write the narrative on proposal submission — describing what their character is doing. When the GM approves:
- If the GM provides `gm_narrative`, that becomes the event narrative.
- If `gm_narrative` is null/empty, the player's `narrative` is used as the event narrative.
- The GM can also reject with a note asking the player to revise their narrative.

This reduces GM workload — players describe their own actions, the GM is an arbiter.

### GM Approval Payload

When the GM approves, they provide:

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| gm_narrative | text | no | What happened. If omitted, player's narrative is used. |
| overrides | JSON | no | **Replaces** fields in `calculated_effect`. E.g., `{"gnosis_gained": 10}` replaces the calculated value. `{"costs": {"free_time": 0}}` waives the FT cost. |
| actual_stat | string | no | For magic actions: the actual Magic Stat used (may differ from player's `suggested_stat`) |
| style_bonus | integer | no | For magic actions: hidden GM-only Gnosis bonus |
| effect_details | JSON | no | For `use_magic`: `{name, description, type, power_level, charges_max?}` — the Magic Effect to create |
| charges_added | integer | no | For `charge_magic` on charged effects: added to `charges_current` and `charges_max` |
| power_boost | integer | no | For `charge_magic` on permanent effects: added to `power_level` (capped at 5) |
| bond_strained | boolean | no | If true, +1 stress applied to the bond used as a modifier. Default false. |
| force | boolean | no | Set true to force-approve when re-validation fails (409 retry). Ignored on normal approvals. |
| rider_event | JSON | no | Optional single rider event (see below) |

**Override semantics**: Overrides **replace** corresponding fields in `calculated_effect`. If the GM sets `costs.gnosis: 0`, no Gnosis is deducted regardless of what was calculated. Unspecified fields use the calculated values.

The system then auto-applies (using overridden values where present):
1. **Costs**: trait charge decrements, Free Time (downtime), Plot, Gnosis sacrifice, Stress sacrifice
2. **Outcomes**: Stress healing (rest), Gnosis gain (regain_gnosis), Magic Effect creation, trait/bond retirement + replacement (new_trait, new_bond), narrative note on Story (work_on_project)
3. **Side effects**: Bond stress +1 if GM flags strain, Trauma cascade if Stress sacrifice hits max

### Rider Events

On approval, the GM can optionally attach **one rider event** — a bundled GM direct-action event that fires atomically in the same transaction as the approval event. The rider event:

- Has its own targets, changes, narrative, and visibility
- Same schema as any Event (see [events.md](events.md))
- Stored as a separate Event row with `parent_event_id` linking to the approval event
- Created in the same database transaction

**Use cases:**
- Side effects alongside approval: "your skill check succeeds AND the clock advances +2 AND this NPC reacts"
- Clock resolution: GM fills in `resolve_clock` narrative and attaches a rider event with world state changes

**Rider event payload** (in approval request):
```
rider_event: {
  targets: [{type, id}],
  changes: {field: {before, after}},
  narrative: string,
  visibility: string,  // One of 7 visibility levels
  metadata: {}         // Optional
}
```

### System Proposals: resolve_clock

When a Clock reaches completion (progress >= segments), the system auto-generates a `resolve_clock` proposal:

- `origin`: `system`
- `character_id`: null
- `status`: `pending`
- `action_type`: `resolve_clock`
- `details`: `{clock_id, associated_object_type, associated_object_id}` — auto-populated from the clock's polymorphic association
- `narrative`: auto-generated stub (e.g., the clock's name)
- `calculated_effect`: `{}` — no calculation needed

The GM resolves it by approving with narrative describing the outcome, optionally attaching a rider event with world state changes. This extends the **Deferred Narrative Resolution** principle — the clock tracked mechanical progress, the resolution is written when it completes.

### System Proposals: resolve_trauma

When a Character's Stress hits its effective max (`9 - count(trauma_bonds)`), the system auto-generates a `resolve_trauma` proposal:

- `origin`: `system`
- `character_id`: the affected character
- `status`: `pending`
- `action_type`: `resolve_trauma`
- `details`: `{character_id}` — auto-populated
- `narrative`: auto-generated stub (e.g., "Stress max reached — Trauma must be resolved")
- `calculated_effect`: `{}` — no calculation needed; GM determines the outcome

**Idempotent**: Only generated if no pending `resolve_trauma` proposal exists for that character.

The GM resolves it by:
1. Choosing which active bond becomes the Trauma (`trauma_bond_id` in `gm_overrides`)
2. Providing the trauma name and description (`trauma_name`, `trauma_description` in `gm_overrides`)
3. Optionally attaching a rider event for narrative consequences

**On approval**, the system atomically:
- Retires the chosen bond to Past (`is_active = false`)
- Creates a new Trauma bond (`is_trauma = true`, no target, fresh charges at 5, degradation 0)
- Resets character Stress to 0
- All mutations recorded in a single event (compound consequence)

This parallels the `resolve_clock` pattern — the system detects a boundary condition, generates a pending proposal, and the GM resolves it with narrative and mechanical details.

### Modifier Stacking

Per proposal, the player may select at most:
- **1 Core Trait** (+1d to dice pool, costs 1 charge)
- **1 Role Trait** (+1d to dice pool, costs 1 charge)
- **1 Bond** (+1d to dice pool, may strain per GM decision)

Maximum modifier bonus: **+3d** on top of the base.

For downtime actions that support modifiers (`regain_gnosis`, `rest`), each selected modifier adds **+1 to the calculated effect** (not +1d — these are fixed formulas, not dice rolls). Charges are still spent.

### Plot Spend

Plot is declared on submission. Each Plot spent places a **guaranteed success** (a die showing 6) on the table before rolling. Not an extra die — a guaranteed result.

Plot can also be used for more flexible purposes (surviving impossible odds, narrative tweaks). The GM has final say on flexible uses.

No cap on Plot spend per proposal.

### Dice Pool Calculations

**Use Skill**:
- Base = Skill level (0–3)
- Modifiers: up to +3d (Core/Role/Bond)
- Plot: +N guaranteed 6s
- **Total dice pool**: 0–6d + Plot successes

**Use Magic / Charge Magic**:
- Base = Magic Stat level (0–5)
- Sacrifice dice = total Gnosis equivalent via tiered table (see [magic-system](magic-system.md))
- Modifiers: up to +3d (Core/Role/Bond)
- Style bonus: hidden GM Gnosis (added to sacrifice total before conversion)
- Plot: +N guaranteed 6s
- **Total dice pool**: 0–5 + sacrifice dice + 0–3d modifiers + Plot successes

### Downtime Effect Calculations

| Type | Formula |
|------|---------|
| `regain_gnosis` | 3 + lowest Magic Stat level + modifiers (0–3) |
| `rest` | 3 + modifiers (0–3) Stress healed |
| `work_on_project` | Narrative note added to target Story |
| `new_trait` | Old trait → Past, new trait at 5 charges (or fills blank) |
| `new_bond` | Old bond → Past, new bond at stress 0 (or fills blank) |
| `recharge_trait` *(direct action)* | Fixed: restore selected trait to 5 charges |
| `maintain_bond` *(direct action)* | Fixed: selected bond charges → effective max |

### Revision Flow

Proposals can be edited in `pending` or `rejected` status:

**Pending proposals**: Player PATCHes before GM review (fix mistakes, change modifiers). System auto-recalculates `calculated_effect`. Status stays `pending`.

**Rejected proposals**: Mutated in place:
1. GM rejects with a note explaining what needs to change
2. Player PATCHes the proposal fields (narrative, modifiers, details, etc.)
3. System **auto-recalculates** `calculated_effect` and reverts status to `pending`
4. GM reviews the updated version

Single proposal ID throughout the conversation. Edit history captured in the event log.

### Resource Validation & Timing

1. **On submit**: System validates the player can afford all costs (trait charges, Free Time, Plot, Gnosis sacrifice, etc.). Rejects immediately if insufficient.
2. **On revision**: System re-validates and recalculates on PATCH.
3. **On approval**: System re-validates affordability. If the player can no longer afford it, the system returns **409 Conflict** with a body listing insufficient resources. GM retries with `force: true` to confirm force-approval. GM authority trumps validation.
4. **Deduction**: Resources are deducted only on approval, never on submission.

### Concurrency

Players can have **unlimited pending proposals** simultaneously. No resource locking between proposals. The system re-validates on each approval. If two proposals compete for the same resources, only the first approved succeeds; the second will trigger a re-validation warning.

---

## GM Actions

The GM has direct actions available via `POST /api/v1/gm/actions`. These validate, apply changes, and create events immediately — no proposal queue. The GM is just another actor with higher-power action types; the underlying system (structured input → validated → event output) is the same.

### GM Action Endpoint

```
POST /api/v1/gm/actions
{
  action_type: string,           // One of the GM action types (see catalog below)
  targets: [{type, id}],         // Affected Game Objects
  changes: {...},                // Type-specific payload (see per-type details)
  narrative: string,             // GM narrative describing the action
  visibility?: string            // Optional override; defaults per action_type
}
```

### GM Action Type Catalog

| action_type | Purpose | Default Visibility |
|-------------|---------|-------------------|
| `modify_character` | Change meters, skills, magic_stats on a Character | `gm_only` |
| `modify_group` | Change tier, notes on a Group | `gm_only` |
| `modify_location` | Change notes on a Location | `gm_only` |
| `create_bond` | Create a new bond between Game Objects | `bonded` |
| `modify_bond` | Change bond stress, labels, description | `bonded` |
| `retire_bond` | Set bond `is_active = false` | `bonded` |
| `create_trait` | Assign a Trait Template to a character slot | `bonded` |
| `modify_trait` | Change charges, name, description on a trait | `bonded` |
| `retire_trait` | Set trait `is_active = false` | `bonded` |
| `create_effect` | Create a Magic Effect on a character | `bonded` |
| `modify_effect` | Change power_level, charges on a Magic Effect | `bonded` |
| `retire_effect` | Set Magic Effect `is_active = false` | `bonded` |
| `award_xp` | Award Magic Stat XP to a character | `private` |
| `modify_clock` | Change progress, segments on a Clock | `bonded` |

Each action type has its own validation rules and `changes` payload shape (defined per-type in implementation). The GM can override visibility on any action.

### GM Action Validation

- **Decision**: The system validates FK references and structural correctness. Meter fields are **clamped** to their documented ranges (not rejected) — values outside range are silently clamped and the change entry is annotated with `"clamped": true`. Skills are clamped to 0–3, Magic Stat levels to 0–5, Magic Stat XP to 0–4. Stress is clamped to `0–9` (the hard upper bound; the effective stress max `9 - trauma_count` is enforced as the Trauma trigger, not a hard cap). Gnosis 0–23, Free Time 0–20. Plot has no practical upper bound (large sentinel).
- **Rationale**: Clamping is more forgiving than rejection — a GM typo doesn't abort the operation. The `clamped` annotation preserves observability. The GM is the final authority so enforcement is lenient.
- **Implications**: Pydantic validates structure; application code validates FK references and applies clamping. Out-of-range values are accepted and silently corrected. The `changes` field records the clamped `after` value with `"clamped": true` so consumers can see when clamping occurred.

### GM Action Event Types

- **Decision**: GM actions reuse domain event types (e.g., `character.stress_changed`, `bond.created`) with `actor_type: "gm"`. No `gm.*` event type prefix.
- **Rationale**: Unifies the event log — the same kind of state change produces the same event type regardless of who triggered it. Filter GM vs player actions via the `actor_type` field, which already exists.
- **Implications**: No ~14 new `gm.*` event types. The event type catalog in events.md remains unchanged. `actor_type` is the distinguishing field.

### GM Action Output

GM actions produce the same Event rows as proposal approvals:
- `actor_type: "gm"`, `actor_id: GM's user ID`
- `type`: domain event type (e.g., `character.stress_changed`, `bond.created`) — same types as player-caused events
- `changes`, `targets`, `narrative`, `visibility` from the request
- `session_id` auto-captured from Active session

---

## Player Direct Actions

Low-stakes player actions that bypass proposals and create events immediately:

| Action | Endpoint | Effect |
|--------|----------|--------|
| Edit notes/description | `PATCH /api/v1/characters/{id}` | Updates character fields |
| Find Time | `POST /api/v1/characters/{id}/find-time` | Converts 3 Plot → 1 FT |
| Use Magic Effect | `POST /api/v1/characters/{id}/effects/{id}/use` | Decrements 1 charge, logs event |
| Retire Magic Effect | `POST /api/v1/characters/{id}/effects/{id}/retire` | Sets `is_active = false`, frees cap |
| Recharge Trait | `POST /api/v1/characters/{id}/recharge-trait` | Restores selected trait to 5 charges, costs 1 FT. Body: `{trait_instance_id, narrative}`. Narrative required. |
| Maintain Bond | `POST /api/v1/characters/{id}/maintain-bond` | Restores selected bond charges to effective max, costs 1 FT. Body: `{bond_instance_id, narrative}`. Narrative required. |

All player direct actions validate ownership and produce events.

---

## Decisions

### Action Type Enumeration

- **Decision**: 10 proposal types in three categories — Actions (`use_skill`, `use_magic`, `charge_magic`), Downtime Actions (`regain_gnosis`, `work_on_project`, `rest`, `new_trait`, `new_bond`), and System Proposals (`resolve_clock`, `resolve_trauma`). Plus 5 direct player actions (`find_time`, `use_effect`, `retire_effect`, `recharge_trait`, `maintain_bond`). `recharge_trait` and `maintain_bond` were promoted from downtime proposals to direct actions — they have fixed outcomes and no meaningful GM decision point.
- **Rationale**: Covers all player-initiated mechanical actions plus system-generated prompts. Clean split between session play, downtime, system triggers, and direct actions. System proposals reuse the same proposal model. Direct actions avoid unnecessary queue overhead for predictable operations.
- **Implications**: Each proposal type has its own validation and calculation logic in Python. The `action_type` enum drives which `details` fields are required. Direct actions have their own endpoints.

### resolve_clock as Same Model

- **Decision**: System proposals (`resolve_clock`, `resolve_trauma`) share the proposals table with player proposals. `character_id` is nullable for `resolve_clock`, set to the affected character for `resolve_trauma`. An `origin` field (`player` | `system`) distinguishes player-submitted from system-generated proposals.
- **Rationale**: Reuses the existing approval workflow. The GM approves system proposals the same way as any proposal. Avoids a separate model for system-generated types.
- **Implications**: `character_id` becomes nullable. `origin` field added. System proposals have no modifiers, no plot_spend, no costs.

### Typed Calculated Effect Per Action Type

- **Decision**: The `calculated_effect` field is a structured object with a known schema per action type, including both outcome AND all resource costs. E.g., `use_skill: {dice_pool: 4, modifiers: [...], costs: {trait_charges: [...], plot: 2}}`.
- **Rationale**: Typed schemas are readable, validatable, and provide clear override points for the GM. Including costs means the GM sees exactly what will be deducted — no surprises. The system pre-computes; the GM tweaks if needed.
- **Implications**: Each action type has a Pydantic schema for its calculated effect. GM overrides replace fields within this structure.

### GM Override Replaces Calculated Values

- **Decision**: The `gm_overrides` field **replaces** corresponding fields in `calculated_effect`. Overrides are not additive deltas — they are replacement values. Unspecified fields retain calculated values.
- **Rationale**: Simpler mental model. "GM sets gnosis cost to 0" means gnosis cost is 0, not "subtract something from the calculated cost." The GM sees calculated values and changes what they disagree with.
- **Implications**: Override application is a merge: `final_effect = {**calculated_effect, **gm_overrides}` (deep merge for nested objects like `costs`).

### Narrative Only — No Dice Recording

- **Decision**: The system does not record dice values or outcome tiers. Dice are rolled at the physical table. The GM writes narrative describing what happened. The system tracks mechanical state changes (resource deltas, effects created) but not the roll.
- **Rationale**: The game is played at the table. The system is a state tracker, not a VTT. Recording dice adds complexity without value — the narrative IS the outcome.
- **Implications**: No dice result fields on proposals. No success tier enum. The GM's narrative and overrides are the complete outcome.

### Player-Written Narratives

- **Decision**: Players write the narrative on submission. The GM can accept it as-is (approve without providing `gm_narrative`), edit it, or reject for revision. The player's narrative becomes the event narrative unless the GM overrides. **For session actions** (`use_skill`, `use_magic`, `charge_magic`), narrative is **optional** on submission — players can PATCH it onto pending proposals later. For downtime actions, narrative remains required. For direct actions (`recharge_trait`, `maintain_bond`), narrative is required.
- **Rationale**: Reduces GM workload. Players describe their own actions. The GM is an arbiter, not a narrator-of-everything. Optional narrative on session actions supports fast table flow — the verbal action at the table is primary, typed text can follow.
- **Implications**: `narrative` is required for downtime proposals and direct actions; optional for session action proposals. `gm_narrative` is optional on approval — if absent, player narrative is used.

### Rider Events on Approval

- **Decision**: The GM can optionally attach **one** rider event when approving a proposal. The rider is a bundled GM direct-action event created atomically in the same transaction. Same Event schema, separate row with `parent_event_id`.
- **Rationale**: GMs often need to narrate side effects alongside approval. Bundling avoids multiple manual steps. One rider is sufficient — compound side effects go in the rider's `changes` field.
- **Implications**: Approval endpoint accepts optional `rider_event` payload. Rider event stored as separate Event row linked via `parent_event_id` (see [events.md](events.md)).

### Auto-Recalculate on Revision

- **Decision**: When a player PATCHes a rejected proposal, the system automatically recalculates `calculated_effect` and reverts status to `pending`. The PATCH is the resubmit — one step.
- **Rationale**: Simplest UX. The player edits and the system handles recalculation. No separate "resubmit" action needed.
- **Implications**: PATCH handler must trigger the calculation pipeline. Re-validates affordability as part of recalculation.

### Downtime Actions Auto-Cost 1 Free Time

- **Decision**: All Downtime Actions automatically cost 1 Free Time, deducted on approval. This is implicit — not player-specified.
- **Rationale**: Uniform cost keeps the downtime economy simple. 1 FT per action means players make meaningful choices about how to spend their limited Free Time.
- **Implications**: Downtime proposals always check Free Time >= 1 on validation. All downtime activity costs are standardized.

### Skill Training via Projects

- **Decision**: Increasing a Skill level uses the `work_on_project` action, targeting a Story/Arc for the skill being trained. No dedicated skill training action type.
- **Rationale**: Skill growth is narrative — it should feel like a journey, not a button press. Using the project system means the GM decides when training is "complete."
- **Implications**: Skill level changes are GM direct actions triggered when the project Story is resolved.

### Rest Downtime Action

- **Decision**: `rest` heals 3 Stress base + up to +3 from trait/bond invocation (standard stacking). Costs 1 FT.
- **Rationale**: Stress healing should be meaningful but not trivial. The 3–6 range means a character at Stress 9 needs 2–3 rest actions to fully recover.
- **Implications**: Stress healing formula is hardcoded.

### Maintain Bond (Renamed)

- **Decision**: `maintain_bond` replaces "Heal Bond Stress" from the bonds spec. Same mechanic: fully restores selected bond's stress to 0. Costs 1 FT.
- **Rationale**: "Maintain" better conveys the ongoing nature of relationship upkeep. The mechanic is unchanged.
- **Implications**: Bonds spec and glossary need terminology update.

### Revision Mutates in Place

- **Decision**: Revising a rejected proposal mutates the existing record. Status reverts to `pending`. Same proposal ID throughout.
- **Rationale**: Simplest model for the GM-player conversation. No proposal proliferation. Edit history is captured in the event log, not in multiple proposal records.
- **Implications**: PATCH endpoint updates fields on an existing proposal with status=rejected. Auto-recalculates and reverts to pending.

### GM Full Override

- **Decision**: The GM can modify any calculated value before approving. Overrides replace calculated values. GM can also force-approve proposals that fail re-validation.
- **Rationale**: The GM is the final arbiter. The system assists but never overrides GM judgment.
- **Implications**: Approval payload includes `overrides` field with replacement semantics. Force-approval bypasses resource checks.

### Binary Approve/Reject

- **Decision**: No intermediate "request changes" status. Only `pending`, `approved`, and `rejected`. GM rejects with a note if revisions are needed.
- **Rationale**: Simplest state machine. "Reject with note → revise → resubmit" achieves the same result as a separate "changes requested" state.
- **Implications**: Three-value status enum. Rejected proposals remain mutable.

### Validated on Submit, Deducted on Approval

- **Decision**: System validates resource affordability on submit (rejects if insufficient). Deduction happens only on approval. System re-validates before applying and warns GM if resources changed.
- **Rationale**: Prevents obviously invalid submissions while avoiding complex resource locking. Re-validation catches drift. GM force-approval handles edge cases.
- **Implications**: Two validation passes per proposal lifecycle (submit + approval). Warning mechanism on approval for insufficient resources.

### Unlimited Concurrent Proposals

- **Decision**: Players can have multiple pending proposals simultaneously. No resource locking. System re-validates on each approval.
- **Rationale**: Avoids artificial bottlenecks. In practice, players rarely have many pending proposals. Re-validation handles resource conflicts.
- **Implications**: If two proposals compete for the same Gnosis, only the first approved succeeds.

### One Event Per Approval (Plus Optional Rider)

- **Decision**: Each approved proposal generates a single Event record capturing the entire outcome. The GM can optionally attach one rider event (separate row, linked via `parent_event_id`).
- **Rationale**: Clean event log. One action = one event. Rider events handle side effects that need independent targets/visibility.
- **Implications**: Event `changes` field must be comprehensive enough to capture all deltas in one record. Rider event is atomic with the approval.

### Plot as Guaranteed Success

- **Decision**: Each Plot spent places a guaranteed 6 (success) on the table before rolling. Plot is declared on submission. Can also be used flexibly (surviving odds, narrative tweaks) at GM discretion.
- **Rationale**: Plot should feel powerful and decisive — a guaranteed result, not just another die. Flexible use preserves narrative agency.
- **Implications**: Plot spend is part of the submission payload. System stores but doesn't mechanically process flexible Plot uses — those are handled by GM override.

### Player Projects Reuse Story/Arc

- **Decision**: Player projects are Story/Arc game objects owned by the character. `work_on_project` targets a Story and adds a narrative entry. No segmented clock — the GM resolves when the fiction warrants it.
- **Rationale**: Reuses existing game object infrastructure. Narrative progress is more appropriate than mechanical segments for personal character projects.
- **Implications**: Stories need to support narrative entry streams (may be event log entries). Group clocks remain segmented (BitD-style) — player projects use a different model.

### Re-Validation Warning: 409 + Force Flag

- **Decision**: When the GM approves a proposal but the player can no longer afford the costs, the system returns **409 Conflict** with a response body listing the insufficient resources. The GM retries with `force: true` in the approval payload to confirm force-approval.
- **Rationale**: Two-step process makes resource insufficiency explicit. The GM must consciously choose to override, not accidentally approve something the player can't afford.
- **Implications**: Approval endpoint returns 409 with a structured error body (list of insufficient resources + amounts). GM retries the same request with `force: true` added. The `force` flag is only checked when validation fails — it's ignored on normal approvals.

### Pending Proposals Are Editable

- **Decision**: Players can PATCH proposals in both `pending` and `rejected` status. Only `approved` proposals are immutable. Auto-recalculates `calculated_effect` on any PATCH.
- **Rationale**: Players should be able to fix mistakes before the GM reviews. No reason to lock pending proposals — the GM hasn't acted yet.
- **Implications**: PATCH endpoint accepts proposals with `status IN (pending, rejected)`. Both trigger recalculation. If the proposal was pending, it stays pending. If rejected, it reverts to pending.

### Charge Magic Approval Outcome

- **Decision**: For `charge_magic` approval, the GM specifies `charges_added` (integer, added to `charges_current` and `charges_max` on charged effects) and optional `power_boost` (integer, added to `power_level` on permanent effects).
- **Rationale**: Delta-based fields match the fiction — the GM says "you restore 3 charges" or "the enchantment grows stronger by 1 level." Simpler than requiring the GM to know the current values and compute final state.
- **Implications**: Approval payload for `charge_magic` includes `charges_added` (required for charged effects) and `power_boost` (required for permanent effects). System applies: `charges_current += charges_added`, `charges_max = max(charges_max, charges_current)`, `power_level += power_boost` (capped at 5).

### Bond Strain Flag

- **Decision**: The GM approval payload includes a `bond_strained: true` boolean flag. When set, the system auto-applies +1 stress to the bond used as a modifier on that proposal.
- **Rationale**: Bond strain is a common GM decision point — it needs a first-class field, not a workaround via overrides or rider events. Simple boolean toggle.
- **Implications**: `bond_strained` added to GM Approval Payload. Only meaningful when the proposal has a bond modifier. System applies +1 bond stress on the referenced bond. If bond stress hits max, standard degradation rules apply.

### Count-Based Slots (Traits and Bonds)

- **Decision**: Both traits and bonds use **count-based slots**, not indexed ordinals. The system enforces a maximum number of active items per type (2 Core Traits, 3 Role Traits, 8 PC Bonds) but assigns no fixed positional indices. Items are referenced by ID. For `new_trait`: player specifies `{slot_type, template_id/proposed_name, retire_trait_id?}`. For `new_bond`: player specifies `{target_type, target_id, retire_bond_id?}`. The `retire_*_id` is required when at max active count, optional otherwise.
- **Rationale**: Count-based is simpler and consistent between traits and bonds. No need to maintain positional mappings. Items are naturally referenced by their unique ID. Display ordering is by creation time.
- **Implications**: Replaces the previous 0-indexed ordinal system. `new_trait` and `new_bond` use retire-by-ID semantics. Validation on submit: if at max count, retire ID is required; if provided, must be active, non-trauma (bonds), and owned by the character.

### Physical Field Mapping Cross-Reference

- **Decision**: This spec describes **logical fields** for readability. The physical database column mapping is defined in [data-model.md](../architecture/data-model.md). Key mappings: `modifiers` + `details` + `plot_spend` → `selections` JSON column; `gm_narrative` + `rejection_note` → `gm_notes` TEXT column. The **API uses logical fields** (modifiers, details, plot_spend as separate top-level fields in request/response bodies). The API layer maps to/from the physical `selections` JSON column.
- **Rationale**: Avoids duplication between domain spec and data model spec. Logical fields make the API cleaner and more readable. Physical column consolidation is an implementation detail hidden from clients.
- **Implications**: Implementers should consult data-model.md for physical schema. API layer translates between logical fields (used in request/response bodies) and physical columns.

### Modifier Shape: Submission IDs, Effect Enriched

- **Decision**: Player submits bare IDs in the modifiers field: `{core_trait_id?, role_trait_id?, bond_id?}`. The system enriches these into the `calculated_effect.modifiers` array: `[{id, type, name}]` with resolved names for display.
- **Rationale**: Submission is minimal (just IDs). The calculated effect includes human-readable context (names, types) for GM review. Clear separation between input and computed output.
- **Implications**: Two representations — input IDs and enriched output array. The enriched form is what the GM sees during review.

### GM Approval Data Persisted in gm_overrides

- **Decision**: All GM approval-specific fields (`actual_stat`, `style_bonus`, `effect_details`, `charges_added`, `power_boost`, `bond_strained`) are persisted in the `gm_overrides` JSON column on the proposal record. The `force` flag is the one exception — it is a transient retry flag that is not stored.
- **Rationale**: Full audit trail on the proposal record. The event log captures what changed, but the proposal record captures what the GM decided and why. Storing in `gm_overrides` keeps the schema flexible without adding columns per field.
- **Implications**: `gm_overrides` JSON structure varies by action_type. Only `force` is transient. The `rider_event_id` FK stores the reference to the created rider event (if any).

### Rider Event Reference on Proposal

- **Decision**: The proposals table has a `rider_event_id` FK column (nullable) pointing to the rider Event row. The rider event payload is part of the approval *request* body (not stored as JSON on the proposal). After both events are created atomically, the rider event's ID is stored on the proposal.
- **Rationale**: Easy bidirectional lookup: `proposal.event_id` = approval event, `proposal.rider_event_id` = rider event, `rider_event.parent_event_id` = approval event.
- **Implications**: data-model.md needs `rider_event_id TEXT` column on the proposals table.

### Style Bonus Applied at Approval Only

- **Decision**: The `calculated_effect` is computed **without** the GM's style bonus. The player sees their submitted sacrifice total. At approval, the GM provides `style_bonus` (stored in `gm_overrides`), and the system recalculates the final sacrifice total and dice pool with the bonus included. The player never sees the bonus in the pre-approval `calculated_effect`.
- **Rationale**: Keeps the style bonus genuinely hidden from the player. The bonus is a GM reward for good narrative, not something the player can predict or game.
- **Implications**: Approval handler recalculates dice pool with style bonus added to sacrifice total before applying tiered conversion.

### work_on_project Narrative Source

- **Decision**: For `work_on_project` proposals, the proposal's `narrative` field IS the story entry text. On approval, the system creates a `story_entries` row with `text = gm_narrative ?? narrative`. No separate `entry_text` field needed.
- **Rationale**: The proposal narrative naturally describes what the character did on the project. Reusing it avoids redundant fields. The GM can override via `gm_narrative` if the entry text should differ.
- **Implications**: The story entry's `author_id` = current user, `character_id` = proposal's character_id, `story_id` = from proposal details.

### No Timeout for MVP

- **Decision**: Proposals stay pending indefinitely until the GM acts. No auto-reject or expiry. Proposals also persist across sessions — ending a session does not auto-reject or flag pending proposals.
- **Rationale**: With a small group and active GM, stale proposals are handled socially. Timeout adds complexity without clear value for MVP.
- **Implications**: No scheduled jobs or cleanup logic needed. No session-boundary cleanup.

### Proposal Withdrawal

- **Decision**: Players can hard-delete their own proposals via `DELETE /api/v1/proposals/{id}`, provided the proposal is in `pending` or `rejected` status. Approved proposals are permanent. The GM can also hard-delete any non-approved proposal (regardless of ownership). Deleted proposals are truly removed from the database — no soft-delete, no event logged.
- **Rationale**: Players should be able to clean up mistakes or abandoned proposals without GM involvement. Hard delete keeps it simple — there's no audit value in tracking withdrawn proposals. The GM needs cleanup power for spam or test data.
- **Implications**: `DELETE` endpoint added to the proposals API. Only `pending` and `rejected` proposals are deletable. Approved proposals return 400 on delete attempts.

### Proposal List Pagination

- **Decision**: ULID cursor-based pagination on `GET /api/v1/proposals`: `?after=<ulid>&limit=N`. Consistent with all other list endpoints.
- **Rationale**: ULIDs are already time-sortable. Same pagination pattern across the API reduces cognitive load.
- **Implications**: Standard paginated response shape with `next_cursor` field.

### Clean CRUD/GM Action Split

- **Decision**: Clear separation between REST CRUD endpoints and the GM actions endpoint. **CRUD endpoints** handle structural operations: creating game objects, soft-deleting game objects, and editing non-mechanical fields (name, description, notes). **GM actions** (`POST /api/v1/gm/actions`) handle all mechanical state changes: meters, skills, magic stats, attributes, bonds, traits, effects, clocks, tier, parent_id. No overlap between the two.
- **Rationale**: CRUD endpoints stay simple RESTful operations. GM actions handle all game-logic-aware state changes that produce meaningful gameplay events. One place for all mechanical operations simplifies the codebase and API documentation.
- **Implications**: All write sub-resource endpoints removed (POST/PATCH/DELETE bonds, traits, clocks under parent resources). PATCH endpoints on all game object types accept only `name`, `description`, `notes`. Creation endpoints (POST) are an exception — they accept all fields including mechanical ones (setup operation). This affects game-objects.md, character-core.md, traits.md, and bonds.md API sections.

### PATCH Scope — All Game Object Types

- **Decision**: `PATCH /api/v1/{type}/{id}` accepts only non-mechanical fields: `name`, `description`, `notes`. For Characters, the owner can PATCH their own `name`, `description`, and `notes`. The GM can PATCH these on any game object. Mechanical fields (`attributes`, `stress`, `skills`, `tier`, `parent_id`, etc.) are changed exclusively via GM actions. This rule applies consistently across Characters, Groups, and Locations.
- **Rationale**: Consistent split across all entity types. PATCH stays simple and predictable. Mechanical changes always flow through GM actions and produce proper events.
- **Implications**: Groups: `tier` changes via GM actions. Locations: `parent_id` changes via GM actions. Characters: `attributes` changes via GM actions. All produce events.

### Creation Accepts All Fields

- **Decision**: `POST` endpoints for creating game objects accept all fields — including mechanical fields like meters, skills, tier, parent_id. Creation is a setup operation exempted from the CRUD/GM split.
- **Rationale**: Requiring the GM to create a bare object and then call multiple GM actions to set initial values would be cumbersome. Creation is inherently a setup operation, not an in-play state change.
- **Implications**: POST /characters accepts full initial state (meters, skills, magic_stats, attributes). POST /groups accepts tier. POST /locations accepts parent_id. Creation still produces an event.

### Common + Extras Data Model

- **Decision**: All proposals share common fields (narrative, action_type, origin, modifiers, plot_spend). Type-specific data goes in a freeform JSON `details` field. `character_id` is nullable (null for system proposals).
- **Rationale**: Flexible — supports new action types without schema changes. Validation is per-type in Python code, not database constraints.
- **Implications**: `details` field is a JSON column. Each action type has a Pydantic validator for its expected details shape.

---

## API Endpoints

### Proposals (Player → GM Approval)
- `POST /api/v1/proposals` — submit a new proposal (player). **Canonical submission endpoint** — all player proposals go through this single endpoint with `character_id` + `action_type` in the body.
- `GET /api/v1/proposals` — list proposals (supports `?status=pending`, `?character_id=`, `?origin=player|system`, `?action_type=`, `?after=<ulid>&limit=N`)
- `GET /api/v1/proposals/{id}` — proposal detail with calculated effects
- `POST /api/v1/proposals/{id}/approve` — approve and apply (GM) — payload includes gm_narrative, overrides, magic-specific fields, optional rider_event
- `POST /api/v1/proposals/{id}/reject` — reject with note (GM)
- `PATCH /api/v1/proposals/{id}` — revise a pending or rejected proposal (player, status must be `pending` or `rejected`). Auto-recalculates. Rejected proposals revert to pending.
- `DELETE /api/v1/proposals/{id}` — hard-delete a proposal (player-owner or GM). Status must be `pending` or `rejected`. Approved proposals cannot be deleted.

### GM Actions (Direct)
- `POST /api/v1/gm/actions` — execute a GM action (GM only). Validates, applies, creates event immediately.

### Player Direct Actions
- `POST /api/v1/characters/{id}/find-time` — convert 3 Plot → 1 FT (player, no approval)
- `POST /api/v1/characters/{id}/effects/{effect_id}/use` — use a charged Magic Effect (player, costs 1 charge)
- `POST /api/v1/characters/{id}/effects/{effect_id}/retire` — retire a Magic Effect (player, frees cap)
- `POST /api/v1/characters/{id}/recharge-trait` — restore a trait to 5 charges (player, costs 1 FT, narrative required). Body: `{trait_instance_id: string, narrative: string}`
- `POST /api/v1/characters/{id}/maintain-bond` — restore a bond to effective max charges (player, costs 1 FT, narrative required). Body: `{bond_instance_id: string, narrative: string}`

---

## Implications for Other Specs

| Spec | Implication |
|------|-------------|
| [downtime](downtime.md) | 5 downtime proposal types + 2 direct actions defined with formulas. All cost 1 FT. `recharge_trait` and `maintain_bond` promoted to direct player actions. "Rest" is a new action. Skill training uses `work_on_project`. |
| [events](events.md) | 🔄 One event per approved proposal + optional rider event. GM actions reuse domain event types (no `gm.*` prefix) — distinguished by `actor_type: "gm"`. Remove any `gm.*` event type references. |
| [traits](traits.md) | 🔄 Trait slots are count-based (not indexed). `new_trait` uses `retire_trait_id`. All GM trait management via `POST /gm/actions` — remove write sub-resource endpoints. |
| [bonds](bonds.md) | 🔄 Bond +1d modifier may cause +1 bond stress. `new_bond` uses `retire_bond_id`. All GM bond management via `POST /gm/actions` — remove write sub-resource endpoints (POST/PATCH/DELETE `/{type}/{id}/bonds`). |
| [magic-system](magic-system.md) | Magic Action and Charge Action integrated as proposal types. GM creates effects in approval payload. Style bonus applied at approval via gm_overrides. |
| [character-core](character-core.md) | 🔄 PATCH `/characters/{id}` accepts only name, description, notes. `attributes` and all mechanical fields via GM actions. Remove `POST /characters/{id}/actions/{action}`. |
| [game-objects](game-objects.md) | 🔄 **Major**: Remove all write sub-resource endpoints for bonds, traits, clocks (now via `POST /gm/actions`). PATCH endpoints accept only name/desc/notes. Creation (POST) still accepts all fields. `tier` (Groups), `parent_id` (Locations) changed via GM actions. |
| [auth](auth.md) | Players submit proposals for their own character. GM approves/rejects/force-approves. GM can delete any non-approved proposal. GM actions endpoint is GM-only. |
| [architecture/data-model](../architecture/data-model.md) | 🔄 Proposals table: add `rider_event_id TEXT` FK. Remove slot_index references. `gm_overrides` stores all approval-specific fields. |

---

## Open Questions

All resolved.

---

_Last updated: 2026-03-18 (Phase 6 UX spec changes: `narrative` now optional for session action proposals; `recharge_trait` and `maintain_bond` promoted from downtime proposals to direct player actions with required narrative; two new direct action endpoints added. Previous: 2026-03-16 verified against Phase 4 implementation.)_
