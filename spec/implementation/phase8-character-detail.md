# Epic 8.5 — Character Detail View Overhaul

**Phase**: 8 — UI Cleanup & UX Modernization
**Depends on**: 8.1.3 (bond fix), 8.1.6 (description fix), 8.1.8 (ExpandableItem component)
**Blocks**: None
**Parallel with**: 8.2, 8.3, 8.4 (after 8.1 completes)

---

## Overview

Overhaul the character detail views (both player's own character sheet and world-detail character pages) to show full descriptions, inline skills, separated Core/Role trait sections, expandable trait/bond cards with edit navigation and bond partner links, and a permanent events feed at the bottom. Fix the non-functional "Full Sheet" button and remove bond dyad duplication (via backend fix in 8.1.3).

---

## Stories

| Story | Status | Completed |
|-------|--------|-----------|
| 8.5.1 — Restructure Character Detail Layout | 🔴 Not started | — |
| 8.5.2 — Expandable Trait and Bond Cards | 🔴 Not started | — |
| 8.5.3 — Character Events Feed at Bottom | 🔴 Not started | — |
| 8.5.4 — Trait and Bond Inline Edit Forms | 🔴 Not started | — |

### Story 8.5.1 — Restructure Character Detail Layout

**Files to modify**:
- `src/wizards_engine/static/js/views/character.js` — restructure header, move skills inline, split trait sections
- `src/wizards_engine/static/js/views/world-detail.js` — same restructuring for world-browser character views
- `src/wizards_engine/static/css/app.css` — add compact skills table styles

**Spec refs**: [character-core.md](../domains/character-core.md) (Character Sheet), [web-ui.md](../domains/web-ui.md) (Character Sheet Layout)

**Implementation notes**:
- **Description**: full text shown (truncation removal done in 8.1.6, wire it through here)
- **Skills**: move from Tier 2 tabbed section to inline compact table immediately after description. Layout as 2×4 grid (4 rows, 2 columns) showing all 8 skills: Awareness, Composure, Influence, Finesse, Speed, Power, Knowledge, Technology. Each cell: skill name (muted label) + skill value (bold number)
- **Traits**: split current "Traits" tab into two sections: "Core Traits (2)" header and "Role Traits (3)" header. The data already has `slot_type` values (`core_trait`, `role_trait`) to distinguish them
- **Tab bar**: reduce from 5 tabs (Traits | Bonds | Effects | Skills | Feed) to 3 tabs (Traits | Bonds | Effects). Skills are now inline above tabs, Feed moves to bottom (Story 8.5.3)
- **Full Sheet button**: in `world-detail.js`, the button links to `#/world` for non-own characters (useless). Fix: for own character, link to `#/character`; for other characters, remove the button entirely (they're already on the detail page)

**Acceptance criteria**:
1. Character description shown in full (not truncated)
2. Skills table appears immediately after description, before the tabbed sections
3. Skills render in a compact 2×4 grid with name and value
4. Traits tab shows "Core Traits" section header above core traits and "Role Traits" section header above role traits
5. Tab bar shows 3 tabs: Traits, Bonds, Effects (Skills and Feed removed from tabs)
6. Full Sheet button removed for non-own characters; links to `#/character` for own character
7. Same layout changes applied to both `character.js` (own character) and `world-detail.js` (world browser)

### Story 8.5.2 — Expandable Trait and Bond Cards

**Files to modify**:
- `src/wizards_engine/static/js/views/character.js` — replace inline trait/bond rendering with ExpandableItem
- `src/wizards_engine/static/js/views/world-detail.js` — same replacement for world-browser character views

**Spec refs**: [traits.md](../domains/traits.md) (Trait Display), [bonds.md](../domains/bonds.md) (Bond Display)

**Implementation notes**:
- Replace `_buildTraitItem()` with `expandableItem.render()` calls
- Trait collapsed state: name + ChargeDots (current/max charges)
- Trait expanded state: full description + recharge cost info + action buttons: "Recharge" (if applicable, triggers recharge_trait action), "Edit" (link to `#/gm/traits/{slot_id}/edit`, GM-only)
- Replace `_buildBondItem()` with `expandableItem.render()` calls
- Bond collapsed state: name (partner entity name) + ChargeDots (current/max charges with degradation indicator)
- Bond expanded state: full description + partner entity link ("Go to [partner name] →" linking to `#/world/{type}/{id}`) + action buttons: "Maintain" (if applicable, triggers maintain_bond action), "Edit" (link to `#/gm/bonds/{slot_id}/edit`, GM-only)
- Bond list is now filtered to owned-only (backend fix from 8.1.3) — no duplicate dyads
- Trauma bonds should render with a trauma badge/indicator next to the name
- Degraded bonds (effectiveMax < max) should show the degradation indicator

**Acceptance criteria**:
1. Each trait renders as an expandable card: collapsed shows name + charge dots
2. Clicking a trait expands to show full description and action buttons
3. Clicking again collapses back to compact view
4. "Recharge" button appears on traits eligible for recharge and triggers the action
5. "Edit" button appears for GM users, linking to trait edit form
6. Each bond renders as an expandable card: collapsed shows partner name + charge dots
7. Expanding a bond shows full description, partner link, and action buttons
8. "Go to [partner] →" link navigates to the bond partner's detail page
9. "Maintain" button appears on bonds eligible for maintenance
10. Bond list shows only owned bonds (no dyad duplication)
11. Trauma bonds display a trauma badge
12. Degraded bonds show degradation indicator (reduced effective max)

### Story 8.5.3 — Character Events Feed at Bottom

**Files to modify**:
- `src/wizards_engine/static/js/views/character.js` — add permanent feed section below tabbed content
- `src/wizards_engine/static/js/views/world-detail.js` — add feed section to character detail views

**Spec refs**: [feed.md](../domains/feed.md) (Per-Entity Feeds), [web-ui.md](../domains/web-ui.md) (Character Sheet Layout)

**Implementation notes**:
- Move the Feed from a tab in the tab bar to a permanent section at the bottom of the character detail page
- Uses existing `GET /api/v1/characters/{id}/feed` endpoint — already returns visibility-filtered merged events + story entries
- Section header: "Recent Events" with a "Load more" button for pagination
- Show the most recent 10 events by default, with cursor-based pagination to load more
- Use the existing FeedList component (reuse, not DataTable — this is a per-character narrative stream similar to the player feed)
- For `character.js` (own character): feed shows events based on character's bond network (visibility-filtered)
- For `world-detail.js` (any character): same endpoint, visibility-filtered per the viewing user's access
- "No events found" message when the character has no visible events

**Acceptance criteria**:
1. Events feed section appears at the bottom of the character detail page (below tabs)
2. Feed shows recent events scoped to the character
3. "Load more" button fetches additional events via cursor pagination
4. Events are visibility-filtered per the viewing user's access level
5. "No events found" message when no events exist for this character
6. Feed renders in both `character.js` (own character) and `world-detail.js` (world browser)
7. Tab bar no longer includes "Feed" tab (moved to bottom section)

### Story 8.5.4 — Trait and Bond Inline Edit Forms

**Files to create**:
- `src/wizards_engine/static/js/views/trait-edit.js` — trait edit form view
- `src/wizards_engine/static/js/views/bond-edit.js` — bond edit form view

**Files to modify**:
- `src/wizards_engine/static/js/router.js` — add routes for `#/gm/traits/{id}/edit` and `#/gm/bonds/{id}/edit`
- `src/wizards_engine/static/index.html` — add script tags for new views

**Spec refs**: [traits.md](../domains/traits.md) (Trait Management), [bonds.md](../domains/bonds.md) (Bond Management)

**Implementation notes**:
- These forms are for GM editing of individual traits and bonds — not player-facing
- Trait edit form fields: Name (text), Description (textarea), Charges (number input, 0-5). Submit uses `POST /api/v1/gm/actions` with `action_type: "modify_trait"` and the slot_id
- Bond edit form fields: Description (textarea), Charges (number input, 0-5). Submit uses `POST /api/v1/gm/actions` with `action_type: "modify_bond"` and the slot_id
- Both forms load current values via `GET /api/v1/characters/{character_id}` (to find the slot data) — the slot_id needs to be mapped back to its owner character
- On save: show success toast and navigate back to the character's detail page
- On cancel: navigate back without saving
- GM-only: redirect non-GM users to home
- Follow existing form patterns (validation, loading/error states, submit button disabled during request)

**Acceptance criteria**:
1. `#/gm/traits/{id}/edit` route loads the trait edit form with current values pre-populated
2. `#/gm/bonds/{id}/edit` route loads the bond edit form with current values pre-populated
3. Saving trait edit form triggers `modify_trait` GM action with updated values
4. Saving bond edit form triggers `modify_bond` GM action with updated values
5. Success toast shown after save; navigates back to character detail
6. Cancel button navigates back without saving
7. Form shows validation errors for invalid input (e.g., charges > 5)
8. Non-GM users redirected to home page
9. Loading state shown while fetching current values

---

## Notes

- 8.5.1 and 8.5.2 can run in parallel (8.5.1 restructures layout, 8.5.2 replaces individual components within it)
- 8.5.3 depends on 8.5.1 (the feed section needs the layout restructured to know where to place it)
- 8.5.4 depends on 8.5.2 (the edit buttons in expandable cards need to link somewhere)
- The bond perspective fix (8.1.3) must be complete before 8.5.2 to avoid showing duplicate dyads
- Both `character.js` and `world-detail.js` need parallel changes — consider extracting shared rendering functions
