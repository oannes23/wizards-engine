# Web UI — Domain Specification

**Status**: 🟢 Complete
**Last interrogated**: 2026-03-18
**Last verified**: —
**Depends on**: [auth](auth.md), [actions](actions.md), [feed](feed.md), [character-core](character-core.md), [game-objects](game-objects.md), [downtime](downtime.md), [events](events.md)
**Depended on by**: None (terminal consumer)

---

## Overview

The Web UI is a lightweight, mobile-first frontend served as static files by the FastAPI backend. It provides the primary interface for players and the GM during table play and between sessions. The design prioritizes fast interactions on phones during active play, with a richer desktop experience for between-session work.

The UI consumes the existing REST API exclusively — no server-side rendering, no WebSocket connections. State updates use polling at sensible intervals.

---

## A. Technology Stack

### Framework Choices

- **Decision**: Pico CSS v2 + Alpine.js v3. No build step, no bundler, no framework compilation.
- **Rationale**: The UI is a thin layer over a rich API. A 4–6 player game doesn't need React-scale infrastructure. Pico provides semantic HTML styling with dark mode out of the box (~10KB). Alpine provides reactive data binding via HTML attributes (~15KB). Total framework weight: ~25KB. The GM and players are on the same WiFi — latency is negligible.
- **Implications**: All JS is vanilla ES modules served as static files. No JSX, no TypeScript compilation, no node_modules. Development iteration is edit-refresh.

| Component | Choice | Size | Notes |
|-----------|--------|------|-------|
| CSS | Pico CSS v2 | ~10KB | Classless semantic styling, dark mode built-in |
| JS | Alpine.js v3 | ~15KB | Reactive HTML attributes, `x-data`, `x-show`, `x-for` |
| Routing | Vanilla hash router | ~50 lines | `#/path` → view loader, no library needed |
| API client | Vanilla `fetch()` wrapper | ~100 lines | Cookie credentials, JSON parsing, error handling, 401 redirect |
| Deployment | FastAPI `StaticFiles` mount | 0 | Same process, same origin, no CORS |

### Dark Mode Default

- **Decision**: Dark mode is the default. No theme toggle for MVP.
- **Rationale**: Game table environment. Phones at the table should minimize screen glare. Pico CSS supports `data-theme="dark"` natively.
- **Implications**: Set `<html data-theme="dark">` in the SPA shell. Custom CSS properties extend Pico's dark palette for game-specific elements (stress red, gnosis blue, etc.).

---

## B. Authentication & Onboarding Flows

### Magic Link Handler (`/login/:code`)

The SPA shell intercepts the `/login/:code` route before hash routing takes over:

1. Extract code from URL path
2. Call `POST /api/v1/auth/login` with `{code}`
3. If response `type: "user"` → cookie is set, redirect to role-appropriate home (`#/` for players, `#/gm` for GM)
4. If response `type: "invite"` → show the join form (character name + display name)
5. On join form submit → call `POST /api/v1/game/join` with `{code, character_name, display_name}` → cookie set, redirect to `#/`

### First-Run GM Setup (`/setup`)

If no GM account exists (detected by `GET /api/v1/me` returning 401 and `POST /api/v1/setup` not returning 409):

1. Show a setup form: display name field
2. Submit → `POST /api/v1/setup` with `{display_name}`
3. Cookie is set → redirect to `#/gm`

### Post-Login Routing

After authentication, `GET /api/v1/me` determines role:
- `role: "gm"` → redirect to `#/gm` (GM dashboard)
- `role: "player"` → redirect to `#/` (player dashboard/feed)

### Session Expiry

If any API call returns 401:
- Clear local state
- Redirect to a "session expired" screen with a message to use their magic link again

---

## C. Navigation Architecture

### Player Navigation

**Mobile (bottom tab bar)**:

| Tab | Icon | Route | Purpose |
|-----|------|-------|---------|
| Feed | 📋 | `#/` | Personal feed — recent activity |
| Character | 👤 | `#/character` | Own character sheet |
| Proposals | ✏️ | `#/proposals` | Submit new / view my proposals |
| World | 🌍 | `#/world` | Browse characters, groups, locations, stories |
| Session | 🎲 | `#/session` | Current session info, participants |

**Desktop (left sidebar)**: Same sections, with sub-navigation visible. Sidebar collapses to icons on narrow viewports.

### GM Navigation

**Mobile (bottom tab bar)**:

| Tab | Icon | Route | Purpose |
|-----|------|-------|---------|
| Queue | 📥 | `#/gm` | Pending proposal review queue |
| Feed | 📋 | `#/gm/feed` | Full activity feed |
| World | 🌍 | `#/gm/world` | World browser + builder tools |
| Session | 🎲 | `#/gm/session` | Session management |
| More | ☰ | `#/gm/more` | Player roster, invites, clock management, settings |

**Desktop (left sidebar)**: Expanded navigation with grouped sections:
- **GM Tools**: Queue, Direct Actions, Players, Invites
- **World**: Characters, Groups, Locations, Stories, Clocks, Trait Templates
- **Feeds**: Full Feed, Silent Feed, Session Timeline

### GM-Player Dual Identity

If the GM has a linked character (`character_id` on user record):
- "More" menu includes a "My Character" link → `#/gm/character`
- The GM character sheet is identical to a player's, with proposal submission and direct actions available
- GM proposals appear in the GM's own queue (self-approve flow)

---

## D. Complete Screen Inventory

### Unauthenticated Screens

| Route | Screen | Purpose |
|-------|--------|---------|
| `/login/:code` | Login Handler | Magic link processing, redirect |
| `/login/:code` (invite) | Join Form | Character name + display name, invite redemption |
| `/setup` | First-Run Setup | GM account creation |

### Player Screens

| Route | Screen | Key Data |
|-------|--------|----------|
| `#/` | Dashboard / Feed | Personal feed (events + story entries), visibility-filtered |
| `#/character` | Character Sheet | Full sheet with progressive disclosure (see §E) |
| `#/character/edit` | Edit Character | Name, description, notes (player-editable fields) |
| `#/proposals/new` | New Proposal (Step 1) | Action type selection, grouped by category |
| `#/proposals/new/:type` | New Proposal (Step 2) | Mechanical selections + narrative |
| `#/proposals/new/:type/preview` | New Proposal (Step 3) | Calculated effect preview, submit |
| `#/proposals` | My Proposals | List of own proposals, filterable by status |
| `#/proposals/:id` | Proposal Detail | Full proposal with status, narrative, calculated effect |
| `#/proposals/:id/edit` | Revise Proposal | Edit pending/rejected proposals |
| `#/world` | World Browser | Tabs: Characters, Groups, Locations, Stories |
| `#/world/characters/:id` | Character Detail | Public character sheet (read-only) |
| `#/world/groups/:id` | Group Detail | Traits, members, relations, holdings, clocks |
| `#/world/locations/:id` | Location Detail | Features, presence, child locations, bonds |
| `#/world/stories/:id` | Story Detail | Entries, owners, status; entry submission form |
| `#/session` | Session View | Current/recent session info, participants, timeline |
| `#/feed/starred` | Starred Feed | Feed filtered to starred game objects |
| `#/profile` | Profile | Display name edit, magic link refresh, starred objects |

### GM Screens

| Route | Screen | Key Data |
|-------|--------|----------|
| `#/gm` | GM Dashboard | Pending proposals (system first), PC resource summaries, near-completion clocks |
| `#/gm/queue` | Proposal Review Queue | All pending proposals, sorted oldest-first |
| `#/gm/queue/:id` | Proposal Review Detail | Full proposal, inline approve/reject forms |
| `#/gm/actions` | GM Direct Actions | Action type selector, target picker, changes form |
| `#/gm/sessions` | Session List | All sessions by status (active first, then draft, then ended) |
| `#/gm/sessions/new` | New Session | Draft session form (time_now, date, summary) |
| `#/gm/sessions/:id` | Session Panel | Participant management, start/end controls, timeline |
| `#/gm/sessions/:id/edit` | Edit Session | Summary, notes (draft/active only) |
| `#/gm/players` | Player Roster | All players with characters, login URLs, status |
| `#/gm/invites` | Invite Management | Create/delete invites, share links |
| `#/gm/world` | World Builder | Same as player world browser + create/edit capabilities |
| `#/gm/world/characters/new` | Create NPC | Name, description, attributes |
| `#/gm/world/characters/:id/setup` | PC Setup | Batch GM actions for initial character configuration |
| `#/gm/world/groups/new` | Create Group | Name, description, tier |
| `#/gm/world/locations/new` | Create Location | Name, description, parent |
| `#/gm/world/stories/new` | Create Story | Name, summary, owners, tags |
| `#/gm/trait-templates` | Trait Template Catalog | List, create, edit, soft-delete templates |
| `#/gm/clocks` | Clock Management | All clocks with progress, associated objects |
| `#/gm/feed` | Full Feed | All events at all visibility levels |
| `#/gm/feed/silent` | Silent Feed | Bookkeeping events only |
| `#/gm/character` | GM Character Sheet | Own character (if linked), same as player sheet |

---

## E. Key Interaction Flows

### Proposal Submission (3-Step)

**Step 1 — Choose Action Type** (`#/proposals/new`):

Action types grouped by category:

```
Session Actions
  ├── Use Skill        (roll skill + modifiers)
  ├── Use Magic        (freeform magic action)
  └── Charge Magic     (recharge/boost an effect)

Downtime Actions (cost 1 FT each)
  ├── Regain Gnosis    (recover magical energy)
  ├── Work on Project  (advance a Story/Arc)
  ├── Rest             (heal Stress)
  ├── New Trait         (replace/fill a trait slot)
  └── New Bond          (replace/fill a bond slot)
```

Tapping a type navigates to Step 2 with that type pre-selected.

**Step 2 — Fill Details** (`#/proposals/new/:type`):

Type-specific form:

| Field | When Shown | Required |
|-------|-----------|----------|
| Narrative | Always | Required for downtime; optional for session actions |
| Skill selector | `use_skill` | Yes |
| Intention + Symbolism | `use_magic`, `charge_magic` | Yes |
| Sacrifice list builder | `use_magic`, `charge_magic` | Yes |
| Suggested Magic Stat | `use_magic`, `charge_magic` | Yes |
| Target effect | `charge_magic` | Yes |
| Story selector | `work_on_project` | Yes |
| Slot type + template/name | `new_trait` | Yes |
| Target game object | `new_bond` | Yes |
| Retire target | `new_trait`, `new_bond` (when at max) | Conditional |
| Modifier selectors | Session actions, `regain_gnosis`, `rest` | Optional |
| Plot spend | Session actions | Optional |

Bottom of form: "Preview" button.

**Step 3 — Preview & Submit** (`#/proposals/new/:type/preview`):

Display the `calculated_effect` returned from a dry-run or client-side calculation:
- Dice pool breakdown (for session actions)
- Resource costs itemized
- Effect description (for fixed-outcome downtime)

"Submit" button. On success, navigate to `#/proposals/:id`.

### GM Review Queue (`#/gm/queue`)

**Layout**:
- System proposals (`resolve_clock`, `resolve_trauma`) displayed at top with distinct visual treatment (different background color, "System" badge)
- Player proposals sorted oldest-first (FIFO — first submitted, first reviewed)
- Each proposal shown as a card with: character name, action type, narrative preview (truncated), submission time

**Inline Expansion**:
- Tapping a proposal card expands it inline (does not navigate away)
- Expanded view shows: full narrative, calculated effect details, modifier breakdown, costs

**Default Approval (One-Tap)**:
- "Approve" button prominently displayed — approves with no overrides, no rider, no bond strain
- This is the common case: player's narrative is good, calculation is right, dice rolled well

**Advanced Approval**:
- "Advanced" expander reveals: GM narrative override, cost overrides, bond strain toggle, rider event form
- For `use_magic`: effect creation fields (name, description, type, power_level, charges_max)
- For `charge_magic`: charges_added / power_boost fields
- For `resolve_trauma`: bond selector (which bond becomes trauma), trauma name/description

**Rejection**:
- "Reject" button opens a rejection note text field
- Submit sends `POST /proposals/{id}/reject`

### Direct Player Actions (No Approval)

These actions bypass the proposal queue — the player triggers them and they resolve immediately:

| Action | Trigger | Effect | Narrative |
|--------|---------|--------|-----------|
| `find_time` | Button on character sheet (when Plot ≥ 3) | 3 Plot → 1 FT | None |
| `use_effect` | "Use" button on a Magic Effect card | −1 charge | Optional |
| `retire_effect` | "Retire" button on a Magic Effect card | Effect → Past, frees cap | None |
| `recharge_trait` | "Recharge" button on a Trait card (when charges < 5) | Restore to 5 charges, costs 1 FT | Required |
| `maintain_bond` | "Maintain" button on a Bond card (when charges < effective max) | Restore to effective max, costs 1 FT | Required |

`recharge_trait` and `maintain_bond` are direct actions (not proposals). When triggered:
1. A modal/bottom sheet appears requesting narrative text
2. Player writes a brief description of what their character does
3. Submit → immediate resolution, event created, UI updates

### Character Sheet (Progressive Disclosure)

**Tier 1 — Always Visible (top of sheet)**:
- Character name, description snippet
- Resource meter bar: Stress, Free Time, Plot, Gnosis — each as a compact horizontal bar with current/max
- Quick action buttons: Find Time (if Plot ≥ 3)

**Tier 2 — Tabbed Sections (middle of sheet)**:

| Tab | Contents |
|-----|----------|
| Bonds | Active bonds with charge dots, maintain button, target name |
| Traits | Core + Role traits with charge dots, recharge button |
| Effects | Active magic effects with charges, use/retire buttons |
| Skills | 8 skills with levels (read-only) |
| Feed | Character's own feed (recent events) |

**Tier 3 — Expandable (bottom of sheet)**:

| Section | Contents |
|---------|----------|
| Magic Stats | 5 stats with levels and XP progress bars |
| Past/Retired | Inactive traits, bonds, effects (collapsed by default) |
| Session History | Sessions participated in (from join table) |
| Locations | Bond-distance presence: Common, Familiar, Known |

---

## F. Component Definitions

### Meter Display

A horizontal bar showing current/max with color fill:

```
Stress    ████████░░  7/9
Free Time ██████░░░░  6/20
Plot      ███░░      3/5
Gnosis    ████░░░░░░  4/23
```

- Fill color: Stress (red), FT (green), Plot (amber), Gnosis (blue)
- Stress bar shows `effective_max` marker when Traumas exist (e.g., `7/9 (max 8)`)
- Compact mode (GM dashboard): just the bar, no label

### Charge Dots

A row of filled/empty circles representing charges (0–5):

```
Relentless    ●●●●○   4/5
Gutter Runner ●●●●●   5/5
```

- Core Traits: primary color dots
- Role Traits: primary color dots
- Bonds: different accent color for bond charges (distinguish from traits visually)
- Tapping a trait/bond dot row opens the detail/action view

### Clock Progress

**List view (compact)**: Segmented dots like charges:
```
Expanding Territory  ●●●○○○  3/6
```

**Detail view**: Segmented bar with filled/unfilled boxes:
```
[■][■][■][□][□][□]  3/6 segments
```

- Completed clocks: all filled, with "Completed" badge
- Near-completion clocks (1 segment away): highlighted on GM dashboard

### Proposal Cards

**Player view** (in "My Proposals" list):
- Status badge: Pending (yellow), Approved (green), Rejected (red)
- Action type label
- Narrative preview (first ~80 chars)
- Submission time (relative: "2h ago")

**GM view** (in review queue):
- Character name + avatar placeholder
- Action type + category badge
- Full narrative (expanded view)
- Calculated effect breakdown
- Inline approval/rejection forms

### Feed Items

Each feed item is a card in the chronological stream:

- **Discriminator**: `event` or `story_entry` (different icon/badge)
- **Event items**: Actor name, event type label (human-readable), narrative, targets listed, relative timestamp
- **Story entry items**: Author name, story name, entry text, timestamp
- **Color coding by actor_type**: Player actions (default), GM actions (accent), System actions (muted)
- **`is_own` indicator**: Subtle highlight on items caused by the current user

### Game Object Cards

Compact cards for entities in the world browser:

- **Character card**: Name, detail_level badge (PC/NPC), description snippet
- **Group card**: Name, tier badge, member count, description snippet
- **Location card**: Name, parent location (if any), description snippet

Tapping navigates to the detail view.

### Trait/Effect Cards

Cards within the character sheet tabs:

- **Trait card**: Name, description, charge dots, "Recharge" button (if charges < 5 and owner is current user)
- **Bond card**: Target name, labels, charge dots (different color), "Maintain" button (if charges < effective max)
- **Effect card**: Name, type badge (charged/permanent), power level, charge dots (if charged), "Use"/"Retire" buttons

---

## G. Information Architecture

### Character Sheet Priority

| Priority | Content | Rationale |
|----------|---------|-----------|
| P0 | Resource meters (Stress, FT, Plot, Gnosis) | Glanceable state at the table |
| P1 | Bonds, Traits, Effects, Skills | Active mechanical elements |
| P2 | Magic Stats + XP progress | Rarely referenced mid-session |
| P3 | Past/Retired, Session History, Locations | Historical/reference data |

### GM Dashboard Priority

| Priority | Content | Rationale |
|----------|---------|-----------|
| P0 | Pending proposals (system proposals first) | The GM's primary action queue |
| P0 | PC resource meter summaries | Quick health check across all characters |
| P1 | Near-completion clocks (1 segment away) | Upcoming narrative triggers |
| P2 | Recent feed items | Awareness of recent activity |

### Feed Priority (Event Ordering by Significance)

Within the chronological feed, items are ordered by timestamp (ULID). No re-ordering by type. However, the following types are visually distinguished:

| Event Category | Visual Treatment |
|----------------|-----------------|
| Proposal approvals/rejections | Bold, full-width card |
| State changes (meters, traits, bonds) | Standard card |
| Story entries | Indented, literary styling |
| World changes (clock advance, group tier) | Standard card with world icon |
| Lifecycle events (session start/end) | Muted, full-width banner |

---

## H. Table-Flow Design Principles

### Core Principle: Minimize Phone Time During Active Play

The game is played at a physical table. The phone is an assistant, not the experience. Design decisions follow from this:

### Immediate Interactions (< 15 seconds)

Actions that happen during a player's turn and should not slow the table:

- **Submit a proposal**: 3-step flow should be completable in under 15 seconds for common cases (skill action with 1-2 modifiers)
- **Use a Magic Effect**: One tap + optional narrative
- **Find Time**: One tap
- **Recharge Trait / Maintain Bond**: Tap + brief narrative text + submit

### Between-Turn Activities (Non-Blocking)

Activities done while other players take their turns or between sessions:

- Writing narrative for proposals
- Browsing the world/feed
- Contributing to Stories
- Reviewing proposal status

### Polling Strategy

No WebSocket connections. The UI polls the API at sensible intervals:

| Context | Interval | Endpoint |
|---------|----------|----------|
| Proposal queue (GM) | 30 seconds | `GET /api/v1/proposals?status=pending` |
| Active session timeline | 30 seconds | `GET /api/v1/sessions/{id}/timeline` |
| My proposals (player) | 60 seconds | `GET /api/v1/proposals?character_id={me}` |
| Character sheet meters | 60 seconds | `GET /api/v1/characters/{id}` |

**Visibility-change pause**: Polling stops when the browser tab is hidden (`document.visibilityState === "hidden"`) and resumes immediately when visible again. Saves battery on idle phones.

### Notification Indicators

No push notifications for MVP. Instead, visual indicators on navigation tabs:

- **Proposals tab (player)**: Badge count of proposals with status changes since last viewed (approved/rejected)
- **Queue tab (GM)**: Badge count of pending proposals
- Updated on each poll cycle

---

## I. Proposed API Additions (Phase 5.5 Backend Work)

The following API changes are needed to support the Web UI efficiently. These are backend implementation items tracked in [implementation/README.md](../implementation/README.md).

### New Endpoints

**`GET /api/v1/gm/dashboard`** — Aggregated GM overview:

Returns a single response combining:
- Pending proposals (system proposals first, then player proposals oldest-first)
- PC resource summaries (character name + Stress/FT/Plot/Gnosis meters for all active PCs)
- Near-completion clocks (clocks where `progress >= segments - 1`)

Rationale: Avoids 3+ separate API calls on the GM dashboard. Single round-trip for the most critical GM view.

**`POST /api/v1/gm/actions/batch`** — Batch GM actions:

Accepts an array of GM action payloads. All actions are validated and applied atomically in a single transaction. If any action fails validation, the entire batch is rolled back.

Rationale: Character setup requires multiple GM actions (set meters, create traits, create bonds). Batch endpoint enables a "Setup Character" UI flow that commits all initial state in one request.

**`GET /api/v1/characters/summary`** — Lightweight PC resource meters:

Returns a compact list of all active PCs with only their resource meters (Stress, FT, Plot, Gnosis) and basic identity (id, name). No traits, bonds, skills, or other detail.

Rationale: GM dashboard needs a quick health-check across all PCs without fetching full character sheets.

### Spec Changes

**`narrative` nullable on session action proposals**: For session actions (`use_skill`, `use_magic`, `charge_magic`), the `narrative` field becomes optional (nullable) on submission. Players can PATCH the narrative onto the proposal later. Downtime actions still require narrative.

Rationale: During active play, the table moves fast. Requiring narrative before submission slows the table. Players can add narrative context after the fact.

**`recharge_trait` promoted to direct player action**: No longer a proposal requiring GM approval. Player triggers directly from the character sheet (costs 1 FT, restores charges to 5). Requires narrative text. Creates an event immediately.

**`maintain_bond` promoted to direct player action**: No longer a proposal requiring GM approval. Player triggers directly from the character sheet (costs 1 FT, restores charges to effective max). Requires narrative text. Creates an event immediately.

Rationale for promotions: These are fixed-outcome, predictable actions. Routing them through the proposal queue adds friction without adding meaningful GM decision-making. The required narrative preserves the fiction requirement — players still describe what their character does.

### New API Endpoints Summary

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/gm/dashboard` | GET | Aggregated GM overview |
| `/api/v1/gm/actions/batch` | POST | Atomic batch GM actions |
| `/api/v1/characters/summary` | GET | Lightweight PC meter summaries |
| `/api/v1/characters/{id}/recharge-trait` | POST | Direct trait recharge (player) |
| `/api/v1/characters/{id}/maintain-bond` | POST | Direct bond maintenance (player) |

---

## J. Static File Structure

```
src/static/
├── index.html              # SPA shell — Pico CSS, Alpine.js, router bootstrap
├── css/
│   ├── pico.min.css        # Pico CSS v2 (vendored)
│   └── app.css             # Custom properties, game-specific styles, meter colors
├── js/
│   ├── alpine.min.js       # Alpine.js v3 (vendored)
│   ├── api.js              # Fetch wrapper (credentials: 'same-origin', JSON, error handling, 401 redirect)
│   ├── router.js           # Hash router (~50 lines: listen hashchange, match routes, load views)
│   ├── store.js            # Alpine global store (current user, role, character_id, polling state)
│   └── views/              # One JS file per major view
│       ├── login.js        # Magic link handler + join form
│       ├── setup.js        # First-run GM setup
│       ├── dashboard.js    # Player feed / GM dashboard
│       ├── character.js    # Character sheet (progressive disclosure)
│       ├── proposals.js    # Proposal list + 3-step submission flow
│       ├── world.js        # World browser (characters, groups, locations, stories)
│       ├── session.js      # Session view (player) / Session management (GM)
│       ├── gm-queue.js     # GM proposal review queue
│       ├── gm-actions.js   # GM direct actions form
│       ├── gm-players.js   # Player roster + invite management
│       ├── gm-clocks.js    # Clock management
│       └── profile.js      # User profile, starred objects
└── img/                    # Icons, placeholder images (if any)
```

### FastAPI Mount

```python
from fastapi.staticfiles import StaticFiles

app.mount("/static", StaticFiles(directory="src/static"), name="static")
```

The `index.html` SPA shell is served for all non-API routes (catch-all route or middleware that serves `index.html` for paths not matching `/api/`).

---

## Decisions

### No Build Step

- **Decision**: No webpack, no Vite, no compilation. Vendor Pico CSS and Alpine.js as minified files. All application JS is vanilla ES modules.
- **Rationale**: The UI is a thin client for 4–6 concurrent users. Build tooling adds complexity without proportional benefit. Edit-refresh development cycle is faster than edit-build-refresh.
- **Implications**: No TypeScript, no JSX, no CSS preprocessor. Code organization is file-based (one JS file per view). Testing is manual + browser dev tools.

### Hash Routing

- **Decision**: Use `#/path` hash routing, not HTML5 History API.
- **Rationale**: No server configuration needed — FastAPI serves `index.html` and the hash handles client-side routing. No 404 issues on refresh. Simpler than configuring catch-all routes.
- **Implications**: URLs look like `https://wizards.example/#/character` rather than `https://wizards.example/character`. Acceptable for a private game tool.

### Same-Origin Deployment

- **Decision**: Static files served by the same FastAPI process. No separate frontend server, no CDN, no reverse proxy (for MVP).
- **Rationale**: Single deployment artifact. No CORS configuration. Cookie auth works without cross-origin setup. The server is on a VPS serving 4–6 users — no performance concern.
- **Implications**: `credentials: 'same-origin'` on all fetch calls. No CORS headers needed.

### Polling Over WebSockets

- **Decision**: Use HTTP polling for state updates. No WebSocket or SSE connections.
- **Rationale**: 30-second polling with 4–6 users generates negligible load. WebSockets add connection management complexity. The table-play context means updates are checked during natural pauses, not real-time chat.
- **Implications**: UI shows data that may be up to 30 seconds stale. Acceptable for this use case. Polling pauses on tab hide to save battery.

### No Offline Support

- **Decision**: No Service Worker, no offline cache, no IndexedDB. The app requires network connectivity.
- **Rationale**: Game table context — all players are in the same physical location with shared WiFi. Offline mode adds significant complexity for a scenario that essentially never happens.
- **Implications**: If the server goes down, the UI shows an error state. Players wait for the GM to fix it.

### Mobile-First Layout

- **Decision**: Design for phone screens first (360px viewport). Desktop layout is an enhancement (sidebar instead of bottom tabs, wider content area).
- **Rationale**: Players use phones at the table. The GM may use a laptop. Phone is the primary viewport.
- **Implications**: Pico CSS handles responsive basics. Custom CSS adds mobile-specific adjustments (bottom tab bar, touch-friendly tap targets ≥ 44px).

### Proposal Flow is 3 Steps (Not 1 Form)

- **Decision**: Proposal submission is a guided 3-step flow (choose type → fill details → preview/submit), not a single long form.
- **Rationale**: On a phone screen, a single form with all fields is overwhelming. Stepped flow provides progressive disclosure and reduces errors. The preview step gives the player confidence before committing.
- **Implications**: Navigation between steps uses hash route segments. Back navigation preserves form state (Alpine `x-data` on a shared store).

### GM Queue is Inline-Expand (Not Navigate)

- **Decision**: Tapping a proposal in the GM queue expands it inline. The GM does not navigate to a separate page.
- **Rationale**: The GM reviews proposals in rapid succession. Navigating away and back for each one is slower than expanding/collapsing in place.
- **Implications**: Queue view needs expandable card components. Only one card expanded at a time (accordion pattern).

### Direct Actions for Recharge Trait and Maintain Bond

- **Decision**: `recharge_trait` and `maintain_bond` are direct player actions (not proposals). They require narrative text and cost 1 FT. See [actions.md](actions.md) for the spec change.
- **Rationale**: Fixed-outcome actions with no meaningful GM decision. Routing through the queue adds latency and queue noise. Required narrative preserves the fiction.
- **Implications**: Two new direct action endpoints. Downtime action list reduced from 7 to 5 proposal types.

### Narrative Optional for Session Actions

- **Decision**: Session action proposals (`use_skill`, `use_magic`, `charge_magic`) accept nullable `narrative`. Players can PATCH narrative onto pending proposals later. Downtime actions still require narrative.
- **Rationale**: At the table, the action happens verbally and physically. Requiring typed narrative before submission slows the flow. Players can add it between turns or after the session.
- **Implications**: Submission validation relaxed for 3 action types. PATCH endpoint already supports narrative updates.

---

## Implications for Other Specs

| Spec | Implication |
|------|-------------|
| [actions](actions.md) | `narrative` nullable for session actions. `recharge_trait` and `maintain_bond` promoted to direct player actions. Two new direct action endpoints. Downtime action count: 7 → 5 proposal types + 2 direct actions. |
| [downtime](downtime.md) | `recharge_trait` and `maintain_bond` removed from the downtime proposal list. Still cost 1 FT. |
| [auth](auth.md) | Frontend handles magic link flow, invite detection, setup flow. Cookie-based auth confirmed compatible with SPA approach. |
| [character-core](character-core.md) | Two new direct action endpoints on character route (`/recharge-trait`, `/maintain-bond`). |
| [architecture/api-conventions](../architecture/api-conventions.md) | New batch endpoint pattern (`POST /gm/actions/batch`). New aggregation endpoint pattern (`GET /gm/dashboard`). |

---

## Open Questions

All resolved.

---

_Last updated: 2026-03-18_
