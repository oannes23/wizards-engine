# Epic 3.3 — PC Bond Mechanics

**Phase**: 3 — Characters
**Depends on**: Epic 2.3 (Bond Graph Service)
**Blocks**: Epic 4.2 (GM Actions) — needs bond stress service
**Parallel with**: Epic 3.2 (Traits & Effects)

---

## Overview

Extend the bond service from Epic 2.3 with PC-specific mechanics: bond stress, degradation, and the Trauma cascade. These are the mechanical depth layers that make PC bonds more than descriptive.

---

## Stories

| Story | Status | Completed |
|-------|--------|-----------|
| 3.3.1 — PC Bond Stress & Degradation | 🔴 Not started | — |
| 3.3.2 — Trauma Mechanic | 🔴 Not started | — |

### Story 3.3.1 — PC Bond Stress & Degradation

**Files to modify**:
- `src/wizards_engine/services/bond.py` — extend with PC bond stress mechanics
- `tests/test_bond_stress.py`

**Spec refs**: [bonds.md](../domains/bonds.md) (PC bond mechanics, bond stress, degradation), [data-model.md](../architecture/data-model.md) (slots table — stress, stress_degradations fields)

**Acceptance criteria**:
- PC bonds (`slot_type = "pc_bond"`) have `stress` (0–effective max) and `stress_degradations` (count)
- Effective bond stress max = `5 - stress_degradations`
- Stress increment: service validates against effective max
- At max stress:
  - Stress resets to 0
  - `stress_degradations` incremented by 1
  - Effective max decreases by 1
  - All in one operation
- Stress decrement (healing): service supports setting stress to 0 (Maintain Bond)
- Degradation reversal: service supports decrementing `stress_degradations` (GM action)
- At 0 effective max (5 degradations): no additional mechanical rule — GM handles narratively
- Bond stress fields are null/absent on non-PC bonds (npc_bond, group_relation, etc.)

### Story 3.3.2 — Trauma Mechanic

**Files to modify**:
- `src/wizards_engine/services/bond.py` — add trauma logic
- `src/wizards_engine/services/character.py` — integrate trauma with character stress
- `tests/test_trauma.py`

**Spec refs**: [character-core.md](../domains/character-core.md) (stress range, trauma, effective stress max), [bonds.md](../domains/bonds.md) (trauma, Past/Retired bonds)

**Acceptance criteria**:
- When Character stress reaches effective max (`9 - count(trauma bonds)`):
  - A chosen bond is retired to Past (`is_active = false`)
  - A new bond instance is created with `is_trauma = true`:
    - No target (`target_type`/`target_id` = null)
    - Trauma name/description set by caller
    - `stress = 0`, `stress_degradations = 0`
    - `is_active = true`
  - Character stress resets to 0
  - `effective_stress_max` decreases by 1 (computed: `9 - count(active trauma bonds)`)
- All mutations happen in a single compound operation (one service call)
- Trauma bonds are excluded from bond-graph traversal (no target = dead end)
- Character detail correctly computes `effective_stress_max` after trauma
- If all 8 bonds are trauma and stress hits max again: no mechanical rule, just return the state (GM handles narratively)
- Fixing trauma: service supports retiring a trauma bond and optionally creating a new regular bond in its place (GM action)

---

## Notes

- Event creation for stress changes and trauma is deferred to Epic 4.1
- Bond stress application during proposal approval (e.g., GM marking a bond as "strained" on approval) comes in Epic 4.3
- The compound operation pattern here (multiple mutations in one call) establishes the pattern used throughout Phase 4
