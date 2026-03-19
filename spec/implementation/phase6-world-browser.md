# Epic 6.4 — World Browser & Feed

**Phase**: 6 — Web UI
**Depends on**: Epic 6.1 (SPA Foundation)
**Blocks**: Epic 6.6 (Polish)
**Parallel with**: Epics 6.2, 6.3

---

## Overview

Build the world browser: navigation and game object card listings for characters, groups, and locations; detail views for each type; story views with entry submission; and feed views (personal, starred, per-object) with ULID cursor pagination. Primarily read-only views except story entry submission. Reuses shared components from Epic 6.2.1.

---

## Stories

| Story | Status | Completed |
|-------|--------|-----------|
| 6.4.1 — World Browser Navigation + Game Object Cards | 🔴 Not started | — |
| 6.4.2 — Character / Group / Location Detail Views | 🔴 Not started | — |
| 6.4.3 — Story Views + Entry Submission | 🔴 Not started | — |
| 6.4.4 — Feed Views (Personal, Starred, Per-Object) | 🔴 Not started | — |

### Story 6.4.1 — World Browser Navigation + Game Object Cards

**Files to create**:
- `src/wizards_engine/static/js/views/world.js` — world browser landing page
- `src/wizards_engine/static/js/views/world-list.js` — filtered object list view

**Spec refs**: [web-ui.md](../domains/web-ui.md) (World Browser, Game Object Cards)

**Acceptance criteria**:
1. `#/world` shows category tabs: Characters, Groups, Locations, Stories
2. Each category tab fetches `GET /api/v1/{type}` and displays GameObjectCard list
3. Character list: shows name, detail_level badge (PC/NPC), basic info
4. Group list: shows name, tier, member count
5. Location list: shows name, parent location (if any)
6. Cards are tappable → navigate to detail view (`#/world/{type}/{id}`)
7. Search/filter: text search by name within loaded results
8. Renders correctly at 390px mobile viewport

### Story 6.4.2 — Character / Group / Location Detail Views

**Files to create**:
- `src/wizards_engine/static/js/views/world-detail.js` — game object detail view (discriminated by type)

**Spec refs**: [web-ui.md](../domains/web-ui.md) (Detail Views), [game-objects.md](../domains/game-objects.md)

**Acceptance criteria**:
1. `#/world/characters/{id}` shows character detail: name, description, attributes (NPC), or full sheet (PC — reuses character sheet component from 6.2.2)
2. `#/world/groups/{id}` shows group detail: name, tier, description, traits (GameObjectCard list), bonds/relations, members (derived), holdings, associated clocks
3. `#/world/locations/{id}` shows location detail: name, description, parent, children (sub-locations), feature traits, bonds, associated clocks
4. Bonds displayed as GameObjectCard links to the bond target
5. Clocks displayed using ClockProgress component
6. Back button returns to world browser list

### Story 6.4.3 — Story Views + Entry Submission

**Files to create**:
- `src/wizards_engine/static/js/views/stories.js` — story list
- `src/wizards_engine/static/js/views/story-detail.js` — story detail + entry submission

**Spec refs**: [web-ui.md](../domains/web-ui.md) (Story Views), [game-objects.md](../domains/game-objects.md) (Stories, Story Entries)

**Acceptance criteria**:
1. Stories tab in world browser lists stories with name, status, owner badges
2. `#/world/stories/{id}` shows story detail: name, status, description, owners, tags
3. Story entries displayed chronologically (oldest first) with author and timestamp
4. "Add Entry" form: text area + submit button. Calls `POST /api/v1/stories/{id}/entries`
5. Entry submission only visible to users who can see the story (see = write rule)
6. Player-authored entries show "Edit" button for the author
7. GM sees "Edit" button on all entries
8. Edit form: inline text area replacement, save/cancel buttons, calls `PATCH /api/v1/stories/{id}/entries/{entry_id}`

### Story 6.4.4 — Feed Views (Personal, Starred, Per-Object)

**Files to create**:
- `src/wizards_engine/static/js/views/feed.js` — personal feed view
- `src/wizards_engine/static/js/components/feed-list.js` — reusable feed list with pagination

**Spec refs**: [web-ui.md](../domains/web-ui.md) (Feed Views), [feed.md](../domains/feed.md)

**Acceptance criteria**:
1. `#/feed` shows personal feed (`GET /api/v1/me/feed`) using FeedItem components
2. "Starred" filter tab shows starred feed (`GET /api/v1/me/feed/starred`)
3. Per-object feed accessible from detail views (e.g., `#/world/characters/{id}` Feed tab) via `GET /api/v1/{type}/{id}/feed`
4. ULID cursor pagination: "Load more" button at bottom, passes `before` cursor parameter
5. Feed items show: timestamp, event type badge, narrative, changes summary, target links
6. Visibility-filtered server-side — no client-side filtering needed
7. Empty feed shows "No events yet" message

---

## Notes

- Reuses shared components from 6.2.1 (GameObjectCard, FeedItem, ClockProgress, MeterBar)
- All views are read-only except story entry submission and editing
- Feed pagination uses ULID cursor (pass last item's ID as `before` parameter)
- World browser is available to both players and GM
