# Epic 4.2 — GM Actions

**Phase**: 4 — Actions
**Depends on**: Epic 4.1 (Event Log)
**Blocks**: Epic 4.4 (Feed System) — partially
**Parallel with**: Epic 4.3 (Proposal Workflow)

---

## Overview

Implement the `POST /api/v1/gm/actions` endpoint — the GM's direct action system for modifying game state. Each action type validates input, applies changes, and produces a domain event. This Epic covers character modifications, bond/trait/effect management, XP awards, and world object changes.

---

## Stories

| Story | Status | Completed |
|-------|--------|-----------|
| 4.2.1 — GM Actions Endpoint + Character Actions | 🔴 Not started | — |
| 4.2.2 — GM Bond/Trait/Effect Actions | 🔴 Not started | — |
| 4.2.3 — GM World Object Actions | 🔴 Not started | — |

### Story 4.2.1 — GM Actions Endpoint + Character Actions

**Files to create**:
- `src/wizards_engine/api/routes/gm_actions.py` — `POST /api/v1/gm/actions` endpoint
- `src/wizards_engine/schemas/gm_actions.py` — request models per action type
- `src/wizards_engine/services/gm_actions.py` — action dispatcher
- `tests/test_gm_actions_character.py`

**Spec refs**: [actions.md](../domains/actions.md) (GM actions, modify_character, CRUD/GM split), [events.md](../domains/events.md) (GM actions reuse domain event types)

**Acceptance criteria**:
- `POST /api/v1/gm/actions` — GM only. Body: `{action_type, target_type, target_id, ...action-specific fields}`
- `modify_character` action type:
  - Modifies meters: `stress`, `free_time`, `plot`, `gnosis` (delta or absolute set)
  - Modifies skills: individual skill level changes (e.g., `{skill: "awareness", level: 2}`)
  - Modifies magic_stats: individual stat xp/level changes
  - Modifies attributes: merge or replace JSON blob
  - Modifies `last_session_time_now`
  - Integrity-only validation (respects ranges: stress 0–9, FT 0–20, plot 0–5, gnosis 0–23, skills 0–3, magic stats level 0–5)
- Each action produces a domain event with:
  - Appropriate type (e.g., `character.stress_changed`, `character.meter_updated`)
  - `actor_type = "gm"`
  - `changes` with fully-qualified keys and correct `op` tags
  - `clamped: true` when boundary hit
  - Targets set to the affected game object
- Stress boundary: if `modify_character` pushes stress to effective max, the Trauma cascade from Epic 3.3 fires. All compound changes recorded in the same event.

### Story 4.2.2 — GM Bond/Trait/Effect Actions

**Files to modify**:
- `src/wizards_engine/services/gm_actions.py` — add action type handlers
- `src/wizards_engine/api/routes/gm_actions.py` — extend schema
- `tests/test_gm_actions_entities.py`

**Spec refs**: [actions.md](../domains/actions.md) (GM action types: create_bond, modify_bond, retire_bond, create_trait, modify_trait, retire_trait, create_effect, modify_effect, retire_effect, award_xp), [bonds.md](../domains/bonds.md) (bond creation fields), [traits.md](../domains/traits.md) (trait lifecycle), [magic-system.md](../domains/magic-system.md) (XP, level-up)

**9 action types**:

1. `create_bond` — create a bond via the bond service. Fields: `owner_type`, `owner_id`, `target_type`, `target_id`, `source_label?`, `target_label?`, `description?`, `bidirectional?`. Auto-infers slot_type. Produces `bond.created` event.
2. `modify_bond` — update bond fields (labels, description, stress, stress_degradations). Produces `bond.stress_changed` or `bond.updated` event.
3. `retire_bond` — set `is_active = false`. Produces `bond.retired` event.
4. `create_trait` — create a trait instance on a character/group/location. For PC traits: links to template, sets charge=5. For group/location: freeform name+description. Produces `trait.created` event.
5. `modify_trait` — update trait fields (name, description, charge for PC traits). Produces `trait.recharged` or equivalent event.
6. `retire_trait` — set `is_active = false`. Produces `trait.retired` event.
7. `create_effect` — create a Magic Effect on a character. Produces `magic.effect_created` event.
8. `modify_effect` — update effect fields (name, description, charges, power_level). Produces event.
9. `retire_effect` — set `is_active = false`. Produces `magic.effect_retired` event.
10. `award_xp` — add XP to a magic stat. Auto-level-up when XP reaches threshold (5 per level). Produces event with XP and level changes.

**Acceptance criteria**:
- All 10 action types (including modify_character from 4.2.1) work via `POST /api/v1/gm/actions`
- Each produces the correct domain event type with `actor_type = "gm"`
- Bond creation uses the bond service from Epic 2.3 (slot limits, duplicate prevention, auto-inference)
- Trait creation uses the trait service from Epic 3.2 (slot limits, template validation)
- Effect creation uses the effect service from Epic 3.2 (cap enforcement)
- `award_xp`: XP added to specified magic stat. When XP >= 5: level increments, XP resets to `xp - 5`. Both XP and level changes in one event.

### Story 4.2.3 — GM World Object Actions

**Files to modify**:
- `src/wizards_engine/services/gm_actions.py` — add world object action handlers
- `tests/test_gm_actions_world.py`

**Spec refs**: [actions.md](../domains/actions.md) (modify_group, modify_location, modify_clock), [game-objects.md](../domains/game-objects.md) (clock completion, resolve_clock auto-generation)

**3 action types**:

1. `modify_group` — change tier (non-negative integer). Produces `group.updated` event.
2. `modify_location` — change `parent_id`. Validates new parent exists. Produces `location.updated` event.
3. `modify_clock` — change `progress` (delta or absolute). Accepts annotation `metadata` (notes, related_events, related_objects). Produces `clock.advanced` event.

**Clock completion detection**:
- After `modify_clock`, check if `progress >= segments`
- If completed and no pending/approved `resolve_clock` proposal exists for this clock:
  - Auto-generate a `resolve_clock` proposal with `origin = "system"`, `character_id = null`, `clock_id` set, status `pending`
  - Produce `clock.resolve_generated` event (silent visibility)
- Idempotent: only one `resolve_clock` proposal per clock, ever

**Acceptance criteria**:
- `modify_group`: tier changes correctly, event produced with correct changes
- `modify_location`: parent_id changes, validates new parent. Event produced.
- `modify_clock`: progress changes, annotations stored in event metadata. Event produced.
- Clock completion auto-generates `resolve_clock` proposal (one per clock, ever)
- `resolve_clock` event has `silent` visibility

---

## Notes

- GM actions bypass the proposal workflow — validate → apply → event
- The `modify_character` handler must integrate with Trauma cascade (from Epic 3.3) and boundary behaviors
- Clock annotation metadata is stored on the event, not on the clock itself
