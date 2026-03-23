# Epic 8.4 — Game Objects Browser Redesign

**Phase**: 8 — UI Cleanup & UX Modernization
**Depends on**: 8.1.5 (tab rename), 8.1.6 (readability fixes), 8.1.7 (DataTable component)
**Blocks**: 8.6 (CRUD forms — needs CRUD buttons from 8.4.4)
**Parallel with**: 8.2, 8.3, 8.5 (after 8.1 completes)

---

## Overview

Redesign the World Browser (renamed to "Game Objects") from a card grid with client-side name search into a sortable, filterable DataTable with PC/NPC sub-tabs, readable descriptions, and CRUD action buttons. Also modernize the Sessions view to use consistent table UX. Backend list endpoints gain sort and filter parameters.

---

## Stories

| Story | Status | Completed |
|-------|--------|-----------|
| 8.4.1 — Backend: Add Sort/Filter Params to List Endpoints | 🟢 Complete | 2026-03-22 |
| 8.4.2 — Frontend: Game Objects Browser with DataTable and PC/NPC Sub-Tabs | 🔴 Not started | — |
| 8.4.3 — Modernize Sessions View | 🟢 Complete | 2026-03-22 |
| 8.4.4 — Add CRUD Action Buttons to Game Objects Browser | 🟢 Complete | 2026-03-22 |

### Story 8.4.1 — Backend: Add Sort/Filter Params to List Endpoints

**Files to modify**:
- `src/wizards_engine/api/routes/characters.py` — add `sort_by`, `sort_dir` params
- `src/wizards_engine/api/routes/groups.py` — add `name`, `sort_by`, `sort_dir` params
- `src/wizards_engine/api/routes/locations.py` — add `name`, `sort_by`, `sort_dir` params
- `src/wizards_engine/api/routes/stories.py` — add `sort_by`, `sort_dir` params
- Corresponding service files — add sort/filter to query builders

**Spec refs**: [game-objects.md](../domains/game-objects.md) (CRUD Operations)

**Implementation notes**:
- Consistent params for all four list endpoints: `sort_by: str = "name"` (allowed: name, created_at, updated_at) and `sort_dir: str = "asc"` (allowed: asc, desc)
- `GET /characters` already has `name` filter. Add to `GET /groups` and `GET /locations` — case-insensitive partial match (same pattern as characters)
- `GET /stories` already has `name` filter via status/tag/owner. Add `sort_by` and `sort_dir`
- Update service query builders to accept sort parameters and apply `ORDER BY` accordingly
- Reuse the `paginate()` `order_by` override added in 8.3.1 — if 8.3.1 hasn't run yet, add it here
- PC/NPC filtering already supported via `detail_level=full` / `detail_level=simplified` on characters — no new parameter needed

**Acceptance criteria**:
1. `GET /api/v1/characters?sort_by=name&sort_dir=desc` returns characters sorted Z→A
2. `GET /api/v1/groups?name=guild&sort_by=created_at` returns groups matching "guild" sorted by creation date
3. `GET /api/v1/locations?name=tower&sort_by=name` returns locations matching "tower" sorted alphabetically
4. `GET /api/v1/stories?sort_by=updated_at&sort_dir=desc` returns stories sorted by most recently updated
5. Default behavior unchanged when no sort params provided (existing tests pass)
6. Pagination cursor works correctly with non-default sort orders
7. Backend tests cover sort params and name filters for all four endpoints

### Story 8.4.2 — Frontend: Game Objects Browser with DataTable and PC/NPC Sub-Tabs

**Files to modify**:
- `src/wizards_engine/static/js/views/world.js` — replace card grid with DataTable, add PC/NPC sub-tabs
- `src/wizards_engine/static/css/app.css` — add Game Objects browser styles

**Spec refs**: [web-ui.md](../domains/web-ui.md) (World Browser)

**Implementation notes**:
- Tab is now labeled "Game Objects" (renamed in 8.1.5). Route remains `#/gm/world` and `#/world`
- Replace GameObjectCard grid with DataTable for Characters, Groups, and Locations tabs
- Stories tab keeps card layout (stories have a richer card shape with entries and ownership)
- Characters tab: add sub-tabs "All" | "PCs" | "NPCs". PCs filter by `detail_level=full`, NPCs by `detail_level=simplified`
- Character columns: Name (linked), Type badge (PC/NPC), Description (readable text, not muted gray), Star toggle
- Group columns: Name (linked), Tier (badge), Description, Star toggle
- Location columns: Name (linked), Parent location name, Description, Star toggle
- DataTable sorting passed to backend API via `sort_by` and `sort_dir` params
- Star toggle remains optimistic UI (existing pattern)
- Search functionality migrates from client-side text input to DataTable's built-in filter

**Acceptance criteria**:
1. Characters, Groups, Locations tabs render as DataTable with column headers
2. Characters tab has sub-tabs: All, PCs, NPCs — filtering works correctly
3. Description text is readable (body color, not muted gray)
4. Columns are sortable via header click
5. Text filter reduces visible rows
6. Star toggle works (optimistic UI with rollback)
7. Row click navigates to appropriate detail view
8. Stories tab keeps existing card layout
9. Responsive: stacked card layout on mobile
10. Existing search by name functionality preserved (via DataTable filter)

### Story 8.4.3 — Modernize Sessions View

**Files to modify**:
- `src/wizards_engine/static/js/views/gm-sessions.js` — replace session list with DataTable
- `src/wizards_engine/static/css/app.css` — add session-specific table styles, participant avatar styles

**Spec refs**: [web-ui.md](../domains/web-ui.md) (Session Management)

**Implementation notes**:
- Replace current plain session list with DataTable
- Columns: Session Name/Number, Status badge (Draft/Active/Ended), Date, Participant count (with initials circles preview), Actions
- Status badges reuse the existing `.proposal-status-badge` pattern with session-specific modifiers
- Participant avatars: initials circles (first letter of display name) overlapping slightly
- Create/edit form remains inline (avoids route change for small forms) but tighten spacing to match modern form pattern
- Row click navigates to `#/gm/sessions/{id}`

**Acceptance criteria**:
1. Sessions list renders as DataTable with sortable columns
2. Status badges show correct colors for Draft (neutral), Active (green), Ended (muted)
3. Participant count shows with overlapping initials circles
4. Row click navigates to session detail
5. Create button still accessible above the table
6. Visual style consistent with other redesigned DataTable views
7. Inline create/edit forms have tighter spacing matching other forms

### Story 8.4.4 — Add CRUD Action Buttons to Game Objects Browser

**Files to modify**:
- `src/wizards_engine/static/js/views/world.js` — add "Create New" button and per-row Edit/Archive actions
- `src/wizards_engine/static/js/views/world-detail.js` — add Edit/Archive buttons on detail views

**Spec refs**: [game-objects.md](../domains/game-objects.md) (CRUD Operations)

**Implementation notes**:
- "Create New" button above each DataTable (Characters, Groups, Locations) — GM-only, hidden for players
- Per-row action buttons: "Edit" navigates to `#/gm/world/{type}/{id}/edit`, "Archive" triggers confirmation dialog then soft-delete
- Confirmation dialog for Archive: "Are you sure you want to archive [name]? This can be undone." with Confirm/Cancel buttons
- Uses existing `DELETE /api/v1/{type}/{id}` endpoints (soft delete)
- After archive, remove the row from the DataTable (optimistic UI) and show success toast
- Detail views (`world-detail.js`) also get Edit and Archive buttons in the header area
- All CRUD buttons GM-only (check `Alpine.store('app').isGm()`)
- "Create New" navigates to routes defined in Epic 8.6: `#/gm/world/characters/new`, `#/gm/world/groups/new`, `#/gm/world/locations/new`

**Acceptance criteria**:
1. "Create New" button visible above each DataTable for GM users
2. "Create New" hidden for player users
3. "Edit" action button on each row navigates to edit route (GM-only)
4. "Archive" action button shows confirmation dialog before soft-deleting (GM-only)
5. After archive, row removed from table and success toast shown
6. Detail views show Edit and Archive buttons in header (GM-only)
7. Player users see no action buttons on rows or detail views
8. Archive confirmation dialog has Confirm and Cancel buttons; Cancel does nothing

---

## Notes

- 8.4.1 (backend) can start immediately — no dependency on 8.1 components
- 8.4.2 depends on 8.4.1 (sort params) and 8.1.7 (DataTable component)
- 8.4.3 depends on 8.1.7 (DataTable) but is independent of other 8.4 stories
- 8.4.4 depends on 8.4.2 (DataTable must be in place to add row actions)
- 8.4.4 blocks Epic 8.6 (CRUD forms need the "Create New" and "Edit" navigation targets)
