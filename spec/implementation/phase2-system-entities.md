# Epic 2.2 — System Entities (Clocks, Stories, Sessions)

**Phase**: 2 — World
**Depends on**: Epic 1.2 (Auth & API Skeleton)
**Blocks**: Epic 2.3 (Bonds & Presence) — partially
**Parallel with**: Epic 2.1 (Game Object CRUD) — once CRUD pattern is established

---

## Overview

Implement CRUD for the three System Entity types: Clocks, Stories (with owners and entries), and Sessions (with participants). These are organizational/tracking tools that don't participate in the bond graph but are essential infrastructure for the game.

---

## Stories

| Story | Status | Completed |
|-------|--------|-----------|
| 2.2.1 — Clock CRUD | 🟢 Complete | 2026-03-16 |
| 2.2.2 — Story CRUD + Owners | 🟢 Complete | 2026-03-16 |
| 2.2.3 — Story Entries | 🟢 Complete | 2026-03-16 |
| 2.2.4 — Session CRUD (Draft Only) | 🟢 Complete | 2026-03-16 |
| 2.2.5 — Session Participants | 🟢 Complete | 2026-03-16 |

### Story 2.2.1 — Clock CRUD

**Files to create**:
- `src/wizards_engine/api/routes/clocks.py` — clock endpoints
- `src/wizards_engine/schemas/clock.py` — request/response Pydantic models
- `src/wizards_engine/services/clock.py` — clock service layer
- `tests/test_clocks.py`

**Spec refs**: [game-objects.md](../domains/game-objects.md) (Clock CRUD, association, completion, dual route), [data-model.md](../architecture/data-model.md) (clocks table)

**Acceptance criteria**:
- `POST /api/v1/clocks` — GM only. Accepts `{name, segments?, associated_type?, associated_id?, notes?}`. Segments default to 5, must be > 0. Progress defaults to 0. Returns 201.
- `POST /api/v1/groups/{id}/clocks` — GM only. Sugar route that auto-sets `associated_type = "group"` and `associated_id` to the group ID. Same body minus association fields. Returns 201.
- `GET /api/v1/clocks` — list with filters: `?associated_type=`, `?associated_id=`, `?include_deleted=true`. ULID pagination.
- `GET /api/v1/clocks/{id}` — detail. Includes computed `is_completed` (`progress >= segments`).
- `PATCH /api/v1/clocks/{id}` — GM only. Update `name`, `notes`, `segments`. Cannot change association. Cannot change progress (via GM actions in Phase 4). Returns 200.
- `DELETE /api/v1/clocks/{id}` — GM only. Soft delete. Returns 204.
- Association is fixed at creation — PATCH rejects `associated_type`/`associated_id`.
- `is_completed` is computed on read, not stored.

### Story 2.2.2 — Story CRUD + Owners

**Files to create**:
- `src/wizards_engine/api/routes/stories.py` — story endpoints
- `src/wizards_engine/schemas/story.py` — request/response Pydantic models
- `src/wizards_engine/services/story.py` — story service layer
- `tests/test_stories.py`

**Spec refs**: [game-objects.md](../domains/game-objects.md) (Story CRUD, owners, mixed owner types, status), [data-model.md](../architecture/data-model.md) (stories, story_owners tables)

**Acceptance criteria**:
- `POST /api/v1/stories` — GM only. Accepts `{name, summary?, status?, parent_id?, tags?}`. Status defaults to `active`. Returns 201.
- `GET /api/v1/stories` — list with filters: `?status=active|completed|abandoned`, `?tag=<string>`, `?owner=<type>:<id>` (e.g., `?owner=character:01H...`), `?include_deleted=true`. ULID pagination.
- `GET /api/v1/stories/{id}` — detail with owners list and entries (inline). Entries sorted by creation time.
- `PATCH /api/v1/stories/{id}` — GM only. Update `name`, `summary`, `status`, `tags`, `visibility_level`, `visibility_overrides`. Status can be set to any valid value freely. Returns 200.
- `DELETE /api/v1/stories/{id}` — GM only. Soft delete. Returns 204.
- `POST /api/v1/stories/{id}/owners` — GM only. Body: `{type, id}` where type is `character`, `group`, or `location`. Returns 201. Validates referenced object exists.
- `DELETE /api/v1/stories/{id}/owners/{type}/{owner_id}` — GM only. Returns 204.
- Mixed owner types accepted (e.g., a Character and a Group on the same Story).

### Story 2.2.3 — Story Entries

**Files to create**:
- Story entry endpoints added to `src/wizards_engine/api/routes/stories.py`
- `tests/test_story_entries.py`

**Spec refs**: [game-objects.md](../domains/game-objects.md) (story entries, see=write), [data-model.md](../architecture/data-model.md) (story_entries table)

**Acceptance criteria**:
- `POST /api/v1/stories/{id}/entries` — any authenticated user. Body: `{text, character_id?, game_object_refs?}`. Sets `author_id` from authenticated user. Auto-captures `session_id` from active session (if any). Returns 201.
- `PATCH /api/v1/stories/{id}/entries/{entry_id}` — update `text`. Players can edit their own entries only. GM can edit any. Returns 200. Sets `updated_by`.
- `DELETE /api/v1/stories/{id}/entries/{entry_id}` — soft delete. Players can delete their own. GM can delete any. Sets `deleted_by`. Returns 204.
- Entries returned inline on story detail (`GET /stories/{id}`), excluding soft-deleted entries by default.
- Soft-deleted entries hidden from detail view.

**Note**: Story visibility filtering (see=write enforcement) is deferred to Epic 4.4 when the visibility model is implemented. For now, any authenticated user can access story entries.

### Story 2.2.4 — Session CRUD (Draft Only)

**Files to create**:
- `src/wizards_engine/api/routes/sessions.py` — session endpoints
- `src/wizards_engine/schemas/session.py` — request/response Pydantic models
- `src/wizards_engine/services/session.py` — session service layer
- `tests/test_sessions.py`

**Spec refs**: [downtime.md](../domains/downtime.md) (session lifecycle, Time Now validation), [game-objects.md](../domains/game-objects.md) (session CRUD, draft delete)

**Acceptance criteria**:
- `POST /api/v1/sessions` — GM only. Accepts `{time_now?, date?, summary?, notes?}`. Creates session with `status = "draft"`. Returns 201.
- `GET /api/v1/sessions` — list all sessions. ULID pagination.
- `GET /api/v1/sessions/{id}` — detail with participants list.
- `PATCH /api/v1/sessions/{id}` — GM only. Update `time_now`, `date`, `summary`, `notes`. Only allowed when status is `draft` or `active`. Returns 200. Returns 400 for ended sessions.
- `DELETE /api/v1/sessions/{id}` — GM only. Hard delete (not soft). Only allowed when `status = "draft"`. Returns 204. Returns 400 for active or ended sessions.
- Time Now validation: `time_now` must be >= the most recent ended session's `time_now` (if any). First session has no constraint.

### Story 2.2.5 — Session Participants

**Files to create**:
- Session participant endpoints added to `src/wizards_engine/api/routes/sessions.py`
- `tests/test_session_participants.py`

**Spec refs**: [downtime.md](../domains/downtime.md) (session participants, self-registration, contribution flag)

**Acceptance criteria**:
- `POST /api/v1/sessions/{id}/participants` — player or GM. Body: `{character_id, additional_contribution?}`. `additional_contribution` defaults to false. Player must own the `character_id` (unless GM). Returns 201.
- `DELETE /api/v1/sessions/{id}/participants/{player_id}` — player self-remove or GM. Returns 204. No resource clawback for active sessions.
- `PATCH /api/v1/sessions/{id}/participants/{player_id}` — update `additional_contribution`. Only allowed when session is in `draft` status. Returns 200. Returns 400 for active/ended sessions.
- Validates that referenced character exists and is a full character.
- Prevents duplicate registration (same character twice in one session).

---

## Notes

- Session Start/End lifecycle transitions are deferred to Epic 5.1
- Story visibility filtering is deferred to Epic 4.4
- Clock progress changes are via GM actions (Phase 4), not PATCH
- Session CRUD at this phase only handles Draft lifecycle — no Start/End transitions

## Implementation Notes (verified 2026-03-16)

**Story 2.2.1 — Clock CRUD**

The standalone `POST /clocks` route validates that the referenced Game Object exists AND is not soft-deleted when `associated_type`/`associated_id` are provided. The spec states "association fixed at creation" but does not explicitly require the target to be non-deleted. The `POST /groups/{id}/clocks` sugar route also rejects soft-deleted groups with 404.

**Story 2.2.2 — Story CRUD + Owners**

Invalid `parent_id` on `POST /stories` returns 422 (not 404 as the docstring draft suggests). This is consistent with the `POST /locations` pattern for `parent_id` validation. Both treat a missing parent as a field validation error, not a resource-not-found error.

**Story 2.2.5 — Session Participants**

The participant URL path uses `character_id` as the path parameter, not `player_id` as the spec acceptance criteria states. All three participant endpoints follow the pattern:

```
POST   /sessions/{id}/participants
DELETE /sessions/{id}/participants/{character_id}
PATCH  /sessions/{id}/participants/{character_id}
```

The spec acceptance criteria reference `{player_id}` in the DELETE and PATCH URLs — the implementation correctly uses `{character_id}` throughout, which is consistent with the request body field (`character_id`) and with how participants are identified everywhere else in the system. The spec wording should be treated as an error; `character_id` is the correct identifier.
