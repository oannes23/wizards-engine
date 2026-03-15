# Epic 1.2 — Auth & API Skeleton

**Phase**: 1 — Foundation
**Depends on**: Epic 1.1 (Scaffolding & Database)
**Blocks**: All Phase 2+ Epics
**Parallel with**: None

---

## Overview

Implement the authentication system (cookie-based magic links), core API endpoints (setup, login, identity), role-based permissions, the test fixture system, and shared API convention utilities. After this Epic, the app has a working auth flow and a reusable test harness.

---

## Stories

### Story 1.2.1 — Auth Middleware

**Files to create**:
- `src/wizards_engine/api/deps.py` — `get_current_user` dependency (read `login_code` from httpOnly cookie, look up user, inject into request state)
- `src/wizards_engine/api/auth.py` — auth helper functions

**Spec refs**: [auth.md](../domains/auth.md) (magic link auth, cookie-only API auth, auth errors)

**Acceptance criteria**:
- `get_current_user` reads the `login_code` cookie from the request
- Looks up user by `login_code` in the database
- Returns the User object if found and `is_active = true`
- Returns 401 with `{error: {code: "cookie_missing"}}` if no cookie present
- Returns 401 with `{error: {code: "cookie_invalid"}}` if cookie doesn't match any user
- Returns 401 with `{error: {code: "account_inactive"}}` if user found but `is_active = false`
- Cookie name is `login_code`
- Cookie is httpOnly, Secure, SameSite=Lax

### Story 1.2.2 — Setup Endpoint

**Files to create**:
- `src/wizards_engine/api/routes/setup.py` — `POST /api/v1/setup`
- `src/wizards_engine/schemas/auth.py` — request/response Pydantic models

**Spec refs**: [auth.md](../domains/auth.md) (first-run setup, GM account creation)

**Acceptance criteria**:
- `POST /api/v1/setup` accepts `{display_name}` (1–50 chars, trimmed, non-empty after trim)
- Creates a GM user with `role = "gm"`, generates a login code via `secrets.token_urlsafe(32)`
- Sets httpOnly cookie with the login code
- Returns 201 with the user info and magic link URL (`/login/<code>`)
- Returns 409 Conflict with `{error: {code: "already_setup"}}` if a GM user already exists
- Unauthenticated endpoint (no cookie required)

### Story 1.2.3 — Login Endpoint

**Files to create**:
- `src/wizards_engine/api/routes/auth.py` — `POST /api/v1/auth/login`

**Spec refs**: [auth.md](../domains/auth.md) (login flow, invite flow detection)

**Acceptance criteria**:
- `POST /api/v1/auth/login` accepts `{code}`
- If code matches a user's `login_code`: set cookie, return user info (id, display_name, role, character_id)
- If code matches an unconsumed invite's `id`: return `{type: "invite"}` (no cookie set)
- If code doesn't match anything: return 404 with `{error: {code: "code_not_found"}}`
- Does not reveal whether a code exists as a consumed invite vs doesn't exist at all

### Story 1.2.4 — Identity & Profile

**Files to create**:
- `src/wizards_engine/api/routes/me.py` — `GET /api/v1/me`, `PATCH /api/v1/me`
- `src/wizards_engine/api/deps.py` — add `require_gm` permission dependency

**Spec refs**: [auth.md](../domains/auth.md) (identity endpoint, player display name updates, permission model)

**Acceptance criteria**:
- `GET /api/v1/me` returns current user identity: `{id, display_name, role, character_id}`
- `PATCH /api/v1/me` accepts `{display_name}` — validates 1–50 chars, trimmed, non-empty after trim
- Returns 200 with updated user info
- `require_gm` dependency returns 403 with `{error: {code: "insufficient_role"}}` for non-GM users
- Both endpoints require authentication (401 if no cookie)

### Story 1.2.5 — Test Fixture System

**Files to create**:
- `tests/conftest.py` — pytest fixtures: test DB, FastAPI test client, auth helpers
- `tests/fixtures.py` — canonical seed data factory
- `tests/test_example.py` — example test demonstrating fixture usage

**Spec refs**: [mvp-scope.md](../architecture/mvp-scope.md) (full test coverage with fixture DB), [data-model.md](../architecture/data-model.md) (table structure for seed data)

**Seed data**:
- 1 GM user (display_name: "Test GM")
- 3 player users with linked full Characters
- 2 simplified Characters (NPCs)
- 1 Group with tier=2
- 2 Locations (one nested under the other)
- A few Slots (bonds linking characters to the group, NPCs to locations)

**Acceptance criteria**:
- `db` fixture provides a fresh SQLite in-memory database per test, with all tables created
- `client` fixture provides a `httpx.AsyncClient` (or `TestClient`) wired to the FastAPI app with the test DB
- `seed_data` fixture populates the test DB with canonical seed data
- Auth helper functions to set the cookie for any test user (GM or player)
- Example test: authenticated request to `GET /api/v1/me` returns expected user data
- Tests run with `pytest` from the project root
- Each test gets an isolated database (no cross-test contamination)

### Story 1.2.6 — API Conventions

**Files to create**:
- `src/wizards_engine/api/pagination.py` — ULID cursor pagination utility
- `src/wizards_engine/api/responses.py` — paginated list envelope, error response helpers
- `src/wizards_engine/schemas/common.py` — shared Pydantic models (PaginatedResponse, ErrorResponse, etc.)

**Spec refs**: [api-conventions.md](../architecture/api-conventions.md) (response format, error format, pagination, PATCH semantics)

**Acceptance criteria**:
- Paginated list helper produces `{items: [...], next_cursor: "<ulid or null>", has_more: bool}`
- `next_cursor` is null when no more items exist
- Accepts `after` (ULID cursor) and `limit` (default 50, max 100) query parameters
- Error response helper produces `{error: {code: "<string>", message: "<string>", details?: {...}}}`
- Validation error helper formats field-level errors into `{error: {code: "validation_error", message: "...", details: {fields: {field: "message"}}}}`
- snake_case validation on all Pydantic models (via `model_config`)
- Shared models importable from `wizards_engine.schemas.common`
- Pagination utility works with any SQLAlchemy query (generic)

---

## Notes

- Auth is cookie-only — no Bearer token support
- Login codes stored in plaintext (per spec — trusted small group)
- The test fixture system is critical infrastructure — all future Epics depend on it
- API conventions must be established here so Phase 2+ code is consistent
