# Epic 3.2 — Traits & Magic Effects

**Phase**: 3 — Characters
**Depends on**: Epic 3.1 Story 4 (Character detail response / sheet model)
**Blocks**: Epic 4.2 (GM Actions) — needs trait/effect service layer
**Parallel with**: Epic 3.3 (PC Bond Mechanics)

---

## Overview

Implement the Trait Template catalog (GM CRUD), Core/Role trait instance management on characters (service layer for creation, retirement, slot enforcement), and Magic Effect lifecycle (creation, use, retirement, cap enforcement). Player-facing direct actions for effects (use, retire) are included here.

---

## Stories

| Story | Status | Completed |
|-------|--------|-----------|
| 3.2.1 — Trait Template Catalog | 🟢 Complete | 2026-03-16 |
| 3.2.2 — Trait Instances on Characters | 🟢 Complete | 2026-03-16 |
| 3.2.3 — Magic Effects on Characters | 🟢 Complete | 2026-03-16 |

### Story 3.2.1 — Trait Template Catalog

**Files to create**:
- `src/wizards_engine/api/routes/trait_templates.py` — trait template CRUD endpoints
- `src/wizards_engine/schemas/trait_template.py` — request/response models
- `tests/test_trait_templates.py`

**Spec refs**: [traits.md](../domains/traits.md) (Trait Template catalog, type immutability, propagation, soft delete), [data-model.md](../architecture/data-model.md) (trait_templates table)

**Acceptance criteria**:
- `POST /api/v1/trait_templates` — GM only. Body: `{name, description, type}`. Type is `core` or `role`. Returns 201.
- `GET /api/v1/trait_templates` — list with filters: `?type=core|role`, `?include_deleted=true`. ULID pagination.
- `GET /api/v1/trait_templates/{id}` — detail. Resolves even when soft-deleted (for instance display).
- `PATCH /api/v1/trait_templates/{id}` — GM only. Update `name`, `description` only. Type is immutable — reject attempts to change. Returns 200.
- `DELETE /api/v1/trait_templates/{id}` — GM only. Soft delete. Existing trait instances keep their `template_id` and remain functional. Template hidden from list but resolvable by ID. Returns 204.
- Editing name/description propagates to all characters referencing the template (via `slots.template_id` — characters inherit the template's name/description).

### Story 3.2.2 — Trait Instances on Characters

**Files to create**:
- `src/wizards_engine/services/trait.py` — trait instance creation, modification, retirement
- `tests/test_trait_service.py`

**Spec refs**: [traits.md](../domains/traits.md) (PC trait lifecycle, slot counts, charges, Past/Retired), [data-model.md](../architecture/data-model.md) (slots table, core_trait/role_trait slot types)

**Acceptance criteria**:
- Service can create Core and Role trait instances on full Characters:
  - Links to a Trait Template via `template_id`
  - Validates template type matches slot type (core template → core_trait, role template → role_trait)
  - Sets `charge = 5` (full charge) on creation
  - Sets `is_active = true`
- Enforces slot count limits: max 2 active `core_trait`, max 3 active `role_trait` per character
- Prevents duplicate templates on the same character (one active instance per template)
- Retirement: sets `is_active = false`, moves to Past
- Replacement: retire existing trait first, then create new one in the slot
- Charge management: decrement charge (min 0), reset to 5 (recharge)
- No API endpoints for players — trait management is via GM actions (Phase 4) or proposals (Phase 4)
- Service layer is directly testable

### Story 3.2.3 — Magic Effects on Characters

**Files to create**:
- `src/wizards_engine/api/routes/effects.py` — player direct action endpoints
- `src/wizards_engine/services/magic_effect.py` — effect creation, use, retirement
- `src/wizards_engine/schemas/magic_effect.py` — request/response models
- `tests/test_magic_effects.py`

**Spec refs**: [magic-system.md](../domains/magic-system.md) (Magic Effects, three types, cap of 9, direct use, self-retire), [character-core.md](../domains/character-core.md) (Magic Effects on sheet), [data-model.md](../architecture/data-model.md) (magic_effects table)

**Acceptance criteria**:
- Service can create Magic Effects on full Characters:
  - Three types: `instant`, `charged`, `permanent`
  - Fields: `name`, `description`, `effect_type`, `power_level` (1–5), `charges_current`, `charges_max` (charged only)
  - Charged + permanent count toward the cap of 9 active effects
  - Instant effects don't count toward cap
  - Rejects creation when cap would be exceeded (excluding instants)
- Player direct action — Use: `POST /api/v1/characters/{id}/effects/{effect_id}/use`
  - Body: `{narrative?}` (optional freeform text)
  - Decrements `charges_current` by 1
  - Rejects if charges_current = 0 or effect is not `charged`
  - Player must own the character
  - Returns 200 with updated effect
- Player direct action — Retire: `POST /api/v1/characters/{id}/effects/{effect_id}/retire`
  - Empty body
  - Sets `is_active = false` (moves to Past)
  - Frees cap space
  - Player must own the character
  - Returns 200
- Retired effects visible in character detail under past effects
- GM can also create/modify/retire effects via service layer (API comes in Phase 4)

---

## Notes

- Event creation for trait changes and effect use/retire is deferred to Epic 4.1 (Event Log)
- The service layer built here is consumed by GM actions (Epic 4.2) and proposal approval (Epic 4.3)
- Auto-catalog on new_trait approval (creating a template from a proposal) is implemented in Epic 4.3
