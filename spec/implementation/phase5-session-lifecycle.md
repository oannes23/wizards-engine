# Epic 5.1 — Session Lifecycle

**Phase**: 5 — Sessions
**Depends on**: Phase 4 complete (actions and events work)
**Blocks**: Phase 6 (Web UI)
**Parallel with**: None (tightly coupled, sequential stories)

---

## Overview

Implement session lifecycle transitions (Start, End), resource distribution (FT via Time Now delta, Plot via participation), late joins, Plot clamping, Find Time direct action, and session timeline view. This Epic completes the API surface.

---

## Stories

### Story 5.1.1 — Session Start

**Files to modify**:
- `src/wizards_engine/api/routes/sessions.py` — add `POST /sessions/{id}/start`
- `src/wizards_engine/services/session.py` — start logic, FT/Plot distribution
- `tests/test_session_start.py`

**Spec refs**: [downtime.md](../domains/downtime.md) (session start, FT distribution, Plot income, one Active at a time), [events.md](../domains/events.md) (session.started, session.ft_distributed, session.plot_distributed — 3 separate events)

**Acceptance criteria**:
- `POST /api/v1/sessions/{id}/start` — GM only.
- Validates session is in `draft` status. Returns 400 otherwise.
- Enforces one Active session at a time. Returns 409 if another session is already Active.
- Transitions status to `active`
- For each registered participant:
  - **FT distribution**: `ft_gained = session.time_now - character.last_session_time_now`. Add to character's `free_time`, capped at 20. Update `character.last_session_time_now` to `session.time_now`.
  - **Plot distribution**: +1 Plot (or +2 if `additional_contribution = true`). Plot can exceed 5 (overflow allowed).
- Locks all contribution flags (no further PATCH on participants)
- Creates **3 separate events** in one transaction:
  1. `session.started` — visibility: `global`. Changes: session status draft→active.
  2. `session.ft_distributed` — visibility: `silent`. Changes: all character FT/last_session_time_now changes.
  3. `session.plot_distributed` — visibility: `silent`. Changes: all character Plot changes.
- All 3 events tagged with the session's ID

### Story 5.1.2 — Late Joins

**Files to modify**:
- `src/wizards_engine/services/session.py` — late join distribution
- `tests/test_session_late_join.py`

**Spec refs**: [downtime.md](../domains/downtime.md) (late joins, immediate distribution)

**Acceptance criteria**:
- Adding a participant to an Active session (via `POST /sessions/{id}/participants`) triggers immediate FT + Plot distribution for that participant only
- Same formula: FT via Time Now delta (capped at 20), Plot +1/+2
- Contribution flag locks immediately on late join
- Distribution for the late joiner only — does not re-distribute to existing participants
- Event created for the late join distribution

### Story 5.1.3 — Session End

**Files to modify**:
- `src/wizards_engine/api/routes/sessions.py` — add `POST /sessions/{id}/end`
- `src/wizards_engine/services/session.py` — end logic, Plot clamping
- `tests/test_session_end.py`

**Spec refs**: [downtime.md](../domains/downtime.md) (session end, Plot clamping, forward-only lifecycle)

**Acceptance criteria**:
- `POST /api/v1/sessions/{id}/end` — GM only. No request body.
- Validates session is in `active` status. Returns 400 otherwise.
- Transitions status to `ended`
- Clamps all participants' Plot to 5 (excess lost)
- Creates `session.ended` event — visibility: `global`. Changes: session status active→ended, any Plot clamp changes.
- Ended sessions are read-only: PATCH returns 400, participant changes rejected

### Story 5.1.4 — Find Time

**Files to create**:
- `src/wizards_engine/api/routes/find_time.py` — `POST /characters/{id}/find-time`
- `tests/test_find_time.py`

**Spec refs**: [downtime.md](../domains/downtime.md) (Find Time, 3 Plot → 1 FT), [character-core.md](../domains/character-core.md) (Plot spending)

**Acceptance criteria**:
- `POST /api/v1/characters/{id}/find-time` — player direct action. Empty request body.
- Player must own the character
- Validates Plot >= 3. Returns 409 with `{error: {code: "insufficient_plot"}}` if not.
- Validates FT < 20. Returns 409 with `{error: {code: "free_time_at_cap"}}` if at cap.
- Converts: -3 Plot, +1 FT
- Creates `player.find_time` event — visibility: `private`. Changes: plot and free_time deltas.
- Returns 200 with updated character meters

### Story 5.1.5 — Session Timeline

**Files to modify**:
- `src/wizards_engine/api/routes/sessions.py` — add `GET /sessions/{id}/timeline`
- `tests/test_session_timeline.py`

**Spec refs**: [game-objects.md](../domains/game-objects.md) (session timeline)

**Acceptance criteria**:
- `GET /api/v1/sessions/{id}/timeline` — returns events filtered by `session_id`
- ULID cursor pagination
- Visibility-filtered per authenticated user (same as events API)
- Returns events only (no story entries — this is the events timeline, not a feed)

---

## Notes

- Clock adjustments during Active sessions are done via `POST /gm/actions` with `modify_clock` (already implemented in Epic 4.2)
- Session Start is a composite action producing 3 events — an exception to the one-event-per-action rule
- The forward-only lifecycle means no undo for Start or End — GM corrects via direct actions
