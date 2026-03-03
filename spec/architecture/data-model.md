# Data Model

**Status**: 🟡 In progress
**Last verified**: —

---

## Overview

This document defines the core entities, their relationships, and storage approach. All entities are game objects sharing common fields (`id`, `name`, `description`, `created_at`, `updated_at`) plus type-specific fields.

---

## Entity Relationship Summary

```
Character (PC) ─────< Bond ─────> Game Object (any)
     │
     ├────< Skill
     ├────< Core Trait (2)
     ├────< Role Trait (3)
     ├────< Magic Stat (5)
     └────< Magic Effect

Group ─────< Clock (project)
   │
   ├────< Group Relationship ─────> Group
   ├────< NPC (membership)
   └────< Location (presence)

Location ────?── Location (parent, nestable hierarchy)
   │
   ├────< NPC (found here)
   └────< Group (present here)

Story ────?── Story (parent, nestable sub-arcs)
   │
   └────< Game Object (owners)

Session ─────< Event

Event ─────> Game Object (target)
   │
   └────> Session (optional)

Proposal ─────> Character (submitter)
   │
   └────> Event (on approval)
```

---

## Core Entities

### Character (PC)

**Purpose**: The player character sheet — the central entity players interact with.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| id | string | yes | Primary key |
| name | string | yes | Character name |
| description | string | no | Character concept/background |
| stress | integer | yes | Meter, range TBD (e.g., 0–9) |
| free_time | integer | yes | Resource meter, 0–20 |
| plot | integer | yes | Resource meter, 0–5 |
| gnosis | integer | yes | Resource meter, 0–23 |
| notes | text | no | Freeform player notes |
| owner | ref → Player | yes | Which player owns this character |
| created_at | datetime | yes | Auto |
| updated_at | datetime | yes | Auto |

**Relationships**:
- Has many: Core Traits (2), Role Traits (3), Bonds (7), Skills (~5), Magic Stats (5), Magic Effects
- Belongs to: Player (owner)

### Core Trait / Role Trait

**Purpose**: Character qualities that provide +1d dice pool bonuses when relevant.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| id | string | yes | Primary key |
| name | string | yes | Trait name |
| description | string | yes | What this trait represents |
| charge | integer | yes | Meter, 0–5 |
| type | enum | yes | `core` or `role` |
| character_id | ref → Character | yes | Owning character |

### Bond

**Purpose**: Meaningful relationships that provide mechanical boosts in proposals.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| id | string | yes | Primary key |
| name | string | yes | Bond name |
| target_type | string | yes | Type of referenced game object |
| target_id | string | yes | ID of referenced game object |
| level | integer | yes | Bond strength |
| stress | integer | yes | Mini stress meter, range TBD |
| character_id | ref → Character | yes | Owning character |

### Skill

**Purpose**: Named abilities that determine base dice pool size.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| id | string | yes | Primary key |
| name | string | yes | Skill name |
| level | integer | yes | 0–3 |
| character_id | ref → Character | yes | Owning character |

### Magic Stat

**Purpose**: Schools/aspects of magic that determine magical capability.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| id | string | yes | Primary key |
| name | string | yes | Magic stat name |
| level | integer | yes | 0–5 |
| xp | integer | yes | Progress toward next level, range TBD |
| character_id | ref → Character | yes | Owning character |

### Magic Effect

**Purpose**: Known magical abilities with power levels and charges.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| id | string | yes | Primary key |
| name | string | yes | Effect name |
| description | string | yes | What this effect does |
| power_level | integer | yes | Effect strength |
| charge | integer | no | Meter, range varies. Null for permanent effects. |
| is_permanent | boolean | yes | If true, always active, no charge needed |
| character_id | ref → Character | yes | Owning character |

### NPC

**Purpose**: GM-controlled characters with simplified records.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| id | string | yes | Primary key |
| name | string | yes | NPC name |
| description | string | no | Who they are |
| traits | JSON | no | Freeform list of trait name/descriptions |
| stats | JSON | no | Freeform key-value mechanical info |
| notes | text | no | GM notes |
| location_id | ref → Location | no | Where they are |
| created_at | datetime | yes | Auto |
| updated_at | datetime | yes | Auto |

**Relationships**:
- Belongs to: Location (optional)
- Many-to-many: Groups

### Group

**Purpose**: Organizations and groups in the game world.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| id | string | yes | Primary key |
| name | string | yes | Group name |
| description | string | no | What this group is |
| tier | integer | yes | Power/influence level |
| notes | text | no | GM notes |
| created_at | datetime | yes | Auto |
| updated_at | datetime | yes | Auto |

**Relationships**:
- Has many: Clocks (project clocks), Group Relationships
- Many-to-many: NPCs, Locations

### Clock

**Purpose**: Progress trackers (BitD-style) for projects and events.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| id | string | yes | Primary key |
| name | string | yes | Clock name |
| segments | integer | yes | Total segments (e.g., 4, 6, 8) |
| progress | integer | yes | Filled segments, 0 to `segments` |
| associated_type | string | no | Type of associated game object |
| associated_id | string | no | ID of associated game object |
| group_id | ref → Group | no | If this is a group project clock |
| notes | text | no | |

### Location

**Purpose**: Places in the game world, forming a nestable hierarchy.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| id | string | yes | Primary key |
| name | string | yes | Location name |
| description | string | no | What this place is |
| parent_id | ref → Location | no | Parent location (hierarchy) |
| notes | text | no | |
| created_at | datetime | yes | Auto |
| updated_at | datetime | yes | Auto |

**Relationships**:
- Has many: child Locations
- Many-to-many: Groups (present here), NPCs (found here)

### Session

**Purpose**: Record of a play session.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| id | string | yes | Primary key |
| date | date | yes | When the session took place |
| summary | text | no | What happened |
| notes | text | no | Additional notes |
| created_at | datetime | yes | Auto |
| updated_at | datetime | yes | Auto |

**Relationships**:
- Has many: Events

### Story (Arc)

**Purpose**: Narrative threads tracked by the system.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| id | string | yes | Primary key |
| name | string | yes | Story name |
| summary | text | no | What this story is about |
| status | enum | yes | `active`, `completed`, `abandoned` |
| parent_id | ref → Story | no | Parent story (sub-arcs) |
| notes | text | no | |
| created_at | datetime | yes | Auto |
| updated_at | datetime | yes | Auto |

**Relationships**:
- Has many: child Stories (sub-arcs)
- Many-to-many: Game Objects (owners — Characters, Groups, etc.)

### Event

**Purpose**: Immutable record of a state change.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| id | string | yes | Primary key |
| type | string | yes | What kind of change (e.g., "gnosis_gained") |
| actor | string | yes | Who did it (player ID or "gm") |
| target_type | string | yes | Type of affected game object |
| target_id | string | yes | ID of affected game object |
| changes | JSON | yes | Before/after or delta |
| narrative | text | no | Fictional description |
| session_id | ref → Session | no | Link to Session |
| timestamp | datetime | yes | When it happened |

**Relationships**:
- Belongs to: Session (optional)
- References: Game Object (target)

### Proposal

**Purpose**: Player-submitted request for a mechanically significant state change.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| id | string | yes | Primary key |
| character_id | ref → Character | yes | Submitting character |
| player_id | ref → Player | yes | Submitting player |
| action_type | string | yes | What kind of action |
| narrative | text | yes | Player's description of the fiction |
| selections | JSON | yes | Selected traits, bonds, magic stats |
| calculated_effect | JSON | no | System-computed result |
| status | enum | yes | `pending`, `approved`, `rejected` |
| gm_notes | text | no | GM's reason for rejection or notes |
| event_id | ref → Event | no | Created event (on approval) |
| created_at | datetime | yes | Auto |
| updated_at | datetime | yes | Auto |

---

## Storage Approach

### Persistence Stack

- **Decision**: SQLite + SQLAlchemy ORM + Alembic migrations + Pydantic validation
- **Rationale**: Single-file database is trivially deployable and backed up. SQLAlchemy provides clean data access. Alembic handles schema evolution. Pydantic validates API boundaries.
- **Implications**: No separate database server. Performance not a concern at this scale.

---

## ID Strategy

- **Format**: TBD — likely UUID or ULID
- **Rationale**: TBD during interrogation. UUIDs are standard; ULIDs are sortable and more compact.

---

## Open Questions

1. ID format — UUID vs ULID vs sequential integer?
2. Exact ranges for TBD meters (Stress, Bond Stress, Magic Stat XP)?
3. How to model the polymorphic "target" reference on Bonds, Events, Clocks, and Story owners? (generic FK, separate tables, or JSON?)
4. Should Traits be a single table with a `type` discriminator, or separate Core Trait / Role Trait tables?
5. How to store the `selections` and `calculated_effect` JSON on Proposals — structured schema or freeform?
6. Player entity — is this separate from Character? What fields does it have?

---

_Last updated: 2026-02-24_
