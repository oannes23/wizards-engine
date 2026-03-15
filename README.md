# Wizards Engine

A backend state tracker for a single narrative-heavy, low-crunch tabletop RPG campaign. Tracks character sheets, game world state, and provides a proposal workflow for player actions. API-first REST backend for a small fixed group (4-6 players + 1 GM).

**Not** a dice roller or virtual tabletop — all rolling happens at the physical table. The system tracks the mechanical consequences.

## Core Design

- **Mutable state + append-only event log** — game objects are updated directly; events record the history
- **No DSL** — all game logic is hardcoded in Python, not configurable via rules files
- **Proposal workflow** — players describe actions, the system computes effects, the GM approves or rejects
- **Bond graph** — relationships between characters, groups, and locations drive both information visibility and narrative presence

## What It Tracks

- **Characters** (PCs and NPCs) — meters (Stress, Free Time, Plot, Gnosis), 8 skills, 5 magic stats, traits, bonds, magic effects
- **Game Objects** — Characters, Groups (orgs/factions), Locations (nestable hierarchy)
- **Proposals** — 11 action types: 3 session actions, 7 downtime actions, 1 system-generated
- **Events** — append-only log with 7-level bond-distance visibility filtering
- **Sessions** — lifecycle (Draft -> Active -> Ended), resource distribution, clock tracking

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11+ |
| Framework | FastAPI |
| Database | SQLite |
| ORM | SQLAlchemy |
| Migrations | Alembic |
| Validation | Pydantic |
| IDs | ULIDs |
| Testing | pytest |

## Project Status

**Current phase: Specification complete, implementation not started.**

All domain specs are finalized. The implementation is planned as 5 API phases (13 epics, 46 stories) plus a future web UI phase. See [`spec/implementation/README.md`](spec/implementation/README.md) for the full breakdown.

## Repository Structure

```
wizards-engine/
├── spec/                        # Specifications (structured for LLM consumption)
│   ├── MASTER.md                # Central index and status tracker
│   ├── glossary.md              # Canonical term definitions
│   ├── architecture/            # System-level design docs
│   │   ├── overview.md          # System context, tech stack, deployment
│   │   ├── api-conventions.md   # Response shapes, errors, pagination
│   │   ├── data-model.md        # All 18 tables, columns, relationships
│   │   └── mvp-scope.md         # Scope decisions, 6-phase build order
│   ├── domains/                 # Feature area specifications
│   │   ├── game-objects.md      # Characters, Groups, Locations, Clocks, Stories, Sessions
│   │   ├── character-core.md    # Character sheet, meters, skills, magic stats
│   │   ├── traits.md            # Core/Role traits, Group/Location traits
│   │   ├── bonds.md             # Bond graph, PC mechanics, presence
│   │   ├── magic-system.md      # Gnosis, sacrifice, Magic/Charge Actions, effects
│   │   ├── actions.md           # Unified action system, proposals, GM actions
│   │   ├── downtime.md          # Session lifecycle, FT/Plot distribution
│   │   ├── events.md            # Event log, visibility, meter boundaries
│   │   ├── feed.md              # Unified feed, story visibility, starring
│   │   └── auth.md              # Magic link auth, invites, permissions
│   └── implementation/          # Epic/Story breakdown for building
├── src/                         # Source code (future)
└── .claude/                     # Claude Code project config
```

## License

Private project — not open source.
