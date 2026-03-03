# Events — Domain Specification

**Status**: 🟢 Complete
**Last interrogated**: 2026-03-01
**Last verified**: —
**Depends on**: [game-objects](game-objects.md) (bond graph for visibility)
**Depended on by**: [proposals](proposals.md), [downtime](downtime.md)

---

## Overview

The event log is an append-only record of every state change in the system. Events provide history, audit trail, activity feed, and session timelines. State is the source of truth — events are the history.

A distinctive feature is **bond-distance visibility**: events are visible to players based on their character's proximity in the bond graph, creating an emergent information network where you learn about things you're connected to.

---

## Core Concepts

### Event Schema

Every mutation to game state produces an event record:

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `id` | string | yes | Primary key |
| `type` | string | yes | Convention-based: `{domain}.{action}` (e.g., `character.stress_changed`, `clock.advanced`) |
| `actor` | JSON | yes | `{type: 'player'\|'gm'\|'system', id?: string}` — who caused the change |
| `targets` | list of refs | yes | Game objects affected. First element is primary. All affected objects listed. |
| `changes` | JSON | yes | Keyed before/after pairs: `{field: {before: X, after: Y}}` |
| `created` | JSON list | no | Objects created by this event: `[{type, id, ...snapshot}]` |
| `deleted` | JSON list | no | Objects deleted (soft): `[{type, id}]` |
| `narrative` | text | no | Describes the fiction. Source: GM (proposals/direct actions), system (auto-generated for lifecycle events), or player (direct actions like Effect Use). |
| `proposal_id` | ref | no | Link to the proposal that triggered this event (when applicable) |
| `session_id` | ref | no | Auto-captured from Active session. Override-capable. Null when no session is Active. |
| `visibility` | string | yes | One of: `global`, `gm_only`, `private`, `bonded`, `familiar`, `public`. Default per event type, GM can override. |
| `metadata` | JSON | no | Freeform context: clock annotations (`notes`, `related_events`, `related_objects`), or any per-event data |
| `timestamp` | datetime | yes | When the event was created |

### Changes Field

The `changes` field uses **keyed before/after pairs**:

```json
{
  "character.gnosis": {"before": 15, "after": 5},
  "character.stress": {"before": 2, "after": 4},
  "trait_42.charges": {"before": 3, "after": 2},
  "bond_7.stress": {"before": 1, "after": 2}
}
```

- Keys use dotted paths to identify the field: `{object_type_or_id}.{field_name}`
- Values are `{before, after}` pairs — enables inversion for future undo
- For compound changes (e.g., a proposal approval affecting multiple objects), all changes go in a single event
- New objects go in the `created` list, not in `changes`
- Soft-deleted objects go in the `deleted` list

### Compound Changes

**One event per state-changing action.** A single proposal approval that modifies Gnosis, creates a Magic Effect, spends a trait charge, and strains a bond produces one event with:
- `changes`: all field mutations across all affected objects
- `created`: any new objects (Magic Effects, Bond instances, etc.)
- `deleted`: any soft-deleted objects (retired traits, etc.)
- `targets`: all affected game objects listed

This matches the "one event per approval" decision from the proposals spec.

### Event Types

Convention-based strings following `{domain}.{action}` naming:

| Domain | Example Types |
|--------|--------------|
| `proposal` | `proposal.approved`, `proposal.rejected`, `proposal.revised` |
| `character` | `character.stress_changed`, `character.gnosis_changed`, `character.meter_updated` |
| `trait` | `trait.charge_spent`, `trait.recharged`, `trait.retired`, `trait.created` |
| `bond` | `bond.stress_changed`, `bond.degraded`, `bond.maintained`, `bond.retired`, `bond.created` |
| `magic` | `magic.effect_created`, `magic.effect_used`, `magic.effect_retired`, `magic.effect_charged` |
| `clock` | `clock.advanced`, `clock.completed`, `clock.created`, `clock.modified` |
| `session` | `session.started`, `session.ended`, `session.participant_added`, `session.participant_removed` |
| `npc` | `npc.created`, `npc.updated`, `npc.deleted` |
| `group` | `group.created`, `group.updated`, `group.bond_changed` |
| `location` | `location.created`, `location.updated` |
| `story` | `story.created`, `story.updated`, `story.entry_added` |
| `player` | `player.find_time` |
| `gm` | `gm.direct_action` |

No category field — the domain prefix provides natural grouping. New types can be added without schema changes.

### Actor Field

Identifies who caused the event:

```json
{"type": "player", "id": "player_42"}   // Player action (proposals, direct actions)
{"type": "gm", "id": "gm_1"}            // GM action (approvals, direct actions)
{"type": "system"}                        // Automated (FT distribution, clock ticks)
```

### Narrative Field

The narrative field is optional and comes from different sources:

- **Proposal approvals**: GM's `gm_narrative` from the approval payload
- **GM direct actions**: GM provides narrative text
- **Player direct actions**: Player provides narrative (e.g., Magic Effect use)
- **System actions**: Auto-generated descriptive text (e.g., "Session 5 started. Free Time distributed to 4 participants.")

### Session Auto-Capture

Events generated while a Session is Active are automatically tagged with that session's ID (decided in [game-objects](game-objects.md)). Callers can override with a specific `session_id`. When no session is Active, `session_id` is null.

### Metadata Field

A freeform JSON field for per-event context. Primary use cases:

- **Clock annotations**: `{notes: string, related_events: [event_ids], related_objects: [object_ids]}` — explaining why a clock was adjusted
- **Event-to-event links**: `{related_events: [event_ids]}` — linking an event to earlier events for context
- **Future extensions**: Any per-event data that doesn't fit the core schema

---

## Bond-Distance Visibility

Events are visible to players based on their character's proximity in the bond graph. This creates an emergent information network — you learn about things you're connected to.

### Visibility Levels

| Level | Who sees it | Hop distance |
|-------|------------|--------------|
| `global` | All players | — |
| `gm_only` | GM only | — |
| `private` | Actor + owner(s) of target object(s) | — |
| `bonded` | Anyone with a direct bond to any target | 1 hop |
| `familiar` | Anyone within 2 hops via bond graph | 2 hops |
| `public` | Anyone within 3 hops via bond graph | 3 hops |

**Default**: `bonded` for most events. Each event type has a default visibility level.

### Bond Graph

The visibility graph includes **all bonds**:
- **PC Bonds** (Trait Instances on character sheets)
- **Lightweight bonds** (on NPCs, Groups, Locations — see [game-objects](game-objects.md))

The unified bond graph creates a social network. A PC bonded to an NPC, where that NPC is bonded to a Group, creates a 2-hop path — the PC would see `familiar`-level events about that Group.

### Hop Traversal

- **1-hop (bonded)**: Player's character has a direct Bond to any of the event's `targets`. Also includes: the character *is* one of the targets.
- **2-hop (familiar)**: Player's character has a Bond to entity X, and entity X has a bond to any of the event's `targets`.
- **3-hop (public)**: Three bond links between the character and any target.

### Defaults Per Event Type

| Type pattern | Default visibility | Rationale |
|-------------|-------------------|-----------|
| `session.*` | Matches target | Session events inherit from target's proximity |
| `proposal.approved` | `bonded` | You hear about actions involving your connections |
| `proposal.rejected` | `private` | Only the proposer and GM see rejections |
| `character.*` | `bonded` | Character changes visible to bonded entities |
| `clock.*` | `bonded` | Clock changes visible to entities bonded to the clock/group |
| `npc.*`, `group.*`, `location.*` | `bonded` | World object changes visible to bonded entities |
| `magic.effect_used` | `bonded` | Magic use is observable by connections |
| `gm.direct_action` | `gm_only` | GM corrections are private by default |
| `player.find_time` | `private` | Resource conversion is personal |
| System lifecycle events | Matches target | Inherit from affected object's proximity |

### GM Override

The GM can change any event's visibility after creation. This allows:
- Making a secret Group event `gm_only` to prevent spoilers
- Elevating a private event to `global` for dramatic reveals
- Adjusting visibility after the fact as the narrative evolves

### Caching

Visibility is **pre-computed and cached** per character. The cache is invalidated when bonds change (created, retired, or modified). This avoids expensive graph traversal on every event query.

Implementation note: The cache maps each character to the set of game objects within 1, 2, and 3 hops. When querying events, the system checks if any of the event's targets fall within the character's cached hop sets.

---

## Append-Only Guarantees

Events are **read-only** after creation. They are never modified or deleted. The only mutable field is `visibility`, which the GM can override.

Exception: `visibility` is the one field the GM can change post-creation. This is acceptable because visibility is a presentation concern, not a data integrity concern.

---

## Event Sources

Events are created by:
- **Approved proposals**: All mechanical consequences of approval produce a single event
- **Rejected proposals**: A `proposal.rejected` event is created
- **Revised proposals**: A `proposal.revised` event is created
- **GM direct actions**: Any GM state change produces an event
- **Player direct actions**: Find Time, Magic Effect use/retirement produce events
- **System actions**: Session start (FT/Plot distribution), session end, clock completions

Events are never created directly via the API — they are always a side-effect of state changes.

---

## Uses

- **Activity feed**: Recent events filtered by bond-distance visibility per player
- **Session timeline**: Events filtered by `session_id` — reconstructs what happened during a session
- **Character history**: Events filtered by `targets` containing the character
- **Game object history**: Events filtered by `targets` for any game object (NPC, Group, Clock, etc.)
- **Audit trail**: Full unfiltered event log (GM only)

### No System Undo for MVP

Undo is deferred to a future version. The GM corrects mistakes via direct actions, which produce their own events. The event log shows the full history, including corrections.

The `changes` field with before/after values preserves the information needed to implement undo later (by applying the inverse).

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

### Keyed Before/After Changes

- **Decision**: The `changes` field uses keyed before/after pairs: `{field: {before: X, after: Y}}`. Keys use dotted paths for cross-object fields. Separate `created` and `deleted` lists for object lifecycle.
- **Rationale**: Before/after is the most readable format. Enables future undo (apply inverse). Dotted paths handle compound changes across multiple objects. Separate lists for creations/deletions keep the schema clean.
- **Implications**: State-change handlers must capture before-state before mutation. The changes JSON can be large for compound events.

### One Event Per Action

- **Decision**: Each state-changing action produces exactly one event, even if it affects multiple game objects. Compound changes go into a single event's `changes`, `created`, and `deleted` fields.
- **Rationale**: Clean event log. One action = one event. Avoids noisy multi-event patterns. Matches the "one event per approval" from proposals spec.
- **Implications**: Events can be large for complex actions (e.g., magic proposals with sacrifice + effect creation + trait charge + bond strain).

### Convention-Based Event Types

- **Decision**: Event types are free-form strings following `{domain}.{action}` convention (e.g., `character.stress_changed`, `clock.advanced`). No hardcoded enum.
- **Rationale**: Extensible without code changes. The domain prefix provides natural grouping for filtering. New event types can be added as new features are built.
- **Implications**: No compile-time type safety for event types. Naming conventions must be documented and followed. Filtering uses string prefix matching.

### No Category Field

- **Decision**: No separate category field. The domain prefix in the type string (`character.*`, `clock.*`, `session.*`) provides natural grouping.
- **Rationale**: A category field would duplicate information already in the type string. The prefix convention is sufficient for filtering.
- **Implications**: UI filtering extracts the domain from the type string.

### Proposal Reference Field

- **Decision**: Events have an optional `proposal_id` field linking back to the proposal that triggered them.
- **Rationale**: Enables easy proposal → event linking. Useful for activity feed ("Player X did Y" with link to the proposal).
- **Implications**: Set by the proposal approval handler. Null for events not triggered by proposals.

### Narrative from GM + System

- **Decision**: The narrative field is optional and comes from: GM (approval narrative, direct actions), player (direct actions like Effect Use), or system (auto-generated for lifecycle events).
- **Rationale**: Narrative adds context to the activity feed. GM narrative is most common (from proposal approvals). System narrative keeps lifecycle events readable.
- **Implications**: System must auto-generate readable narrative for session start/end, FT distribution, etc.

### Retain Forever

- **Decision**: Event log retained indefinitely. No cleanup, no archival.
- **Rationale**: For a single campaign with a small group (4–6 players + GM), the event volume is manageable. Permanent history is valuable. No benefit to archival complexity.
- **Implications**: No TTL or cleanup jobs. Database may grow over a long campaign but within manageable bounds.

### Actor Type + Ref Pair

- **Decision**: `actor` is a JSON object: `{type: 'player'|'gm'|'system', id?: string}`. For player/GM, includes their ID. For system, no ID.
- **Rationale**: Distinguishes between player actions, GM actions, and automated system actions. Simple structure covers all cases.
- **Implications**: Actor field is not a simple foreign key — it's a typed reference.

### Targets as List

- **Decision**: `targets` is always a list of game object references. First element is the primary target. All affected objects are listed.
- **Rationale**: Compound events affect multiple objects (character + traits + bonds). A list captures all of them, enabling rich querying ("show me all events affecting this NPC").
- **Implications**: Event queries can filter by any target in the list. Index on target IDs for performance.

### Generic Metadata Field

- **Decision**: Events have an optional freeform `metadata` JSON field for per-event context. Used for clock annotations (notes + refs), event-to-event links, and future extensions.
- **Rationale**: Flexible — accommodates clock annotations, related event links, and any future per-event data without schema changes.
- **Implications**: No type safety on metadata contents. Consuming code must handle varied structures.

### Bond-Distance Visibility

- **Decision**: Events have a `visibility` field with 6 levels: `global`, `gm_only`, `private`, `bonded` (1-hop, default), `familiar` (2-hop), `public` (3-hop). Visibility is determined by bond-graph proximity between the querying player's character and the event's targets.
- **Rationale**: Creates an emergent information network. Players learn about things they're connected to. Deeper connections (familiar, public) propagate information further. The bond graph — both PC Bonds and lightweight bonds on world objects — forms a social network.
- **Implications**: Requires bond-graph traversal for visibility checks. Cached per character, invalidated on bond changes. GM can override any event's visibility. Significant architectural feature that affects all event queries.
- **Alternatives considered**: All-visible (too simple, spoiler-prone), GM-manual-per-event (too tedious), role-based (misses the social graph opportunity).

### No System Undo for MVP

- **Decision**: No undo endpoint or mechanism in MVP. GM corrects mistakes via direct actions. Undo deferred to future version.
- **Rationale**: Implementing undo (especially for compound events) adds complexity. GM direct actions provide a good-enough correction path. The before/after changes data preserves the option to add undo later.
- **Implications**: No inverse-operation logic needed for MVP. GM is the error correction mechanism.

### Session Auto-Capture

- **Decision**: Events generated while a Session is Active are automatically tagged with that session's `session_id`. Callers can override. Null when no session is Active.
- **Rationale**: Eliminates manual session tagging. Most events occur during active play. Override handles edge cases.
- **Implications**: Event creation checks for Active session and auto-fills. Decided in [game-objects](game-objects.md), documented here for completeness.

---

## API Endpoints

- `GET /api/v1/events` — list with filtering, visibility-scoped per player
  - Filters: `?type=`, `?target=`, `?session_id=`, `?since=`, `?actor_type=`, `?proposal_id=`
  - Type prefix filtering: `?type=character.*` returns all character events
  - Results filtered by bond-distance visibility for the requesting player. GM sees all.
- `GET /api/v1/events/{id}` — single event detail (visibility check applied)
- `PATCH /api/v1/events/{id}/visibility` — GM-only: change an event's visibility level

Read-only for events themselves — never created directly via API. Visibility is the only mutable field (GM-only).

---

## Open Questions

None — all questions resolved.

---

## Implications for Other Specs

| Spec | Implication |
|------|-------------|
| [proposals](proposals.md) | Approved proposals generate one event with `proposal_id` set. Rejection and revision also generate events. |
| [downtime](downtime.md) | Session lifecycle events (start/end, FT distribution, clock adjustments) all produce events with auto-captured `session_id`. |
| [game-objects](game-objects.md) | All game object mutations produce events. Bond graph (PC + lightweight) drives event visibility. |
| [character-core](character-core.md) | Character state changes produce events. Character bond graph determines what events the player sees. |
| [bonds](bonds.md) | 🔄 Bond changes invalidate the visibility cache. Both PC Bonds and lightweight bonds participate in the visibility graph. |
| [auth](auth.md) | 🔄 Event visibility is bond-distance based, not role-based (except `gm_only` and `global`). Auth must support per-player visibility filtering. The `actor` field uses a typed ref, not a simple user ID. |
| [architecture/data-model](../architecture/data-model.md) | 🔄 Event model with `changes` JSON, `created`/`deleted` lists, `targets` list, `metadata` JSON, `visibility` enum, `actor` typed ref. Bond-graph visibility cache model. |

---

_Last updated: 2026-03-01 (interrogation complete)_
