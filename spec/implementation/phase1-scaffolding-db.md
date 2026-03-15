# Epic 1.1 — Project Scaffolding & Database

**Phase**: 1 — Foundation
**Depends on**: None (first Epic)
**Blocks**: Epic 1.2 (Auth & API Skeleton), all subsequent Epics
**Parallel with**: None

---

## Overview

Bootstrap the entire project: Python package structure, FastAPI application, SQLAlchemy ORM with ULID primary keys, Alembic migrations, and all 18 database tables from the data model spec. This Epic produces a runnable application with an empty database — no business logic yet.

---

## Stories

### Story 1.1.1 — Project Structure

**Files to create**:
- `pyproject.toml` — project metadata, dependencies (fastapi, uvicorn, sqlalchemy, alembic, pydantic, python-ulid, pytest, httpx)
- `src/wizards_engine/__init__.py`
- `src/wizards_engine/app.py` — FastAPI application factory
- `src/wizards_engine/api/__init__.py`
- `src/wizards_engine/models/__init__.py`
- `src/wizards_engine/services/__init__.py`
- `src/wizards_engine/schemas/__init__.py`

**Spec refs**: [overview.md](../architecture/overview.md) (tech stack), [api-conventions.md](../architecture/api-conventions.md) (FastAPI, OpenAPI docs)

**Acceptance criteria**:
- `pyproject.toml` lists all dependencies with versions pinned to compatible ranges
- Package is installable via `pip install -e .`
- FastAPI app starts with `uvicorn wizards_engine.app:app`
- `GET /docs` serves Swagger UI
- `GET /redoc` serves ReDoc
- `GET /openapi.json` returns the OpenAPI spec
- Directory layout follows `src/wizards_engine/{api,models,services,schemas}/`
- Python 3.11+ required

### Story 1.1.2 — Database & ORM Setup

**Files to create**:
- `src/wizards_engine/db.py` — SQLAlchemy engine, session factory, `get_db` dependency
- `src/wizards_engine/models/base.py` — declarative base, ULID PK mixin (`id` as TEXT/26 chars), `created_at`/`updated_at` auto-timestamps
- `alembic.ini` — Alembic configuration
- `alembic/env.py` — Alembic environment with SQLAlchemy metadata binding
- `alembic/versions/` — empty versions directory

**Spec refs**: [data-model.md](../architecture/data-model.md) (ULID PKs, persistence stack), [overview.md](../architecture/overview.md) (SQLite)

**Acceptance criteria**:
- SQLAlchemy engine connects to a SQLite database file
- Base model mixin provides `id` (ULID, TEXT, PK), `created_at` (datetime, auto), `updated_at` (datetime, auto on update)
- ULID generation uses `python-ulid` library
- `get_db` FastAPI dependency yields a scoped session
- Alembic is initialized and configured to read metadata from the Base
- `alembic upgrade head` runs without error (creates empty DB)
- Database file path is configurable (env var or config)

### Story 1.1.3 — All Table Migrations

**Files to create**:
- `alembic/versions/001_initial_schema.py` — single migration creating all 18 tables

**Spec refs**: [data-model.md](../architecture/data-model.md) (complete table definitions)

**Tables to create** (18 total):
1. `users` — id, display_name, role, login_code (indexed), character_id (FK→characters, unique), is_active, timestamps
2. `invites` — id (also the shareable code), is_consumed, created_at only
3. `characters` — id, name, description, detail_level, attributes (JSON), stress, free_time, plot, gnosis, skills (JSON), magic_stats (JSON), last_session_time_now, notes, is_deleted, timestamps
4. `groups` — id, name, description, tier, notes, is_deleted, timestamps
5. `locations` — id, name, description, parent_id (self-ref FK), notes, is_deleted, timestamps
6. `trait_templates` — id, name, description, type, is_deleted, timestamps
7. `slots` — id, slot_type, owner_type, owner_id, name, description, is_active, target_type, target_id, source_label, target_label, bidirectional, template_id (FK→trait_templates), charge, stress, stress_degradations, is_trauma, timestamps. Indexes: (owner_type, owner_id, slot_type), (target_type, target_id)
8. `magic_effects` — id, character_id (FK→characters), name, description, effect_type, power_level, charges_current, charges_max, is_active, timestamps
9. `clocks` — id, name, segments, progress, associated_type, associated_id, notes, is_deleted, timestamps
10. `sessions` — id, status, time_now, date, summary, notes, timestamps
11. `session_participants` — session_id (FK→sessions), character_id (FK→characters), additional_contribution. Composite PK.
12. `stories` — id, name, summary, status, parent_id (self-ref FK), tags (JSON), visibility_level, visibility_overrides (JSON), is_deleted, timestamps
13. `story_owners` — story_id (FK→stories), owner_type, owner_id. Composite PK.
14. `story_entries` — id, story_id (FK→stories), text, author_id (FK→users), character_id (FK→characters), session_id (FK→sessions), event_id (FK→events), game_object_refs (JSON), is_deleted, deleted_by (FK→users), updated_by (FK→users), timestamps
15. `events` — id, type, actor_type, actor_id (FK→users), changes (JSON), created_objects (JSON), deleted_objects (JSON), narrative, visibility, proposal_id (FK→proposals), parent_event_id (self-ref FK→events), session_id (FK→sessions), metadata (JSON), created_at only
16. `event_targets` — event_id (FK→events), target_type, target_id, is_primary. Composite PK.
17. `proposals` — id, character_id (FK→characters, nullable), action_type, origin, narrative, selections (JSON), calculated_effect (JSON), status, gm_notes, gm_overrides (JSON), event_id (FK→events), clock_id (FK→clocks), rider_event_id (FK→events), timestamps
18. `starred_objects` — user_id (FK→users), object_type, object_id. Composite PK.

**Acceptance criteria**:
- `alembic upgrade head` creates all 18 tables
- All columns have correct types (TEXT for ULIDs, INTEGER, BOOLEAN, JSON, DATETIME, DATE)
- All foreign key constraints are defined
- All composite primary keys are defined
- Indexes on `users.login_code`, `slots.(owner_type, owner_id, slot_type)`, `slots.(target_type, target_id)` exist
- `alembic downgrade base` drops all tables cleanly
- Migration is a single file (initial schema)

### Story 1.1.4 — SQLAlchemy Models

**Files to create**:
- `src/wizards_engine/models/user.py` — User, Invite
- `src/wizards_engine/models/character.py` — Character
- `src/wizards_engine/models/group.py` — Group
- `src/wizards_engine/models/location.py` — Location
- `src/wizards_engine/models/slot.py` — Slot (unified traits + bonds), TraitTemplate
- `src/wizards_engine/models/magic_effect.py` — MagicEffect
- `src/wizards_engine/models/clock.py` — Clock
- `src/wizards_engine/models/session.py` — Session, SessionParticipant
- `src/wizards_engine/models/story.py` — Story, StoryOwner, StoryEntry
- `src/wizards_engine/models/event.py` — Event, EventTarget
- `src/wizards_engine/models/proposal.py` — Proposal
- `src/wizards_engine/models/starred.py` — StarredObject

**Spec refs**: [data-model.md](../architecture/data-model.md) (all table definitions and relationships)

**Acceptance criteria**:
- All 18 tables have corresponding SQLAlchemy ORM models
- All models inherit from the ULID-base mixin (except join tables with composite PKs)
- Relationships defined: User↔Character, Character→MagicEffects, Character→Slots, Story→StoryEntries, Story→StoryOwners, Session→SessionParticipants, Event→EventTargets, Location→children (self-ref), Story→parent (self-ref), Event→parent_event (self-ref)
- JSON columns use SQLAlchemy `JSON` type
- Enum-like TEXT columns (role, detail_level, status, slot_type, etc.) documented with valid values
- All models importable from `wizards_engine.models`
- Relationships navigable in both directions (e.g., `user.character`, `character.user`)

---

## Notes

- No business logic in this Epic — purely structural
- The database schema is the authoritative implementation of [data-model.md](../architecture/data-model.md)
- JSON columns (skills, magic_stats, attributes, changes, selections, etc.) store arbitrary dicts — Pydantic validation happens at the API layer, not ORM layer
