# Epic 4.1 — Event Log

**Phase**: 4 — Actions
**Depends on**: Phase 3 complete (characters with full mechanical depth)
**Blocks**: Epic 4.2 (GM Actions), Epic 4.3 (Proposal Workflow), Epic 4.4 (Feed System)
**Parallel with**: None (blocks 4.2 and 4.3)

---

## Overview

Implement the event creation service, the events API (read-only with filtering), and the bond-distance visibility filtering. Events are the append-only audit trail for all state changes. This Epic establishes the event infrastructure that all subsequent action-producing code depends on.

---

## Stories

| Story | Status | Completed |
|-------|--------|-----------|
| 4.1.1 — Event Creation Service | 🟢 Complete | 2026-03-16 |
| 4.1.2 — Events API | 🟢 Complete | 2026-03-16 |
| 4.1.3 — Bond-Distance Visibility Filtering | 🟢 Complete | 2026-03-16 |

### Story 4.1.1 — Event Creation Service

**Files to create**:
- `src/wizards_engine/services/event.py` — internal event creation service
- `tests/test_event_service.py`

**Spec refs**: [events.md](../domains/events.md) (event schema, changes field, operation types, compound changes, targets, session auto-capture, rider events)

**Acceptance criteria**:
- Internal service (no direct API creation) for creating events with:
  - `type`: convention-based `{domain}.{action}` string
  - `actor_type`: `player`, `gm`, or `system`
  - `actor_id`: FK to users (null for system)
  - `changes`: fully-qualified keys `{type}.{id}.{field}` with `{op, before, after, clamped?}`. Op is one of `field.set`, `meter.delta`, `meter.set`
  - `created_objects`: list of `{type, id}` for newly created objects
  - `deleted_objects`: list of `{type, id}` for soft-deleted objects
  - `narrative`: optional text
  - `visibility`: one of 7 levels (`silent`, `gm_only`, `private`, `bonded`, `familiar`, `public`, `global`)
  - `targets`: list of `{target_type, target_id, is_primary}` — written to `event_targets` table
  - `proposal_id`: optional back-ref
  - `parent_event_id`: optional (for rider events)
  - `session_id`: optional (auto-captured from Active session if not specified)
  - `metadata`: optional freeform JSON
- Session auto-capture: if an Active session exists and no `session_id` provided, auto-tag with that session's ID
- Rider events inherit `session_id` from parent event
- Event ID is a ULID (time-sortable)
- Events are immutable after creation (except visibility)
- Service returns the created Event with its targets

### Story 4.1.2 — Events API

**Files to create**:
- `src/wizards_engine/api/routes/events.py` — events endpoints
- `src/wizards_engine/schemas/event.py` — response Pydantic models
- `tests/test_events_api.py`

**Spec refs**: [events.md](../domains/events.md) (events API, ULID pagination, filtering, GM override), [api-conventions.md](../architecture/api-conventions.md) (pagination)

**Acceptance criteria**:
- `GET /api/v1/events` — list with ULID cursor pagination (`?after=<ulid>&limit=N`, default 50, max 100). Response: `{items, next_cursor, has_more}`.
- Filters (all optional, combined with AND):
  - `?type=<string>` — event type, supports prefix matching (e.g., `?type=character.*` → all character events)
  - `?target_type=<string>` — filter by target Game Object type
  - `?target_id=<string>` — filter by specific target ID
  - `?session_id=<ulid>` — filter by session
  - `?actor_type=<string>` — filter by actor type (player, gm, system)
  - `?proposal_id=<ulid>` — filter by proposal
  - `?since=<datetime>` — items after this timestamp (inclusive)
  - `?until=<datetime>` — items before this timestamp (inclusive)
- `GET /api/v1/events/{id}` — single event detail (visibility check applied)
- `PATCH /api/v1/events/{id}/visibility` — GM only. Body: `{visibility}`. Changes the event's visibility level. Returns 200.
- Results visibility-filtered per authenticated user (see Story 4.1.3)

### Story 4.1.3 — Bond-Distance Visibility Filtering

**Files to create**:
- `src/wizards_engine/services/visibility.py` — unified visibility filtering
- `tests/test_visibility.py`

**Spec refs**: [feed.md](../domains/feed.md) (unified visibility model, 7 levels, bond-graph traversal, private owner determination), [events.md](../domains/events.md) (visibility levels, GM sees all)

**Acceptance criteria**:
- Implements the unified 7-level visibility model for event reads:
  - `silent`: GM only (via silent feed endpoint — excluded from normal queries)
  - `gm_only`: GM only (appears in GM's normal feed)
  - `private`: union of actor's character + primary target's owner (if PC) + GM. If neither actor nor primary target is a PC, GM-only.
  - `bonded`: PCs with a direct bond (1-hop) to any event target + GM
  - `familiar`: PCs within 2-hop Character-intermediary traversal of any event target + GM
  - `public`: PCs within 3-hop Character-intermediary traversal of any event target + GM
  - `global`: all players + GM
- Reuses the Character-intermediary traversal algorithm from Epic 2.3 (presence service)
- GM sees all events (except `silent` — those only appear in the silent feed)
- Visibility filter applied on all event reads (list and detail)
- Private visibility uses union rule: both actor and primary target owner see private events

---

## Notes

- Events are never created via the API — always side-effects of state changes
- The visibility service built here is reused by the Feed system (Epic 4.4) for Story entry visibility
- Session auto-capture requires knowing the current Active session — query `sessions` table for `status = "active"`
