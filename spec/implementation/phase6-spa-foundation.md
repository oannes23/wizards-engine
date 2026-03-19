# Epic 6.1 — SPA Foundation & Auth

**Phase**: 6 — Web UI
**Depends on**: Phase 5 (full backend API)
**Blocks**: All other Phase 6 epics (6.2–6.6)
**Parallel with**: None (foundational)

---

## Overview

Build the single-page application shell: static file serving from FastAPI, Alpine.js + Pico CSS frontend, API client with error handling, hash-based routing, authentication flows (login, join, setup), responsive navigation shell with role-based tabs, and polling infrastructure with visibility-change pause. This epic establishes every pattern used by subsequent UI epics.

---

## Stories

| Story | Status | Completed |
|-------|--------|-----------|
| 6.1.1 — Static File Serving + SPA Shell | 🟢 Complete | 2026-03-18 |
| 6.1.2 — API Client + Hash Router + Alpine Store | 🟢 Complete | 2026-03-18 |
| 6.1.3 — Auth Flows (Login, Join, Setup, 401 Redirect) | 🟢 Complete | 2026-03-18 |
| 6.1.4 — Navigation Shell (Player Tabs, GM Tabs, Responsive) | 🟢 Complete | 2026-03-18 |
| 6.1.5 — Polling Infrastructure + Visibility-Change Pause | 🟢 Complete | 2026-03-18 |

### Story 6.1.1 — Static File Serving + SPA Shell

**Files to create**:
- `src/wizards_engine/static/index.html` — SPA shell (Alpine.js, Pico CSS CDN links, `<div x-data>` root)
- `src/wizards_engine/static/css/app.css` — custom styles (minimal, extends Pico)
- `src/wizards_engine/static/js/app.js` — Alpine.js app initialization

**Files to modify**:
- `src/wizards_engine/app.py` — add static file serving routes

**Spec refs**: [web-ui.md](../domains/web-ui.md) (Technology Stack, Static Serving)

**Implementation notes**:
- Use explicit FastAPI routes for `GET /`, `GET /login/{code}`, `GET /setup` returning `FileResponse(index.html)`. No wildcard catch-all (preserves `/docs`, `/redoc`)
- Pico CSS v2 via CDN, Alpine.js v3 via CDN — no build step
- HTML shell: `<!DOCTYPE html>`, viewport meta, Pico CSS link, Alpine.js script, app.js script, app.css link

**Acceptance criteria**:
1. `GET /` returns 200 with `Content-Type: text/html`
2. `GET /login/abc123` returns 200 with same index.html
3. `GET /setup` returns 200 with same index.html
4. `GET /docs` still returns Swagger UI (not caught by SPA routes)
5. `GET /api/v1/me` still works (API routes unaffected)
6. Index.html loads Pico CSS and Alpine.js from CDN
7. Add 1 backend test: `GET /` returns 200 with `Content-Type: text/html`

### Story 6.1.2 — API Client + Hash Router + Alpine Store

**Files to create**:
- `src/wizards_engine/static/js/api.js` — API client (fetch wrapper, error envelope parsing, 401 redirect)
- `src/wizards_engine/static/js/store.js` — Alpine.js global store (user state, role, character_id)
- `src/wizards_engine/static/js/router.js` — hash-based router (`#/character`, `#/world`, `#/proposals`, etc.)

**Spec refs**: [web-ui.md](../domains/web-ui.md) (Navigation Architecture, API Client)

**Implementation notes**:
- `api.js`: wraps `fetch()` with automatic error envelope parsing (`{error: {code, detail}}`), toast/banner display convention, 401 → redirect to `#/login`
- `store.js`: Alpine `$store` with `user` (from `GET /me`), `role` (player/gm), `character_id`, `isOwner(characterId)` utility
- `router.js`: listens to `hashchange`, dispatches to view components. Default routes: `#/login`, `#/setup`, `#/character`, `#/world`, `#/proposals`, `#/gm`

**Acceptance criteria**:
1. Hash navigation works: clicking links updates view without page reload
2. `api.get('/api/v1/me')` returns parsed JSON on success
3. `api.post(url, body)` sends JSON with credentials
4. API errors display in a toast/banner element
5. 401 responses redirect to `#/login`
6. `$store.user` populated after successful `GET /me`
7. `$store.isOwner(id)` returns true when `character_id` matches

### Story 6.1.3 — Auth Flows (Login, Join, Setup, 401 Redirect)

**Files to create**:
- `src/wizards_engine/static/js/views/login.js` — login view component
- `src/wizards_engine/static/js/views/setup.js` — first-run setup view
- `src/wizards_engine/static/js/views/join.js` — invite join view

**Spec refs**: [web-ui.md](../domains/web-ui.md) (Auth Flows), [auth.md](../domains/auth.md) (login, setup, invite)

**Acceptance criteria**:
1. `#/login` shows login code input field
2. Submitting login code calls `POST /auth/login` → on success, redirects to `#/character` (player) or `#/gm` (GM)
3. `#/setup` shows first-run setup form (display name) → calls `POST /setup` → redirects to `#/gm`
4. `GET /login/{code}` auto-submits the code (deep link from invite email/message)
5. `#/join` shows character setup form (display name, character name) after invite login
6. 401 from any API call → redirect to `#/login` with return-to hash preserved
7. Logout clears store and redirects to `#/login`

### Story 6.1.4 — Navigation Shell (Player Tabs, GM Tabs, Responsive)

**Files to create**:
- `src/wizards_engine/static/js/components/nav.js` — navigation component

**Files to modify**:
- `src/wizards_engine/static/index.html` — add nav container
- `src/wizards_engine/static/css/app.css` — responsive nav styles

**Spec refs**: [web-ui.md](../domains/web-ui.md) (Navigation Architecture, Mobile/Desktop layouts)

**Acceptance criteria**:
1. **Player tabs** (mobile bottom bar): Character, World, Proposals, Profile
2. **GM tabs** (mobile bottom bar): Dashboard, Sessions, Players, World, Profile
3. **Desktop**: tabs move to sidebar or top bar
4. Active tab highlighted based on current hash route
5. GM-player dual identity: conditional "My Character" link when GM has a character
6. Tab visibility matches `$store.role` — players never see GM tabs, GM never sees player-only tabs
7. Touch targets >= 44px on mobile viewport (390px)
8. Responsive breakpoint: bottom tabs on mobile, horizontal/sidebar on desktop

### Story 6.1.5 — Polling Infrastructure + Visibility-Change Pause

**Files to modify**:
- `src/wizards_engine/static/js/store.js` — add polling registry and visibility-change handler

**Spec refs**: [web-ui.md](../domains/web-ui.md) (Polling Strategy)

**Implementation notes**:
- Polling registry: views register `{url, interval, callback}` entries on mount, deregister on unmount
- Visibility-change: pause all polling when `document.visibilityState === 'hidden'`, resume on visible
- Per-view polling config established here; views register their own polling in their own stories

**Acceptance criteria**:
1. `store.registerPoll(key, {url, intervalMs, callback})` starts periodic fetch
2. `store.unregisterPoll(key)` stops it
3. All polling pauses when tab is hidden (`document.visibilityState`)
4. All polling resumes when tab becomes visible again
5. Multiple polls can run concurrently with different intervals
6. Poll errors do not crash the app — logged to console, next poll fires on schedule

---

## Notes

- No build step — all JS served as plain files via FastAPI static routes
- Pico CSS provides the base styling; custom CSS is minimal overrides
- Hash routing chosen to avoid server-side route handling complexity while preserving `/docs` and `/api` paths
- This epic produces a functional login → empty shell → polling loop that all subsequent epics build on
