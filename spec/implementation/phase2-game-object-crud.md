# Epic 2.1 — Game Object CRUD (Characters, Groups, Locations)

**Phase**: 2 — World
**Depends on**: Epic 1.2 (Auth & API Skeleton)
**Blocks**: Epic 2.3 (Bonds & Presence) — partially
**Parallel with**: Epic 2.2 (System Entities) — once Stories 1–2 establish the CRUD pattern

---

## Overview

Implement standard CRUD endpoints for the three Game Object types (Characters, Groups, Locations) plus the player roster. Establishes the reusable CRUD pattern (list with filters, detail, create, update, soft delete) for the rest of the project.

---

## Stories

### Story 2.1.1 — NPC Character CRUD

**Files to create**:
- `src/wizards_engine/api/routes/characters.py` — character endpoints
- `src/wizards_engine/schemas/character.py` — request/response Pydantic models
- `src/wizards_engine/services/character.py` — character service layer
- `tests/test_characters.py`

**Spec refs**: [character-core.md](../domains/character-core.md) (NPC creation, detail levels), [game-objects.md](../domains/game-objects.md) (character CRUD), [api-conventions.md](../architecture/api-conventions.md) (pagination, soft delete)

**Acceptance criteria**:
- `POST /api/v1/characters` — GM only. Accepts `{name}` (required), `{description?, notes?, attributes?}` (optional). Creates a `simplified` character. Returns 201 with full resource.
- `GET /api/v1/characters` — list with filters:
  - `?detail_level=full|simplified`
  - `?has_player=true|false` (has a linked User)
  - `?include_deleted=true` (default excludes soft-deleted)
  - `?name=<partial>` (case-insensitive partial match)
  - ULID cursor pagination (`?after=<ulid>&limit=N`)
  - Returns paginated envelope `{items, next_cursor, has_more}`
- `GET /api/v1/characters/{id}` — returns character detail. Accessible for soft-deleted characters (with `is_deleted` visible).
- `PATCH /api/v1/characters/{id}` — update `name`, `description`, `notes`. Owner can edit their own, GM can edit any. Returns 200. Validates non-empty name.
- `DELETE /api/v1/characters/{id}` — GM only. Soft delete (sets `is_deleted = true`). Returns 204.
- Soft-deleted characters hidden from list by default, accessible by direct ID lookup.
- Non-GM users cannot create or delete characters.

### Story 2.1.2 — Group CRUD

**Files to create**:
- `src/wizards_engine/api/routes/groups.py` — group endpoints
- `src/wizards_engine/schemas/group.py` — request/response Pydantic models
- `src/wizards_engine/services/group.py` — group service layer
- `tests/test_groups.py`

**Spec refs**: [game-objects.md](../domains/game-objects.md) (Group CRUD, tier)

**Acceptance criteria**:
- `POST /api/v1/groups` — GM only. Accepts `{name, description?, tier, notes?}`. `tier` is a non-negative integer. Returns 201.
- `GET /api/v1/groups` — list with `?include_deleted=true`. ULID pagination.
- `GET /api/v1/groups/{id}` — detail. Accessible when soft-deleted.
- `PATCH /api/v1/groups/{id}` — GM only. Update `name`, `description`, `notes` only. Tier changes via GM actions (Phase 4). Returns 200.
- `DELETE /api/v1/groups/{id}` — GM only. Soft delete. Returns 204.

### Story 2.1.3 — Location CRUD

**Files to create**:
- `src/wizards_engine/api/routes/locations.py` — location endpoints
- `src/wizards_engine/schemas/location.py` — request/response Pydantic models
- `src/wizards_engine/services/location.py` — location service layer
- `tests/test_locations.py`

**Spec refs**: [game-objects.md](../domains/game-objects.md) (Location CRUD, hierarchy)

**Acceptance criteria**:
- `POST /api/v1/locations` — GM only. Accepts `{name, description?, parent_id?, notes?}`. Validates `parent_id` references an existing location. Returns 201.
- `GET /api/v1/locations` — list with `?parent={id}` (returns direct children only), `?include_deleted=true`. ULID pagination.
- `GET /api/v1/locations/{id}` — detail. Accessible when soft-deleted.
- `PATCH /api/v1/locations/{id}` — GM only. Update `name`, `description`, `notes` only. `parent_id` changes via GM actions (Phase 4). Returns 200.
- `DELETE /api/v1/locations/{id}` — GM only. Soft delete. Returns 204.
- Parent filter returns only direct children (not recursive).

### Story 2.1.4 — Player Roster

**Files to create**:
- `src/wizards_engine/api/routes/players.py` — player roster endpoint
- `src/wizards_engine/schemas/player.py` — response Pydantic models
- `tests/test_players.py`

**Spec refs**: [auth.md](../domains/auth.md) (player roster visibility)

**Acceptance criteria**:
- `GET /api/v1/players` — requires authentication. Returns all users with `display_name`, `role`, `character_id`, `is_active`.
- For GM callers: response includes `login_url` per player (the magic link URL).
- For non-GM callers: `login_url` is omitted from the response.
- Returns all users (GM + players), not paginated (small fixed group).

---

## Notes

- This Epic establishes the CRUD pattern reused by Epic 2.2
- Character detail is simplified at this stage — full sheet (bonds, traits, computed values) comes in Phase 3
- Mechanical field changes (meters, skills, attributes, tier, parent_id) are not exposed via PATCH — those come via GM actions in Phase 4
