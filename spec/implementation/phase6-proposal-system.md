# Epic 6.3 — Proposal System

**Phase**: 6 — Web UI
**Depends on**: Epic 6.1 (SPA Foundation), Story 5.5.3 (nullable narrative)
**Blocks**: Epic 6.6 (Polish)
**Parallel with**: Epics 6.2, 6.4

---

## Overview

Build the complete proposal submission and review UI: the 3-step submission flow for all action types, GM review queue with inline expand and one-tap approve, player proposal list with revise capability, and notification badges. Ships `use_skill` end-to-end first (6.3.1), then GM queue immediately after (6.3.2), so the submit→review loop is functional at the earliest point.

---

## Stories

| Story | Status | Completed |
|-------|--------|-----------|
| 6.3.1 — Proposal Submission — Complete 3-Step Flow for `use_skill` | 🟢 Complete | 2026-03-19 |
| 6.3.2 — GM Review Queue | 🟢 Complete | 2026-03-19 |
| 6.3.3 — Proposal Submission — Non-Magic Types | 🟢 Complete | 2026-03-18 |
| 6.3.4 — Proposal Submission — Magic Types | 🟢 Complete | 2026-03-19 |
| 6.3.5 — My Proposals List + Detail + Revise + Notification Badges | 🟢 Complete | 2026-03-19 |

### Story 6.3.1 — Proposal Submission — Complete 3-Step Flow for `use_skill`

**Files to create**:
- `src/wizards_engine/static/js/views/proposal-submit.js` — 3-step proposal submission flow
- `src/wizards_engine/static/js/components/step-indicator.js` — step progress indicator

**Spec refs**: [web-ui.md](../domains/web-ui.md) (3-Step Proposal Submission, use_skill flow), [actions.md](../domains/actions.md) (use_skill)

**Implementation notes**:
- Step 1: Select action type (initially only `use_skill` available, others added in 6.3.3/6.3.4)
- Step 2: Action-specific form — for `use_skill`: skill picker, optional trait/bond modifiers, optional narrative, Plot spend
- Step 3: Review & confirm — calculated effect preview, submit button
- `POST /api/v1/proposals` on confirm
- Narrative is optional for session actions (Story 5.5.3 dependency)

**Acceptance criteria**:
1. Navigate to `#/proposals/new` → Step 1: action type selector
2. Select `use_skill` → Step 2: skill picker dropdown with all 8 skills
3. Optional modifier selection: core trait, role trait, bond (max 1 each, +1d each)
4. Optional narrative text area
5. Optional Plot spend (number input, max = current Plot)
6. Step 3: review shows selected skill, modifiers, narrative, Plot — "Submit" button
7. Submit calls `POST /api/v1/proposals` → success toast → redirect to `#/proposals`
8. Back button navigates to previous step (does not lose form state)
9. Validation errors shown inline (e.g., no skill selected)
10. Submitting from character sheet in ≤ 5 taps + 0 narrative → under 15 seconds

### Story 6.3.2 — GM Review Queue

**Files to create**:
- `src/wizards_engine/static/js/views/gm-queue.js` — GM proposal review queue
- `src/wizards_engine/static/js/components/proposal-card.js` — expandable proposal card

**Spec refs**: [web-ui.md](../domains/web-ui.md) (GM Review Queue), [actions.md](../domains/actions.md) (GM approval)

**Implementation notes**:
- Fetches `GET /api/v1/proposals?status=pending` on mount
- Registers 30s polling on same endpoint
- System proposals (`origin: "system"`) displayed first, then player proposals oldest-first
- Each proposal card: inline expand → shows full details, calculated effect, narrative
- One-tap approve: sends `POST /api/v1/proposals/{id}/approve` with no overrides
- Advanced: expand approval form with GM narrative, override fields, force flag
- Reject: reject button with optional GM note
- System proposals (`resolve_clock`, `resolve_trauma`): advanced approval fields specific to type

**Acceptance criteria**:
1. `#/gm/queue` shows pending proposals list
2. System proposals appear first, then player proposals in ULID order
3. Tap proposal → inline expand shows full details (action type, character, skill, modifiers, narrative, calculated effect)
4. "Approve" button → `POST /proposals/{id}/approve` → proposal removed from queue → success toast
5. "Advanced" toggle → shows GM narrative field, override fields (stat, style bonus), force checkbox
6. "Reject" button → optional note field → `POST /proposals/{id}/reject` → proposal removed from queue
7. `resolve_clock` proposals show clock details + narrative field + optional rider event
8. `resolve_trauma` proposals show character stress state + bond selection + trauma details
9. GM one-tap approval: expand → tap Approve → done → under 5 seconds
10. Queue polls every 30s (using polling infrastructure from 6.1.5)
11. Empty queue shows "No pending proposals" message

### Story 6.3.3 — Proposal Submission — Non-Magic Types

**Files to modify**:
- `src/wizards_engine/static/js/views/proposal-submit.js` — add form variants for non-magic types

**Spec refs**: [web-ui.md](../domains/web-ui.md) (Proposal Forms), [actions.md](../domains/actions.md) (downtime actions)

**Acceptance criteria**:
1. Action type selector includes: `regain_gnosis`, `rest`, `work_on_project`, `new_trait`, `new_bond`
2. **regain_gnosis**: modifier selection (trait/bond), narrative (required — downtime type)
3. **rest**: modifier selection (trait/bond), narrative (required)
4. **work_on_project**: story/arc selector (from `GET /stories`), narrative (required — becomes story entry text)
5. **new_trait**: slot type picker (core/role), template picker (from `GET /trait-templates`) OR "propose new" with name/description, optional retire_trait_id picker, narrative (required)
6. **new_bond**: target picker (character/group/location search), optional retire_bond_id picker, narrative (required)
7. All downtime types validate narrative is non-empty before allowing submit
8. Each type shows its calculated effect on the review step (Step 3)

### Story 6.3.4 — Proposal Submission — Magic Types

**Files to modify**:
- `src/wizards_engine/static/js/views/proposal-submit.js` — add magic type forms

**Files to create**:
- `src/wizards_engine/static/js/components/sacrifice-builder.js` — sacrifice list builder

**Spec refs**: [web-ui.md](../domains/web-ui.md) (Magic Proposal Forms), [actions.md](../domains/actions.md) (use_magic, charge_magic), [magic-system.md](../domains/magic-system.md) (Sacrifice system)

**Acceptance criteria**:
1. Action type selector includes: `use_magic`, `charge_magic`
2. **use_magic Step 2**: magic stat selector, sacrifice list builder, intention narrative (optional — session type)
3. **Sacrifice builder**: add/remove sacrifice entries. Types: Gnosis (amount), Stress (amount), Free Time (amount), Bond (select bond — value 10), Trait (select trait — value 10), Other (description + amount)
4. Running Gnosis-equivalent counter updates as sacrifices are added/removed
5. **charge_magic Step 2**: effect selector (from active effects list), sacrifice list builder, narrative (optional)
6. Review step shows magic stat, total sacrifice value, sacrifice breakdown, narrative
7. Submit calls `POST /api/v1/proposals` with sacrifice list in selections

**Implementation note**: `sacrifice-builder.js` exists as a standalone component (`window.components.sacrificeBuilder`) with `makeData()` and `buildHtml()` methods. However, `proposal-submit.js` inlines the sacrifice builder logic directly into its own Alpine data object rather than composing the component. The `sacrifice-builder.js` component is present for potential reuse but is not called by `proposal-submit.js`. The logic (sacrifice list, `addSacrifice()`, `removeSacrifice()`, `totalGnosisEquiv()`, `_toApiSacrificeList()`) is duplicated inline in `proposal-submit.js`. Both implementations are functionally equivalent.

**Implementation note**: The narrative field label in the `use_magic` Step 2 form reads "Narrative (optional)" consistent with session action rules. The review step labels the narrative field "Intention" for `use_magic` and `charge_magic` — a minor UX clarification not specified in the acceptance criteria.

### Story 6.3.5 — My Proposals List + Detail + Revise + Notification Badges

**Files to create**:
- `src/wizards_engine/static/js/views/proposals-list.js` — player proposals list
- `src/wizards_engine/static/js/views/proposal-detail.js` — proposal detail + revise

**Files to modify**:
- `src/wizards_engine/static/js/components/nav.js` — add notification badges

**Spec refs**: [web-ui.md](../domains/web-ui.md) (My Proposals, Notification Badges)

**Acceptance criteria**:
1. `#/proposals` shows player's proposals grouped by status (pending, approved, rejected)
2. Tap proposal → detail view with full proposal data, calculated effect, GM narrative (if any)
3. Rejected proposals show GM rejection note
4. Rejected proposals have "Revise" button → opens edit form → `PATCH /proposals/{id}` → status reverts to pending
5. Pending proposals have "Edit" button → opens edit form → `PATCH /proposals/{id}`
6. **Player notification badge**: Proposals tab shows count of newly-approved or newly-rejected proposals (since last viewed)
7. **GM notification badge**: Queue tab shows count of pending proposals
8. Badges update on each poll cycle
9. Viewing the proposals list clears the player badge count

**Implementation note**: Notification badges update only while the associated view is mounted. The `proposals-list.js` view updates the `window.navBadges.proposals` counter via its `_pollCallback`, and `gm-queue.js` updates `window.navBadges.queue` via its own poll callback. Once a view is torn down (`_teardown()`), its poll is unregistered and badge updates stop until the view is remounted. Badges are not updated globally in the background — they reflect the last-known count from when the view was last active.

**Implementation note**: Story owners and entry authors in `story-detail.js` display truncated ULIDs (first 8 characters) rather than resolved names. The API returns `{type, id}` for owners and `author_id` for entries; there is no name field available without a separate users lookup. Resolving display names is deferred.

---

## Notes

- The submit→review loop is functional after stories 6.3.1 + 6.3.2 (2 stories). This is intentional — maximizes testable surface area early
- Notification badges are the primary feedback channel during table play — they must work before polish
- System proposal forms (`resolve_clock`, `resolve_trauma`) are GM-only review items in 6.3.2, not player submission flows
