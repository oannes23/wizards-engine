# Epic 9.1 — Viewer Role

**Phase**: 9 — Viewer Role
**Depends on**: All prior phases (8.7 complete)
**Blocks**: None
**Parallel with**: None

---

## Overview

Add a third user role, "viewer", that has GM-level read access to all game state (except silent system events) but cannot take any mutating actions. Viewers are created via invites with a role field, have no character, and are invisible to players in the roster. This also introduces a centralized Role StrEnum and refactors scattered string literals.

---

## Stories

| Story | Status | Completed |
|-------|--------|-----------|
| 9.1.1 — Role Constants Module | 🟢 Complete | 2026-03-28 |
| 9.1.2 — Database Migration | 🟢 Complete | 2026-03-28 |
| 9.1.3 — Auth Dependency Refactor | 🟢 Complete | 2026-03-28 |
| 9.1.4 — Viewer Onboarding (Invite + Join) | 🟢 Complete | 2026-03-28 |
| 9.1.5 — Visibility & Feed Updates | 🟢 Complete | 2026-03-28 |
| 9.1.6 — Route Permission Audit: Read Endpoints | 🟢 Complete | 2026-03-28 |
| 9.1.7 — Route Permission Audit: Write Endpoints & Roster | 🟢 Complete | 2026-03-28 |
| 9.1.8 — Schema & /me Response Updates | 🟢 Complete | 2026-03-28 |
| 9.1.9 — Example Campaign Data Update | 🟢 Complete | 2026-03-28 |
| 9.1.10 — Tests | 🟢 Complete | 2026-03-28 |
| 9.1.11 — Spec & Frontend Handoff Docs | 🟢 Complete | 2026-03-28 |

### Story 9.1.1 — Role Constants Module

**Files to create**:
- `src/wizards_engine/roles.py` — `Role` StrEnum, convenience sets, helper functions

**Spec refs**: [auth.md](../domains/auth.md)

**Acceptance criteria**:
- `Role.GM == "gm"` and `Role.PLAYER == "player"` (StrEnum, backward-compatible)
- All existing string literal role checks replaced with `Role.*` constants across ~10 files (`api/deps.py`, `services/visibility.py`, `api/routes/proposals.py`, `api/routes/players.py`, `api/routes/effects.py`, `api/routes/sessions.py`, `services/player_actions.py`, `services/onboarding.py`, `api/routes/setup.py`, `campaign/schemas.py`)
- `has_full_visibility()` returns True for GM and viewer, False for player
- `actor_type_for()` returns "gm" for GM, "player" for player, raises `ValueError` for viewer
- All existing tests still pass after refactoring

### Story 9.1.2 — Database Migration

**Files to create**:
- `alembic/versions/XXXX_add_viewer_role_and_invite_role.py`

**Files to modify**:
- `src/wizards_engine/models/user.py` — add `role` column to `Invite` model: `role: Mapped[str] = mapped_column(String(10), nullable=False, default="player")`

**Spec refs**: [auth.md](../domains/auth.md)

**Acceptance criteria**:
- `uv run alembic upgrade head` applies cleanly
- `uv run alembic downgrade -1` reverses cleanly
- `users.role` has CHECK constraint: `CHECK(role IN ('gm', 'player', 'viewer'))`
- `invites` table has `role` column: String(10), NOT NULL, default `"player"`
- `invites.role` has CHECK constraint: `CHECK(role IN ('player', 'viewer'))`
- `Invite` model has `role: Mapped[str]` column with default `"player"`

### Story 9.1.3 — Auth Dependency Refactor

**Files to modify**:
- `src/wizards_engine/api/deps.py` — add `require_role()` factory and named aliases

**Spec refs**: [auth.md](../domains/auth.md)

**Acceptance criteria**:
- `require_role()` factory produces correct FastAPI dependencies for any combination of roles
- `require_gm` alias still works identically (backward-compatible)
- `require_privileged` alias allows GM and viewer, blocks player
- Error code remains `insufficient_role` with 403 status
- All existing tests still pass

### Story 9.1.4 — Viewer Onboarding (Invite + Join)

**Files to modify**:
- `src/wizards_engine/api/routes/invites.py` — accept optional `role` field in create
- `src/wizards_engine/schemas/invite.py` — add `CreateInviteRequest`, update `InviteResponse`
- `src/wizards_engine/services/invites.py` — pass role to invite creation
- `src/wizards_engine/services/onboarding.py` — read `invite.role`, skip character creation for viewer
- `src/wizards_engine/schemas/auth.py` — make `character_name` optional in `JoinRequest`
- `src/wizards_engine/api/routes/game.py` — handle viewer join (no character)

**Spec refs**: [auth.md](../domains/auth.md)

**Acceptance criteria**:
- `POST /game/invites` accepts optional `{"role": "viewer"}` body field (default: `"player"`)
- `POST /game/invites` with `{"role": "viewer"}` creates invite with `role="viewer"`
- `InviteResponse` includes `role` field (`"player"` or `"viewer"`)
- `POST /game/join` with a viewer invite: `character_name` is not required, no character created
- `POST /game/join` with a player invite: existing behavior unchanged
- `JoinResponse` for viewer: `character_id` is null, `role` is `"viewer"`

### Story 9.1.5 — Visibility & Feed Updates

**Files to modify**:
- `src/wizards_engine/services/visibility.py` — use `has_full_visibility()` instead of `role == "gm"` in `can_user_see_event()`, `can_user_see_story()`, and `filter_events_for_user()`
- `src/wizards_engine/api/routes/feed.py` — keep `GET /me/feed/silent` GM-only (do not open to viewer)

**Spec refs**: [events.md](../domains/events.md), [feed.md](../domains/feed.md)

**Acceptance criteria**:
- Viewer sees events with visibility: `gm_only`, `private`, `bonded`, `familiar`, `public`, `global`
- Viewer does NOT see events with visibility: `silent`
- `GET /me/feed/silent` returns 403 for viewer
- Player visibility unchanged (bond-graph filtering still applies)
- GM visibility unchanged (sees everything including silent)

### Story 9.1.6 — Route Permission Audit: Read Endpoints

**Files to modify**:
- `src/wizards_engine/api/routes/gm_dashboard.py` — change `require_gm` to `require_privileged` on `GET /gm/dashboard` and `GET /gm/queue-summary`
- `src/wizards_engine/api/routes/invites.py` — change `require_gm` to `require_privileged` on `GET /game/invites`
- `src/wizards_engine/api/routes/proposals.py` — update `_assert_can_read` so viewer sees all proposals like GM
- `src/wizards_engine/api/routes/effects.py` — viewer can read any character's effects like GM

**Spec refs**: [proposals.md](../domains/proposals.md)

**Acceptance criteria**:
- `GET /gm/dashboard` returns 200 for viewer (same data as GM)
- `GET /gm/queue-summary` returns 200 for viewer
- `GET /game/invites` returns 200 for viewer
- `GET /proposals` for viewer returns all proposals (not filtered by character)
- `GET /proposals/{id}` for viewer returns any proposal
- Viewer can read effects for any character
- All these endpoints still work identically for GM and for player (unchanged behavior)

### Story 9.1.7 — Route Permission Audit: Write Endpoints & Roster

**Files to modify** (inline write checks — block viewer):
- `src/wizards_engine/api/routes/proposals.py` — `POST /proposals` and `POST /proposals/calculate`: currently blocks GM, must also block viewer
- `src/wizards_engine/api/routes/find_time.py` — player action: viewer blocked
- `src/wizards_engine/api/routes/recharge_trait.py` — player action: viewer blocked
- `src/wizards_engine/api/routes/maintain_bond.py` — player action: viewer blocked
- `src/wizards_engine/api/routes/effects.py` — use/retire: viewer blocked
- `src/wizards_engine/api/routes/sessions.py` — participant add/remove: viewer blocked
- `src/wizards_engine/api/routes/starred.py` — POST/DELETE starred: viewer allowed (personal convenience feature)
- `src/wizards_engine/api/routes/players.py` — roster visibility logic per caller role

**Spec refs**: [auth.md](../domains/auth.md)

**Acceptance criteria**:
- Every mutating GM-only endpoint returns 403 for viewer (all POST/PATCH/DELETE on characters, groups, locations, clocks, trait_templates, stories, sessions, events; `POST /gm/actions`, `POST /gm/actions/batch`; `POST /proposals/{id}/approve`, `POST /proposals/{id}/reject`; `POST /players/{id}/regenerate-token`; `POST /me/character`; `DELETE /game/invites/{id}`)
- Every player-only action endpoint returns 403 for viewer
- `POST /proposals` returns 403 for viewer (not just GM)
- Player roster for player callers excludes viewers
- Player roster for viewer callers includes all users but no `login_url`
- Player roster for GM callers includes all users with `login_url`
- Viewer CAN star/unstar game objects (personal convenience)

### Story 9.1.8 — Schema & /me Response Updates

**Files to modify**:
- `src/wizards_engine/schemas/auth.py` — add `can_view_gm_content: bool` and `can_take_gm_actions: bool` to `MeResponse`; update `role` type to `Literal["gm", "player", "viewer"]` on `MeResponse`, `LoginUserResponse`, `JoinResponse`, `SetupResponse`
- `src/wizards_engine/schemas/player.py` — update `PlayerResponse.role` type
- `src/wizards_engine/schemas/invite.py` — add `role: str | None` field to `InviteResponse`
- `src/wizards_engine/api/routes/me.py` — populate capability fields based on role in `GET /me`

**Spec refs**: [auth.md](../domains/auth.md)

**Acceptance criteria**:
- `GET /me` for viewer returns `can_view_gm_content: true, can_take_gm_actions: false`
- `GET /me` for GM returns `can_view_gm_content: true, can_take_gm_actions: true`
- `GET /me` for player returns `can_view_gm_content: false, can_take_gm_actions: false`
- All response schemas document `"viewer"` as a valid role value
- OpenAPI spec reflects the updated role values and capability fields

### Story 9.1.9 — Example Campaign Data Update

**Files to modify**:
- `src/wizards_engine/campaign/schemas.py` — `UserYaml.validate_role()`: add `"viewer"` to valid roles set

**Files to create**:
- `campaign-data/users/viewer-iris.yaml` — example viewer account with `display_name: "Viewer Iris"`, `role: viewer`, `character: null`

**Spec refs**: [auth.md](../domains/auth.md)

**Acceptance criteria**:
- `UserYaml` accepts `role: "viewer"` without validation error
- `campaign-data/users/viewer-iris.yaml` exists with `role: viewer`, `character: null`
- Campaign import handles viewer users correctly (creates user with no character)
- Existing campaign data still imports successfully

### Story 9.1.10 — Tests

**Files to create**:
- `tests/test_viewer_role.py` — comprehensive viewer-specific tests

**Spec refs**: [auth.md](../domains/auth.md), [events.md](../domains/events.md), [feed.md](../domains/feed.md), [proposals.md](../domains/proposals.md)

**Acceptance criteria**:
- Auth: Viewer can log in, `GET /me` returns correct role and capability fields
- Onboarding: Viewer invite creation, viewer join (no character), player invite unchanged
- Visibility: Viewer sees `gm_only` events, does NOT see `silent` events
- Read access: Viewer can access dashboard, queue, all proposals, all characters
- Write blocking: Every mutating endpoint returns 403 for viewer (exhaustive list)
- Roster: Player sees no viewers; viewer sees all users without `login_url`; GM sees all users with `login_url`
- Starring: Viewer can star/unstar game objects
- Backward compat: All existing player and GM test suites still pass
- All new tests pass, all existing tests pass (no regressions)

### Story 9.1.11 — Spec & Frontend Handoff Docs

**Files to modify**:
- `spec/domains/auth.md` — revise the "Only two roles" decision block to document three roles
- `spec/glossary.md` — add "Viewer" term definition
- `spec/MASTER.md` — update status, add Phase 9 reference

**Files to create**:
- `VIEWER_ROLE_HANDOFF.md` — frontend team handoff document covering: what changed, `GET /me` capability fields, routing guidance, endpoint access matrix, error handling, roster behavior, recommended frontend pattern (derive `canViewGmContent`/`canTakeGmActions` from `/me` response instead of `role === "gm"` checks), and integration checklist

**Spec refs**: [auth.md](../domains/auth.md), [events.md](../domains/events.md), [feed.md](../domains/feed.md), [proposals.md](../domains/proposals.md)

**Acceptance criteria**:
- `spec/domains/auth.md` accurately describes all three roles and their permissions
- `spec/glossary.md` has a "Viewer" entry
- `VIEWER_ROLE_HANDOFF.md` exists with all 8 sections listed above
- Frontend team can implement viewer support from the handoff document alone

---

## Notes

- No persistent production data exists — the database migration does not need backward-compatibility safeguards
- `GET /me/feed/silent` stays GM-only even though viewer has elevated read access; silent events are system audit plumbing, not narratively meaningful
- Viewer starring is explicitly allowed as a personal convenience feature with no game-state impact
- The `require_gm` alias must remain fully backward-compatible — no existing callers should need updating after 9.1.3
