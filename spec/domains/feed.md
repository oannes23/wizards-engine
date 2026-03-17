# Feed — Domain Specification

**Status**: 🟢 Complete
**Last interrogated**: 2026-03-12
**Last verified**: 2026-03-16
**Depends on**: [game-objects](game-objects.md), [bonds](bonds.md), [events](events.md)
**Depended on by**: [auth](auth.md)

---

## Overview

The **Feed** is a unified, visibility-filtered view of activity on Game Objects. It merges **Events** and **Story entries** into a single chronological stream per Game Object, filtered by the authenticated player's bond-graph proximity.

The Feed is a **query pattern**, not a stored entity. No new data model — just API endpoints that merge existing Events (via `targets`) and Story entries (via `game_object_refs` and owner associations) with unified visibility filtering.

The bond graph drives three computed systems from one algorithm:
- **Feed visibility** — who can see which Events and Story entries
- **Bond-Distance Presence** — who is present at which Locations (see [bonds.md](bonds.md))
- **Story visibility** — which Stories a player can see and contribute to

---

## Unified Visibility Model

All feed items (Events and Story entries) use the same 7-level visibility system, computed from the bond graph on read.

### Visibility Levels

| Level | Who Sees | Hop Distance | Description |
|-------|----------|-------------|-------------|
| `silent` | GM only (silent feed) | — | Bookkeeping changes that don't need to surface. Only visible in a dedicated GM-only "silent" feed. |
| `gm_only` | GM only | — | Sensitive GM actions. Visible in the GM's normal feed. |
| `private` | Owner-scoped + GM | 0-hop | PC-owned → that PC + GM. NPC/Group/Location-owned → GM only. |
| `bonded` | Direct bond to target + GM | 1-hop | Only PCs with a direct bond to any target Game Object. |
| `familiar` | 2-hop bond graph + GM | 2-hop | Direct bond + paths through NPCs (see traversal rules below). **Default for Stories.** |
| `public` | 3-hop bond graph + GM | 3-hop | One more hop out from `familiar` (see traversal rules below). |
| `global` | All players + GM | All | System announcements, global events. |

### Bond-Graph Traversal Rules

The `familiar` level (2-hop) traverses:

1. **Direct bond**: PC → target Game Object (1-hop)
2. **Through Group membership**: PC → Group → NPC members of that Group (PC bonded to Group, NPC also bonded to Group)
3. **Through Location**: PC → Location → NPCs bonded to that Location
4. **Through NPC**: PC → NPC → Groups/Locations that NPC is bonded to

The `public` level (3-hop) adds one more hop:

5. **NPC → Group/Location → NPC**: PC → NPC → Group/Location → another NPC
6. **Group/Location → NPC → Group/Location**: PC → Group/Location → NPC → another Group/Location

**Key**: Characters (PCs and NPCs) serve as the intermediary nodes in the bond graph. You can't traverse through two Groups or two Locations — the path must alternate through Characters. PCs are valid intermediaries — richer than NPCs since they can connect to other Characters.

### Traversal Constraints

- **Soft-deleted Game Objects are excluded** from traversal. Their bonds exist but are dead ends.
- **All bond types participate**: PC bonds (mechanical), NPC bonds (descriptive), Group bonds (Relations, Holdings), Location bonds. The traversal doesn't care about mechanical depth.
- **PCs are valid intermediaries**: The Character-intermediary rule applies to all Characters (PCs and NPCs). PCs are richer intermediary nodes than NPCs since they can connect to other Characters via mechanical bonds.
- **Computed on read**: No caching. SQLite handles it for 4–6 players.

### Private Visibility — Owner Determination

For Events, `private` visibility uses a **union rule** — an event is visible to:
- The **actor's character** (the PC whose player triggered the event)
- The **primary target's owner** (if the primary target is a PC, that PC sees it)
- The **GM** (always)

If neither the actor nor the primary target is a PC, the event is GM-only.

### GM Override

The GM can manually grant visibility to specific players, overriding the bond-graph computation:
- **Per-Event**: GM can override any Event's visibility level
- **Per-Story**: GM can override the Story's base `visibility_level` AND/OR add player IDs to `visibility_overrides`

### Default Visibility by Item Type

| Item Type | Default Level | Notes |
|-----------|--------------|-------|
| Story entries | `familiar` | Stories default to familiar. Inherited by their entries. |
| Events | Varies by event type | Each event type definition specifies its default. E.g., `character.stress_changed` might default to `bonded`, `session.started` to `global`. |

---

## Story Visibility

Story visibility is derived from the Story's **owners** and the unified visibility model:

### Rules

1. **PC-owned Stories** (`private`): Only the owning PC and GM can see. Even if the Story also has NPC/Group/Location owners, the union rule applies — but the PC-owner's own access is guaranteed.
2. **NPC/Group/Location-owned Stories**: Visible at `familiar` level by default — any PC whose bond-graph traversal reaches that owner (within 2 hops) can see the Story.
3. **Mixed owners**: Visibility is the **union** of all owner rules. If a Story is owned by both a PC and a Group, the PC can see it (owner), AND anyone bonded to the Group can see it (familiar traversal through the Group owner).
4. **GM override**: GM can add specific player IDs to `visibility_overrides`, granting access regardless of bond-graph proximity.
5. **See = write**: If a player can see a Story, they can add entries to it.

### Private = Owner-Scoped

The `private` visibility level is owner-scoped:
- A `private` Story owned by a PC → that PC + GM can see
- A `private` Story owned by an NPC/Group/Location → GM only
- This means only PC-owned private Stories have non-GM player visibility

---

## Feed Item Response Shape

Feed items use a **discriminated union** — each item has a `type` field (`event` or `story_entry`) with common fields at the top level and type-specific fields alongside.

### Common Fields (All Feed Items)

| Field | Type | Notes |
|-------|------|-------|
| `id` | ULID | The Event or Story Entry ID |
| `type` | string | `event` or `story_entry` |
| `timestamp` | datetime | When it happened |
| `narrative` | text (nullable) | Narrative text from GM/player/system |
| `visibility` | string | The item's visibility level |
| `targets` | list of `{type, id}` | Involved Game Objects (see below) |
| `is_own` | boolean | True if the authenticated player is the actor |

### Target Derivation

- **Events**: Targets from `event_targets` association table
- **Story entries**: Union of the Story's owners + the entry's `game_object_refs`

### Type-Specific Fields

**`event` items** include: `event_type` (the `{domain}.{action}` string), `actor_type`, `actor_id`, `changes`, `created_objects`, `deleted_objects`, `proposal_id`, `parent_event_id`, `session_id`, `metadata`.

**`story_entry` items** include: `story_id`, `story_name`, `entry_text`, `author_id`.

### Rider Events

Rider events (linked via `parent_event_id`) appear as **separate feed items** with their own visibility. The `parent_event_id` field allows the client to group them visually with their parent event if desired.

---

## Pagination

All feed endpoints use **ULID cursor-based pagination**.

### Query Parameters

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `after` | ULID | — | Return items after this cursor (exclusive). Items sorted newest-first. |
| `limit` | integer | 50 | Number of items per page. Max 100. |

### Response Envelope

```json
{
  "items": [...],
  "next_cursor": "<ulid or null>",
  "has_more": true
}
```

`next_cursor` is the ID of the last item in the page. Pass it as `?after=` for the next page. `null` when no more items exist.

---

## Feed Filtering

All feed endpoints support the same filter parameters (matching the Events API):

| Parameter | Type | Notes |
|-----------|------|-------|
| `type` | string | Event type prefix filter (e.g., `?type=character.*`). Only applies to `event` items. |
| `target_type` | string | Filter by target Game Object type (`character`, `group`, `location`) |
| `target_id` | string | Filter by specific target Game Object ID |
| `actor_type` | string | Filter by actor type (`player`, `gm`, `system`). Only applies to `event` items. |
| `session_id` | ULID | Filter by session |
| `since` | datetime | Items after this timestamp (inclusive) |
| `until` | datetime | Items before this timestamp (inclusive) |

Filters are combined with AND. Filters that only apply to events (`type`, `actor_type`) exclude all `story_entry` items when used.

---

## Feed Endpoints

Four endpoints provide different scopes of the same unified feed:

### Per-Game Object Feed

`GET /api/v1/{type}/{id}/feed`

Where `{type}` is `characters`, `groups`, or `locations`.

Returns a chronological stream of Events and Story entries targeting/involving that Game Object, filtered by the authenticated player's visibility. Includes:
- Events where the Game Object is a target
- Story entries on Stories owned by the Game Object
- Story entries with `game_object_refs` including the Game Object

**Access**: Any player can view a Game Object's feed if they can access that Game Object. Items within the feed are individually visibility-filtered.

### Complete Personal Feed

`GET /api/v1/me/feed`

Returns all feed items visible to the authenticated player across all their bonds. Merges Events and Story entries from all Game Objects reachable via the player's bond graph, within the visibility level of each item. Includes the player's own actions, flagged with `is_own: true`.

### Starred Feed

`GET /api/v1/me/feed/starred`

Same as the complete feed, but filtered to only Game Objects the player has starred.

### GM Silent Feed

`GET /api/v1/me/feed/silent` (GM only)

Returns all `silent`-level Events. Story entries are excluded (they do not have a `silent` visibility level). The GM's audit log for bookkeeping changes. Uses the same pagination and filtering as all other feed endpoints.

### Starring API

- `GET /api/v1/me/starred` — list starred Game Objects
- `POST /api/v1/me/starred` — star a Game Object `{type, id}`. Returns 201 on success. Returns 200 if the object is already starred (idempotent). Returns 404 if the Game Object does not exist or is soft-deleted.
- `DELETE /api/v1/me/starred/{type}/{id}` — unstar. Returns 204 whether or not the object was starred (idempotent).

Starring is stored in the `starred_objects` table (typed Game Object refs per user).

---

## Decisions

### Feed Is a Query Pattern

- **Decision**: The Feed is a merged, visibility-filtered view of existing Events and Story entries. No new data model. API endpoints query and merge existing data.
- **Rationale**: Events and Story entries already exist with all necessary fields (`targets`, `game_object_refs`, owner associations). A query pattern avoids data duplication and keeps the system simple.
- **Implications**: Feed endpoints may be slower than pre-computed feeds, but SQLite handles it for 4–6 players.

### Unified 7-Level Visibility

- **Decision**: Seven visibility levels (silent, gm_only, private, bonded, familiar, public, global) applied uniformly to Events and Story entries. Replaces the previous 6-level event-specific model.
- **Rationale**: Events and Stories share the same bond-graph visibility pattern. One model is simpler to implement and reason about.
- **Implications**: Events spec updated to reference this model. `silent` is new. `familiar` and `public` now defined by the bond-graph Character-intermediary traversal pattern.

### Characters as Bond-Graph Intermediaries

- **Decision**: In the `familiar` (2-hop) and `public` (3-hop) traversal, Characters (PCs and NPCs) serve as the intermediary nodes. After a non-Character node (Group or Location), the next hop must go through a Character. The first hop from any starting node can go to any type. PCs are valid intermediaries — richer than NPCs since they can connect to other Characters.
- **Rationale**: This models real-world information flow: you learn about a Group's members through your Group connection, not about random other Groups. Characters are the social connective tissue.
- **Implications**: Bond-graph traversal algorithm must track node types during hop expansion. Rename from "NPC-intermediary" to "Character-intermediary" across all specs.

### Stories Default to Familiar

- **Decision**: Stories use `familiar` as their default visibility level.
- **Rationale**: Stories are collaborative narrative content that should be visible to players with reasonable proximity. `familiar` (2-hop) provides meaningful reach without exposing everything.
- **Implications**: Most Stories are visible to players with 2-hop bond-graph connections to any owner.

### Story Mixed Owners — Union Visibility

- **Decision**: A Story can have owners of any Game Object type. Visibility is the union of all owner rules.
- **Rationale**: Narrative threads involve multiple entities. Union ensures the broadest reasonable access.
- **Implications**: Visibility computation iterates all owners.

### GM Visibility Override

- **Decision**: GM can override visibility per-Event (change level) and per-Story (add player IDs to `visibility_overrides`).
- **Rationale**: Narrative flexibility. Sometimes bond-graph proximity doesn't match the GM's intent.
- **Implications**: Override data stored on Event and Story records.

### Silent Visibility Level

- **Decision**: `silent` is a new visibility level. Items at this level don't appear in any feed except the GM's dedicated silent feed.
- **Rationale**: Bookkeeping events (automated system changes, internal adjustments) clutter the feed without adding narrative value. The GM needs an audit log but players shouldn't see it.
- **Implications**: New GM-only endpoint. Event type definitions can specify `silent` as default.

### Starring — Simple List on User

- **Decision**: Starring is a list of typed Game Object refs on the User record. Starred feed = personal feed filtered to starred objects.
- **Rationale**: Minimal implementation. Players track a handful of important Game Objects. No need for categories, ordering, or metadata.
- **Implications**: User model gets `starred_game_objects` field. Starring API is three simple endpoints.

### Three Feed Endpoints

- **Decision**: Three player endpoints (per-Game Object, personal, starred) plus a GM-only silent feed. Four total.
- **Rationale**: Covers the three natural viewing contexts: "what's happening with this entity", "what's happening in my world", and "what's happening with things I'm tracking".
- **Implications**: All endpoints use the same visibility filtering, pagination, and filtering logic, just with different scope.

### ULID Cursor Pagination

- **Decision**: All feed endpoints use ULID cursor-based pagination. `?after=<ulid>&limit=N`. Default page size 50, max 100.
- **Rationale**: ULIDs are time-sortable, making them natural cursors. No offset drift issues when new items are inserted between page loads.
- **Implications**: Response envelope includes `next_cursor` and `has_more`. Same pagination for all endpoints including the silent feed.

### Discriminated Union Feed Items

- **Decision**: Feed items are a discriminated union with `type` field (`event` or `story_entry`). Common fields at top level: `id`, `type`, `timestamp`, `narrative`, `visibility`, `targets`, `is_own`. Type-specific fields alongside.
- **Rationale**: Common fields enable unified rendering (timeline, filtering). Type-specific fields allow rich display per item type. Client switches on `type`.
- **Implications**: Frontend needs a feed item renderer that dispatches on `type`.

### Private Visibility — Union of Actor and Primary Target

- **Decision**: For `private` events, visibility is the union of the actor's character and the primary target's owner (if PC). Both see the event, plus the GM.
- **Rationale**: Broadest reasonable access for private events. The person who did it AND the person it happened to should both see it.
- **Implications**: Visibility computation must resolve both actor → user → character and primary target → PC owner.

### Story Base Visibility Override

- **Decision**: Stories have a nullable `visibility_level` field. When set by the GM, it overrides the default `familiar`. Combined with `visibility_overrides` (player ID list) for per-player grants.
- **Rationale**: The GM needs to restrict or expand Story visibility at the level, not just per-player. E.g., making a Story `bonded` or `public`.
- **Implications**: `stories` table gets a `visibility_level` column. Story visibility computation checks this field first, falls back to `familiar`.

### Full Filter Set on Feed Endpoints

- **Decision**: All feed endpoints support the same filters as the Events API: `type`, `target_type`, `target_id`, `actor_type`, `session_id`, `since`, `until`. Filters combined with AND. Event-only filters (`type`, `actor_type`) exclude Story entries when used.
- **Rationale**: Maximum flexibility. The feed is the primary interface for players — filtering should be rich. Implementation reuses the Events API filter logic.
- **Implications**: Story entries are excluded from results when event-only filters are active.

### Own Actions Included with Flag

- **Decision**: The `/me/feed` endpoint includes the player's own actions with an `is_own: true` boolean flag.
- **Rationale**: Complete timeline — players see everything visible to them in one stream. The flag lets the client style own actions differently or filter them out.
- **Implications**: Feed query must resolve the authenticated user's character ID and set `is_own` per item.

### Story Entry Targets — Union of Owners and Refs

- **Decision**: For Story entry feed items, `targets` is the union of the Story's owners and the entry's `game_object_refs`.
- **Rationale**: Both owners and refs represent Game Objects involved in the narrative. Union gives the fullest picture for filtering and display.
- **Implications**: Story entry target computation joins `story_owners` and entry-level `game_object_refs`.

### Rider Events as Separate Feed Items

- **Decision**: Rider events appear as separate feed items with their own visibility. `parent_event_id` field enables client-side grouping.
- **Rationale**: Independent visibility per rider event. Simple feed logic — no special nesting. Client groups visually if desired.
- **Implications**: Client should check `parent_event_id` to optionally group related events.

---

## API Endpoints

### Feed Endpoints
- `GET /api/v1/characters/{id}/feed` — Character feed (visibility-filtered)
- `GET /api/v1/groups/{id}/feed` — Group feed (visibility-filtered)
- `GET /api/v1/locations/{id}/feed` — Location feed (visibility-filtered)
- `GET /api/v1/me/feed` — complete personal feed (includes own actions with `is_own` flag)
- `GET /api/v1/me/feed/starred` — starred feed
- `GET /api/v1/me/feed/silent` — GM-only silent feed

All feed endpoints support: `?after=<ulid>&limit=<int>&type=&target_type=&target_id=&actor_type=&session_id=&since=&until=`

### Starring
- `GET /api/v1/me/starred` — list starred Game Objects
- `POST /api/v1/me/starred` — star `{type, id}`
- `DELETE /api/v1/me/starred/{type}/{id}` — unstar

### Story Visibility (GM)
- `PATCH /api/v1/stories/{id}` — GM can set `visibility_level` and `visibility_overrides`

---

## Implications for Other Specs

| Spec | Implication |
|------|-------------|
| [events](events.md) | 🔄 Unified visibility model replaces the 6-level system. `silent` added. `familiar` and `public` redefined by bond-graph traversal. Events reference feed.md for visibility. Default visibility per event type definition. |
| [game-objects](game-objects.md) | Stories now have `visibility_level` (nullable) and `visibility_overrides`. Story entry access = see = write. Feed endpoints on Game Object routes. |
| [bonds](bonds.md) | Bond graph traversal algorithm must track node types for Character-intermediary pattern. Soft-deleted objects excluded. |
| [auth](auth.md) | 🔄 `starred_objects` table. `/me/feed` and `/me/starred` endpoints. GM role required for silent feed and story visibility override. |
| [architecture/data-model](../architecture/data-model.md) | ✅ `starred_objects` table. `stories.visibility_level` column. `stories.visibility_overrides` JSON. No new tables for Feed itself. |

---

## Open Questions

_None — all questions resolved during 2026-03-12 interrogation._

---

_Last updated: 2026-03-16 (verified against Phase 4 implementation: GM silent feed excludes story entries (they have no silent visibility level); POST /me/starred is idempotent — returns 200 if already starred, 201 on new star, 404 if object not found; DELETE /me/starred/{type}/{id} returns 204 whether or not the object was starred.)_
