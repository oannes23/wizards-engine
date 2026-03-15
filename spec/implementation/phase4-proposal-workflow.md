# Epic 4.3 — Proposal Workflow

**Phase**: 4 — Actions
**Depends on**: Epic 4.1 (Event Log)
**Blocks**: Epic 4.4 (Feed System) — partially
**Parallel with**: Epic 4.2 (GM Actions)

---

## Overview

Implement the player proposal system: submit, calculate effects, GM approve/reject, resource deduction, and all 11 action types. This is the core gameplay loop — players describe actions, the system computes effects, and the GM resolves them.

---

## Stories

### Story 4.3.1 — Proposal CRUD + Submission

**Files to create**:
- `src/wizards_engine/api/routes/proposals.py` — proposal endpoints
- `src/wizards_engine/schemas/proposal.py` — request/response models
- `src/wizards_engine/services/proposal.py` — proposal creation, validation, calculation
- `tests/test_proposals.py`

**Spec refs**: [actions.md](../domains/actions.md) (proposal workflow, action types, selections, calculated_effect), [data-model.md](../architecture/data-model.md) (proposals table)

**Acceptance criteria**:
- `POST /api/v1/proposals` — authenticated player. Body: `{character_id, action_type, narrative, selections}`.
  - Validates `character_id` belongs to the authenticated user
  - Validates `action_type` is one of 11 valid types
  - Validates `selections` structure per action_type
  - Computes `calculated_effect` (server-side, per action type — see Stories 4.3.2, 4.3.4, 4.3.5)
  - Validates affordability (e.g., enough FT for downtime, enough charges for trait use)
  - Sets `status = "pending"`, `origin = "player"`
  - Returns 201 with full proposal
- `GET /api/v1/proposals` — list with filters: `?status=pending|approved|rejected`, `?character_id=<ulid>`. ULID pagination. Players see own proposals. GM sees all.
- `GET /api/v1/proposals/{id}` — detail. Players see own only. GM sees all.
- `PATCH /api/v1/proposals/{id}` — update selections/narrative. Only when status is `pending` or `rejected`. Recalculates `calculated_effect`. Returns 200.
- `DELETE /api/v1/proposals/{id}` — hard delete. Only when status is `pending` or `rejected`. Returns 204.
- Revision flow: PATCH a rejected proposal → status returns to `pending`, `calculated_effect` recalculated. Produces `proposal.revised` event (private visibility).

### Story 4.3.2 — Skill Action Calculations

**Files to modify**:
- `src/wizards_engine/services/proposal.py` — add `use_skill` calculation
- `tests/test_skill_actions.py`

**Spec refs**: [actions.md](../domains/actions.md) (use_skill, dice pool calculation, modifier stacking, Plot spend), [traits.md](../domains/traits.md) (modifier stacking rule)

**Acceptance criteria**:
- `use_skill` calculated_effect includes:
  - `dice_pool`: skill level + modifier count
  - `modifiers`: list of selected modifiers with source details
  - `plot_spend`: number of Plot spent (each = 1 guaranteed 6)
  - `costs`: list of trait charges that will be spent on approval
- Modifier stacking validation: max 1 Core Trait (+1d) + 1 Role Trait (+1d) + 1 Bond (+1d) = max +3d
- Core/Role trait selection: validates trait exists, is active, has charge > 0
- Bond selection: validates bond exists, is active
- Plot spend: validates character has enough Plot. No cap on spend per proposal.
- Trait charge cost computed but not deducted yet (deducted on approval)

### Story 4.3.3 — GM Approval + Rejection

**Files to modify**:
- `src/wizards_engine/api/routes/proposals.py` — add approve/reject endpoints
- `src/wizards_engine/services/proposal.py` — approval and rejection logic
- `tests/test_proposal_approval.py`

**Spec refs**: [actions.md](../domains/actions.md) (GM approval, overrides, rejection, rider events, affordability re-validation), [events.md](../domains/events.md) (proposal.approved, proposal.rejected events)

**Acceptance criteria**:
- `POST /api/v1/proposals/{id}/approve` — GM only. Body: `{narrative?, gm_overrides?, rider_event?}`.
  - Re-validates affordability at approval time. If insufficient: returns 409 with `{error: {code: "insufficient_resources"}}`. GM can force with `{force: true}`.
  - Applies `gm_overrides` — replacement semantics (override fields replace calculated_effect fields)
  - Auto-deducts resources: trait charges (-1 per selected trait), FT (-1 for downtime), Plot (per spend), Gnosis (per sacrifice), etc.
  - Creates `proposal.approved` event with:
    - `actor_type = "gm"`, all changes as compound changes
    - `proposal_id` back-ref
    - Default visibility per action type (typically `bonded`)
  - Optional rider event: if `rider_event` payload provided, create a separate Event row linked via `parent_event_id`. Same transaction.
  - Sets proposal `status = "approved"`, `event_id` = generated event, `rider_event_id` if applicable
  - Returns 200 with updated proposal
- `POST /api/v1/proposals/{id}/reject` — GM only. Body: `{rejection_note?}`.
  - Sets `status = "rejected"`, `gm_notes` = rejection_note
  - Creates `proposal.rejected` event (private visibility)
  - Returns 200
- Revision: PATCH a rejected proposal → recalculate → status back to `pending`

### Story 4.3.4 — Downtime Action Types

**Files to modify**:
- `src/wizards_engine/services/proposal.py` — add downtime action calculations and approval effects
- `tests/test_downtime_actions.py`

**Spec refs**: [actions.md](../domains/actions.md) (7 downtime types), [downtime.md](../domains/downtime.md) (downtime actions), [traits.md](../domains/traits.md) (recharge, new trait), [bonds.md](../domains/bonds.md) (maintain, new bond), [character-core.md](../domains/character-core.md) (rest, gnosis)

**7 downtime action types**, each with auto-cost of 1 FT:

1. **`regain_gnosis`**: calculated_effect = `{gnosis_gained: 3 + lowest_magic_stat + modifier_count}`. Supports modifiers (max +3d stacking). On approval: add gnosis (capped at 23), deduct FT, deduct trait charges.
2. **`recharge_trait`**: selections = `{trait_id}`. calculated_effect = `{trait_id, charges_restored: 5}`. On approval: set charge to 5, deduct FT.
3. **`maintain_bond`**: selections = `{bond_id}`. calculated_effect = `{bond_id, stress_healed}`. On approval: reset bond stress to 0, deduct FT.
4. **`work_on_project`**: selections = `{story_id, entry_text}`. On approval: add story entry, deduct FT.
5. **`rest`**: calculated_effect = `{stress_healed: 3 + modifier_count}`. Supports modifiers. On approval: reduce stress (min 0), deduct FT.
6. **`new_trait`**: selections = `{slot_type, template_id? OR proposed_name + proposed_description, retire_trait_id?}`. On approval: retire old trait (if specified), create new trait (charge=5), deduct FT. If proposed name/desc: auto-create Trait Template in catalog.
7. **`new_bond`**: selections = `{target_type, target_id, retire_bond_id?}`. On approval: retire old bond (if specified), create new bond, deduct FT.

**Acceptance criteria**:
- All 7 types calculate correctly with proper `calculated_effect` structure
- Affordability validation: character has FT >= 1 and any type-specific resources
- Approval applies all effects atomically: resource deduction + entity changes + event creation
- `new_trait` with proposed name auto-creates a Trait Template in the catalog on approval
- `new_bond` validates no duplicate active bond to the same target
- FT deducted on approval (not submission)

### Story 4.3.5 — Magic Actions + Sacrifice

**Files to modify**:
- `src/wizards_engine/services/proposal.py` — add magic action calculations
- `tests/test_magic_actions.py`

**Spec refs**: [magic-system.md](../domains/magic-system.md) (Magic Action, Charge Action, sacrifice types, tiered Gnosis conversion, style bonus), [actions.md](../domains/actions.md) (use_magic, charge_magic)

**Acceptance criteria**:
- `use_magic` action:
  - Selections include: `suggested_stat`, `sacrifice` (list of entries), `modifiers` (trait/bond use, stacking rule)
  - Sacrifice processing: each entry has `{type, amount?, target_id?}`
    - Gnosis: 1:1 conversion
    - Stress: 1 Stress = 2 Gnosis equivalent
    - Free Time: 1 FT = 3 + lowest magic stat Gnosis equivalent
    - Bond sacrifice: 10 Gnosis equivalent (bond goes to Past)
    - Trait sacrifice: 10 Gnosis equivalent (trait goes to Past)
    - Other: `{type: "other", description}` — GM sets value in overrides
  - Total Gnosis equivalent computed → tiered dice conversion: N dice costs N*(N+1)/2 Gnosis
  - calculated_effect includes: `dice_pool` (stat level + sacrifice dice + modifier dice), `total_gnosis_equivalent`, `sacrifice_details`, `costs`
  - Stress sacrifice can trigger Trauma cascade if it pushes stress to max
- `charge_magic` action:
  - Selections include: `effect_id`, `suggested_stat`, `sacrifice`, `modifiers`
  - Same sacrifice/dice processing as use_magic
  - calculated_effect includes target effect details
- GM approval for `use_magic`:
  - GM provides `gm_overrides` with `{actual_stat?, style_bonus?, effect_details?}` (name, description, effect_type, power_level, charges)
  - `style_bonus`: hidden Gnosis added by GM (not visible to player)
  - On approval: deduct all sacrificed resources, create Magic Effect (if effect_details provided), create event
- GM approval for `charge_magic`:
  - GM provides `{charges_added?, power_boost?}` in overrides
  - For charged effects: `charges_added` restores charges (current increases, max grows if needed)
  - For permanent effects: `power_boost` increases power_level (1–5 scale)
- Stress sacrifice triggering Trauma: if stress sacrifice pushes character to effective stress max, full Trauma cascade fires within the same approval event

---

## Notes

- The proposal system is the most complex part of the codebase — each action type has its own validation, calculation, and approval logic
- `resolve_clock` proposals are system-generated (Epic 4.2) but approved through this workflow
- The rider event mechanism on approval enables atomic bundled GM actions alongside proposal resolution
