# Events — Domain Specification

**Status**: 🟢 Complete
**Last interrogated**: 2026-03-12
**Last verified**: 2026-03-16
**Depends on**: [game-objects](game-objects.md), [bonds](bonds.md) (bond graph), [feed](feed.md) (visibility model)
**Depended on by**: [actions](actions.md), [downtime](downtime.md)

---

## Overview

The event log is an append-only record of every state change in the system. Events provide history, audit trail, activity feed, and session timelines. State is the source of truth — events are the history.

Events are visible to players based on their character's proximity in the bond graph, using the **unified visibility model** defined in [feed.md](feed.md). This creates an emergent information network where you learn about things you're connected to.

---

## Core Concepts

### Event Schema

Every mutation to game state produces an event record. See [data-model.md](../architecture/data-model.md) for the complete physical schema.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `id` | ULID | yes | Primary key (time-sortable — provides sort order) |
| `type` | string | yes | Convention-based: `{domain}.{action}` (e.g., `character.stress_changed`, `clock.advanced`) |
| `actor_type` | string | yes | `player`, `gm`, or `system` |
| `actor_id` | ref → users | no | FK to users table. Null for `system` actor. |
| `changes` | JSON | yes | Fully qualified before/after pairs: `{type.id.field: {before: X, after: Y}}` |
| `created_objects` | JSON | no | List of `{type, id}` for newly created objects |
| `deleted_objects` | JSON | no | List of `{type, id}` for soft-deleted objects |
| `narrative` | text | no | From GM, player, or system |
| `visibility` | string | yes | One of 7 levels: `silent`, `gm_only`, `private`, `bonded`, `familiar`, `public`, `global`. See [feed.md](feed.md). |
| `proposal_id` | ref → proposals | no | Back-ref for proposal-originated events |
| `parent_event_id` | ref → events | no | For rider events — links to the approval event |
| `session_id` | ref → sessions | no | Auto-captured from Active session. Rider events inherit from parent. |
| `metadata` | JSON | no | Freeform: clock annotations, event links, extensions |
| `created_at` | datetime | yes | When the event was created (auto) |

**No separate `timestamp` column.** The ULID `id` provides time-sortable ordering. `created_at` is the only timestamp — events are created in real-time, so there's no meaningful distinction between "when it happened" and "when the row was inserted."

**Targets** are stored in the `event_targets` association table (not inline on the event row):

| Field | Type | Notes |
|-------|------|-------|
| `event_id` | ref → events | Composite PK |
| `target_type` | string | `character`, `group`, or `location` |
| `target_id` | string | ID of affected Game Object |
| `is_primary` | boolean | First/main target = true |

### Changes Field

The `changes` field uses **fully qualified before/after pairs** with the convention `{type}.{id}.{field}`:

```json
{
  "character.01HXYZ.gnosis": {"op": "meter.delta", "before": 15, "after": 5},
  "character.01HXYZ.stress": {"op": "meter.delta", "before": 2, "after": 4},
  "slot.01HABC.charge": {"op": "meter.delta", "before": 3, "after": 2},
  "slot.01HDEF.stress": {"op": "meter.delta", "before": 1, "after": 2}
}
```

**Key convention**: `{type}.{id}.{field}` where `type` matches the **database table name** (singular):
- Game Objects: `character`, `group`, `location`
- System Entities: `clock`, `session`
- Sub-entities: `slot` (all traits and bonds), `magic_effect`
- Workflow: `proposal`

All keys are fully qualified — no shorthand, no ambiguity. Every key includes the entity type, its ULID, and the field name.

- Values are `{op, before, after}` — the `op` tag classifies the mutation; `before`/`after` enable inversion for future undo
- For compound changes (e.g., a proposal approval affecting multiple objects), all changes go in a single event
- New objects go in the `created_objects` list, not in `changes`
- Soft-deleted objects go in the `deleted_objects` list

### Operation Types

Each entry in the `changes` dict carries an `op` field that classifies the mutation. Three operation types:

| Op | When to use | Example |
|----|-------------|---------|
| `field.set` | Non-numeric or unbounded fields (name, status, is_active, target_id) | `"slot.01HABC.is_active": {"op": "field.set", "before": true, "after": false}` |
| `meter.delta` | Bounded numeric adjusted by a signed amount (stress +2, charge -1, progress +1) | `"character.01HXYZ.stress": {"op": "meter.delta", "before": 2, "after": 4}` |
| `meter.set` | Bounded numeric set to an absolute value (stress reset to 0, bond stress reset via Maintain Bond) | `"character.01HXYZ.stress": {"op": "meter.set", "before": 7, "after": 0}` |

The `op` tag is set by the Python code that creates the event — it is not caller-supplied. It makes the event log queryable by mutation kind (e.g., "show me all meter changes") without introducing a DSL.

`created_objects` / `deleted_objects` already cover object lifecycle — no `op` tag needed there.

### Compound Changes

**One event per state-changing action.** A single proposal approval that modifies Gnosis, creates a Magic Effect, spends a trait charge, and strains a bond produces one event with:
- `changes`: all field mutations across all affected objects
- `created_objects`: any new objects (Magic Effects, Bond instances, etc.)
- `deleted_objects`: any soft-deleted objects (retired traits, etc.)
- Targets in `event_targets`: all affected game objects listed

This matches the "one event per approval" decision from the actions spec.

**Exception**: Session start is a composite action that produces **3 separate events** (see Session Start Decomposition decision below).

### Event Types

Convention-based strings following `{domain}.{action}` naming. NPCs use `character.*` types (NPCs are Characters with `detail_level = simplified`):

| Domain | Example Types |
|--------|--------------|
| `proposal` | `proposal.approved`, `proposal.rejected`, `proposal.revised` |
| `character` | `character.created`, `character.updated`, `character.deleted`, `character.stress_changed`, `character.gnosis_changed`, `character.meter_updated` |
| `trait` | `trait.charge_spent`, `trait.recharged`, `trait.retired`, `trait.created` |
| `bond` | `bond.stress_changed`, `bond.degraded`, `bond.maintained`, `bond.retired`, `bond.created` |
| `magic` | `magic.effect_created`, `magic.effect_used`, `magic.effect_retired`, `magic.effect_charged` |
| `clock` | `clock.advanced`, `clock.completed`, `clock.created`, `clock.modified`, `clock.resolve_generated` |
| `session` | `session.started`, `session.ended`, `session.ft_distributed`, `session.plot_distributed`, `session.participant_added`, `session.participant_removed` |
| `group` | `group.created`, `group.updated`, `group.bond_changed` |
| `location` | `location.created`, `location.updated` |
| `story` | `story.created`, `story.updated` |
| `player` | `player.find_time` |
| `character` | `character.resolve_trauma_generated` |

No category field — the domain prefix provides natural grouping. New types can be added without schema changes.

**GM actions reuse domain event types** — e.g., a GM changing a character's stress produces a `character.stress_changed` event, not a `gm.direct_action` event. The `actor_type: "gm"` field distinguishes GM-initiated events from player-initiated ones. See [actions.md](actions.md) for the full GM action type catalog.

**Story entries do not produce events.** Direct story entry creation by players/GM appears in the feed as a `story_entry` feed item — no backing event. The `work_on_project` downtime action produces a `proposal.approved` event (FT deducted) and separately adds a story entry. `story.created` and `story.updated` are events for GM Story object mutations only.

**User-level actions do not produce events.** Profile changes (display name), starring/unstarring, and other preference changes are not game state and do not generate events.

### Rider Events

When the GM approves a proposal, they can optionally attach a **rider event** — a bundled direct-action event that fires atomically in the same transaction. Rider events are full Event rows with:
- `parent_event_id` set to the approval event's ID
- `session_id` inherited from the parent event (always the same session)
- Their own targets, changes, narrative, and visibility
- Same schema as any event

**Use cases:**
- Side effects alongside approval: "your skill check succeeds AND the clock advances +2 AND this NPC reacts"
- Clock resolution: GM fills in the `resolve_clock` proposal and attaches a rider event with world state changes

See [data-model.md](../architecture/data-model.md) for the `parent_event_id` column.

### Narrative Field

The narrative field is optional and comes from different sources:

- **Proposal approvals**: Player-written narrative from submission (GM can edit)
- **GM direct actions**: GM provides narrative text
- **Player direct actions**: Player provides narrative (e.g., Magic Effect use)
- **System actions**: Auto-generated descriptive text (e.g., "Session 5 started.")

### Session Auto-Capture

Events generated while a Session is Active are automatically tagged with that session's ID (decided in [game-objects](game-objects.md)). Callers can override with a specific `session_id`. When no session is Active, `session_id` is null. Rider events always inherit `session_id` from their parent event.

### Metadata Field

A freeform JSON field for per-event context. Primary use cases:

- **Clock annotations**: `{notes: string, related_events: [event_ids], related_objects: [object_ids]}` — explaining why a clock was adjusted
- **Event-to-event links**: `{related_events: [event_ids]}` — linking an event to earlier events for context
- **Future extensions**: Any per-event data that doesn't fit the core schema

---

## Visibility

Event visibility uses the **unified 7-level visibility model** defined in [feed.md](feed.md). This section summarizes event-specific behavior; feed.md is authoritative for the model itself.

### Visibility Levels (Summary)

| Level | Who sees it | Hop distance |
|-------|------------|--------------|
| `silent` | GM only (silent feed) | — |
| `gm_only` | GM only (normal feed) | — |
| `private` | Owner-scoped + GM | 0-hop |
| `bonded` | Direct bond to any target + GM | 1-hop |
| `familiar` | 2-hop via Character-intermediary traversal + GM | 2-hop |
| `public` | 3-hop via Character-intermediary traversal + GM | 3-hop |
| `global` | All players + GM | All |

**Traversal rule**: `familiar` and `public` use the Character-intermediary traversal — after a non-Character node (Group or Location), the next hop must go through a Character (PC or NPC). PCs are valid intermediaries. See [feed.md](feed.md) and [bonds.md](bonds.md) for details.

**Computed on read** (no caching). SQLite handles it for 4–6 players. Add caching only if performance becomes an issue.

### Defaults Per Event Type

| Type pattern | Default visibility | Rationale |
|-------------|-------------------|-----------|
| `session.started`, `session.ended` | `global` | All players see session lifecycle |
| `session.participant_added` | `global` | Late-join distribution is visible to all |
| `session.ft_distributed` | `silent` | Batch FT calculation is bookkeeping |
| `session.plot_distributed` | `silent` | Batch Plot awards are bookkeeping |
| `clock.resolve_generated` | `silent` | Auto-proposal creation is system plumbing |
| `character.resolve_trauma_generated` | `silent` | Auto-proposal creation is system plumbing |
| `proposal.approved` | `bonded` | You hear about actions involving your connections |
| `proposal.rejected` | `private` | Only the proposer and GM see rejections |
| `proposal.revised` | `private` | Only the proposer and GM see revisions |
| `character.*` | `bonded` | Character changes visible to bonded entities |
| `clock.*` (except `resolve_generated`) | `bonded` | Clock changes visible to entities bonded to the clock's associated object |
| `group.*`, `location.*` | `bonded` | World object changes visible to bonded entities |
| `magic.effect_used` | `bonded` | Magic use is observable by connections |
| `story.*` | `bonded` | Story object mutations visible to bonded entities |
| GM-initiated domain events | Per action type default | GM actions reuse domain event types (e.g., `character.stress_changed`) with `actor_type: "gm"`. Default visibility per action type — see [actions.md](actions.md). |
| `player.find_time` | `private` | Resource conversion is personal |

### GM Override

The GM can change any event's visibility after creation. This allows:
- Making a secret Group event `gm_only` to prevent spoilers
- Elevating a private event to `global` for dramatic reveals
- Adjusting visibility after the fact as the narrative evolves

---

## Append-Only Guarantees

Events are **read-only** after creation. They are never modified or deleted. The only mutable field is `visibility`, which the GM can override.

Exception: `visibility` is the one field the GM can change post-creation. This is acceptable because visibility is a presentation concern, not a data integrity concern.

---

## Event Sources

Events are created by:
- **Approved proposals**: All mechanical consequences of approval produce a single event. Optionally includes a rider event.
- **Rejected proposals**: A `proposal.rejected` event is created (private visibility)
- **Revised proposals**: A `proposal.revised` event is created (private visibility)
- **GM direct actions**: Any GM state change produces an event
- **Player direct actions**: Find Time, Magic Effect use/retirement produce events
- **Session start**: Produces 3 separate events — `session.started` (global), `session.ft_distributed` (silent), `session.plot_distributed` (silent)
- **Session end**: Produces a `session.ended` event (global)
- **Clock completion**: System detects completion, produces `clock.completed` event (bonded) and auto-generates a `resolve_clock` proposal with a `clock.resolve_generated` event (silent)
- **Stress hitting max**: System detects boundary, auto-generates a `resolve_trauma` proposal (one per character, pending only) with a `character.resolve_trauma_generated` event (silent). Parallels the clock completion pattern.

Events are never created directly via the API — they are always a side-effect of state changes.

---

## Uses

- **Activity feed**: Events merged with Story entries into the unified Feed, visibility-filtered per player. See [feed.md](feed.md).
- **Session timeline**: Events filtered by `session_id` — reconstructs what happened during a session
- **Character history**: Events filtered by `event_targets` containing the character
- **Game object history**: Events filtered by `event_targets` for any game object
- **Audit trail**: Full unfiltered event log (GM only), including `silent` events via the silent feed endpoint
- **Low-level events API**: Events-only endpoint (`GET /api/v1/events`) for programmatic access, GM audit, and debugging — separate from the feed endpoints which merge events with story entries

### No System Undo for MVP

Undo is deferred to a future version. The GM corrects mistakes via direct actions, which produce their own events. The event log shows the full history, including corrections.

The `changes` field with before/after values preserves the information needed to implement undo later (by applying the inverse).

---

## Meter Boundary Patterns

Several meters have boundary behaviors — side effects that fire when a meter hits its min or max. These are hardcoded in Python (not a generic trigger system) and documented here as a cross-referenced catalog.

### The `clamped` Annotation

When a meter operation hits a boundary and the actual delta differs from the requested delta, or when the boundary triggers a side effect, the change entry gains `"clamped": true`:

```json
{
  "character.01HXYZ.stress": {"op": "meter.delta", "before": 7, "after": 8, "clamped": true}
}
```

The `clamped` flag is informational — Python code handles all boundary logic. It signals to consumers that the change was constrained or triggered additional effects.

### Boundary Catalog

| Meter | Boundary | Behavior | Spec |
|-------|----------|----------|------|
| Character Stress | Max (`9 - trauma_count`) | Auto-generates `resolve_trauma` proposal (one per character, pending only). On approval: chosen bond retired, trauma bond created, stress reset to 0. | [character-core.md](character-core.md) |
| Bond Stress (PC) (conceptually "bond charges" per [bonds.md](bonds.md)) | Max (`5 - degradations`) | Reset to 0, `stress_degradations` incremented by 1 | [bonds.md](bonds.md) |
| Free Time | Max 20 | Excess from Time Now delta lost (clamped) | [downtime.md](downtime.md) |
| Plot | Exceeds 5 | Clamped to 5 at Session End | [downtime.md](downtime.md) |
| Clock Progress | `>= segments` | Auto-generates `resolve_clock` proposal (one per clock, ever) | [game-objects.md](game-objects.md) |

### Compound Consequences

When a boundary triggers additional mutations, the pattern depends on whether those mutations happen immediately or on proposal approval.

**Immediate boundary effects** (Bond Stress / bond charges, FT cap, Plot clamp) are recorded within the **same event** (preserving the "one event per action" rule).

**Trauma** follows the auto-proposal pattern, paralleling clock completion:

1. The stress-increase event records the stress change with `clamped: true` — the stress is clamped at the max value and the event notes the boundary was hit. No bond retirement or trauma creation happens yet.
2. A `resolve_trauma` proposal is auto-generated (silent `character.resolve_trauma_generated` event).
3. On `resolve_trauma` proposal **approval**, a single approval event records all the Trauma mutations:
   - The old bond retirement (`deleted_objects`)
   - The new trauma bond creation (`created_objects`)
   - The stress reset to 0 (`meter.set`)

This means the stress-hit event and the Trauma-consequence event are **separate events** linked via `proposal_id`. The stress hit records what happened to the meter; the approval event records what the player chose and the resulting state changes.

### No Trigger System

Boundary behaviors are hardcoded Python functions, not a configurable trigger engine. This catalog documents what the code does — it is not configuration. This reinforces the project's core principle: **no DSL, all game logic in Python**.

---

## Decisions

### State is Source of Truth

- **Decision**: Mutable state is the source of truth. The event log is history, not the authoritative record.
- **Rationale**: Simpler than event sourcing. No need to replay events to get current state. Appropriate for a single-game, small-scale system.
- **Implications**: Event log can theoretically be truncated without losing current state (though we retain forever). Undo would require applying inverse operations, not replaying events.

### Events are Never Direct-Created

- **Decision**: Events are always a side-effect of state changes, never created via a direct API call.
- **Rationale**: Ensures events are accurate — every event corresponds to a real state change.
- **Implications**: Event creation is internal to the state-change handlers. The events API is read-only (except GM visibility override).

### Fully Qualified Changes Keys

- **Decision**: The `changes` field uses fully qualified keys: `{type}.{id}.{field}` where `type` is the database table name (singular). Examples: `character.01HXYZ.stress`, `slot.01HABC.charge`, `clock.01HDEF.progress`, `magic_effect.01HGHI.charges_current`. Each value carries `{op, before, after}` plus an optional `clamped` flag (see Operation Type Tags and Meter Boundary Annotations). Separate `created_objects` and `deleted_objects` lists for object lifecycle.
- **Rationale**: Fully qualified keys are unambiguous — no special-casing for primary targets vs secondary objects. Table names are what implementers already know. Before/after pairs enable future undo. The `op` tag makes the log queryable by mutation kind.
- **Implications**: State-change handlers must capture before-state before mutation and set the appropriate `op` tag. All keys include the entity's ULID. The changes JSON can be large for compound events.

### Operation Type Tags

- **Decision**: Each entry in the `changes` dict carries an `op` field: `field.set`, `meter.delta`, or `meter.set`. Set by the Python code creating the event.
- **Rationale**: Makes the event log queryable by mutation kind ("show me all meter changes") without introducing a DSL. Three tags cover all current mutations: non-numeric/unbounded sets, bounded numeric deltas, and absolute meter resets.
- **Implications**: State-change handlers must classify each mutation. `op` is part of the stored JSON value. No impact on existing key convention or object lifecycle patterns.

### Meter Boundary Annotations

- **Decision**: When a meter operation hits a boundary (actual delta differs from requested, or boundary triggers a side effect), the change entry gains `"clamped": true`.
- **Rationale**: Consumers can identify boundary-triggered changes without re-deriving meter limits. Informational only — Python code handles all boundary logic. Keeps the event log self-describing.
- **Implications**: `clamped` is an optional boolean on change entries. Only present when true. Does not affect event structure or visibility.

### Boundary Behaviors Are Hardcoded

- **Decision**: All meter boundary behaviors (Trauma auto-proposal on max stress, bond degradation on max bond stress, clock auto-proposal on completion, Plot clamp at Session End, FT cap) are hardcoded in Python. No generic trigger or rule engine.
- **Rationale**: Reinforces the project's core principle: no DSL, all game logic in Python. The boundary catalog in this spec documents what the code does — it is not configuration for a trigger system.
- **Implications**: Adding a new boundary behavior requires a code change, not a data entry. The catalog in the Meter Boundary Patterns section must be kept in sync with implementation.

### One Event Per Action

- **Decision**: Each state-changing action produces exactly one event, even if it affects multiple game objects. Compound changes go into a single event's `changes`, `created_objects`, and `deleted_objects` fields. Rider events are the exception — they're separate rows linked via `parent_event_id`.
- **Rationale**: Clean event log. One action = one event. Avoids noisy multi-event patterns. Rider events need independent targets and visibility.
- **Implications**: Events can be large for complex actions. Rider events are created in the same transaction.

### Session Start Decomposition

- **Decision**: Session start is a composite action that produces **3 separate events**: `session.started` (global, session status change), `session.ft_distributed` (silent, all character FT changes), `session.plot_distributed` (silent, all character Plot changes).
- **Rationale**: Separates the visible session lifecycle event from silent bookkeeping. Players see "Session started" without the noise of individual FT/Plot calculations. The GM can audit resource distribution via the silent feed. Different visibility levels require separate events.
- **Implications**: Exception to the one-event-per-action rule. Session start handler creates 3 events in one transaction. FT/Plot distribution events can have large `changes` payloads (one entry per participating character).

### Convention-Based Event Types

- **Decision**: Event types are free-form strings following `{domain}.{action}` convention (e.g., `character.stress_changed`, `clock.advanced`). No hardcoded enum.
- **Rationale**: Extensible without code changes. The domain prefix provides natural grouping for filtering. New event types can be added as new features are built.
- **Implications**: No compile-time type safety for event types. Naming conventions must be documented and followed. Filtering uses string prefix matching.

### Unified Character Event Types

- **Decision**: NPCs use `character.*` event types, not separate `npc.*` types. NPCs are Characters with `detail_level = simplified`.
- **Rationale**: Consistent with the unified Character model. The event's target Game Object tells you the detail_level if needed.
- **Implications**: No `npc.*` event type prefix. Filter by target's `detail_level` if NPC-specific queries are needed.

### Story Entries Are Not Events

- **Decision**: Direct story entry creation (by players or GM) does not produce an event. Story entries appear directly in the feed as `story_entry` feed items. Only Story object-level mutations (`story.created`, `story.updated`) produce events. The `work_on_project` downtime action produces a `proposal.approved` event (mechanical: FT deducted) and separately creates a story entry.
- **Rationale**: Story entries are their own feed item type — creating an event for each would duplicate content in the feed. The entry itself is the narrative content; the event would be redundant.
- **Implications**: No `story.entry_added` event type. Story entries and events are parallel feed item types merged in the feed query.

### No User-Level Events

- **Decision**: User-level actions (profile changes, starring/unstarring) do not produce events. Only game state changes are recorded in the event log.
- **Rationale**: User preferences and profile data are not game state. The user record itself tracks current state. Keeping the event log focused on game state maintains its value as a game history.
- **Implications**: No `user.*` event type prefix.

### Workflow Events

- **Decision**: Proposal rejection and revision produce events (`proposal.rejected`, `proposal.revised`) with `private` visibility.
- **Rationale**: Rejection is a GM decision worth recording. Revision is a player action that changes the proposal. Both are useful audit trail for the proposer and GM. Low noise since they're private.
- **Implications**: Proposal status changes create events even though they don't change game state. These are workflow events, not game-state events.

### Silent Event Defaults

- **Decision**: Four event types default to `silent` visibility: `session.ft_distributed`, `session.plot_distributed`, `clock.resolve_generated`, and `character.resolve_trauma_generated`. All other event types default to a visible level.
- **Rationale**: These are mechanical bookkeeping that clutters feeds without narrative value. Players see the effects (updated meters, pending proposals) without the plumbing. The GM can audit via the silent feed.
- **Implications**: Event type definitions must specify default visibility. Silent events only appear in the GM's dedicated silent feed endpoint.

### Physical Schema Alignment

- **Decision**: The event schema in this spec aligns with data-model.md: `actor_type`/`actor_id` as separate columns, targets in an `event_targets` association table, `parent_event_id` for rider events. No separate `timestamp` column — `created_at` is the only timestamp, with ULID providing sort order.
- **Rationale**: One source of truth. The domain spec should match what's actually implemented. Events are created in real-time with no backdating, so a separate `timestamp` adds complexity without value.
- **Implications**: See [data-model.md](../architecture/data-model.md) for the complete column definitions. Data-model.md `timestamp` column should be removed.

### Unified Visibility Model

- **Decision**: Events use the unified 7-level visibility model from [feed.md](feed.md): `silent`, `gm_only`, `private`, `bonded`, `familiar`, `public`, `global`. Visibility is computed on read using Character-intermediary bond-graph traversal.
- **Rationale**: One visibility model for all feed items (Events and Story entries). Compute-on-read is sufficient for 4–6 players. Character-intermediary traversal models realistic information flow.
- **Implications**: No visibility cache needed for MVP. feed.md is the authoritative spec for visibility rules.
- **Alternatives considered**: Pre-computed cache (unnecessary for this scale), separate visibility models for events vs stories (added complexity for no benefit).

### Rider Events as Separate Rows

- **Decision**: Rider events are full Event rows in the `events` table with a `parent_event_id` FK linking to the approval event. Created atomically in the same transaction. Rider events always inherit `session_id` from the parent event.
- **Rationale**: Same schema, same queryability, same visibility filtering. Rider events can have their own targets, visibility, and narrative. Session inheritance is correct because both events occur in the same session.
- **Implications**: `parent_event_id` column on events table. Rider events appear in feeds independently.

### Proposal Reference Field

- **Decision**: Events have an optional `proposal_id` field linking back to the proposal that triggered them.
- **Rationale**: Enables easy proposal → event linking. Useful for activity feed ("Player X did Y" with link to the proposal).
- **Implications**: Set by the proposal approval handler. Null for events not triggered by proposals.

### Narrative from GM + Player + System

- **Decision**: The narrative field is optional and comes from: player (submission narrative, GM can edit), GM (direct actions), or system (auto-generated for lifecycle events).
- **Rationale**: Narrative adds context to the activity feed. Player-written narrative from proposals is the most common. System narrative keeps lifecycle events readable.
- **Implications**: System must auto-generate readable narrative for session start/end events.

### Retain Forever

- **Decision**: Event log retained indefinitely. No cleanup, no archival.
- **Rationale**: For a single campaign with a small group (4–6 players + GM), the event volume is manageable. Permanent history is valuable. No benefit to archival complexity.
- **Implications**: No TTL or cleanup jobs. Database may grow over a long campaign but within manageable bounds.

### Session Auto-Capture

- **Decision**: Events generated while a Session is Active are automatically tagged with that session's `session_id`. Callers can override. Null when no session is Active. Rider events always inherit from their parent event.
- **Rationale**: Eliminates manual session tagging. Most events occur during active play. Override handles edge cases. Rider inheritance is correct since both occur in the same transaction during the same session.
- **Implications**: Event creation checks for Active session and auto-fills.

### No System Undo for MVP

- **Decision**: No undo endpoint or mechanism in MVP. GM corrects mistakes via direct actions. Undo deferred to future version.
- **Rationale**: Implementing undo (especially for compound events) adds complexity. GM direct actions provide a good-enough correction path. The before/after changes data preserves the option to add undo later.
- **Implications**: No inverse-operation logic needed for MVP. GM is the error correction mechanism.

### Generic Metadata Field

- **Decision**: Events have an optional freeform `metadata` JSON field for per-event context. Used for clock annotations (notes + refs), event-to-event links, and future extensions.
- **Rationale**: Flexible — accommodates clock annotations, related event links, and any future per-event data without schema changes.
- **Implications**: No type safety on metadata contents. Consuming code must handle varied structures.

### ULID Cursor Pagination

- **Decision**: `GET /api/v1/events` uses ULID cursor-based pagination, consistent with all feed endpoints: `?after=<ulid>&limit=N` (default 50, max 100). Response envelope: `{items, next_cursor, has_more}`.
- **Rationale**: Consistent with feed endpoint pagination. ULIDs are time-sortable, making them natural cursors. No offset drift issues.
- **Implications**: Same pagination pattern across events and feed endpoints. `next_cursor` is the ULID of the last item in the page.

### Events API Alongside Feed

- **Decision**: Keep `GET /api/v1/events` as a standalone events-only endpoint alongside the feed endpoints. The events API is the low-level, events-only view; the feed merges events with story entries.
- **Rationale**: Different audiences and use cases. Events API is useful for: GM audit (events only, no story noise), programmatic access (integrations, debugging), `proposal_id` filtering (trace a specific proposal's event). Feed endpoints serve the primary player UI.
- **Implications**: Two ways to access events: via `/events` (events only) and via `/me/feed` or `/{type}/{id}/feed` (merged with story entries). Both use the same visibility filtering and pagination.

---

## API Endpoints

- `GET /api/v1/events` — list with filtering, visibility-scoped per player
  - Pagination: `?after=<ulid>&limit=N` (default 50, max 100)
  - Response: `{items: [...], next_cursor: "<ulid or null>", has_more: true}`
  - Filters: `?type=`, `?target_type=`, `?target_id=`, `?session_id=`, `?since=`, `?until=`, `?actor_type=`, `?proposal_id=`
  - Type prefix filtering: `?type=character.*` returns all character events
  - Results filtered by unified visibility for the requesting player. GM sees all (except `silent` — use silent feed).
- `GET /api/v1/events/{id}` — single event detail (visibility check applied). `silent` events return 404 for all callers including the GM — they are only accessible via the silent feed endpoint.
- `PATCH /api/v1/events/{id}/visibility` — GM-only: change an event's visibility level

Read-only for events themselves — never created directly via API. Visibility is the only mutable field (GM-only).

Note: Events are also surfaced via the Feed endpoints (see [feed.md](feed.md)) merged with Story entries.

---

## Open Questions

_None — all questions resolved during 2026-03-12 interrogation._

---

## Implications for Other Specs

| Spec | Implication |
|------|-------------|
| [actions](actions.md) | Approved proposals generate one event with `proposal_id` set. Rider event optionally created in same transaction. Rejection and revision also generate events. |
| [downtime](downtime.md) | Session lifecycle events (start/end, FT/Plot distribution) produce events with auto-captured `session_id`. |
| [game-objects](game-objects.md) | All game object mutations produce events. Character events use `character.*` types for both PCs and NPCs. |
| [bonds](bonds.md) | Bond changes logged as events. Bond graph drives visibility (Character-intermediary traversal). Bond stress is conceptually "bond charges" per bonds.md terminology. |
| [feed](feed.md) | Events are one of two feed item types (with Story entries). Visibility model defined in feed.md. |
| [auth](auth.md) | Event visibility is bond-graph based. Auth supports per-player visibility filtering. `actor_type`/`actor_id` reference users. |
| [architecture/data-model](../architecture/data-model.md) | Aligned. No separate `timestamp` column (uses `created_at` only). Changes key convention `{type}.{id}.{field}` documented. |

---

_Last updated: 2026-03-16 (verified against Phase 4 implementation: clarified that GET /events/{id} returns 404 for silent events for all callers including the GM — silent events are only accessible via the dedicated silent feed endpoint. Updated 2026-03-16: added session.participant_added default visibility (global) — verified against Story 5.1.2 implementation.)_
