# Epic 6.2 — Player Character & Direct Actions

**Phase**: 6 — Web UI
**Depends on**: Epic 6.1 (SPA Foundation), Stories 5.5.1 + 5.5.2 (direct action endpoints)
**Blocks**: Epic 6.6 (Polish)
**Parallel with**: Epics 6.3, 6.4

---

## Overview

Build the player character sheet view with shared UI components, full character data display (meters, traits, bonds, effects, skills, feed), direct player actions (find time, recharge trait, maintain bond, use/retire effect), and character editing. This epic establishes reusable UI components used across 4+ subsequent epics.

---

## Stories

| Story | Status | Completed |
|-------|--------|-----------|
| 6.2.1 — Shared UI Components | 🟢 Complete | 2026-03-19 |
| 6.2.2 — Character Sheet — Meters + Tier 2 Tabs | 🟢 Complete | 2026-03-19 |
| 6.2.3 — Direct Player Actions | 🟢 Complete | 2026-03-19 |
| 6.2.4 — Character Edit | 🟢 Complete | 2026-03-19 |

### Story 6.2.1 — Shared UI Components

**Files to create**:
- `src/wizards_engine/static/js/components/meter-bar.js` — MeterBar component
- `src/wizards_engine/static/js/components/charge-dots.js` — ChargeDots component
- `src/wizards_engine/static/js/components/clock-progress.js` — ClockProgress component
- `src/wizards_engine/static/js/components/game-object-card.js` — GameObjectCard component
- `src/wizards_engine/static/js/components/feed-item.js` — FeedItem component

**Spec refs**: [web-ui.md](../domains/web-ui.md) (Component Definitions, Information Hierarchy)

**Acceptance criteria**:
1. **MeterBar**: horizontal bar with label, current/max values, color coding, effective_max marker for degraded bonds
2. **ChargeDots**: row of filled/empty dots (5 max for traits, variable for bonds). Bond variant shows effective_max marker. Trait variant uses trait color, bond variant uses bond color.
3. **ClockProgress**: compact mode (segments filled/total) and detail mode (visual segment display). Handles any positive segment count.
4. **GameObjectCard**: card with name, type badge, summary fields. Variants for character/group/location.
5. **FeedItem**: event display with timestamp, narrative, changes summary. Discriminated union for event vs story_entry.
6. All components accept data via Alpine.js `x-data` props
7. All components render correctly at 390px mobile viewport

### Story 6.2.2 — Character Sheet — Meters + Tier 2 Tabs

**Files to create**:
- `src/wizards_engine/static/js/views/character.js` — character sheet view

**Spec refs**: [web-ui.md](../domains/web-ui.md) (Character Sheet, Progressive Disclosure, Tier 2 Tabs)

**Implementation notes**:
- Fetches `GET /api/v1/characters/{id}` on mount
- Registers 60s polling on same endpoint
- Tier 1 (always visible): meters (Stress, Free Time, Plot, Gnosis), name, basic info
- Tier 2 (tabbed): Traits, Bonds, Effects, Skills, Feed
- Buttons on cards (Recharge on traits, Maintain on bonds, Use/Retire on effects, Find Time on meter bar) — buttons rendered here but action flows wired in 6.2.3

**Acceptance criteria**:
1. Character sheet loads and displays all meters using MeterBar components
2. Stress bar shows effective max marker when Trauma bonds exist
3. Tier 2 tabs switch between Traits, Bonds, Effects, Skills, Feed
4. Traits tab shows active traits with ChargeDots, grouped by core/role
5. Bonds tab shows active bonds with ChargeDots, trauma bonds visually distinct
6. Effects tab shows active magic effects with charges (if charged) or power level (if permanent)
7. Skills tab shows all 8 skills with current level
8. Feed tab shows personal feed using FeedItem components with ULID cursor pagination
9. "Recharge" button visible on traits with charges < 5
10. "Maintain" button visible on non-trauma bonds with charges < effective max
11. "Use"/"Retire" buttons visible on active effects
12. "Find Time" button visible on meter bar when Plot >= 3
13. Character sheet polls every 60s (using polling infrastructure from 6.1.5)
14. Renders correctly at 390px mobile viewport

**Implementation note**: Feed pagination uses `after` cursor parameter (not `before`). The character feed endpoint is called as `GET /api/v1/characters/{id}/feed?limit=20&after={cursor}`. The `_feedNextCursor` is populated from `data.next_cursor` in the response. This is consistent with how all other feed views paginate (see feed-list.js).

**Implementation note**: Bond charges are displayed via the physical `stress` field from the API response (`b.stress` for current charges, `b.stress_degradations` for degradation count). The `effectiveMax` displayed to users is computed client-side as `5 - stress_degradations`. This matches the documented physical/conceptual naming gap in [bonds.md](../domains/bonds.md) and [CLAUDE.md](../../.claude/CLAUDE.md).

### Story 6.2.3 — Direct Player Actions

**Files to modify**:
- `src/wizards_engine/static/js/views/character.js` — wire action flows

**Files to create**:
- `src/wizards_engine/static/js/components/narrative-modal.js` — reusable narrative input modal

**Spec refs**: [web-ui.md](../domains/web-ui.md) (Direct Actions), [actions.md](../domains/actions.md) (Player Direct Actions)

**Acceptance criteria**:
1. **Find Time**: tap button → confirmation → `POST /characters/{id}/find-time` → meter updates immediately → under 3 seconds
2. **Recharge Trait**: tap "Recharge" → narrative modal opens → enter narrative → submit → `POST /characters/{id}/recharge-trait` → charges update to 5, FT decrements
3. **Maintain Bond**: tap "Maintain" → narrative modal opens → enter narrative → submit → `POST /characters/{id}/maintain-bond` → charges restore to effective max, FT decrements
4. **Use Effect**: tap "Use" → optional narrative → `POST /characters/{id}/use-effect` → charges decrement
5. **Retire Effect**: tap "Retire" → confirmation → `POST /characters/{id}/retire-effect` → effect removed from active list
6. Narrative modal: text area, submit button, cancel button. Submit disabled when empty (for recharge/maintain)
7. Error states: insufficient FT, trait already full, bond already maintained — shown as inline error message
8. All actions optimistically update the UI, roll back on error
9. All buttons disabled during in-flight requests (prevent double-tap)

**Implementation note**: Use Effect opens the narrative modal with `required: false` (optional narrative), consistent with the spec. The API endpoint for use effect is `POST /characters/{id}/effects/{effectId}/use` and for retire effect is `POST /characters/{id}/effects/{effectId}/retire` — both use sub-resource paths rather than the flat pattern shown in the acceptance criteria above.

**Implementation note**: Error states (criterion 7) are handled via the api.js error toast system, not inline error messages on the character sheet. The toast is dispatched by api.js on any non-2xx response; the character sheet rolls back optimistic state but does not display a per-action inline error. This is a minor deviation from the spec — acceptable for MVP given the toast provides the same information.

### Story 6.2.4 — Character Edit

**Files to create**:
- `src/wizards_engine/static/js/views/character-edit.js` — character edit form

**Spec refs**: [web-ui.md](../domains/web-ui.md) (Character Edit), [character-core.md](../domains/character-core.md) (player-editable fields)

**Acceptance criteria**:
1. Edit button on character sheet navigates to `#/character/edit`
2. Editable fields: name, description, notes
3. Form pre-populated with current values
4. Submit calls `PATCH /api/v1/characters/{id}` with changed fields only
5. Cancel returns to character sheet without saving
6. Success returns to character sheet with updated values
7. Validation: name required (non-empty string)
8. Only visible when `$store.isOwner(characterId)` or `$store.role === 'gm'`

---

## Notes

- Shared components from 6.2.1 are reused in Epics 6.4 (world browser) and 6.5 (GM tools)
- Character sheet is the most-visited view — optimize for fast initial load
- The character sheet component is also reused for GM-player dual identity (`#/gm/character`)
