# Epic 6.5 — GM Tools & Session Management

**Phase**: 6 — Web UI
**Depends on**: Epic 6.1 (SPA Foundation), Epic 6.3 (GM queue component), Stories 5.5.4 + 5.5.5 + 5.5.6
**Blocks**: Epic 6.6 (Polish)
**Parallel with**: Epics 6.2, 6.4 (partially — 6.5.2–6.5.5 can start after 6.1)

---

## Overview

Build the GM-specific tooling: aggregated dashboard (pending proposals, PC summaries, near-completion clocks), session management with timeline view, player roster and invite management, the GM direct actions form (14 action types), and trait template catalog + clock management. The GM dashboard is the GM's landing page and requires Phase 5.5 backend endpoints.

---

## Stories

| Story | Status | Completed |
|-------|--------|-----------|
| 6.5.1 — GM Dashboard | 🟢 Complete | 2026-03-19 |
| 6.5.2 — Session Management + Session Timeline | 🟢 Complete | 2026-03-19 |
| 6.5.3 — Player Roster + Invite Management | 🟢 Complete | 2026-03-19 |
| 6.5.4 — GM Direct Actions Form | 🟢 Complete | 2026-03-19 |
| 6.5.5 — Trait Template Catalog + Clock Management | 🟢 Complete | 2026-03-19 |

### Story 6.5.1 — GM Dashboard

**Files to create**:
- `src/wizards_engine/static/js/views/gm-dashboard.js` — GM dashboard view

**Spec refs**: [web-ui.md](../domains/web-ui.md) (GM Dashboard), Stories 5.5.4, 5.5.6

**Implementation notes**:
- Fetches `GET /api/v1/gm/dashboard` on mount (Story 5.5.4)
- Also uses `GET /api/v1/characters/summary` (Story 5.5.6) if needed for richer PC data
- Three sections: pending proposals (links to queue), PC summaries (links to character detail), near-completion clocks

**Acceptance criteria**:
1. `#/gm` shows GM dashboard with three sections
2. **Pending proposals section**: count badge, list of proposal summaries (character name, action type, submitted time). Tap → navigates to `#/gm/queue`
3. **PC summaries section**: card per PC showing name, stress bar, FT, Plot, Gnosis. Tap → navigates to character detail
4. **Near-completion clocks section**: clocks at `segments - 1` progress, showing name, association, progress. Tap → navigates to associated object detail
5. All sections show empty state when no items
6. Dashboard registers polling (60s interval on `GET /gm/dashboard`)

### Story 6.5.2 — Session Management + Session Timeline

**Files to create**:
- `src/wizards_engine/static/js/views/gm-sessions.js` — session list and management
- `src/wizards_engine/static/js/views/session-detail.js` — session detail + timeline

**Spec refs**: [web-ui.md](../domains/web-ui.md) (Session Management), [downtime.md](../domains/downtime.md) (Session Lifecycle)

**Acceptance criteria**:
1. `#/gm/sessions` shows session list grouped by status (active first, then draft, then ended)
2. "Create Session" button → form with name, summary, time_now fields → `POST /api/v1/sessions`
3. Draft session: edit button (name, summary, time_now, notes), participant management, "Start" button, "Delete" button
4. Active session: "End" button, participant management (late joins), view timeline
5. Ended session: read-only detail view, view timeline
6. Participant management: add from character list (`POST /sessions/{id}/participants`), toggle additional_contribution flag
7. Start session: confirmation dialog → `POST /sessions/{id}/start` → FT/Plot distribution summary shown
8. End session: confirmation dialog → `POST /sessions/{id}/end`
9. `#/gm/sessions/{id}/timeline` shows session events using FeedItem components, ULID cursor pagination
10. Timeline registers 30s polling on `GET /sessions/{id}/timeline` (for active sessions only)

### Story 6.5.3 — Player Roster + Invite Management

**Files to create**:
- `src/wizards_engine/static/js/views/gm-players.js` — player roster and invite management

**Spec refs**: [web-ui.md](../domains/web-ui.md) (Player Management), [auth.md](../domains/auth.md) (Invites)

**Acceptance criteria**:
1. `#/gm/players` shows player roster: display name, character name, last active
2. "Invite Player" button → form with character name → `POST /api/v1/invites` → shows invite link/code
3. Pending invites section: shows unused invites with character name and invite code
4. Each player row: link to character detail, option to regenerate login code (`POST /api/v1/users/{id}/regenerate-token`)
5. Invite link displayed as copyable text (click to copy)

### Story 6.5.4 — GM Direct Actions Form

**Files to create**:
- `src/wizards_engine/static/js/views/gm-actions.js` — GM direct actions form

**Spec refs**: [web-ui.md](../domains/web-ui.md) (GM Actions), [actions.md](../domains/actions.md) (GM Actions — 14 types)

**Implementation notes**:
- This is the most complex single form in the UI
- 14 GM action types with per-type `changes` payloads
- Target picker: select game object type → search/select specific object
- Changes form: per-type fields (e.g., modify_character shows meter fields, modify_bond shows stress/degradation)
- Narrative field, optional visibility override

**Acceptance criteria**:
1. `#/gm/actions` shows action type selector with all 14 types
2. **Target picker**: type selector (character/group/location/bond/trait/effect/clock) → search by name → select
3. **modify_character**: meter sliders/inputs for stress, free_time, plot, gnosis. Skill level pickers. Magic stat XP/level. Attributes JSON editor.
4. **create_bond / modify_bond / retire_bond**: bond-specific fields (target, labels, stress, degradations)
5. **create_trait / modify_trait / retire_trait**: trait-specific fields (template picker, slot type, charge)
6. **create_effect / modify_effect / retire_effect**: effect-specific fields (name, charges, power_level)
7. **award_xp**: magic stat selector, XP amount
8. **modify_group**: tier input
9. **modify_location**: parent selector
10. **modify_clock**: progress delta/absolute, annotation fields
11. Narrative text area and optional visibility dropdown on all types
12. Submit calls `POST /api/v1/gm/actions` → success toast with event summary
13. Batch mode toggle: queue multiple actions → submit all via `POST /api/v1/gm/actions/batch` (Story 5.5.5)
14. Validation errors shown inline per field

### Story 6.5.5 — Trait Template Catalog + Clock Management

**Files to create**:
- `src/wizards_engine/static/js/views/gm-templates.js` — trait template CRUD
- `src/wizards_engine/static/js/views/gm-clocks.js` — clock management

**Spec refs**: [web-ui.md](../domains/web-ui.md) (Trait Templates, Clocks), [traits.md](../domains/traits.md) (Trait Template CRUD), [game-objects.md](../domains/game-objects.md) (Clocks)

**Acceptance criteria**:
1. **Trait Templates**: list all templates (`GET /trait-templates`), filterable by type (core/role)
2. "Create Template" form: name, description, type (core/role) → `POST /api/v1/trait-templates`
3. Edit template: name, description (type immutable) → `PATCH /api/v1/trait-templates/{id}`
4. Delete template: confirmation → `DELETE /api/v1/trait-templates/{id}` (soft-delete)
5. Template cards show usage count (how many characters reference this template)
6. **Clocks**: list all clocks (`GET /clocks`), grouped by association (character/group/location)
7. "Create Clock" form: name, segments, association type + target → `POST /api/v1/clocks`
8. Clock cards show ClockProgress component, association link, completion status
9. Tap clock → detail: progress history via event log, modify progress via GM action shortcut

---

## Notes

- GM dashboard is the GM's primary landing page — fast load and clear information hierarchy are critical
- 6.5.4 (GM direct actions form) is the most complex single form in the UI — 14 action types with per-type payloads
- 6.5.2–6.5.5 can start in parallel after 6.1 completes, but 6.5.1 requires Phase 5.5 backend endpoints
- GM-player dual identity: `#/gm/character` reuses the character sheet component from 6.2.2
