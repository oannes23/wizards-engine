# Epic 5.5 — Pre-UI API Additions

**Phase**: 5.5 — API Additions
**Depends on**: Phase 4 (Proposals + GM Actions), Phase 5 (Sessions)
**Blocks**: Phase 6 (specific per-story dependencies below)
**Parallel with**: All 6 stories are independent — max parallelism = 6

---

## Overview

Six backend API additions required before the Web UI. These include two new direct player actions (recharge trait, maintain bond), a schema change (nullable narrative on session actions), three new endpoints (GM dashboard aggregation, batch GM actions, characters summary). All follow established patterns from Phases 1–5.

---

## Stories

| Story | Status | Completed |
|-------|--------|-----------|
| 5.5.1 — Recharge Trait Direct Action | 🟢 Complete | 2026-03-18 |
| 5.5.2 — Maintain Bond Direct Action | 🟢 Complete | 2026-03-18 |
| 5.5.3 — Nullable Narrative on Session Actions | 🟢 Complete | 2026-03-18 |
| 5.5.4 — GM Dashboard Aggregation Endpoint | 🟢 Complete | 2026-03-18 |
| 5.5.5 — Batch GM Actions Endpoint | 🟢 Complete | 2026-03-18 |
| 5.5.6 — Characters Summary Endpoint | 🟢 Complete | 2026-03-18 |

### Story 5.5.1 — Recharge Trait Direct Action

**Blocks**: Story 6.2.3 (direct action buttons)

**Files to create**:
- `src/wizards_engine/api/routes/recharge_trait.py` — endpoint (follows `find_time.py` pattern)
- `tests/test_recharge_trait.py` — ~18 test cases

**Files to modify**:
- `src/wizards_engine/schemas/proposal.py` — remove `recharge_trait` from `VALID_ACTION_TYPES`
- `src/wizards_engine/api/__init__.py` — register new router

**Spec refs**: [actions.md](../domains/actions.md) (Player Direct Actions), [web-ui.md](../domains/web-ui.md) (§I), [character-core.md](../domains/character-core.md)

**Implementation notes**:
- Reuse `services/trait.py:recharge_trait()` for the slot mutation
- Follow `find_time.py` pattern: auth check → detail_level check → resource validation → `db.flush()` (no explicit commit — `get_db` handles it) → event creation → return character
- Must verify slot ownership in route (trait belongs to character, character belongs to user)

**Acceptance criteria**:
- `POST /api/v1/characters/{id}/recharge-trait` — authenticated player or GM
  - Body: `{trait_instance_id: string, narrative: string}`
  - Validates character exists, not deleted, `detail_level = "full"` (422 `not_a_pc` otherwise)
  - Validates ownership (player owns character, or caller is GM)
  - Validates trait exists, belongs to character, `is_active = true`, `slot_type IN ('core_trait', 'role_trait')`
  - Validates trait charges < 5 (409 `trait_already_full` if at 5)
  - Validates FT >= 1 (409 `insufficient_free_time`)
  - Validates narrative is non-empty string (422 if missing or empty)
  - On success: set charges to 5, decrement FT by 1, create event (`player.recharge_trait`, visibility `private`), return updated character
  - Guard against NULL `charge` column on slot (default to 0 if null)
- `POST /api/v1/proposals` with `action_type: "recharge_trait"` → 422 (rejected action type)
- All existing tests pass without modification

### Story 5.5.2 — Maintain Bond Direct Action

**Blocks**: Story 6.2.3 (direct action buttons)

**Files to create**:
- `src/wizards_engine/api/routes/maintain_bond.py` — endpoint
- `tests/test_maintain_bond.py` — ~18 test cases

**Files to modify**:
- `src/wizards_engine/schemas/proposal.py` — remove `maintain_bond` from `VALID_ACTION_TYPES`
- `src/wizards_engine/api/__init__.py` — register new router

**Spec refs**: [actions.md](../domains/actions.md), [bonds.md](../domains/bonds.md), [web-ui.md](../domains/web-ui.md) (§I), [character-core.md](../domains/character-core.md)

**Implementation notes**:
- Reuse `services/bond.py:restore_bond_charges()` for the slot mutation (NOT the proposal handler `_apply_maintain_bond` which has a bug — sets stress=0 instead of computing effective max)
- Effective max = `5 - stress_degradations`. Guard against NULL `stress_degradations` (default to 0)

**Acceptance criteria**:
- `POST /api/v1/characters/{id}/maintain-bond` — authenticated player or GM
  - Body: `{bond_instance_id: string, narrative: string}`
  - Validates character exists, not deleted, `detail_level = "full"` (422 `not_a_pc`)
  - Validates ownership
  - Validates bond exists, belongs to character, `is_active = true`, `slot_type = 'pc_bond'`
  - Validates bond is NOT a trauma bond (`is_trauma != true`, 422 `cannot_maintain_trauma`)
  - Validates bond charges < effective max (409 `bond_already_maintained`)
  - Validates FT >= 1 (409 `insufficient_free_time`)
  - Validates narrative is non-empty string
  - On success: restore charges to effective max, decrement FT by 1, create event (`player.maintain_bond`, visibility `private`), return updated character
  - Test with degraded bond: 2 degradations → effective max 3 → charges restored to 3 (not 5)
- `POST /api/v1/proposals` with `action_type: "maintain_bond"` → 422
- All existing tests pass without modification

### Story 5.5.3 — Nullable Narrative on Session Actions

**Blocks**: Story 6.3.1 (proposal submission)

**Files to create**:
- `alembic/versions/XXX_nullable_proposal_narrative.py` — migration

**Files to modify**:
- `src/wizards_engine/models/proposal.py` — `narrative: Mapped[str | None]` with `nullable=True`
- `src/wizards_engine/schemas/proposal.py` — `narrative: str | None = None`, add cross-field validator
- `src/wizards_engine/services/proposal.py` — validate narrative required for downtime types at service layer
- `tests/test_proposals.py` — add nullable narrative tests + regression guards

**Spec refs**: [actions.md](../domains/actions.md) (Narrative Requirements)

**Implementation notes**:
- SQLite requires `batch_alter_table` for ALTER COLUMN: `with op.batch_alter_table("proposals") as batch_op: batch_op.alter_column("narrative", nullable=True)`
- Add Pydantic `model_validator` that raises 422 if `narrative is None` and `action_type` is a downtime type
- System proposals with auto-generated narrative (`narrative=""`) — verify empty string is preserved, not coerced to null

**Acceptance criteria**:
- Session actions (`use_skill`, `use_magic`, `charge_magic`) accepted with `narrative: null` or omitted → 201
- Downtime actions (`regain_gnosis`, `work_on_project`, `rest`, `new_trait`, `new_bond`) with null narrative → 422
- PATCH narrative onto pending session-action proposal → 200
- GM approval with both `narrative=null` and `gm_narrative=null` → event narrative is null (does not crash)
- Alembic migration applies and rolls back cleanly
- All existing tests pass

### Story 5.5.4 — GM Dashboard Aggregation Endpoint

**Blocks**: Story 6.5.1 (GM dashboard view)

**Files to create**:
- `src/wizards_engine/api/routes/gm_dashboard.py` — endpoint
- `src/wizards_engine/schemas/gm_dashboard.py` — response models
- `src/wizards_engine/services/gm_dashboard.py` — aggregation queries
- `tests/test_gm_dashboard.py` — ~12 test cases

**Spec refs**: [web-ui.md](../domains/web-ui.md) (§I), [api-conventions.md](../architecture/api-conventions.md)

**Acceptance criteria**:
- `GET /api/v1/gm/dashboard` — GM only (401 unauthenticated, 403 player)
- Response: `{pending_proposals: [...], pc_summaries: [...], near_completion_clocks: [...]}`
- `pending_proposals`: system proposals (`origin: "system"`) first, then player proposals oldest-first (ULID order)
- `pc_summaries`: only `detail_level = "full"`, not deleted, includes id/name/stress/free_time/plot/gnosis
- `near_completion_clocks`: clocks where `progress >= segments - 1` and `progress < segments` (not already completed)
- All lists return `[]` when empty (not absent keys)
- No new indexes required (scale is ~100 rows per table)

### Story 5.5.5 — Batch GM Actions Endpoint

**Blocks**: Epic 6.5 (PC setup flow)

**Files to create**:
- `src/wizards_engine/api/routes/gm_actions_batch.py` — endpoint
- `tests/test_gm_actions_batch.py` — ~10 test cases

**Spec refs**: [web-ui.md](../domains/web-ui.md) (§I), [actions.md](../domains/actions.md) (GM Actions)

**Implementation notes**:
- Use savepoint pattern: `db.begin_nested()` before each action dispatch, rollback on failure
- Reuse `services/gm_actions.py:dispatch_gm_action()` for each action in the array
- Max batch size: 50 actions (422 if exceeded)

**Acceptance criteria**:
- `POST /api/v1/gm/actions/batch` — GM only
- Body: `{actions: [{action_type, targets, changes, narrative, visibility?}, ...]}`
- All actions validated and applied atomically. If ANY fails, entire batch rolls back
- Response on success: `{events: [...]}` — list of created events
- Response on failure: 422 with `{error: {code: "batch_failed", failed_index: N, detail: "..."}}`
- Empty array `[]` → 422 `batch_empty`
- Array exceeding 50 → 422 `batch_too_large`
- Test atomicity: action 1 valid + action 2 invalid → DB unchanged, no events created

### Story 5.5.6 — Characters Summary Endpoint

**Blocks**: Story 6.5.1 (GM dashboard view)

**Files to create**:
- `src/wizards_engine/api/routes/characters_summary.py` — endpoint (or add to `characters.py`)
- `tests/test_characters_summary.py` — ~6 test cases

**Spec refs**: [web-ui.md](../domains/web-ui.md) (§I)

**Acceptance criteria**:
- `GET /api/v1/characters/summary` — authenticated (player or GM)
- Response: `{items: [{id, name, stress, free_time, plot, gnosis}, ...]}`
- Only `detail_level = "full"` characters, not deleted
- Response shape explicitly excludes: skills, magic_stats, bonds, traits, effects, description, notes
- Handle nullable meter columns (`stress`, `free_time`, etc.) — return 0 if null

---

## Notes

- All stories follow established patterns from Phases 1–5 (auth checks, error envelope, event creation)
- Stories 5.5.1 and 5.5.2 follow the `find_time.py` direct action pattern exactly
- Story 5.5.3 is the only schema migration in this epic
- All stories include regression criterion: existing ~1,980 tests must pass without modification
