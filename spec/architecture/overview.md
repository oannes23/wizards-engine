# System Overview

**Status**: 🟡 In progress
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
- **Real-time features** — no WebSockets, no live updates (polling or manual refresh is fine)

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

## Open Questions

1. What is the deployment model? (local-only, self-hosted VPS, cloud?)
2. How is the web UI served? (same process, separate static hosting?)
3. Should there be any real-time notification mechanism (e.g., SSE for proposal status)?

---

_Last updated: 2026-02-24_
