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
| **5.1** — Session Lifecycle | [phase5-session-lifecycle.md](phase5-session-lifecycle.md) | 5 | Phase 4 | Phase 5.5 |

**Parallelism**: Sequential — tightly coupled stories.

---

## Phase 5.5: API Additions (Pre-UI Backend Work)

| Epic | File | Stories | Depends On | Blocks |
|------|------|---------|------------|--------|
| **5.5** — Pre-UI API Additions | [phase55-api-additions.md](phase55-api-additions.md) | 6 | Phases 3–5 | Phase 6 |

Backend API additions required before the Web UI. Six independent stories: two new direct player actions (`recharge_trait`, `maintain_bond`), one schema change (nullable narrative), and three new endpoints (GM dashboard, batch actions, characters summary). All follow established patterns from Phases 1–5.

**Parallelism**: All 6 stories are independent — max parallelism = 6.

**Per-story dependency arrows**:
- 5.5.1 Recharge Trait → blocks 6.2.3 (direct action buttons)
- 5.5.2 Maintain Bond → blocks 6.2.3 (direct action buttons)
- 5.5.3 Nullable Narrative → blocks 6.3.1 (proposal submission)
- 5.5.4 GM Dashboard → blocks 6.5.1 (GM dashboard view)
- 5.5.5 Batch Actions → blocks 6.5.4 (GM direct actions form)
- 5.5.6 Characters Summary → blocks 6.5.1 (GM dashboard view)

---

## Phase 6: Web UI

| Epic | File | Stories | Depends On | Blocks |
|------|------|---------|------------|--------|
| **6.1** — SPA Foundation & Auth | [phase6-spa-foundation.md](phase6-spa-foundation.md) | 5 | Phase 5 | 6.2–6.6 |
| **6.2** — Player Character & Direct Actions | [phase6-player-character.md](phase6-player-character.md) | 4 | 6.1, 5.5.1, 5.5.2 | 6.6 |
| **6.3** — Proposal System | [phase6-proposal-system.md](phase6-proposal-system.md) | 5 | 6.1, 5.5.3 | 6.5, 6.6 |
| **6.4** — World Browser & Feed | [phase6-world-browser.md](phase6-world-browser.md) | 4 | 6.1 | 6.6 |
| **6.5** — GM Tools & Session Management | [phase6-gm-tools.md](phase6-gm-tools.md) | 5 | 6.1, 6.3, 5.5.4–6 | 6.6 |
| **6.6** — Polish & Integration | [phase6-polish.md](phase6-polish.md) | 3 | 6.2–6.5 | — |

**Parallelism**: Epics 6.2, 6.3, and 6.4 can run in parallel after 6.1 completes (max 3 parallel tracks). 6.5 waits for 6.3 (GM queue component). 6.6 waits for all.

**Critical path**: 6.1 → 6.3 → 6.5 → 6.6

---

## Phase 7: Campaign Data

| Epic | File | Stories | Depends On | Blocks |
|------|------|---------|------------|--------|
| **7.1** — Campaign Import/Export & Notes Ingestion | [phase7-campaign-import-export.md](phase7-campaign-import-export.md) | 7 | Phases 1–6 | — |

YAML-based campaign import/export system (CLI-only tool, no new API endpoints). Converts game notes into importable YAML data files for campaign portability.

**Parallelism**: 7.1.1 → 7.1.2 → {7.1.3, 7.1.4} parallel → 7.1.5. Story 7.1.6 starts after 7.1.1. Story 7.1.7 after 7.1.5.

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

Phase 5.5 (all 6 stories parallel)
  5.5.1 Recharge Trait ─────────────────────────> 6.2 (direct action buttons)
  5.5.2 Maintain Bond  ─────────────────────────> 6.2 (direct action buttons)
  5.5.3 Nullable Narrative ─────────────────────> 6.3 (proposal submission)
  5.5.4 GM Dashboard  ──────────────────────────> 6.5 (GM dashboard view)
  5.5.5 Batch Actions  ─────────────────────────> 6.5 (GM direct actions form)
  5.5.6 Char Summary  ──────────────────────────> 6.5 (GM dashboard view)

Phase 6 (3 parallel tracks, then merge)
  6.1 SPA Foundation ──┬──> 6.2 Player Character ─────────┐
                       ├──> 6.3 Proposals ─────────────────┤
                       ├──> 6.4 World & Feed ──────────────┤
                       │                                    │
                       └──> 6.5 GM Tools <── 5.5.4/5/6 ───┤
                              │                             │
                       ┌──────┘                             │
                       ▼                                    │
                    6.6 Polish <────────────────────────────┘

Phase 7 (sequential, depends on all prior phases)
  7.1 Campaign Import/Export & Notes Ingestion
    7.1.1 Schemas ──> 7.1.2 Resolver ──┬──> 7.1.3 Exporter ──┐
                                        └──> 7.1.4 Importer ──┼──> 7.1.5 CLI + Round-Trip
                                                               │
    7.1.1 Schemas ──────────────────────> 7.1.6 Notes Data ───┘
    7.1.5 CLI ──> 7.1.7 Documentation
```

## Summary

| Metric | Count |
|--------|-------|
| Phases | 6 complete (1–6) + Phase 7 |
| Epics | 20 complete + 1 new (campaign tooling) |
| Stories | 52 complete + 8 new (campaign tooling) |
| Max parallel tracks | 2 (7.1.3 + 7.1.4 after 7.1.2) |
| Estimated new backend tests | ~120 (across Phase 7) |

---

## Status Tracking

| Epic | Status | Progress |
|------|--------|----------|
| 1.1 — Scaffolding & DB | 🟢 Complete | 4/4 |
| 1.2 — Auth & API Skeleton | 🟢 Complete | 6/6 |
| 2.1 — Game Object CRUD | 🟢 Complete | 4/4 |
| 2.2 — System Entities | 🟢 Complete | 5/5 |
| 2.3 — Bonds & Presence | 🟢 Complete | 3/3 |
| 3.1 — Character Sheet Model | 🟢 Complete | 4/4 |
| 3.2 — Traits & Magic Effects | 🟢 Complete | 3/3 |
| 3.3 — PC Bond Mechanics | 🟢 Complete | 2/2 |
| 4.1 — Event Log | 🟢 Complete | 3/3 |
| 4.2 — GM Actions | 🟢 Complete | 3/3 |
| 4.3 — Proposal Workflow | 🟢 Complete | 5/5 |
| 4.4 — Feed System | 🟢 Complete | 4/4 |
| 5.1 — Session Lifecycle | 🟢 Complete | 5/5 |
| 5.5 — Pre-UI API Additions | 🟢 Complete | 6/6 |
| 6.1 — SPA Foundation & Auth | 🟢 Complete | 5/5 |
| 6.2 — Player Character & Direct Actions | 🟢 Complete | 4/4 |
| 6.3 — Proposal System | 🟢 Complete | 5/5 |
| 6.4 — World Browser & Feed | 🟢 Complete | 4/4 |
| 6.5 — GM Tools & Session Management | 🟢 Complete | 5/5 |
| 6.6 — Polish & Integration | 🟢 Complete | 3/3 |
| 7.1 — Campaign Import/Export & Notes Ingestion | 🟢 Complete | 8/8 |
| 8.4 — Game Objects Browser Redesign | 🟡 In progress | 3/4 |
| 8.6 — Game Object CRUD Forms | 🟡 In progress | 2/3 |
