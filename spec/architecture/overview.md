# System Overview

**Status**: 🟢 Complete
**Last verified**: —

---

## What This System Does

Wizards Engine is a backend state tracker for a single narrative-heavy, low-crunch tabletop RPG campaign. It tracks character sheets, game world state, and provides a proposal workflow for player actions. Designed for a small fixed group (4–6 players + 1 GM) with a simple mobile-friendly web UI to follow.

This is **not** a dice roller or virtual tabletop — all rolling happens at the physical table.

---

## Core Architectural Principles

### Mutable State + Event Log

- **Decision**: Game state is mutable — when an action is approved, game objects are updated directly. An append-only event log records every state change for history and audit.
- **Rationale**: Simpler than event sourcing and appropriate for a single-game system. State is the source of truth, not the event log. Events are the history.
- **Implications**: No need for event replay to reconstruct state. Undo is possible by applying inverse changes from the event log.

### No DSL or Expression System

- **Decision**: All game logic — schemas, calculations, effect modifiers, computed fields — is hardcoded in Python. No configuration language, no expression evaluator, no YAML-driven schemas.
- **Rationale**: Keeps the system simple and debuggable. This is a single-campaign tool, not a generic RPG engine.
- **Implications**: Changing game rules means changing code. This is acceptable for a single campaign with a developer-GM.

### API-First REST

- **Decision**: API-first REST backend. All endpoints under `/api/v1/` with standard CRUD patterns and action-specific sub-routes.
- **Rationale**: Enables a decoupled web UI and potential future clients (bots, scripts, etc.).
- **Implications**: The web UI is a separate concern that consumes the API.

### Deferred Narrative Resolution

- **Decision**: Game state is intentionally left ambiguous until narratively observed. Rather than tracking precise "current state" for every game object, the system records what is known and defers resolution to the moment it matters in play.
- **Rationale**: Matches how narrative TTRPGs actually work — the GM doesn't decide where an NPC is until a player goes looking for them. Forcing precise state creates busywork and false precision.
- **Implications**: Character presence at Locations is derived via Bond-Distance Presence (computed from the bond graph — 1-hop = commonly present, 2-hop = often present, 3-hop = sometimes present) rather than a pinned position. Group project outcomes follow Deferred Narrative Resolution — clocks track mechanical progress, outcomes are defined retroactively when the clock completes. This principle should guide future design decisions — prefer "known facts + GM resolution" over "precise simulation."

---

## System Context

### Users/Actors

- **GM (Game Master)**: Runs the campaign. Has full read/write access to all game state. Creates and manages game objects (NPCs, Groups, Locations, Stories). Triggers downtime phases. Approves or rejects player proposals. Can directly modify any state without proposals.
- **Players (4–6)**: Each owns one Character (PC). Can read all public game state. Can modify their own character's notes and submit proposals for mechanically significant actions. Can revise rejected proposals.

### External Systems

- None — this is a self-contained application. No external auth providers, no third-party integrations.

---

## Constraints

### Technical Constraints

- Single-game system — not multi-tenant
- Small fixed group — no need for horizontal scaling
- SQLite single-file database — simple deployment, no database server
- Python 3.11+ required

### Business Constraints

- Single campaign — rules are hardcoded, not configurable
- Developer-GM — the GM can modify game logic in code as the campaign evolves
- Trusted small group — simple auth model is sufficient

### Non-Goals

- **Dice rolling** — all rolling happens at the physical table
- **Virtual tabletop** — no maps, tokens, or tactical grid
- **Complex auth** — no OAuth, no external identity providers
- **Multi-campaign support** — one database, one campaign
- **Generic RPG engine** — no DSL, no configurable rule systems
- **Real-time features** — deferred. Polling/manual refresh for MVP. SSE is a possible future addition if players find stale data frustrating. Architecture should not preclude it.

---

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Language | Python 3.11+ | Application logic |
| API Framework | FastAPI | REST API with automatic OpenAPI docs |
| ORM | SQLAlchemy | Database models and queries |
| Validation | Pydantic | Request/response schemas |
| Database | SQLite | Single-file persistence |
| Migrations | Alembic | Schema versioning and migrations |
| Testing | pytest | Unit and integration tests |

---

## Key Architectural Decisions

### Proposal Workflow

- **Decision**: Player actions that change game state go through a proposal system: submit → calculate effects → GM review → approve/reject.
- **Rationale**: Maintains GM authority over the narrative while giving players agency to describe their actions and select mechanical boosts. Keeps the GM as the final arbiter.
- **Implications**: Every mechanically significant player action has a review step. GM actions bypass this entirely. Some low-stakes player actions (e.g., editing notes) also bypass proposals.

### Persistence Strategy

- **Decision**: SQLite with SQLAlchemy ORM and Alembic migrations.
- **Rationale**: Single-file database is trivially deployable and backed up. SQLAlchemy provides a clean data access layer. Alembic handles schema evolution as the game develops.
- **Implications**: No separate database server to manage. Performance is not a concern at this scale.

---

## Deployment & Serving

### Deployment Model

- **Decision**: Self-hosted VPS. Single process serving both API and frontend. SQLite database file on disk.
- **Rationale**: Simple, cheap, full control. No cloud vendor dependency. SQLite is ideal for single-process deployment.
- **Implications**: Need a reverse proxy (e.g., Caddy or Nginx) for TLS termination. Process management via systemd or Docker. Backup strategy needed for the SQLite file. Specific tooling deferred to implementation.

### Web UI Serving

- **Decision**: FastAPI serves both the REST API (under `/api/v1/`) and static frontend files. Single deployment artifact.
- **Rationale**: Simplest possible setup for a small project. No CORS configuration, no separate hosting, one thing to deploy.
- **Implications**: Frontend build output is bundled with the backend. Static file serving via FastAPI's `StaticFiles` mount.

### API Pagination

- **Decision**: ULID cursor-based pagination. All list endpoints support `?after=<ulid>&limit=N` (default limit TBD, likely 50). Response includes a `next_cursor` field when more results exist.
- **Rationale**: Natural fit — ULIDs are already sortable by creation time. No offset drift issues. Consistent across all endpoints.
- **Implications**: All list endpoints return a standard paginated response shape. API conventions doc (to be created) will define the exact response envelope.

### API Conventions

- **Decision**: A separate `spec/architecture/api-conventions.md` document will define error response format, HTTP status code conventions, validation error shape, response envelopes, and naming conventions.
- **Rationale**: These cross-cutting concerns deserve their own spec rather than cluttering the system overview.
- **Implications**: New spec document needed. Should be written before implementation begins.

---

## Open Questions

All resolved.

---

_Last updated: 2026-03-05 (interrogation — resolved all 5 open questions: deployment model, UI serving, pagination, real-time, stale reference fix)_
