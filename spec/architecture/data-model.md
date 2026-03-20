# Data Model

**Status**: 🟢 Complete
**Last interrogated**: 2026-03-13
**Last verified**: 2026-03-16 (users and invites tables verified against Epic 1.2 implementation; remaining tables not yet implemented)

---

## Overview

This document defines all database tables, their columns, relationships, and storage conventions. It is the **authoritative source of truth for the physical schema** — column names, types, and structure. Domain specs (proposals.md, auth.md, etc.) describe logical fields and behavior; where naming or structure differs, this document wins for implementation.

**Key conventions:**
- All primary keys are **ULIDs** (stored as TEXT, 26 chars, sortable by creation time)
- All tables have `created_at` (datetime, auto) and `updated_at` (datetime, auto) unless noted
- Polymorphic single-references use **type+id columns** inline (e.g., `target_type` + `target_id`)
- Polymorphic list-references use **association tables** (e.g., `event_targets`, `story_owners`)
- All traits and bonds share a single **`slots`** table with a `slot_type` discriminator
- JSON columns use SQLite JSON1 extension

**Persistence stack:** SQLite + SQLAlchemy ORM + Alembic migrations + Pydantic validation.

---

## Entity Relationship Summary

```
users ──────────────> characters (optional character_id)
invites (bare — no character link, consumed on redemption)

characters ─┐
groups      ├─ Game Objects ──< slots (unified traits + bonds)
locations ──┘

characters ──< magic_effects
characters .... skills (JSON), magic_stats (JSON)

clocks ─────────────> Game Object (associated_type + associated_id)

sessions ──< session_participants >── characters
stories  ──< story_entries
stories  ──< story_owners ──> Game Object (owner_type + owner_id)

events   ──< event_targets ──> Game Object (target_type + target_id)
events   ──?── events (parent_event_id, for rider events)
events   ──?── proposals (proposal_id back-ref)
events   ──?── sessions (session_id)

proposals ──?── characters (character_id, nullable for system proposals)
proposals ──?── events (event_id, on approval)

starred_objects ──> users + Game Object (user_id + object_type + object_id)
```

---

## Tables

### `users`

**Purpose**: Player accounts. The GM is a User with `role = gm`.

| Column | Type | Required | Notes |
|--------|------|----------|-------|
| id | TEXT (ULID) | yes | PK |
| display_name | TEXT | yes | 1–50 chars, trimmed, non-empty. Shown as "GM [name]" for GM role. |
| role | TEXT | yes | `gm` or `player` |
| login_code | TEXT | yes | Plaintext login code (the invite code, or regenerated). Indexed. Used for magic link auth. |
| character_id | TEXT | no | FK → `characters`. Null for GM (unless self-playing). |
| is_active | BOOLEAN | yes | Default true. Deactivated on re-invite. |
| created_at | DATETIME | yes | Auto |
| updated_at | DATETIME | yes | Auto |

**Constraints**: Unique `character_id` (1:1 player-character mapping). Exactly one `role = gm` user.

### `invites`

**Purpose**: Single-use invite codes. The invite `id` IS the shareable code — no separate `code` column. Bare invite (not pre-linked to a character).

| Column | Type | Required | Notes |
|--------|------|----------|-------|
| id | TEXT (ULID) | yes | PK. Also the shareable code in the magic link `/login/<id>`. |
| is_consumed | BOOLEAN | yes | Default false. Set true on redemption. |
| created_at | DATETIME | yes | Auto |

**Notes**: Bare invites — not pre-linked to a character. Character is created during redemption via `POST /api/v1/game/join`. The invite `id` becomes the user's initial `login_code`.

---

### `characters`

**Purpose**: Unified PC + NPC entity. The central Game Object for beings in the fiction.

| Column | Type | Required | Notes |
|--------|------|----------|-------|
| id | TEXT (ULID) | yes | PK |
| name | TEXT | yes | |
| description | TEXT | no | Character concept/background |
| detail_level | TEXT | yes | `full` (PC) or `simplified` (NPC). Fixed at creation. |
| attributes | JSON | no | Freeform key-value data (all characters) |
| stress | INTEGER | no | 0–9. Full characters only. Effective max = `9 - count(trauma bonds)`. |
| free_time | INTEGER | no | 0–20. Full characters only. |
| plot | INTEGER | no | 0–5. Full characters only. |
| gnosis | INTEGER | no | 0–23. Full characters only. |
| skills | JSON | no | Full only. `{awareness: 2, composure: 1, ...}` — all 8, level 0–3. |
| magic_stats | JSON | no | Full only. `{being: {level: 0, xp: 3}, wyrding: {...}, ...}` — all 5, level 0–5, xp 0–5. |
| last_session_time_now | INTEGER | no | Full only. Default 0. Last session's Time Now value for FT calculation. GM can override at creation for mid-campaign joins. |
| notes | TEXT | no | Freeform notes |
| is_deleted | BOOLEAN | yes | Default false. Soft delete. |
| created_at | DATETIME | yes | Auto |
| updated_at | DATETIME | yes | Auto |

**Notes**: Simplified characters leave meter/skill/magic columns null. `detail_level` auto-determined: characters created via invite flow → `full`; GM-created without invite → `simplified`.

**Slot counts** (in `slots` table):
- Full: 2 `core_trait` + 3 `role_trait` + 8 `pc_bond` = 13 slots
- Simplified: 7 `npc_bond` = 7 slots

### `groups`

**Purpose**: Organizations, crews, families, guilds — Game Objects.

| Column | Type | Required | Notes |
|--------|------|----------|-------|
| id | TEXT (ULID) | yes | PK |
| name | TEXT | yes | |
| description | TEXT | no | |
| tier | INTEGER | yes | Power/influence level. Any non-negative integer. |
| notes | TEXT | no | GM notes |
| is_deleted | BOOLEAN | yes | Default false |
| created_at | DATETIME | yes | Auto |
| updated_at | DATETIME | yes | Auto |

**Slot counts** (in `slots` table): 10 `group_trait` + 7 `group_relation` + unlimited `group_holding`.

**Derived**: `members` = all Characters with a bond targeting this Group (query `slots`).

### `locations`

**Purpose**: Places in the game world — Game Objects. Nestable hierarchy.

| Column | Type | Required | Notes |
|--------|------|----------|-------|
| id | TEXT (ULID) | yes | PK |
| name | TEXT | yes | |
| description | TEXT | no | |
| parent_id | TEXT | no | FK → `locations`. Self-referential hierarchy, unlimited depth. |
| notes | TEXT | no | |
| is_deleted | BOOLEAN | yes | Default false |
| created_at | DATETIME | yes | Auto |
| updated_at | DATETIME | yes | Auto |

**Slot counts** (in `slots` table): 5 `feature_trait` + unlimited `location_bond`.

---

### `trait_templates`

**Purpose**: GM-created catalog of Core and Role Trait definitions. Shared across characters.

| Column | Type | Required | Notes |
|--------|------|----------|-------|
| id | TEXT (ULID) | yes | PK |
| name | TEXT | yes | |
| description | TEXT | yes | |
| type | TEXT | yes | `core` or `role`. Fixed — determines which slot type can reference this. |
| is_deleted | BOOLEAN | yes | Default false |
| created_at | DATETIME | yes | Auto |
| updated_at | DATETIME | yes | Auto |

**Notes**: Editing a template's name/description propagates to all characters referencing it (via `slots.template_id`). Type is immutable after creation.

### `slots`

**Purpose**: Unified table for all traits and bonds across all Game Object types. The `slot_type` discriminator determines which columns are active.

| Column | Type | Required | Notes |
|--------|------|----------|-------|
| id | TEXT (ULID) | yes | PK |
| slot_type | TEXT | yes | Discriminator. See catalog below. |
| owner_type | TEXT | yes | `character`, `group`, or `location` |
| owner_id | TEXT | yes | ID of owning Game Object |
| name | TEXT | yes | Display name (or inherited from template for Core/Role) |
| description | TEXT | no | |
| is_active | BOOLEAN | yes | Default true. False = Past/Retired. |
| target_type | TEXT | no | Bond target type (`character`, `group`, `location`). Bonds only. |
| target_id | TEXT | no | Bond target ID. Bonds only. |
| source_label | TEXT | no | Relationship label from source's perspective. Bonds only. |
| target_label | TEXT | no | Label from target's perspective. Bidirectional bonds only. |
| bidirectional | BOOLEAN | no | Whether both sides see this bond. Bonds only. |
| template_id | TEXT | no | FK → `trait_templates`. Core/Role traits only. |
| charge | INTEGER | no | 0–5. Core/Role traits only. |
| charges | INTEGER | no | 0–5 (effective max = `5 - degradations`). PC bonds only. Bond charges. |
| degradations | INTEGER | no | Count of max reductions. PC bonds only. |
| is_trauma | BOOLEAN | no | True if slot holds a Trauma. PC bonds only. |
| created_at | DATETIME | yes | Auto |
| updated_at | DATETIME | yes | Auto |

#### Slot Type Catalog

| slot_type | Owner | Max Slots | Target? | Mechanical Fields |
|-----------|-------|-----------|---------|-------------------|
| `core_trait` | Character (full) | 2 | No | `template_id`, `charge` |
| `role_trait` | Character (full) | 3 | No | `template_id`, `charge` |
| `pc_bond` | Character (full) | 8 | Yes | `charges`, `degradations`, `is_trauma` + labels/bidirectional |
| `npc_bond` | Character (simplified) | 7 | Yes | Labels/bidirectional only (no charges) |
| `group_trait` | Group | 10 | No | None (descriptive only) |
| `group_relation` | Group | 7 | Yes (Group) | Labels/bidirectional only |
| `group_holding` | Group | Unlimited | Yes (Location) | None (directional, descriptive) |
| `feature_trait` | Location | 5 | No | None (descriptive only) |
| `location_bond` | Location | Unlimited | Yes (any) | Labels only (directional) |

**Indexes**: `(owner_type, owner_id, slot_type)` for slot queries. `(target_type, target_id)` for reverse lookups (membership, bond graph traversal).

### `magic_effects`

**Purpose**: Magical effects on a character's sheet.

| Column | Type | Required | Notes |
|--------|------|----------|-------|
| id | TEXT (ULID) | yes | PK |
| character_id | TEXT | yes | FK → `characters` |
| name | TEXT | yes | |
| description | TEXT | yes | |
| effect_type | TEXT | yes | `instant`, `charged`, or `permanent` |
| power_level | INTEGER | yes | 1–5 |
| charges_current | INTEGER | no | Charged effects only. Unbounded. |
| charges_max | INTEGER | no | Charged effects only. Unbounded. |
| is_active | BOOLEAN | yes | Default true. False = retired/used up. |
| created_at | DATETIME | yes | Auto |
| updated_at | DATETIME | yes | Auto |

**Constraints**: Max 9 active effects per character (charged + permanent; instants don't count toward cap).

---

### `clocks`

**Purpose**: Progress trackers (System Entity, not a Game Object).

| Column | Type | Required | Notes |
|--------|------|----------|-------|
| id | TEXT (ULID) | yes | PK |
| name | TEXT | yes | |
| segments | INTEGER | yes | Total segments. Any positive integer, default 5. |
| progress | INTEGER | yes | Filled segments. 0 to segments (soft cap — can exceed). |
| associated_type | TEXT | no | `character`, `group`, or `location`. Polymorphic single-ref. |
| associated_id | TEXT | no | ID of associated Game Object. |
| notes | TEXT | no | |
| is_deleted | BOOLEAN | yes | Default false |
| created_at | DATETIME | yes | Auto |
| updated_at | DATETIME | yes | Auto |

**Computed**: `is_completed` = `progress >= segments` (not stored). Completion triggers auto-generation of a `resolve_clock` proposal.

### `sessions`

**Purpose**: Play session records (System Entity).

| Column | Type | Required | Notes |
|--------|------|----------|-------|
| id | TEXT (ULID) | yes | PK |
| status | TEXT | yes | `draft`, `active`, or `ended`. Forward-only lifecycle. |
| time_now | INTEGER | no | Abstract campaign time counter. GM-set. |
| date | DATE | no | When the session took/takes place. |
| summary | TEXT | no | Editable in Draft + Active. Read-only in Ended. |
| notes | TEXT | no | Same editability as summary. |
| created_at | DATETIME | yes | Auto |
| updated_at | DATETIME | yes | Auto |

**Notes**: Only one `active` session at a time. Draft sessions can be hard-deleted. Active/Ended are permanent. `time_now` must be >= previous session's `time_now`.

### `session_participants`

**Purpose**: Which characters are registered for a session.

| Column | Type | Required | Notes |
|--------|------|----------|-------|
| session_id | TEXT | yes | FK → `sessions`. Composite PK. |
| character_id | TEXT | yes | FK → `characters`. Composite PK. |
| additional_contribution | BOOLEAN | yes | Default false. Meta-game reward flag (+1 bonus Plot). |

**Constraints**: PK = `(session_id, character_id)`. Contribution flag locks on session Start (or at moment of late join).

### `stories`

**Purpose**: Narrative threads (System Entity).

| Column | Type | Required | Notes |
|--------|------|----------|-------|
| id | TEXT (ULID) | yes | PK |
| name | TEXT | yes | |
| summary | TEXT | no | |
| status | TEXT | yes | `active`, `completed`, `abandoned`. GM sets freely. |
| parent_id | TEXT | no | FK → `stories`. Sub-arc hierarchy. |
| tags | JSON | no | Freeform string array for categorization. |
| visibility_level | TEXT | no | Override default visibility (`familiar`). One of: `silent`, `gm_only`, `private`, `bonded`, `familiar`, `public`, `global`. Null = default (`familiar`). GM-set. |
| visibility_overrides | JSON | no | Array of user IDs granted access regardless of bond graph. GM-set. |
| is_deleted | BOOLEAN | yes | Default false |
| created_at | DATETIME | yes | Auto |
| updated_at | DATETIME | yes | Auto |

**Notes**: GM-only creation. Visibility derived from owners + unified visibility model (see [feed.md](../domains/feed.md)). Default visibility: `familiar`.

### `story_owners`

**Purpose**: Association table — which Game Objects own a Story.

| Column | Type | Required | Notes |
|--------|------|----------|-------|
| story_id | TEXT | yes | FK → `stories`. Composite PK. |
| owner_type | TEXT | yes | `character`, `group`, or `location`. Composite PK. |
| owner_id | TEXT | yes | ID of owning Game Object. Composite PK. |

**Constraints**: PK = `(story_id, owner_type, owner_id)`.

### `story_entries`

**Purpose**: Individual narrative entries within a Story.

| Column | Type | Required | Notes |
|--------|------|----------|-------|
| id | TEXT (ULID) | yes | PK |
| story_id | TEXT | yes | FK → `stories` |
| text | TEXT | yes | Narrative content |
| author_id | TEXT | yes | FK → `users`. Who wrote this entry. |
| character_id | TEXT | no | FK → `characters`. Optional character linkage. |
| session_id | TEXT | no | FK → `sessions`. Optional session linkage. |
| event_id | TEXT | no | FK → `events`. Optional event linkage. |
| game_object_refs | JSON | no | Array of `{type, id}` for additional Game Object references. |
| is_deleted | BOOLEAN | yes | Default false. Soft delete. |
| deleted_by | TEXT | no | FK → `users`. Who deleted this entry. |
| updated_by | TEXT | no | FK → `users`. Who last edited. |
| created_at | DATETIME | yes | Auto |
| updated_at | DATETIME | yes | Auto |

**Access rules**: Players edit own entries, GM edits any. See = write (if you can see the Story, you can add entries).

---

### `events`

**Purpose**: Immutable record of a state change (append-only log).

| Column | Type | Required | Notes |
|--------|------|----------|-------|
| id | TEXT (ULID) | yes | PK |
| type | TEXT | yes | Convention-based `{domain}.{action}` string (e.g., `character.stress_changed`) |
| actor_type | TEXT | yes | `player`, `gm`, or `system` |
| actor_id | TEXT | no | FK → `users`. Null for `system` actor. |
| changes | JSON | yes | Fully qualified change entries: `{type.id.field: {op, before, after, clamped?}}`. See convention below. |
| created_objects | JSON | no | List of `{type, id}` for newly created objects. |
| deleted_objects | JSON | no | List of `{type, id}` for soft-deleted objects. |
| narrative | TEXT | no | From GM, player, or system. |
| visibility | TEXT | yes | One of: `silent`, `gm_only`, `private`, `bonded`, `familiar`, `public`, `global`. See [feed.md](../domains/feed.md). |
| proposal_id | TEXT | no | FK → `proposals`. Back-ref for proposal-originated events. |
| parent_event_id | TEXT | no | FK → `events`. For rider events — links to the approval event. |
| session_id | TEXT | no | FK → `sessions`. Auto-captured from Active session. |
| metadata | JSON | no | Freeform JSON for clock annotations, event links, future extensions. |
| created_at | DATETIME | yes | Auto. The only timestamp — no separate `timestamp` column. ULID `id` provides time-sortable ordering. |

**Immutability**: Events are never modified or deleted, **except** `visibility` (GM can override).

**Changes key convention**: Fully qualified `{type}.{id}.{field}` where `type` is the DB table name (singular): `character`, `group`, `location`, `clock`, `session`, `slot`, `magic_effect`, `proposal`. Each value carries `{op, before, after}` plus an optional `clamped` boolean. `op` is one of `field.set`, `meter.delta`, or `meter.set` — classifying the mutation kind. `clamped` is present (true) when a boundary was hit. Example: `"character.01HXYZ.stress": {"op": "meter.delta", "before": 2, "after": 4}`, `"slot.01HABC.charge": {"op": "meter.delta", "before": 5, "after": 4}`. See [events.md](../domains/events.md) for operation type definitions and meter boundary patterns.

### `event_targets`

**Purpose**: Association table — which Game Objects are affected by an Event.

| Column | Type | Required | Notes |
|--------|------|----------|-------|
| event_id | TEXT | yes | FK → `events`. Composite PK. |
| target_type | TEXT | yes | `character`, `group`, or `location`. Composite PK. |
| target_id | TEXT | yes | ID of affected Game Object. Composite PK. |
| is_primary | BOOLEAN | yes | Default false. First/main target = true. |

**Constraints**: PK = `(event_id, target_type, target_id)`.

### `proposals`

**Purpose**: Request for a state change — player-submitted or system-generated.

| Column | Type | Required | Notes |
|--------|------|----------|-------|
| id | TEXT (ULID) | yes | PK |
| character_id | TEXT | no | FK → `characters`. Submitting character. **Null for system-generated proposals** (e.g., `resolve_clock`). |
| action_type | TEXT | yes | One of 12 types (see catalog below). |
| origin | TEXT | yes | `player` or `system`. Distinguishes player-submitted from system-generated. |
| narrative | TEXT | yes | Player-written description of the action. GM can override on approval. |
| selections | JSON | yes | All player selections: modifiers (`{core_trait_id?, role_trait_id?, bond_id?}`), plot_spend, and type-specific details. Structure varies by action_type. |
| calculated_effect | JSON | no | System-computed result. Typed per action_type — includes both outcome and costs. GM overrides replace fields within this structure. Auto-recalculated on revision. |
| status | TEXT | yes | `pending`, `approved`, `rejected`. |
| gm_notes | TEXT | no | GM's narrative on approval, or reason for rejection. Contextual on status. |
| gm_overrides | JSON | no | GM modifications that **replace** corresponding fields in `calculated_effect`. |
| event_id | TEXT | no | FK → `events`. Set on approval — links to the generated event. |
| clock_id | TEXT | no | FK → `clocks`. For `resolve_clock` proposals only. Pre-linked by system. |
| rider_event_id | TEXT | no | FK → `events`. Set on approval if a rider event was created. |
| created_at | DATETIME | yes | Auto |
| updated_at | DATETIME | yes | Auto |

#### Action Type Catalog

| action_type | Category | Auto-Cost | Notes |
|-------------|----------|-----------|-------|
| `use_skill` | Action | — | Dice pool = skill level + modifiers + Plot |
| `use_magic` | Action | — | Magic Action. Sacrifice list in selections. |
| `charge_magic` | Action | — | Charge Action. Targets existing effect. |
| `regain_gnosis` | Downtime | 1 FT | 3 base + lowest magic stat + modifiers |
| `recharge_trait` | Downtime | 1 FT | Full restore to 5 charges |
| `maintain_bond` | Downtime | 1 FT | Reset bond stress to 0 |
| `work_on_project` | Downtime | 1 FT | Adds narrative entry to target Story |
| `rest` | Downtime | 1 FT | 3 base + modifiers Stress healed |
| `new_trait` | Downtime | 1 FT | Replace/fill a Core or Role trait slot |
| `new_bond` | Downtime | 1 FT | Replace/fill a bond slot |
| `resolve_clock` | System | — | System-generated when clock completes. `origin = system`, `character_id = null`. |
| `resolve_trauma` | System | — | System-generated when character Stress hits max. `origin = system`, `character_id = affected character`. GM fills in trauma details. |

### `starred_objects`

**Purpose**: Player starring — tracks Game Objects of interest for the starred feed.

| Column | Type | Required | Notes |
|--------|------|----------|-------|
| user_id | TEXT | yes | FK → `users`. Composite PK. |
| object_type | TEXT | yes | `character`, `group`, or `location`. Composite PK. |
| object_id | TEXT | yes | ID of starred Game Object. Composite PK. |

**Constraints**: PK = `(user_id, object_type, object_id)`.

---

## Decisions

### ULID Primary Keys

- **Decision**: All tables use ULID (Universally Unique Lexicographically Sortable Identifier) as primary keys, stored as TEXT (26 chars).
- **Rationale**: Sortable by creation time (useful for the append-only event log and debugging). URL-safe, more compact than UUID. Well-supported in Python (`python-ulid`).
- **Implications**: No auto-increment. IDs generated in application code. Sort by ID ≈ sort by creation time.

### Polymorphic Reference Strategy (Hybrid)

- **Decision**: Single-reference polymorphism uses **type+id columns inline** (e.g., Bond `target_type`/`target_id`, Clock `associated_type`/`associated_id`). List-reference polymorphism uses **association tables** (e.g., `event_targets`, `story_owners`).
- **Rationale**: Type+id is simple for 1:1 relationships — no JOINs. Association tables are cleaner for 1:many polymorphic lists and enable independent querying of list members. Hybrid approach uses the right tool for each shape.
- **Implications**: No FK constraints on polymorphic references (enforced in application code). Acceptable for a trusted single-user app. Association tables have composite PKs.
- **Alternatives considered**: Separate FK columns per type (too many nullable columns, migration needed for new types). Association tables everywhere (unnecessary JOINs for single refs).

### Unified `slots` Table

- **Decision**: All traits and bonds across all Game Object types live in one `slots` table with a `slot_type` discriminator and nullable mechanical columns.
- **Rationale**: All slot types share common patterns (owner, name, description, active/retired). One table with nullable columns is simpler than 9 separate tables. Performance is fine for 4–6 players. Enables unified bond-graph queries.
- **Implications**: Application code enforces which columns are valid per `slot_type`. Null mechanical fields on descriptive slots. Indexes on `(owner_type, owner_id, slot_type)` and `(target_type, target_id)`.

### Skills and Magic Stats as JSON

- **Decision**: Skills (8 hardcoded, level 0–3) and Magic Stats (5 hardcoded, level 0–5 + xp 0–5) stored as JSON columns on the `characters` table.
- **Rationale**: Fixed, known sets with no relational needs. JSON avoids 13 extra rows per PC. Queries by skill level are rare — only needed for the character sheet API response.
- **Implications**: No separate `skills` or `magic_stats` tables. Schema validation in Pydantic. Skill/stat names hardcoded in application code.

### Story Entries as Separate Table

- **Decision**: Story entries are rows in a `story_entries` table, not a JSON array on the Story.
- **Rationale**: Enables per-entry queries, soft-delete, `updated_by` tracking, pagination, and per-entry permissions (players edit own, GM edits any).
- **Implications**: Standard FK relationship. Entry ordering by `created_at`.

### Session Participants as Join Table

- **Decision**: Session participants tracked in a `session_participants` join table with `additional_contribution` flag.
- **Rationale**: Standard M:M pattern. Enables per-participant queries and cross-session character history lookups.
- **Implications**: Contribution flag locks on session Start or at moment of late join.

### Starred Objects as Separate Table

- **Decision**: Starred Game Objects stored in a `starred_objects` table rather than a JSON array on User.
- **Rationale**: Consistent with the association table pattern for list-shaped polymorphic refs. Enables SQL queries.
- **Implications**: Three-column table with composite PK.

### Rider Events as Separate Rows

- **Decision**: Rider events are full Event rows in the `events` table with a `parent_event_id` FK linking to the approval event.
- **Rationale**: Same schema, same queryability, same visibility filtering. Rider events can have their own targets, visibility level, and narrative. Created in the same transaction as the approval event.
- **Implications**: `parent_event_id` column on events (nullable, self-referential FK).

### Calculated Effect: Typed Schemas in JSON

- **Decision**: Each action type has a typed schema for `calculated_effect` including both outcome and costs (defined in [proposals.md](../domains/proposals.md)). Stored as JSON. GM overrides replace fields within this structure.
- **Rationale**: JSON column with Pydantic validation per action_type. Typed schemas provide clear GM override points without schema changes.
- **Implications**: `calculated_effect` stored as JSON. Auto-recalculated on proposal revision. Pydantic models define per-type schemas.

### Physical Schema Authority

- **Decision**: This document is the authoritative source of truth for the physical database schema. Domain specs describe logical fields and behavior. Where naming or structure differs, data-model.md wins.
- **Rationale**: A single source of truth for column names prevents ambiguity during implementation. Domain specs evolve faster and describe intent; this spec defines structure.
- **Implications**: Domain specs may describe logical fields (e.g., `modifiers`, `details`, `plot_spend` in proposals.md) that map to a single physical column (`selections` JSON). The mapping is noted in this spec.

### Proposals: Logical-to-Physical Field Mapping

- **Decision**: The actions domain spec (formerly proposals.md) describes several logical fields (`modifiers`, `details`, `plot_spend`, `gm_narrative`, `rejection_note`) that map to fewer physical columns (`selections` JSON, `gm_notes` TEXT). The **API uses logical fields** in request/response bodies; the API layer maps to/from physical columns.
- **Rationale**: Fewer columns = simpler schema. The logical fields are useful for domain understanding; the physical columns are what gets implemented. JSON columns provide flexibility.
- **Implications**: `selections` JSON contains: modifiers (trait/bond IDs), plot_spend, and type-specific details. `gm_notes` serves as approval narrative or rejection reason (contextual on status). `gm_overrides` JSON stores all approval-specific fields (actual_stat, style_bonus, effect_details, charges_added, power_boost, bond_strained). `rider_event_id` is a separate FK column (not in JSON).

### Persistence Stack

- **Decision**: SQLite + SQLAlchemy ORM + Alembic migrations + Pydantic validation.
- **Rationale**: Single-file database is trivially deployable and backed up. SQLAlchemy provides clean data access. Alembic handles schema evolution. Pydantic validates API boundaries.
- **Implications**: No separate database server. Performance not a concern at this scale.

---

## Table Summary

| Table | Type | Row Count Estimate | Notes |
|-------|------|-------------------|-------|
| `users` | Auth | 5–7 | 1 GM + 4–6 players |
| `invites` | Auth | ~10 | One per character, consumed on use |
| `characters` | Game Object | 20–50 | 4–6 PCs + ~20–40 NPCs |
| `groups` | Game Object | 5–20 | |
| `locations` | Game Object | 10–30 | Hierarchical |
| `trait_templates` | Catalog | 20–50 | Shared across characters |
| `slots` | Unified | 200–500 | All traits + bonds for all Game Objects |
| `magic_effects` | Character sub | 10–50 | Max 9 active per PC |
| `clocks` | System Entity | 5–20 | |
| `sessions` | System Entity | 20–100 | One per play session |
| `session_participants` | Join | 50–500 | ~5 per session |
| `stories` | System Entity | 10–30 | |
| `story_entries` | System Entity | 50–200 | |
| `story_owners` | Association | 20–60 | |
| `events` | Append-only | 500–5000 | Grows over campaign lifetime |
| `event_targets` | Association | 500–5000 | ~1–3 per event |
| `proposals` | Workflow | 200–1000 | |
| `starred_objects` | User pref | 10–30 | |

**Total: 18 tables.**

---

## Open Questions

_All resolved._

1. ~~**`invites` table: `id` vs `code`**~~: **Resolved** — Merged. The invite's ULID `id` IS the shareable code. `code` column dropped. The invite `id` becomes the user's initial `login_code`.
2. ~~**`session_participants` missing `distributed` flag**~~: **Resolved** — No flag needed. Re-adding re-distributes; GM corrects via direct actions. See [downtime.md](../domains/downtime.md).
3. ~~**Proposals `rider_event` storage**~~: **Resolved** — `rider_event_id` FK on the proposals table (nullable). Direct reference to the rider event row. Also linked via `events.parent_event_id` on the rider event itself.
4. ~~**Event `changes` key convention**~~: **Resolved** — Fully qualified `{type}.{id}.{field}` where type = DB table name (singular).
5. ~~**Trait Template endpoints**~~: **Resolved** — Standard REST CRUD: `GET/POST /api/v1/trait-templates`, `GET/PATCH/DELETE /api/v1/trait-templates/{id}`. All GM-only. Soft delete. See [traits.md](../domains/traits.md).

---

## Implications for Other Specs

| Spec | Implication |
|------|-------------|
| [bonds.md](../domains/bonds.md) | ✅ PC bond slots = 8. Slot type catalog defined here. |
| [character-core.md](../domains/character-core.md) | ✅ Skills/magic_stats as JSON. PC bond slots = 8. |
| [traits.md](../domains/traits.md) | ✅ Unified `slots` table. `template_id` FK. Trait template CRUD defined in traits.md. |
| [events.md](../domains/events.md) | ✅ Rider events with `parent_event_id`. `event_targets` table. 7-level visibility. |
| [actions.md](../domains/actions.md) | ✅ Logical-to-physical field mapping. `origin`, nullable `character_id`, `gm_overrides` replacement semantics. |
| [auth.md](../domains/auth.md) | ✅ `starred_objects` table. Invite `id` is the code (no separate `code` column). `login_code` plaintext on users. |

---

_Last updated: 2026-03-19 (renamed `stress`/`stress_degradations` columns to `charges`/`degradations` in `slots` table)_
