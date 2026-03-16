# Epic 4.4 — Feed System

**Phase**: 4 — Actions
**Depends on**: Epic 4.2 (GM Actions) + Epic 4.3 (Proposal Workflow)
**Blocks**: None (last Epic in Phase 4)
**Parallel with**: None

---

## Overview

Implement the unified feed — merging events and story entries into a single visibility-filtered chronological stream. Includes per-Game Object feeds, personal feed, starred feed, GM silent feed, the starring API, and Story visibility enforcement.

---

## Stories

| Story | Status | Completed |
|-------|--------|-----------|
| 4.4.1 — Per-Game Object Feed | 🔴 Not started | — |
| 4.4.2 — Personal + Starred + Silent Feeds | 🔴 Not started | — |
| 4.4.3 — Starring API | 🔴 Not started | — |
| 4.4.4 — Story Visibility | 🔴 Not started | — |

### Story 4.4.1 — Per-Game Object Feed

**Files to create**:
- `src/wizards_engine/api/routes/feed.py` — feed endpoints
- `src/wizards_engine/services/feed.py` — feed query and merge logic
- `src/wizards_engine/schemas/feed.py` — feed item response models (discriminated union)
- `tests/test_feed.py`

**Spec refs**: [feed.md](../domains/feed.md) (per-Game Object feed, feed item shape, discriminated union, pagination, filtering)

**Acceptance criteria**:
- `GET /api/v1/characters/{id}/feed` — Character feed
- `GET /api/v1/groups/{id}/feed` — Group feed
- `GET /api/v1/locations/{id}/feed` — Location feed
- All three return a merged chronological stream of:
  - Events where the Game Object is a target (via `event_targets`)
  - Story entries on Stories owned by the Game Object (via `story_owners`)
  - Story entries with `game_object_refs` including the Game Object
- Feed items use discriminated union format:
  - Common fields: `id`, `type` (`event` or `story_entry`), `timestamp`, `narrative`, `visibility`, `targets`, `is_own`
  - Event-specific: `event_type`, `actor_type`, `actor_id`, `changes`, `created_objects`, `deleted_objects`, `proposal_id`, `parent_event_id`, `session_id`, `metadata`
  - Story entry-specific: `story_id`, `story_name`, `entry_text`, `author_id`
- ULID cursor pagination (`?after=<ulid>&limit=N`, default 50, max 100)
- All feed filters supported: `?type=`, `?target_type=`, `?target_id=`, `?actor_type=`, `?session_id=`, `?since=`, `?until=`
- Event-only filters (`type`, `actor_type`) exclude story entries when used
- Visibility-filtered per authenticated user (using visibility service from Epic 4.1)
- Story entry targets = union of Story owners + entry's `game_object_refs`

### Story 4.4.2 — Personal + Starred + Silent Feeds

**Files to modify**:
- `src/wizards_engine/api/routes/feed.py` — add personal/starred/silent endpoints
- `src/wizards_engine/services/feed.py` — scope filtering
- `tests/test_feed_personal.py`

**Spec refs**: [feed.md](../domains/feed.md) (complete personal feed, starred feed, GM silent feed)

**Acceptance criteria**:
- `GET /api/v1/me/feed` — complete personal feed. Returns all feed items visible to the authenticated player across all their bonds. `is_own` flag set correctly (true when player is the event actor).
- `GET /api/v1/me/feed/starred` — same as personal feed, filtered to only Game Objects the player has starred.
- `GET /api/v1/me/feed/silent` — GM only. Returns all `silent`-level events. Returns 403 for non-GM.
- All three endpoints support full filter set and ULID pagination
- Silent feed excludes non-silent items
- Personal feed excludes `silent` items (even for GM — use silent feed for those)

### Story 4.4.3 — Starring API

**Files to create**:
- `src/wizards_engine/api/routes/starred.py` — starring endpoints
- `src/wizards_engine/schemas/starred.py` — request/response models
- `tests/test_starring.py`

**Spec refs**: [feed.md](../domains/feed.md) (starring API), [auth.md](../domains/auth.md) (starring), [data-model.md](../architecture/data-model.md) (starred_objects table)

**Acceptance criteria**:
- `GET /api/v1/me/starred` — list starred Game Objects. Returns `[{type, id, name}]`.
- `POST /api/v1/me/starred` — star a Game Object. Body: `{type, id}`. Validates object exists. Returns 201. Idempotent (starring already-starred is a no-op 200).
- `DELETE /api/v1/me/starred/{type}/{id}` — unstar. Returns 204.
- Starred feed (Story 4.4.2) uses this data to filter feed items

### Story 4.4.4 — Story Visibility

**Files to modify**:
- `src/wizards_engine/services/visibility.py` — add Story visibility logic
- `src/wizards_engine/api/routes/stories.py` — enforce visibility on story list/detail/entries
- `tests/test_story_visibility.py`

**Spec refs**: [feed.md](../domains/feed.md) (Story visibility, mixed owners, union rule, GM override, see=write)

**Acceptance criteria**:
- Story visibility computed from owners using the unified visibility model:
  - Default level: `familiar` (or Story's `visibility_level` if set by GM)
  - PC-owned: that PC + GM can see
  - NPC/Group/Location-owned: visible at the Story's level via bond-graph traversal from owners
  - Mixed owners: union of all owner rules
  - GM `visibility_overrides`: list of user IDs granted access regardless of bond graph
- `GET /api/v1/stories` — list is visibility-filtered per authenticated player. GM sees all.
- `GET /api/v1/stories/{id}` — returns 404 if player doesn't have visibility
- Story entry creation (`POST /stories/{id}/entries`) — enforces see=write: only users who can see the Story can add entries. Returns 404 if not visible.
- Story entries in feeds are visibility-filtered using the parent Story's visibility rules

---

## Notes

- The feed is a query pattern, not a stored entity — no new tables
- Feed query performance may need optimization for the merged event + story entry query. Start simple, optimize if needed.
- Story visibility enforcement should be applied retroactively to Epic 2.2's story endpoints
