# Epic 6.6 — Polish & Integration

**Phase**: 6 — Web UI
**Depends on**: Epics 6.2–6.5
**Blocks**: None (terminal)
**Parallel with**: None (final epic)

---

## Overview

Final polish: profile and starring management, GM silent feed, mobile optimizations with touch target validation, and table-flow acceptance testing with concrete timed criteria. Polling and notification badges have already been implemented in earlier epics (6.1.5 and 6.3.5).

---

## Stories

| Story | Status | Completed |
|-------|--------|-----------|
| 6.6.1 — Profile, Starring, GM Silent Feed | 🔴 Not started | — |
| 6.6.2 — Mobile Optimizations + Touch Targets | 🔴 Not started | — |
| 6.6.3 — Table-Flow Acceptance Testing | 🔴 Not started | — |

### Story 6.6.1 — Profile, Starring, GM Silent Feed

**Files to create**:
- `src/wizards_engine/static/js/views/profile.js` — profile view

**Files to modify**:
- `src/wizards_engine/static/js/views/feed.js` — add starred filter, GM silent feed
- `src/wizards_engine/static/js/components/game-object-card.js` — add star/unstar button

**Spec refs**: [web-ui.md](../domains/web-ui.md) (Profile, Starring, Silent Feed), [auth.md](../domains/auth.md) (Player profile), [feed.md](../domains/feed.md) (Starring, Silent feed)

**Acceptance criteria**:
1. `#/profile` shows user profile: display name (editable via `PATCH /me`), role, character link
2. Player self-refresh login link button
3. **Starring**: star/unstar toggle on GameObjectCards throughout the app
4. Star calls `POST /api/v1/me/starred` with `{target_type, target_id}`, unstar calls `DELETE /api/v1/me/starred/{type}/{id}`
5. Star state persisted — starred objects visually marked across views
6. Starred feed filter on personal feed (`GET /me/feed/starred`)
7. **GM silent feed**: GM-only view (`#/gm/silent-feed`) showing `GET /api/v1/me/feed/silent` — system bookkeeping events (FT distribution, Plot distribution, etc.)
8. Silent feed uses FeedItem components with ULID cursor pagination

### Story 6.6.2 — Mobile Optimizations + Touch Targets

**Files to modify**:
- `src/wizards_engine/static/css/app.css` — mobile-specific styles

**Spec refs**: [web-ui.md](../domains/web-ui.md) (Mobile Design, Touch Targets)

**Acceptance criteria**:
1. All interactive elements (buttons, links, tabs) have touch targets >= 44px on mobile (390px viewport)
2. Bottom tab bar does not overlap content on any view
3. Modal dialogs (narrative input, confirmation) are full-width on mobile with adequate padding
4. Character sheet meters are readable and tappable on mobile
5. Proposal submission flow works without horizontal scrolling on mobile
6. GM queue cards are fully readable without horizontal scrolling
7. Forms have appropriate mobile keyboard types (`inputmode="numeric"` for number fields)
8. No content is clipped or hidden behind fixed elements (bottom tabs, headers)

### Story 6.6.3 — Table-Flow Acceptance Testing

**Spec refs**: [web-ui.md](../domains/web-ui.md) (Table-Flow Design Principles)

**Implementation notes**:
- This is a manual testing story with concrete timed criteria
- No new code expected — only bug fixes discovered during testing

**Acceptance criteria**:
1. **use_skill proposal**: from character sheet → 5 taps + 0 narrative → submitted → under 15 seconds
2. **Recharge Trait**: tap button → narrative modal → enter text → submit → under 15 seconds
3. **Find Time**: 1 tap → immediate → under 3 seconds
4. **GM one-tap approval**: expand proposal → tap Approve → done → under 5 seconds
5. **Mobile viewport (390px)**: bottom tabs visible on every view, tap targets >= 44px
6. **Security checklist**: verify no `x-html` directives used with user-supplied content (XSS prevention)
7. **Polling verification**: tab hidden for 2 minutes → tab visible → data refreshes within one poll interval
8. **Error resilience**: API error during action → error displayed → app still functional → can retry
9. All acceptance criteria from Epics 6.1–6.5 still pass (no regressions from polish changes)

---

## Notes

- Polling and notification badges are NOT in this epic — they were moved to 6.1.5 and 6.3.5 respectively
- This is the terminal epic — no other work depends on it
- 6.6.3 is a manual testing story that may produce bug fix commits but no planned new features
