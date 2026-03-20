# Pre-Launch Review Report

**Date**: 2026-03-19
**Reviewers**: Code Reviewer, Game Designer, QA Engineer, Architect (AI agents)
**Test results**: 2350 passed, 1 failed, 1 xfailed | 94% line coverage

---

## Executive Summary

The Wizards Engine is substantially code-complete and well-engineered for its scope. The test suite is extensive (2350 tests, 94% coverage) and the architecture is clean. However, **3 confirmed logic bugs** need fixing before launch, and there are several medium-priority items that would improve reliability and maintainability.

**Verdict: Fix critical/high bugs, then ready for first deployment.**

---

## Table of Contents

1. [Critical — Must Fix Before Launch](#1-critical--must-fix-before-launch)
2. [High — Should Fix Before Launch](#2-high--should-fix-before-launch)
3. [Test Results & Coverage](#3-test-results--coverage)
4. [Game Design Assessment](#4-game-design-assessment)
5. [Architecture Assessment](#5-architecture-assessment)
6. [Medium Priority — Fix Soon After Launch](#6-medium-priority--fix-soon-after-launch)
7. [Low Priority — Future Improvements](#7-low-priority--future-improvements)
8. [What Looks Good](#8-what-looks-good)

---

## 1. Critical — Must Fix Before Launch

### C1. `_apply_maintain_bond` resets bond charges to 0 instead of effective max

- **File**: `src/wizards_engine/services/proposal.py:2501-2528`
- **Found by**: Code Reviewer
- **Impact**: When a player's "Maintain Bond" proposal is approved via the legacy proposal path, the bond's charges are set to 0 (empty) instead of `5 - degradation_count` (full). This corrupts character data — the opposite of the intended healing action.
- **Note**: The direct-action route (`maintain_bond.py:271`) and the bond service's `restore_bond_charges()` (`bond.py:832-856`) both do this correctly. Only the proposal approval path is wrong.
- **Fix**: In `_apply_maintain_bond`, replace `bond_slot.stress = 0` with `effective_max = 5 - (bond_slot.stress_degradations or 0); bond_slot.stress = max(0, effective_max)`.

### C2. Bond strain semantics inverted in proposal approval path

- **File**: `src/wizards_engine/services/proposal.py:1682-1709`
- **Found by**: Code Reviewer, Game Designer
- **Impact**: When `bond_strained` is True during `_apply_use_skill` / `_apply_use_magic` / `_apply_charge_magic`, the code does `stress += 1`. But `stress` represents **charges remaining** (5 = full, 0 = empty). Losing a charge should be `stress -= 1`. The bond service's `apply_bond_strain` (`bond.py:815`) correctly decrements. The proposal approval path has inverted semantics.
- **Fix**: Change the bond strain logic to decrement `stress` by 1 and trigger degradation at `stress <= 0` (matching `apply_bond_strain` in bond service).

### C3. Bond degradation trigger inverted in `handle_modify_bond`

- **File**: `src/wizards_engine/services/gm_actions.py:990`
- **Found by**: Game Designer
- **Impact**: The condition `raw >= effective_max` triggers degradation when charges are *set to or above the max* — the opposite of the intended behavior. Should trigger when `raw <= 0` (charges depleted), matching `apply_bond_strain` in `bond.py`.
- **Fix**: Change the degradation check from `raw >= effective_max` to `raw <= 0`.

---

## 2. High — Should Fix Before Launch

### H1. `db.commit()` calls in GM actions violate transaction pattern

- **File**: `src/wizards_engine/services/gm_actions.py` (14 occurrences: lines 379, 517, 640, 796, 890, 1054, 1119, 1293, 1399, 1464, 1533, 1673, 1738, 1855)
- **Found by**: Code Reviewer, Architect
- **Impact**: Every `handle_*` function calls `db.commit()`, but `get_db()` also commits after the route yields. This is architecturally inconsistent with every other service. The batch GM actions endpoint works around this by monkey-patching `db.commit = db.flush`, which is fragile.
- **Fix**: Replace all `db.commit()` calls in GM action handlers with `db.flush()`. Remove the monkey-patch in `gm_actions_batch.py`.

### H2. Auth cookie `secure=True` blocks local development

- **File**: `src/wizards_engine/api/auth.py:32-36`
- **Found by**: Code Reviewer, Architect
- **Impact**: The cookie is hardcoded with `secure=True`. Local development over HTTP (the default `uvicorn --reload`) will silently fail auth — the browser won't send the cookie back.
- **Fix**: Make `secure` configurable via environment variable (`WIZARDS_COOKIE_SECURE`, default `true`).

### H3. 1 failing test

- **Test**: `tests/test_gm_tools_6_5_5.py::TestClocksDetailView::test_progress_patch_uses_correct_payload`
- **Found by**: QA Engineer
- **Impact**: Asserts that `gm-clocks.js` contains `progress: newProgress` in its PATCH payload. The assertion fails, suggesting the JS source doesn't match the expected pattern.
- **Fix**: Either update the JS source or the test assertion to match.

### H4. Dead code paths for `recharge_trait` / `maintain_bond` in proposal service

- **File**: `src/wizards_engine/services/proposal.py:1381-1384, 862-963, 2781-2782`
- **Found by**: Code Reviewer, Game Designer
- **Impact**: These action types were promoted to direct player actions in Phase 5.5. The code still has calculator functions and apply handlers that are unreachable for new proposals but could confuse maintainers.
- **Fix**: Remove dead branches from `create_proposal`, `update_proposal`. Decide whether to keep `_APPLY_HANDLERS` entries for backward compatibility with any existing DB proposals, and comment accordingly.

### H5. `time_now` validation gap in `start_session` service

- **File**: `src/wizards_engine/services/session.py` (start_session function, ~line 300)
- **Found by**: Game Designer
- **Impact**: The monotonicity check (`time_now >= max_ended_time_now`) appears to rely on the route handler. If the service is called from another code path, a backwards `time_now` could produce negative FT deltas.
- **Fix**: Move the `validate_time_now` call into the service function itself.

---

## 3. Test Results & Coverage

### Test Suite

```
2350 passed, 1 failed, 1 xfailed, 18 warnings
Duration: ~2-3.5 minutes
```

The 1 failure is `test_progress_patch_uses_correct_payload` — a JS source assertion (see H3).

The 18 warnings are all `DeprecationWarning` from Starlette's test client about per-request cookies.

### Coverage Summary

| Module | Coverage | Notes |
|--------|----------|-------|
| models/ | **100%** | All models fully covered |
| schemas/ | **95-100%** | Minor gaps in clock, event, proposal, story, trait_template schemas |
| services/bond.py | **98%** | 4 uncovered lines |
| services/character.py | **100%** | |
| services/clock.py | **98%** | |
| services/event.py | **100%** | |
| services/feed.py | **80%** | Largest gap — 56 uncovered lines in personal feed filtering |
| services/gm_actions.py | **93%** | 39 uncovered lines across various action handlers |
| services/gm_dashboard.py | **100%** | |
| services/magic_effect.py | **98%** | |
| services/presence.py | **94%** | 5 uncovered lines |
| services/proposal.py | **80%** | 192 uncovered lines — primarily downtime action apply handlers and edge cases |
| services/session.py | **97%** | |
| services/story.py | **99%** | |
| services/trait.py | **99%** | |
| services/visibility.py | **95%** | |
| **TOTAL** | **94%** | |

### Key Coverage Gaps

1. **`services/proposal.py` (80%)** — 192 uncovered lines. Notable gaps:
   - Downtime action apply handlers (`_apply_regain_gnosis`, `_apply_work_on_project`, `_apply_rest`, `_apply_new_trait`, `_apply_new_bond`, `_apply_recharge_trait`, `_apply_maintain_bond`) — lines 1789-1918
   - Force-approve path for stale calculations — lines 2127-2129
   - Various magic sacrifice edge cases — lines 258-392, 460-468

2. **`services/feed.py` (80%)** — 56 uncovered lines, mostly in personal feed filtering and edge cases within `_personal_feed_query` and `_session_feed_query`.

3. **`services/gm_actions.py` (93%)** — 39 uncovered lines across error branches in various action handlers (modify_bond degradation, modify_clock edge cases, retire operations).

---

## 4. Game Design Assessment

### Overall Verdict: Strong

The system implements a mechanically sound, narratively aligned design for a low-crunch tabletop RPG. The core loop — proposal submission, GM adjudication, state tracking — is well-engineered.

### Strongest Design Elements

- **Unified bond model**: One concept serving as mechanical resource (charges/+1d), social connection (membership/presence), and narrative tissue. Degradation spiral tells a story.
- **Freeform magic system**: Intention + Symbolism + Sacrifice. No spell lists. The style bonus rewards narrative quality. Every magic action is a creative prompt.
- **Resource economy**: FT as universal currency, Plot as guaranteed success with diminishing marginal utility, Gnosis with triangular-number diminishing returns. No degenerate strategies detected.
- **Deferred narrative resolution**: The GM writes outcomes, not the system. The fiction leads and mechanics follow.

### Balance Observations (Monitor in Play)

- **Plot is powerful**: No cap on Plot spend per proposal. A player hoarding Plot (max 5-7) could dump it all for 5+ guaranteed successes. Balanced by scarcity (+1-2 per session, 3:1 FT conversion) and GM override authority.
- **Rest healing vs. stress rate**: 3-6 Stress healed per 1 FT may make Stress feel non-threatening if FT is plentiful. Balanced by modifier charge consumption.
- **Bond degradation spiral accelerates**: Each degradation shrinks the charge pool, making the next degradation come faster. Intentional design, but GMs should be aware.
- **Magic economy scales with progression**: Recovery rate (3 + lowest magic stat) grows as stats increase, which feels appropriate.

### Player Experience Concerns

1. **Magic proposal complexity**: `use_magic` requires intention, symbolism, sacrifice_list, suggested_stat, optional modifiers, optional plot_spend. The mobile UI must provide guided input with auto-calculation.
2. **Bond "stress" terminology**: DB column `stress` means "charges remaining" (5 = full). UI must present as "Charges: 3/5" not "Stress: 3".
3. **"Other" sacrifice shows 0 Gnosis**: Players see 0 contribution until GM assigns value. UI should explain "GM will assign value."
4. **Gnosis-to-dice conversion table not player-visible**: The triangular number table (1/3/6/10/15/21 Gnosis for 1-6 dice) is essential for magic planning. Should be exposed via API or UI.

### GM Experience Concerns

1. **Dashboard missing stress proximity**: Should show characters near their effective Stress max.
2. **14 GM action types through one endpoint**: Powerful but requires UI-driven forms to be usable.
3. **Clock adjustment is per-clock**: 5-10 individual API calls at session end for 5-10 active clocks. A batch shortcut would help.
4. **No undo for GM actions**: Corrections require a second action, doubling event log entries.
5. **resolve_trauma workflow is multi-field**: Choose bond → name trauma → provide description → optional rider event. UI must guide this smoothly.

### Narrative Alignment: Excellent

The system consistently prioritizes narrative over simulation. Player-written narratives, no dice recording, skill training via projects, bond-as-narrative-core, and the magic intention/symbolism/sacrifice structure all serve the vision.

**One structural dependency**: The system is heavily GM-dependent. No formula produces a result without GM interpretation. Intentional for the "developer-GM" model, but the game cannot function with a disengaged GM.

---

## 5. Architecture Assessment

### Overall Verdict: Clean with Known Technical Debt

The three-layer architecture (routes → services → models) is well-maintained across most of the codebase, with good cross-cutting concerns (auth, pagination, error envelopes, event creation, visibility).

### Layer Violations

1. **Proposal service raises `HTTPException`** (`proposal.py:28, 676, 2128, 2935, 2961, 3108`) — should raise domain exceptions, let routes translate to HTTP.
2. **Business logic in route handlers** — `find_time.py`, `recharge_trait.py`, `maintain_bond.py` each contain 100-200 lines of validation, state mutation, and event creation that should be in services.
3. **Character detail assembly in route** — `characters.py:314-455` has ~140 lines of data aggregation that should be a service function.

### DRY Violations

1. **Game object lookup by type**: 5 independent implementations of the `type-string → model-class` mapping (`bond.py`, `presence.py`, `story.py`, `starred.py`, `clock.py`).
2. **Active session ID query**: 3 implementations (`event.py`, `story.py`, `session.py`).
3. **404 error envelope**: ~50+ inline repetitions of `{"error": {"code": "not_found", ...}}`.
4. **Owner-or-GM authorization check**: 4+ repetitions of the same pattern.
5. **`_count_trauma_bonds` helper**: 3 identical implementations (`proposal.py`, `gm_actions.py`, `bond.py`).
6. **Full-character creation defaults**: Duplicated between `onboarding.py` and `me.py`.

### Data Model Issues

- **No DB-level enum constraints** on status/type string columns (relies on app-layer validation only).
- **Missing index on `Event.created_at`** — used by all feed endpoints with `?since=`/`?until=` filters.
- **N+1 risk in visibility filtering** — `_load_active_bonds` called per event per target. Bounded by small graph size but wasteful.

### Deployment Concerns

- **No CORS middleware** — not needed for same-origin SPA, but blocks cross-origin dev setups (e.g., Vite dev server).
- **No request logging/observability** — debugging production issues will require SQLite inspection.
- **Database URL at import time** — engine created at module import, complicating test configuration.

### Proposal Service is a God-Service

`services/proposal.py` at 3000+ lines handles CRUD, all 12 action type calculators, approval state machine, and effect application. Should be split into `proposal_crud.py`, `proposal_calculations.py`, and `proposal_approval.py`.

---

## 6. Medium Priority — Fix Soon After Launch

### M1. Proposal service raises HTTPException (layer violation)
- **File**: `src/wizards_engine/services/proposal.py:28`
- Define domain exceptions; catch-and-translate in routes.

### M2. Extract player direct-action business logic from routes
- **Files**: `api/routes/find_time.py`, `recharge_trait.py`, `maintain_bond.py`
- ~500 lines of business logic should be in a `services/player_actions.py`.

### M3. `calculate_maintain_bond` returns wrong semantic value
- **File**: `src/wizards_engine/services/proposal.py:959-963`
- `stress_healed` field contains current stress, not amount healed. Misleading in calculated_effect shown to GM.

### M4. Session timeline post-filters visibility after pagination
- **File**: `src/wizards_engine/api/routes/sessions.py:529-542`
- Can return fewer items than `limit` while `has_more` is True.

### M5. Consolidate duplicate helpers
- `_count_trauma_bonds` (3 copies), `_has_pending_resolve_trauma` (2 copies), game object lookup (5 copies), active session query (3 copies).

### M6. Add `raise_not_found` helper
- Eliminate ~50 inline error dict constructions across route files.

### M7. Add stress proximity to GM dashboard
- Characters near effective Stress max should be highlighted.

### M8. Improve test coverage for proposal approval paths
- `services/proposal.py` at 80% with 192 uncovered lines, primarily in downtime action apply handlers.

### M9. Improve test coverage for feed service
- `services/feed.py` at 80% with 56 uncovered lines in personal feed filtering.

---

## 7. Low Priority — Future Improvements

### Architecture & Code Quality
- Split proposal service into 3 modules (CRUD, calculations, approval)
- Add DB-level CHECK constraints on enum/status columns
- Add index on `Event.created_at`
- Cache bond graph per request in visibility filtering
- Add ULID format validation to path parameters
- Add request logging middleware
- Add CORS middleware for dev environments
- Add `__all__` exports to service modules
- Promote private imports from `presence.py` used by `visibility.py`

### Game Design & UX
- Expose Gnosis-to-dice conversion table to players
- Add batch clock adjustment endpoint for GM session-end workflow
- Add "danger zone" indicators to character sheet (near stress max, high bond degradation, 0-charge traits)
- Clarify "Other" sacrifice display with "GM assigns value" indicator
- Consider adding player-visible style bonus hint ("GM's assessment may adjust your final dice pool")

### Test Quality
- Fix the 18 DeprecationWarning from Starlette test client cookie usage
- Add integration tests for full proposal lifecycle (submit → approve → verify state changes) for all 12 action types
- Add edge case tests for magic sacrifice combinations
- Add concurrent proposal tests (two proposals consuming same resource)

---

## 8. What Looks Good

These areas are well-implemented and need no changes:

- **Authentication & authorization**: Consistently applied via `get_current_user`/`require_gm` dependencies. Player ownership checks are thorough.
- **Error envelope format**: Uniform `{"error": {"code": ..., "message": ..., "details": ...}}` across all routes. Custom exception handler ensures consistency.
- **ULID-based cursor pagination**: Well-implemented and consistent across all list endpoints.
- **Event creation**: Single `create_event` path ensures consistent structure, validated actor types, and visibility levels.
- **Session lifecycle**: Draft → Active → Ended with forward-only transitions, no skip states.
- **Bond-graph BFS traversal**: Correctly implements Character-intermediary constraint per spec.
- **Soft delete pattern**: Consistent across all Game Objects.
- **SQLite pragmas**: FK enforcement + WAL mode correctly set on every connection.
- **No SQL injection vectors**: All DB access through SQLAlchemy ORM with parameterized queries.
- **No mass assignment**: Pydantic schemas validate all input at the boundary.
- **GM actions discriminated union**: Excellent type safety and auto-generated OpenAPI documentation.
- **TimestampMixin**: ULID PKs + created_at/updated_at with no duplication.
- **Model coverage**: 100% across all model files.
- **Test suite scale**: 2350 tests providing strong regression safety net.
