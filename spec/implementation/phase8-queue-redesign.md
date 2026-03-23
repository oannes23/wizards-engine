# Epic 8.2 — GM Queue Tab Redesign

**Phase**: 8 — UI Cleanup & UX Modernization
**Depends on**: 8.1.2 (meter fixes), 8.1.4 (shared constants), 8.1.7 (DataTable component)
**Blocks**: None
**Parallel with**: 8.3, 8.4, 8.5 (after 8.1 completes)

---

## Overview

Redesign the GM Queue tab (`#/gm`) from a wide single-column layout into an information-dense dashboard with a 3-column PC card grid showing correct meter maximums, low-charge trait/bond indicators, recent events per PC, and a Groups section sorted by activity with project clocks. Requires a new backend endpoint (`/gm/queue-summary`) and one database index migration.

---

## Stories

| Story | Status | Completed |
|-------|--------|-----------|
| 8.2.1 — Backend: New /gm/queue-summary Endpoint | 🟢 Complete | 2026-03-22 |
| 8.2.2 — Database Migration: event_targets Index | 🟢 Complete | 2026-03-22 |
| 8.2.3 — Frontend: 3-Column PC Card Grid | 🟢 Complete | 2026-03-22 |
| 8.2.4 — Frontend: Groups Section in Queue | 🟢 Complete | 2026-03-22 |

### Story 8.2.1 — Backend: New /gm/queue-summary Endpoint

**Files to create/modify**:
- `src/wizards_engine/schemas/gm_dashboard.py` — add `PCQueueCard`, `GroupQueueCard`, `LowChargeItem`, `RecentEventSummary`, `GmQueueSummaryResponse`
- `src/wizards_engine/services/gm_dashboard.py` (or new `services/queue_summary.py`) — add `get_low_charge_slots()`, `get_recent_events_for_target()`, `get_active_clocks_for_group()`
- `src/wizards_engine/api/routes/gm.py` — add `GET /api/v1/gm/queue-summary` route

**Spec refs**: [character-core.md](../domains/character-core.md) (Meters), [bonds.md](../domains/bonds.md) (Bond Charges), [traits.md](../domains/traits.md) (Trait Charges)

**Implementation notes**:
- `PCQueueCard` includes: id, name, meters with actual maxes (stress_max = 9 - trauma_count, ft_max = 20, plot_max = 5, gnosis_max = 23), `low_charge_traits` (active core/role traits with charge <= 2), `low_charge_bonds` (active pc_bonds with charges <= 2, excluding is_trauma), `recent_events` (last 3 events targeting this character)
- `GroupQueueCard` includes: id, name, tier, `active_clocks` (all non-completed clocks associated with group), `recent_events` (last 3 events targeting this group)
- Groups sorted by most-recent-event timestamp descending (groups with no events at end)
- Low-charge query uses existing `ix_slots_owner` index: `WHERE owner_type='character' AND owner_id=? AND slot_type IN ('core_trait','role_trait','pc_bond') AND is_active=True`
- Recent events query joins `event_targets` + `events` filtered by target — needs the new `ix_event_targets_target` index from 8.2.2
- Reuse `count_trauma_bonds` pattern from `get_stress_proximity()` for stress_max computation

**Acceptance criteria**:
1. `GET /api/v1/gm/queue-summary` returns 200 with `pc_cards` and `group_cards` lists
2. Each PC card includes correct meter values and maximums
3. PC with trauma bonds shows reduced `stress_max`
4. Low-charge traits list includes only active core/role traits with charge <= 2
5. Low-charge bonds list includes only active non-trauma pc_bonds with charges <= 2
6. Recent events per PC/group return at most 3 items, newest first
7. Groups sorted by most-recent-event desc; groups with no events appear last
8. Endpoint returns 403 for non-GM users
9. Backend tests cover all the above scenarios

### Story 8.2.2 — Database Migration: event_targets Index

**Files to create**:
- New Alembic migration file — `ix_event_targets_target` index

**Implementation notes**:
- Add composite index on `event_targets(target_type, target_id)` for efficient reverse lookups
- This index supports: "recent 3 events for PC X", "recent 3 events for Group Y", "groups sorted by activity"
- Without this index, every per-entity event query does a full scan of `event_targets`
- Migration is fully reversible (`op.create_index` / `op.drop_index`)

**Acceptance criteria**:
1. `uv run alembic upgrade head` succeeds without errors
2. `uv run alembic downgrade -1` succeeds (reversible)
3. Index appears in SQLite schema: `ix_event_targets_target` on `event_targets(target_type, target_id)`
4. Query `SELECT * FROM event_targets WHERE target_type=? AND target_id=?` uses the new index

### Story 8.2.3 — Frontend: 3-Column PC Card Grid

**Files to modify**:
- `src/wizards_engine/static/js/views/gm-queue.js` — replace current PC summary rendering with compact card grid
- `src/wizards_engine/static/css/app.css` — add `.queue-pc-grid`, `.queue-pc-card`, `.queue-alert` styles

**Spec refs**: [web-ui.md](../domains/web-ui.md) (GM Dashboard)

**Implementation notes**:
- Use CSS Grid: `grid-template-columns: repeat(auto-fill, minmax(260px, 1fr))` for responsive 3→2→1 column layout
- Each card contains: name (linked to character detail), compact thin meter bars (using existing MeterBar component with correct maxes from API), low-charge badge list (red badges for traits/bonds at ≤2 charges), last 3 events as compact rows (timestamp + event type label)
- Render the already-computed `stress_proximity` data as a red warning highlight on PCs within 2 of effective stress max
- "No events found" message for PCs with no recent events
- Fetch data from `GET /api/v1/gm/queue-summary` (new endpoint from 8.2.1)
- Polling: 60s interval on queue-summary endpoint

**Acceptance criteria**:
1. PC cards display in 3-column grid on desktop (≥960px), 2-column on tablet, 1-column on mobile
2. Each card shows character name as clickable link
3. Meter bars show correct maximums (Stress/9, FT/20, Plot/5, Gnosis/23)
4. PC with trauma shows reduced stress max in meter bar
5. Low-charge indicators appear as red badges for traits/bonds with ≤2 charges
6. PCs within 2 of effective stress max have highlighted/red card border
7. Last 3 events shown per PC with relative timestamps
8. "No events found" shown for PCs with no events
9. Cards are compact — each takes roughly 1/3 screen width on desktop

### Story 8.2.4 — Frontend: Groups Section in Queue

**Files to modify**:
- `src/wizards_engine/static/js/views/gm-queue.js` — add Groups section below PC grid
- `src/wizards_engine/static/css/app.css` — add Groups section styles

**Spec refs**: [web-ui.md](../domains/web-ui.md) (GM Dashboard)

**Implementation notes**:
- Render below the PC card grid, separated by a section header "Groups"
- Use DataTable component (from 8.1.7) with columns: Group Name, Tier (badge), Active Clocks (compact progress indicators), Last Activity (relative timestamp)
- Data source: `group_cards` from `GET /api/v1/gm/queue-summary`
- Pre-sorted by backend (most recent event first); DataTable allows re-sorting by name or tier
- Clock progress shown inline using existing ClockProgress component
- Row click navigates to `#/gm/world/groups/{id}`
- "No recent activity" for groups with no events
- "No groups found" empty state if no groups exist

**Acceptance criteria**:
1. Groups section appears below PC cards with "Groups" heading
2. DataTable renders with Name, Tier, Active Clocks, Last Activity columns
3. Groups sorted by most-recent-event by default
4. Active clocks displayed with progress indicators inline
5. Row click navigates to group detail view
6. "No recent activity" shown for groups with no events
7. "No groups found" shown when no groups exist
8. Columns are sortable via DataTable functionality

---

## Notes

- 8.2.1 and 8.2.2 (backend + migration) can run in parallel
- 8.2.3 depends on both 8.2.1 (endpoint) and 8.2.2 (index for efficient queries)
- 8.2.4 depends on 8.2.1 (endpoint data) and 8.1.7 (DataTable component)
- The existing proposal queue rendering (pending proposals section) in `gm-queue.js` should remain — the PC grid and Groups section are additions, not replacements
