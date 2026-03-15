# Implementation Specs — Epic Index

This directory contains one specification file per Epic, organized by the 6-phase build order defined in [mvp-scope.md](../architecture/mvp-scope.md).

---

## Phase 1: Foundation

| Epic | File | Stories | Depends On | Blocks |
|------|------|---------|------------|--------|
| **1.1** — Project Scaffolding & Database | [phase1-scaffolding-db.md](phase1-scaffolding-db.md) | 4 | — | 1.2, all |
| **1.2** — Auth & API Skeleton | [phase1-auth-api-skeleton.md](phase1-auth-api-skeleton.md) | 6 | 1.1 | Phase 2+ |

**Parallelism**: Sequential — 1.1 must complete before 1.2.

---

## Phase 2: World

| Epic | File | Stories | Depends On | Blocks |
|------|------|---------|------------|--------|
| **2.1** — Game Object CRUD | [phase2-game-object-crud.md](phase2-game-object-crud.md) | 4 | 1.2 | 2.3 |
| **2.2** — System Entities | [phase2-system-entities.md](phase2-system-entities.md) | 5 | 1.2 | 2.3 |
| **2.3** — Bonds & Presence | [phase2-bonds-presence.md](phase2-bonds-presence.md) | 3 | 2.1 + 2.2 | 3.1 |

**Parallelism**: 2.1 and 2.2 can run in parallel. 2.3 waits for both.

---

## Phase 3: Characters

| Epic | File | Stories | Depends On | Blocks |
|------|------|---------|------------|--------|
| **3.1** — Character Sheet Model | [phase3-character-sheet.md](phase3-character-sheet.md) | 4 | 2.3 | 3.2, 3.3 |
| **3.2** — Traits & Magic Effects | [phase3-traits-effects.md](phase3-traits-effects.md) | 3 | 3.1 | 4.2 |
| **3.3** — PC Bond Mechanics | [phase3-pc-bond-mechanics.md](phase3-pc-bond-mechanics.md) | 2 | 2.3 | 4.2 |

**Parallelism**: 3.2 and 3.3 can run in parallel after 3.1 completes.

---

## Phase 4: Actions

| Epic | File | Stories | Depends On | Blocks |
|------|------|---------|------------|--------|
| **4.1** — Event Log | [phase4-event-log.md](phase4-event-log.md) | 3 | Phase 3 | 4.2, 4.3, 4.4 |
| **4.2** — GM Actions | [phase4-gm-actions.md](phase4-gm-actions.md) | 3 | 4.1 | 4.4 |
| **4.3** — Proposal Workflow | [phase4-proposal-workflow.md](phase4-proposal-workflow.md) | 5 | 4.1 | 4.4 |
| **4.4** — Feed System | [phase4-feed-system.md](phase4-feed-system.md) | 4 | 4.2 + 4.3 | — |

**Parallelism**: 4.2 and 4.3 can run in parallel after 4.1. 4.4 waits for both.

---

## Phase 5: Sessions

| Epic | File | Stories | Depends On | Blocks |
|------|------|---------|------------|--------|
| **5.1** — Session Lifecycle | [phase5-session-lifecycle.md](phase5-session-lifecycle.md) | 5 | Phase 4 | Phase 6 |

**Parallelism**: Sequential — tightly coupled stories.

---

## Phase 6: Web UI

Not broken down here. UI epics will be planned separately once the API is complete.

---

## Dependency Graph

```
Phase 1 (sequential)
  1.1 Scaffolding + DB ──> 1.2 Auth + API Skeleton

Phase 2 (2 parallel tracks, then merge)
  2.1 Game Object CRUD ──────┐
                              ├──> 2.3 Bonds + Presence
  2.2 System Entities  ──────┘

Phase 3 (1 then 2 parallel)
  3.1 Character Sheet ──┬──> 3.2 Traits + Effects
                        └──> 3.3 PC Bond Mechanics

Phase 4 (1 then 2 parallel, then merge)
  4.1 Event Log ──┬──> 4.2 GM Actions    ──┐
                  └──> 4.3 Proposals      ──┼──> 4.4 Feed System
                                            ┘

Phase 5 (sequential)
  5.1 Session Lifecycle
```

## Summary

| Metric | Count |
|--------|-------|
| Phases | 5 (+ Phase 6 UI deferred) |
| Epics | 13 |
| Stories | 46 |
| Max parallel tracks | 2 |

---

## Status Tracking

| Epic | Status |
|------|--------|
| 1.1 — Scaffolding & DB | 🔴 Not started |
| 1.2 — Auth & API Skeleton | 🔴 Not started |
| 2.1 — Game Object CRUD | 🔴 Not started |
| 2.2 — System Entities | 🔴 Not started |
| 2.3 — Bonds & Presence | 🔴 Not started |
| 3.1 — Character Sheet Model | 🔴 Not started |
| 3.2 — Traits & Magic Effects | 🔴 Not started |
| 3.3 — PC Bond Mechanics | 🔴 Not started |
| 4.1 — Event Log | 🔴 Not started |
| 4.2 — GM Actions | 🔴 Not started |
| 4.3 — Proposal Workflow | 🔴 Not started |
| 4.4 — Feed System | 🔴 Not started |
| 5.1 — Session Lifecycle | 🔴 Not started |
