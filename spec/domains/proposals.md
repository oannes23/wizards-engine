# Proposals — Domain Specification

**Status**: 🟢 Complete
**Last interrogated**: 2026-03-01
**Last verified**: —
**Depends on**: [character-core](character-core.md), [traits](traits.md), [bonds](bonds.md), [magic-system](magic-system.md), [game-objects](game-objects.md)
**Depended on by**: [downtime](downtime.md), [events](events.md)

---

## Overview

The proposal system is the core gameplay loop. Players submit proposals for mechanically significant actions; the system validates and calculates effects; the GM reviews, rolls dice at the physical table, and approves with the full outcome — or rejects with a note. On approval, the system auto-applies all mechanical consequences in one transaction.

Two categories of proposals: **Actions** (during session play) and **Downtime Actions** (between sessions, auto-cost 1 Free Time each).

---

## Core Concepts

### Proposal Workflow

1. **Player submits**: selects an action type, writes narrative, selects modifiers and any type-specific details. System validates affordability (rejects immediately if resources insufficient).

2. **System calculates**: computes dice pool or effect value based on action type, base value, modifiers, and sacrifice (if applicable). Stores the calculated result on the proposal.

3. **GM reviews**: GM sees the proposal with narrative, selections, and calculated effect. Rolls dice at the physical table.

4. **GM approves**: GM provides narrative outcome, optional resource change overrides, and any type-specific outcome data (e.g., Magic Effect details). System auto-applies all mechanical consequences.

5. **GM rejects**: No state changes. GM provides a rejection note. Player can revise (mutate in place) and resubmit.

### Action Types

Two categories, 10 types total:

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
| `recharge_trait` | Fully restore charges on one trait | Fixed: restore to 5 | No |
| `maintain_bond` | Fully heal stress on one bond | Fixed: stress → 0 | No |
| `work_on_project` | Advance a personal project (Story/Arc) | Narrative note added | No |
| `rest` | Heal accumulated Stress | 3 + modifiers (up to +3) | Yes |
| `new_trait` | Replace a trait or fill a blank slot | Structural change | No |
| `new_bond` | Replace a bond or fill a blank slot | Structural change | No |

**Downtime structural rule**: All Downtime Actions automatically cost 1 Free Time, deducted on approval. This cost is implicit — not specified by the player.

**Skill training**: Increasing a Skill level is a project — players use `work_on_project` targeting a Story/Arc for the skill they're training. GM resolves when the narrative warrants it.

### Proposal Data Model

**Common fields** (all proposals):

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| id | string | yes | Primary key |
| character_id | ref → Character | yes | Submitting character |
| action_type | enum | yes | One of the 10 types |
| narrative | text | yes | Player's description of the fiction |
| modifiers | JSON | no | `{core_trait_id?, role_trait_id?, bond_id?}` — up to 1 of each |
| plot_spend | integer | no | Number of Plot points spent (default 0) |
| details | JSON | no | Type-specific data (see below) |
| calculated_effect | JSON | no | System-computed result |
| status | enum | yes | `pending`, `approved`, `rejected` |
| gm_narrative | text | no | GM's outcome narrative (set on approval) |
| gm_overrides | JSON | no | GM-modified values, resource deltas (set on approval) |
| rejection_note | text | no | GM's reason for rejection |
| created_at | datetime | yes | Auto |
| updated_at | datetime | yes | Auto |

**Type-specific `details` JSON**:

| Action Type | Details Fields |
|-------------|---------------|
| `use_skill` | `{skill: string}` — which of the 8 hardcoded skills |
| `use_magic` | `{intention: string, symbolism: string, sacrifice_list: [{type, amount, target_id?}], suggested_stat: string}` |
| `charge_magic` | `{intention: string, symbolism: string, sacrifice_list: [...], suggested_stat: string, target_effect_id: string}` |
| `regain_gnosis` | `{}` — no extra details |
| `recharge_trait` | `{trait_instance_id: string}` |
| `maintain_bond` | `{bond_instance_id: string}` |
| `work_on_project` | `{story_id: string}` — which Story/Arc to progress |
| `rest` | `{}` — no extra details |
| `new_trait` | `{slot_type: "core"\|"role", slot_index: int, template_id?: string, proposed_name?: string, proposed_description?: string}` |
| `new_bond` | `{slot_index: int, target_id: string, target_type: string}` |

### GM Approval Payload

When the GM approves, they provide:

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| gm_narrative | text | yes | What happened — the outcome of the action |
| resource_changes | JSON | no | `{meter_name: int_delta}` — e.g., `{"stress": 2, "gnosis": -3}`. Applied on top of auto-calculated costs. |
| overrides | JSON | no | Override any calculated values (dice pool, effect amount, etc.) |
| actual_stat | string | no | For magic actions: the actual Magic Stat used (may differ from player's `suggested_stat`) |
| style_bonus | integer | no | For magic actions: hidden GM-only Gnosis bonus |
| effect_details | JSON | no | For `use_magic`: `{name, description, type, power_level, charges_max?}` — the Magic Effect to create |

The system then auto-applies:
1. **Costs**: trait charge decrements, Free Time (downtime), Plot, Gnosis sacrifice, Stress sacrifice
2. **Outcomes**: Stress healing (rest), Gnosis gain (regain_gnosis), trait charge restore (recharge_trait), bond stress heal (maintain_bond), Magic Effect creation, trait/bond retirement + replacement (new_trait, new_bond), narrative note on Story (work_on_project)
3. **GM resource_changes**: any additional deltas the GM specified
4. **Side effects**: Bond stress +1 if GM flags strain, Trauma cascade if Stress sacrifice hits max

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
| `recharge_trait` | Fixed: restore selected trait to 5 charges |
| `maintain_bond` | Fixed: selected bond stress → 0 |
| `work_on_project` | Narrative note added to target Story |
| `new_trait` | Old trait → Past, new trait at 5 charges (or fills blank) |
| `new_bond` | Old bond → Past, new bond at stress 0 (or fills blank) |

### Revision Flow

Rejected proposals are mutated in place:
1. GM rejects with a note explaining what needs to change
2. Player updates the proposal fields (narrative, modifiers, details, etc.)
3. Status reverts to `pending`
4. GM reviews the updated version

Single proposal ID throughout the conversation. Edit history captured in the event log.

### Resource Validation & Timing

1. **On submit**: System validates the player can afford all costs (trait charges, Free Time, Plot, Gnosis sacrifice, etc.). Rejects immediately if insufficient.
2. **On approval**: System re-validates affordability. If the player can no longer afford it (resources changed since submission), the system **warns the GM but allows force-approval**. GM authority trumps validation.
3. **Deduction**: Resources are deducted only on approval, never on submission.

### Concurrency

Players can have **unlimited pending proposals** simultaneously. No resource locking between proposals. The system re-validates on each approval. If two proposals compete for the same resources, only the first approved succeeds; the second will trigger a re-validation warning.

### GM Bypass

**GM actions bypass proposals entirely** — the GM can directly modify any game state without approval. This is fundamental to the GM's authority over the game.

### Player Direct Actions

Some low-stakes player actions also bypass proposals:
- Editing character notes and description
- Using a charged Magic Effect (see [magic-system](magic-system.md))
- Retiring a Magic Effect (see [magic-system](magic-system.md))

Only mechanically significant state changes require proposals.

---

## Decisions

### Action Type Enumeration

- **Decision**: 10 action types in two categories — Actions (`use_skill`, `use_magic`, `charge_magic`) and Downtime Actions (`regain_gnosis`, `recharge_trait`, `maintain_bond`, `work_on_project`, `rest`, `new_trait`, `new_bond`).
- **Rationale**: Covers all player-initiated mechanical actions. Clean split between session play and downtime. Downtime actions share a structural rule (1 FT auto-cost).
- **Implications**: Each type has its own validation and calculation logic in Python. The `action_type` enum drives which `details` fields are required.

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
- **Implications**: New downtime action not in the original spec. Stress healing formula is hardcoded.

### Maintain Bond (Renamed)

- **Decision**: `maintain_bond` replaces "Heal Bond Stress" from the bonds spec. Same mechanic: fully restores selected bond's stress to 0. Costs 1 FT.
- **Rationale**: "Maintain" better conveys the ongoing nature of relationship upkeep. The mechanic is unchanged.
- **Implications**: Bonds spec and glossary need terminology update.

### Revision Mutates in Place

- **Decision**: Revising a rejected proposal mutates the existing record. Status reverts to `pending`. Same proposal ID throughout.
- **Rationale**: Simplest model for the GM-player conversation. No proposal proliferation. Edit history is captured in the event log, not in multiple proposal records.
- **Implications**: PATCH endpoint updates fields on an existing proposal with status=rejected. No new record created.

### GM Full Override

- **Decision**: The GM can modify any calculated value before approving. The system's calculation is a suggestion, not binding. GM can also force-approve proposals that fail re-validation.
- **Rationale**: The GM is the final arbiter. The system assists but never overrides GM judgment.
- **Implications**: Approval payload includes an `overrides` field and a `resource_changes` field. Force-approval bypasses resource checks.

### Binary Approve/Reject

- **Decision**: No intermediate "request changes" status. Only `pending`, `approved`, and `rejected`. GM rejects with a note if revisions are needed.
- **Rationale**: Simplest state machine. "Reject with note → revise → resubmit" achieves the same result as a separate "changes requested" state.
- **Implications**: Three-value status enum. Rejected proposals remain mutable.

### Validated on Submit, Deducted on Approval

- **Decision**: System validates resource affordability on submit (rejects if insufficient). Deduction happens only on approval. System re-validates before applying and warns GM if resources changed.
- **Rationale**: Prevents obviously invalid submissions while avoiding complex resource locking. Re-validation catches drift. GM force-approval handles edge cases.
- **Implications**: Two validation passes per proposal lifecycle. Warning mechanism on approval for insufficient resources.

### Unlimited Concurrent Proposals

- **Decision**: Players can have multiple pending proposals simultaneously. No resource locking. System re-validates on each approval.
- **Rationale**: Avoids artificial bottlenecks. In practice, players rarely have many pending proposals. Re-validation handles resource conflicts.
- **Implications**: If two proposals compete for the same Gnosis, only the first approved succeeds.

### One Event Per Approval

- **Decision**: Each approved proposal generates a single Event record capturing the entire outcome — all resource changes, narrative, and references.
- **Rationale**: Clean event log. One action = one event. Avoids noisy multi-event patterns.
- **Implications**: Event `changes` field must be comprehensive enough to capture all deltas in one record.

### Plot as Guaranteed Success

- **Decision**: Each Plot spent places a guaranteed 6 (success) on the table before rolling. Plot is declared on submission. Can also be used flexibly (surviving odds, narrative tweaks) at GM discretion.
- **Rationale**: Plot should feel powerful and decisive — a guaranteed result, not just another die. Flexible use preserves narrative agency.
- **Implications**: Plot spend is part of the submission payload. System stores but doesn't mechanically process flexible Plot uses — those are handled by GM override.

### Player Projects Reuse Story/Arc

- **Decision**: Player projects are Story/Arc game objects owned by the character. `work_on_project` targets a Story and adds a narrative entry. No segmented clock — the GM resolves when the fiction warrants it.
- **Rationale**: Reuses existing game object infrastructure. Narrative progress is more appropriate than mechanical segments for personal character projects.
- **Implications**: Stories need to support narrative entry streams (may be event log entries). Group clocks remain segmented (BitD-style) — player projects use a different model.

### No Timeout for MVP

- **Decision**: Proposals stay pending indefinitely until the GM acts. No auto-reject or expiry.
- **Rationale**: With a small group and active GM, stale proposals are handled socially. Timeout adds complexity without clear value for MVP.
- **Implications**: No scheduled jobs or cleanup logic needed.

### Common + Extras Data Model

- **Decision**: All proposals share common fields (narrative, action_type, modifiers, plot_spend). Type-specific data goes in a freeform JSON `details` field.
- **Rationale**: Flexible — supports new action types without schema changes. Validation is per-type in Python code, not database constraints.
- **Implications**: `details` field is a JSON column. Each action type has a Pydantic validator for its expected details shape.

---

## API Endpoints

- `GET /api/v1/proposals` — list proposals (supports `?status=pending`, `?character_id=`)
- `POST /api/v1/proposals` — submit a new proposal (player)
- `GET /api/v1/proposals/{id}` — proposal detail with calculated effects
- `POST /api/v1/proposals/{id}/approve` — approve and apply (GM) — payload includes gm_narrative, resource_changes, overrides, magic-specific fields
- `POST /api/v1/proposals/{id}/reject` — reject with note (GM)
- `PATCH /api/v1/proposals/{id}` — revise a rejected proposal (player, status must be `rejected`)

---

## Implications for Other Specs

| Spec | Implication |
|------|-------------|
| [downtime](downtime.md) | 🔄 All 7 downtime action types defined with formulas. All cost 1 FT. "Heal Bond Stress" renamed to "Maintain Bond". "Rest" is a new action. Skill training uses `work_on_project`. |
| [events](events.md) | 🔄 One event per approved proposal. Event `changes` field must capture all resource deltas comprehensively. Revision history also generates events. |
| [traits](traits.md) | Trait charges spent on approval (not submit). Recharge Trait fully restores to 5. New Trait goes through proposal workflow. |
| [bonds](bonds.md) | 🔄 "Heal Bond Stress" renamed to "Maintain Bond". Bond +1d modifier may cause +1 bond stress (GM flags on approval). New Bond goes through proposal workflow. |
| [magic-system](magic-system.md) | Magic Action and Charge Action integrated as proposal types. GM creates effects in approval payload. Style bonus is part of approval. |
| [character-core](character-core.md) | Plot spend = guaranteed success (not +1d). Resource changes auto-applied on approval. Rest heals 3–6 Stress. |
| [game-objects](game-objects.md) | 🔄 Player projects use Stories/Arcs (narrative entries, no segmented clock). Stories need to support narrative entry streams. |
| [auth](auth.md) | Players can only submit proposals for their own character. GM approves/rejects. GM can force-approve. |
| [architecture/data-model](../architecture/data-model.md) | 🔄 Proposal model with common fields + JSON details. Approval payload structure. One event per approval pattern. |

---

_Last updated: 2026-03-01_
