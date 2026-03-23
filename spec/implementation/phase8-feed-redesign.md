# Epic 8.3 — Event Feed Redesign

**Phase**: 8 — UI Cleanup & UX Modernization
**Depends on**: 8.1.5 (tab rename), 8.1.7 (DataTable component)
**Blocks**: None
**Parallel with**: 8.2, 8.4, 8.5 (after 8.1 completes)

---

## Overview

Transform the GM Event Feed from a low-density card stream into a rich, sortable, filterable data table optimized for batch review and world-state auditing. Enrich the backend events API with sort parameters, denormalized actor/target names, and change summaries. Keep the player feed card-based for narrative engagement, but add clickable actor/target links and source type badges.

---

## Stories

| Story | Status | Completed |
|-------|--------|-----------|
| 8.3.1 — Backend: Add Sort Params and Denormalized Names to Events API | 🟢 Complete | 2026-03-22 |
| 8.3.2 — Frontend: GM Event Feed as Rich Data Table | 🔴 Not started | — |
| 8.3.3 — Keep Player Feed Card-Based with Minor Enrichments | 🔴 Not started | — |

### Story 8.3.1 — Backend: Add Sort Params and Denormalized Names to Events API

**Files to modify**:
- `src/wizards_engine/api/routes/events.py` (or feed routes) — add `sort_by`, `sort_dir` query parameters
- `src/wizards_engine/schemas/event.py` — add `actor_name`, `primary_target_name`, `primary_target_type`, `changes_summary` fields to `EventResponse`
- `src/wizards_engine/api/pagination.py` — add optional `order_by` override to `paginate()` helper

**Spec refs**: [events.md](../domains/events.md) (Event Structure), [feed.md](../domains/feed.md) (Feed Queries)

**Implementation notes**:
- Add `sort_by: str = "created_at"` (allowed: created_at, type, actor_type) and `sort_dir: str = "desc"` (allowed: asc, desc) to `GET /api/v1/events`
- `paginate()` currently unconditionally applies `ORDER BY id DESC`. Add an `order_by` parameter that overrides the default when provided. When `sort_by = "created_at"` and `sort_dir = "desc"`, behavior is unchanged (ULID order = chronological)
- `actor_name`: resolve from User.display_name or Character.name via DB join. Nullable (system events have no actor)
- `primary_target_name` and `primary_target_type`: from the first (primary) entry in `event_targets`. Nullable
- `changes_summary`: derive from the `changes` JSON dict. Format each entry as `"{field}: {before} → {after}"`, join with ", ". E.g., "Stress: 3 → 5, Plot: 5 → 3". Nullable (events without changes return null)
- These fields are computed at serialization time — no schema changes to the Event model itself

**Acceptance criteria**:
1. `GET /api/v1/events?sort_by=type&sort_dir=asc` returns events sorted by type alphabetically ascending
2. `GET /api/v1/events?sort_by=created_at&sort_dir=desc` returns events newest-first (default behavior)
3. Pagination cursor still works correctly with non-default sort order
4. `actor_name` populated for player/GM events, null for system events
5. `primary_target_name` populated when event has targets, null otherwise
6. `changes_summary` populated for events with changes dict, null for events without
7. Existing `GET /api/v1/events` behavior unchanged when no sort params provided
8. Backend tests cover sort params, denormalized name resolution, and changes_summary generation

### Story 8.3.2 — Frontend: GM Event Feed as Rich Data Table

**Files to modify**:
- `src/wizards_engine/static/js/views/gm-feed.js` — replace FeedList with DataTable
- `src/wizards_engine/static/css/app.css` — add feed-specific table styles

**Spec refs**: [web-ui.md](../domains/web-ui.md) (Feed Views), [feed.md](../domains/feed.md) (Feed System)

**Implementation notes**:
- Replace the card-based FeedList component with DataTable for the GM feed (`#/gm/feed`)
- Columns: Timestamp (sortable, relative time render), Source Type (badge: Event/Story Entry/Proposal), Actor (sortable, linked to character detail), Event Type (sortable, select filter), Primary Target (linked to game object detail), Changes Summary, Narrative (truncated, full on row expand)
- Category filter tabs above the table: All | Events | Story Entries | Proposals
- Additional filter controls: actor type dropdown (Player/GM/System), session dropdown, target text search
- Row click navigates to the primary target's detail view. Individual cells with links (actor, target) navigate to those specific entities
- Silent feed tab (`#/gm/feed/silent`) also uses DataTable with same column structure
- Pagination: cursor-based "Load more" button (DataTable appends rows)

**Acceptance criteria**:
1. GM feed renders as a sortable data table with column headers
2. Clicking column headers sorts the table (toggles asc/desc)
3. Category filter tabs (All/Events/Story Entries/Proposals) filter rows correctly
4. Actor type and session dropdown filters work
5. Global text search filters across all columns
6. Timestamp column shows relative time (just now, 2m ago, 1h ago, etc.)
7. Source type badges visually distinguish events, story entries, and proposals
8. Actor names and target names are clickable links to their detail views
9. "Load more" button fetches next page of results
10. Silent feed tab uses same DataTable with same functionality
11. Empty state shown when no items match filters

### Story 8.3.3 — Keep Player Feed Card-Based with Minor Enrichments

**Files to modify**:
- `src/wizards_engine/static/js/views/feed.js` — add clickable links to actor/target names
- `src/wizards_engine/static/js/components/feed-item.js` — render actor as link when actor_id available, render targets as links

**Spec refs**: [web-ui.md](../domains/web-ui.md) (Feed Views)

**Implementation notes**:
- Player feed (`#/`) keeps its existing card-based layout — narrative-focused for player engagement
- Enrich feed items: actor name becomes a clickable link to `#/world/characters/{actor_id}` when actor_id is available (not for "System" or "You")
- Target names become clickable links to `#/world/{target_type}/{target_id}`
- Add a small source type badge (Event/Story/Proposal) to each feed item card
- Uses the existing `actor_name` and `primary_target_name` fields added in 8.3.1

**Acceptance criteria**:
1. Player feed layout unchanged (card-based, not table)
2. Actor names with actor_id render as clickable links to character detail
3. Target names render as clickable links to game object detail
4. Source type badge (small, unobtrusive) visible on each feed item
5. "You" and "System" actor labels are not clickable (no actor_id to link to)
6. Starred feed tab (`#/feed/starred`) also shows enriched feed items

---

## Notes

- 8.3.1 (backend) can start as soon as Phase 8 begins — no dependency on 8.1.7
- 8.3.2 (GM table feed) depends on both 8.3.1 (enriched API data) and 8.1.7 (DataTable component)
- 8.3.3 (player feed enrichments) depends on 8.3.1 (actor/target name fields)
- Key design decision: GM feed is table-based for data-dense scanning; player feed stays card-based for narrative immersion. These are different user needs, not a consistency issue.
