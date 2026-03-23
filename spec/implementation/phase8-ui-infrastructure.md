# Epic 8.1 — Shared Infrastructure & Bug Fixes

**Phase**: 8 — UI Cleanup & UX Modernization
**Depends on**: Phase 6 (complete Web UI)
**Blocks**: All other Phase 8 epics (8.2–8.6)
**Parallel with**: None (foundational)

---

## Overview

Fix all reported UI bugs (nav bar race condition, meter maximums, bond dyad duplication, description truncation, text readability), extract duplicated code into shared utilities, and build two reusable components (DataTable, ExpandableItem) that subsequent epics depend on. This epic establishes the corrected foundations and new patterns used by all Phase 8 view redesigns.

---

## Stories

| Story | Status | Completed |
|-------|--------|-----------|
| 8.1.1 — Fix Nav Bar Visibility on Initial Load | 🟢 Complete | 2026-03-22 |
| 8.1.2 — Fix Meter Maximums and Extend PCSummary Schema | 🔴 Not started | — |
| 8.1.3 — Fix Bond Perspective Filtering (Backend) | 🔴 Not started | — |
| 8.1.4 — Extract Shared Constants and Utilities | 🔴 Not started | — |
| 8.1.5 — Rename GM Tabs and Fix More Tab | 🔴 Not started | — |
| 8.1.6 — Fix Description Readability and Truncation | 🔴 Not started | — |
| 8.1.7 — Build Reusable DataTable Component | 🔴 Not started | — |
| 8.1.8 — Build Reusable ExpandableItem Component | 🔴 Not started | — |

### Story 8.1.1 — Fix Nav Bar Visibility on Initial Load

**Files to modify**:
- `src/wizards_engine/static/js/store.js` — dispatch `nav:refresh` after `setUser()` completes
- `src/wizards_engine/static/js/app.js` — ensure auth init flow triggers nav re-render

**Spec refs**: [web-ui.md](../domains/web-ui.md) (Navigation Architecture)

**Implementation notes**:
- Root cause: `store.init()` fires async `GET /me`. By the time `nav.mount()` runs, `store.user` is still null, so `_buildNav()` returns null and nav is hidden
- Nav re-renders on `hashchange` or `nav:refresh` events, which is why clicking "All" in the Feed makes it appear
- Fix: after `store.setUser(data)` resolves in `store.init()`, dispatch `document.dispatchEvent(new CustomEvent("nav:refresh"))`
- Alternative: have `setUser()` itself dispatch `nav:refresh` automatically

**Acceptance criteria**:
1. Navigate to `#/gm` on fresh page load (hard refresh) — nav bar appears immediately without any user interaction
2. Navigate to `#/` as player on fresh page load — nav bar appears immediately
3. Test on throttled connection (slow 3G) — nav bar appears as soon as auth check completes, not before
4. Existing nav behavior (tab switching, badge updates, hashchange) unchanged

### Story 8.1.2 — Fix Meter Maximums and Extend PCSummary Schema

**Files to modify**:
- `src/wizards_engine/schemas/gm_dashboard.py` — add `stress_max`, `free_time_max`, `plot_max`, `gnosis_max` to `PCSummary`
- `src/wizards_engine/services/gm_dashboard.py` — compute `stress_max` as `9 - count_trauma_bonds(db, char.id)`, set static maxes for others
- `src/wizards_engine/static/js/views/gm-dashboard.js` — remove hardcoded `STRESS_MAX=5` and `RESOURCE_MAX=5`, read from API response

**Spec refs**: [character-core.md](../domains/character-core.md) (Stress, Meters)

**Implementation notes**:
- Bug: `gm-dashboard.js` lines 44-46 hardcode `STRESS_MAX = 5` and `RESOURCE_MAX = 5` for all four meters
- Correct values: Stress max = 9 (minus trauma bond count), FT max = 20, Plot max = 5, Gnosis max = 23
- `character.js` lines 40-43 already has the correct constants — but the dashboard should read from API, not hardcode
- The `count_trauma_bonds` pattern already exists in `get_stress_proximity()` — reuse it
- Also fix the dashboard meter color variables to use `--we-stress-red`, `--we-ft-green`, `--we-plot-amber`, `--we-gnosis-blue` instead of generic Pico variables for visual consistency with character sheet

**Acceptance criteria**:
1. `GET /api/v1/gm/dashboard` response includes `stress_max`, `free_time_max`, `plot_max`, `gnosis_max` per PC
2. PC with 0 trauma bonds: `stress_max = 9`
3. PC with 1 trauma bond: `stress_max = 8`
4. Dashboard meter bars render with correct ranges (Stress out of 9, FT out of 20, etc.)
5. Dashboard meter colors match character sheet meter colors
6. Add backend test asserting PCSummary meter maximums are correct

### Story 8.1.3 — Fix Bond Perspective Filtering (Backend)

**Files to modify**:
- `src/wizards_engine/services/bonds.py` (or `shared.py`) — add `owned_only` parameter to `get_bonds_display_for_entity()`
- `src/wizards_engine/api/routes/characters.py` — pass `owned_only=True`
- `src/wizards_engine/api/routes/groups.py` — pass `owned_only=True`
- `src/wizards_engine/api/routes/locations.py` — pass `owned_only=True`

**Spec refs**: [bonds.md](../domains/bonds.md) (Bond Dyads)

**Implementation notes**:
- Bug: character/group/location detail views show both sides of a bond dyad. If NPC has a bond to PC AND PC has a bond to NPC, both appear on each entity's bond list
- Root cause: `get_bonds_display_for_entity()` queries both outbound bonds (owner_id = entity) AND inbound bidirectional bonds (target_id = entity)
- Fix: add `owned_only: bool = False` parameter. When True, skip the inbound bond query — only return bonds where the entity is the owner
- Set `owned_only=True` in all detail route handlers
- Update existing bond display tests that explicitly assert inbound bonds appear — these are now testing the old (incorrect) behavior
- The partner's bond is still viewable by navigating to the partner's detail page

**Acceptance criteria**:
1. NPC detail view shows only bonds owned by the NPC, not bonds from PCs pointing at the NPC
2. PC detail view shows only bonds owned by the PC
3. Group detail view shows only bonds owned by the group
4. Location detail view shows only bonds owned by the location
5. Navigating to the bond partner's detail page still shows the partner's own bond to the original entity
6. Bond counts in summary views are updated to reflect owned-only counts
7. Backend tests updated and passing

### Story 8.1.4 — Extract Shared Constants and Utilities

**Files to create**:
- `src/wizards_engine/static/js/constants.js` — game constants (`STRESS_MAX`, `FT_MAX`, `PLOT_MAX`, `GNOSIS_DISPLAY_MAX`, skill names, meter colors)

**Files to modify**:
- `src/wizards_engine/static/js/utils.js` — add `snippet()`, `escAttr()`, `showSuccess()`, `requireGm()`
- `src/wizards_engine/static/index.html` — add `<script defer src="/static/js/constants.js">` before other scripts
- All views/components that duplicate `_esc`, `_snippet`, `_clamp` local closures — remove duplicates

**Spec refs**: [web-ui.md](../domains/web-ui.md) (Technology Stack)

**Implementation notes**:
- DRY violations identified by architect: `_esc` duplicated in 10+ files, `_snippet` in 4 files, `_clamp` in 3 files
- `world.js` and `sacrifice-builder.js` have a diverged `_esc` variant that adds `.replace(/'/g, "&#39;")` for Alpine attribute safety — consolidate as `window.utils.escAttr()`
- `_showSuccess()` duplicated in `gm-queue.js` and `gm-sessions.js` — move to `window.utils.showSuccess(message)`
- GM access guard duplicated in `gm-queue.js`, `gm-dashboard.js`, `gm-sessions.js` — extract as `window.utils.requireGm(viewEl)` returning boolean
- `constants.js` must load before all views (add to index.html script order)

**Acceptance criteria**:
1. `window.constants.STRESS_MAX === 9`, `FT_MAX === 20`, `PLOT_MAX === 5`, `GNOSIS_DISPLAY_MAX === 23`
2. No file contains a local `_esc` function definition (all use `window.utils.esc()` or `window.utils.escAttr()`)
3. No file contains a local `_snippet` function definition (all use `window.utils.snippet()`)
4. No file contains a local `_clamp` function definition (all use `window.utils.clamp()`)
5. `window.utils.showSuccess(message)` works from any view
6. `window.utils.requireGm(viewEl)` renders access denied and returns false for non-GM users
7. All existing functionality unchanged after refactor

### Story 8.1.5 — Rename GM Tabs and Fix More Tab

**Files to modify**:
- `src/wizards_engine/static/js/components/nav.js` — update GM tab labels
- `src/wizards_engine/static/js/router.js` — update or remove More tab route

**Spec refs**: [web-ui.md](../domains/web-ui.md) (Navigation Architecture)

**Implementation notes**:
- Rename: "Feed" → "Event Feed", "World" → "Game Objects"
- "More" tab currently routes to a static placeholder with no content
- Option A: implement More as a dropdown/submenu linking to Players, Invites, Trait Templates, Clocks, Profile
- Option B: remove More tab and add a gear/settings icon that opens a dropdown for those items
- The items currently under More (players, invites, templates, clocks) have their own routes and views — they just need nav access

**Acceptance criteria**:
1. GM nav bar shows "Queue", "Event Feed", "Game Objects", "Sessions" as primary tabs
2. More tab either functions as a working dropdown/submenu or is removed with its items accessible elsewhere
3. All routes (`#/gm/feed`, `#/gm/world`, `#/gm/players`, `#/gm/invites`, `#/gm/trait-templates`, `#/gm/clocks`) still functional
4. Player tab labels unchanged
5. Mobile nav bar renders correctly with new labels (labels may be shorter on mobile)

### Story 8.1.6 — Fix Description Readability and Truncation

**Files to modify**:
- `src/wizards_engine/static/css/app.css` — change description text color from `--pico-muted-color` to `--pico-color`
- `src/wizards_engine/static/js/views/character.js` — remove `_snippet(c.description, 160)` call in header
- `src/wizards_engine/static/js/views/world-detail.js` — remove `_snippet(c.description, 160)` call in PC summary

**Spec refs**: [web-ui.md](../domains/web-ui.md) (Component Definitions)

**Implementation notes**:
- Readability: `.game-object-card__snippet` uses `color: var(--pico-muted-color, #aaa)` which is hard to read on dark backgrounds. Change to `var(--pico-color, #ddd)` for body text. Apply same fix to other `__desc` CSS classes
- Truncation: `character.js:195` and `world-detail.js:235` both call `_snippet(c.description, 160)` — the GM explicitly says "The Description shouldn't be truncated" on detail views
- Keep truncation on list/card views (GameObjectCard 120-char snippet is appropriate for browsing)
- Add utility CSS classes: `.text-body` (readable), `.text-muted` (metadata), `.text-label` (uppercase small)

**Acceptance criteria**:
1. Game object card descriptions readable without hover on dark background
2. Character detail view shows full description text (not truncated to 160 chars)
3. World-detail PC summary shows full description text
4. Card views (world browser list) still show 120-char snippet
5. All description text meets WCAG AA contrast ratio on dark theme

### Story 8.1.7 — Build Reusable DataTable Component

**Files to create**:
- `src/wizards_engine/static/js/components/data-table.js` — sortable, filterable table component

**Files to modify**:
- `src/wizards_engine/static/css/app.css` — add DataTable CSS (`.dt-root`, `.dt-table`, `.dt-th`, `.dt-row`, `.dt-td`, etc.)
- `src/wizards_engine/static/index.html` — add script tag

**Spec refs**: [web-ui.md](../domains/web-ui.md) (Component Definitions)

**Implementation notes**:
- This is the highest-leverage new component — used by GM Feed (8.3), Game Objects browser (8.4), Sessions (8.4.3), and Queue Groups (8.2.4)
- Component API: `new DataTable(container, { columns, onRowClick, rowActions })` with `.setRows(data)` and `.destroy()`
- Column config: `{ key, label, sortable, filter ('text'|'select'), render(value, row), width, linkTo(row) }`
- Client-side sort (click header toggles asc/desc) and filter (global text + per-column select dropdowns)
- Row click fires `onRowClick(rowData)` for navigation
- Responsive: table layout on desktop (>=600px), stacked card layout on mobile (<600px) using `.dt-th--hide-mobile`/`.dt-td--hide-mobile` classes
- Keyboard accessible: arrow keys navigate rows, Enter activates row click, tab moves between filter controls
- Empty state: shows configurable message when no rows match filters
- Follows existing component pattern: `window.components.DataTable` namespace
- Loading skeleton shimmer animation while data loads

**Acceptance criteria**:
1. Component renders a table with column headers from config
2. Clicking a sortable column header toggles sort direction (asc → desc → asc)
3. Global text filter reduces visible rows to matches (case-insensitive)
4. Select filter dropdown shows distinct values from data for that column
5. Row click fires `onRowClick` callback with row data
6. Row action buttons render and fire callbacks
7. Custom `render` function on column transforms cell content
8. Empty state message shown when no rows match filters
9. Responsive: renders as card list below 600px viewport width
10. Arrow key navigation between rows works; Enter activates row
11. ARIA attributes: `role="grid"`, `aria-sort` on sorted column, `scope="col"` on headers

### Story 8.1.8 — Build Reusable ExpandableItem Component

**Files to create**:
- `src/wizards_engine/static/js/components/expandable-item.js` — expand/collapse card pattern

**Files to modify**:
- `src/wizards_engine/static/css/app.css` — add ExpandableItem CSS (`.exp-item`, `.exp-item__trigger`, `.exp-item__body`, etc.)
- `src/wizards_engine/static/index.html` — add script tag

**Spec refs**: [web-ui.md](../domains/web-ui.md) (Component Definitions)

**Implementation notes**:
- Used for trait and bond cards in character detail views (Epic 8.5)
- Component API: `window.components.expandableItem.render(props)` returns HTML string, `.attach(container)` wires toggle listeners
- Props: `{ id, name, dotsHtml, badgeHtml, description, actions: [{label, href?, dataAttrs?}], footerLinkHtml, variant: 'trait'|'bond' }`
- Collapsed state: name + charge dots + optional badge (e.g., trauma indicator)
- Expanded state: full description + action buttons + optional footer link (e.g., "Go to [partner] →")
- Toggle: click trigger button, toggle `exp-item--open` class, set `aria-expanded`, show/hide body
- Pure DOM event handling (no Alpine dependency) via delegated click listeners
- Chevron rotates 90deg on expand via CSS transition

**Acceptance criteria**:
1. Collapsed item shows name and charge dots in a single row
2. Clicking the item trigger expands to show description and action buttons
3. Clicking again collapses back to compact view
4. `aria-expanded` attribute toggles correctly (screen reader accessible)
5. Trait variant shows recharge/edit action buttons
6. Bond variant shows "View [partner]" link and maintain/edit buttons
7. Optional badge (trauma, degraded) renders next to name when provided
8. Component works when multiple items are rendered in a list
9. Keyboard: Enter/Space on trigger toggles expand/collapse

---

## Notes

- All 8 stories in this epic are independent and can run in parallel (maximum parallelism = 8)
- Stories 8.1.1–8.1.6 are bug fixes and refactors; stories 8.1.7–8.1.8 are new component builds
- The DRY extraction in 8.1.4 touches many files but is safe — each change replaces a local function with a call to the shared utility
- The bond perspective fix (8.1.3) is the most impactful behavioral change — requires updating existing tests
