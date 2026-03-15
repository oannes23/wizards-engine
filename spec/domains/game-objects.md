# Game Objects — Domain Specification

**Status**: 🟢 Complete
**Last interrogated**: 2026-03-13
**Last verified**: —
**Depends on**: None (primitive)
**Depended on by**: [character-core](character-core.md), [bonds](bonds.md), [events](events.md), [downtime](downtime.md), [feed](feed.md)

---

## Overview

**Game Objects** are the things that exist "in the fiction" — the entities that populate the game world. There are exactly three types: **Characters**, **Groups**, and **Locations**.

**Bonds** are the connections between Game Objects. Every relationship in the system is represented as a Bond — whether it's a PC's deep relationship with an NPC, a Group's alliance with another Group, or a Character's connection to a place. Bonds are a unified concept with varying mechanical depth depending on context.

**System Entities** (Clocks, Sessions, Stories) are tracking and organizational tools. They are *not* Game Objects — they don't exist "in the fiction" in the same way and are not bond targets.

A core design principle is **Deferred Narrative Resolution** — game state is intentionally left ambiguous until narratively observed. NPCs exist in a probability smear across their bonded locations. Group projects progress mechanically but their outcomes are defined retroactively. The system supports fuzzy/potential state alongside concrete state.

---

## Game Object Types

### Characters

Characters represent beings in the fiction — both player characters (PCs) and non-player characters (NPCs). **NPCs are Characters without a Player assigned.** The hierarchy is:

- **Character**: A Game Object with information about an in-fiction being
- **Player Character (PC)**: A Character with a player login assigned. Full character sheet.
- **NPC**: A Character without a player login. Simplified record.
- **GM**: A Player with full visibility, configuration, and proposal approval capabilities.

Characters have a **detail level** that determines which fields are active:

#### Full (PC) Character

All shared Game Object fields plus:
- `detail_level`: `full`
- `notes`: text
- `attributes`: JSON blob — freeform GM notes (available on all Characters)
- **Resource meters**: Stress (0–9), Free Time (0–20), Plot (0–5), Gnosis (0–23)
- **Skills**: 8 hardcoded skills (Awareness, Composure, Influence, Finesse, Speed, Power, Knowledge, Technology), levels 0–3
- **Magic Stats**: 5 schools (Being, Wyrding, Summoning, Enchanting, Dreaming), levels 0–5 with XP
- **Magic Effects**: Up to 9 active (charged + permanent)
- **Traits**: Core Traits (2 slots), Role Traits (3 slots) — mechanical (charges 0–5, +1d on proposals)
- **Bonds**: 8 slots — can target any Game Object (Character, Group, or Location). Full stress/degradation mechanics, +1d on proposals.

See [character-core](character-core.md) for full field definitions and mechanics.

#### Simplified (NPC) Character

All shared Game Object fields plus:
- `detail_level`: `simplified`
- `notes`: text
- `attributes`: JSON blob — freeform structure for traits, stats, abilities, and any other info the GM wants to track. No enforced schema.
- **Bonds**: 7 slots — can target any Game Object. Descriptive only (no stress, no degradation, no +1d).
- No resource meters, no skills, no magic stats, no magic effects, no Core/Role traits.

**Design intent**: NPCs are mechanically lightweight but participate in the bond graph as first-class entities. Their bonds define who they know, where they go, and what groups they belong to.

### Groups

Organizations, crews, families, guilds, and other groups in the game world:
- `name`: string
- `description`: string
- `tier`: non-negative integer — power/influence level. No upper bound.
- `project_clocks`: list of embedded Clock objects — ongoing group projects
- `notes`: text

**Group Traits**: 10 descriptive trait slots — freeform name + description, no enforced categories. No charges, no dice bonuses. See [traits.md](traits.md) for authoritative spec.

**Group Bonds** (descriptive — no stress, no degradation):

| Bond Type | Slots | Direction | Purpose |
|-----------|-------|-----------|---------|
| Relations | 7 | Group ↔ Group | Alliances, rivalries, debts, political ties. Bidirectional with `source_label`/`target_label`. |
| Holdings | Unlimited | Group → Location | Territories, properties, meeting places, sacred sites. Directional. |
| Members | Derived | Character → Group | Any Character (PC or NPC) with a bond targeting the Group is a member. Not a stored type — computed from inbound bonds. |

See [bonds.md](bonds.md) for full bond model, directionality rules, and bond-distance presence.

**Group projects and deferred resolution**: Project clocks track mechanical progress (segment fill), but the *outcome* of a project is intentionally left ambiguous until the clock completes. At resolution time, the GM looks at accumulated context and decides what the group was doing.

**Powerful individuals at Group scale**: A Character powerful enough to operate at the Group level gets their own Group with just themselves as a member. Their Group can then have Relations with other Groups.

### Locations

Places in the game world with nestable hierarchy:
- `name`: string
- `description`: string
- `parent`: optional reference to another Location — unlimited nesting depth
- `notes`: text

**Location Traits**: 5 descriptive Feature trait slots — freeform, interchangeable (no typed sub-slots). No charges, no dice bonuses. See [traits.md](traits.md) for authoritative spec.

**Location Bonds** (descriptive — unlimited):

Locations can bond to any Game Object (Characters, Groups, other Locations). Bonds represent notable connections — "headquarters of [Group]", "home of [Character]", "path to [Location]".

**Hierarchy**: No system-imposed depth limit. A city can contain districts, which contain streets, which contain buildings, etc. Location list API uses flat parent filtering (`?parent={id}` for direct children only).

---

## Shared Game Object Fields

All Game Objects have:
- `id`: string (primary key)
- `name`: string
- `description`: string (optional)
- `is_deleted`: boolean (default false) — soft delete flag
- `created_at`: datetime
- `updated_at`: datetime

Plus type-specific fields.

### Soft Delete

- All Game Objects use soft delete via `is_deleted`.
- Deleted objects are hidden from list endpoints but accessible via direct lookup.
- References to deleted objects remain valid — a Bond targeting a deleted Character still resolves.
- **Soft-deleted objects are excluded from the bond graph** — they don't participate in bond-distance visibility, presence, or feed computations. Their bonds still exist in the database but are skipped during graph traversal.
- Per-type lifecycle fields (e.g., Story `status`) are independent of the deletion flag.
- **No cascade**: Soft-deleting a Game Object does NOT cascade to its Clocks, Story entries, or other associated records. Those remain accessible independently.

---

## Bonds

Bonds are the relationship primitive connecting Game Objects. See [bonds.md](bonds.md) for the authoritative spec covering:
- Unified bond model and shared fields
- All bond categories (PC Bond, NPC Bond, Group Relations, Group Holdings, Location Bond)
- Directionality rules and bidirectional labels
- PC Bond mechanics (stress, degradation, +1d, Trauma)
- Derived membership (Character bonds to Groups)
- Bond-Distance Presence (computed location proximity from the bond graph)
- Bond management via GM actions

---

## System Entities

These are tracking and organizational tools — NOT Game Objects. They don't participate in the bond graph.

### Clocks

Progress trackers (BitD-style):
- `name`: string
- `segments`: positive integer — total segments. Any positive value, default 5.
- `progress`: integer — filled segments. Soft cap at `segments` (GM can advance past completion).
- `associated_type`: optional — type of associated Game Object (`character`, `group`, or `location`)
- `associated_id`: optional — ID of associated Game Object
- `notes`: text

Clocks can be associated with any Game Object (Character, Group, or Location) or exist independently. Group project clocks are the most common pattern. **Both access routes work**: embedded clocks via `/groups/{id}/clocks/{clock_id}` and standalone via `/clocks/{id}`. Single underlying table with optional association fields.

**Single association**: A Clock can be associated with at most one Game Object. If a project involves multiple entities, pick the primary one.

**Completion**: Computed on read (`progress >= segments`). No stored `is_completed` flag. When completion is detected, the system **auto-generates a `resolve_clock` proposal** in pending state. The GM fills in narrative and approves. See [actions.md](actions.md). This is a meter boundary behavior — see [events.md](events.md) Meter Boundary Patterns for the full catalog.

**Soft cap**: The GM can continue advancing a clock past its segment count (e.g., for over-achievement tracking). The clock remains flagged as completed.

**Annotations**: Clock adjustments are recorded via the Event log with annotation metadata. No denormalized history on the Clock object.

### Sessions

Records of play sessions with a strictly forward lifecycle: **Draft → Active → Ended**.

- `time_now`: integer — abstract campaign time counter (GM-set)
- `status`: enum — `draft`, `active`, `ended`
- `date`: date
- `summary`: text
- `notes`: text
- `participants`: list of participant records

**Lifecycle** (fully specified in [downtime](downtime.md)):
- **Draft**: Editable. **Hard deletable** (exception — no downstream references). Players self-register.
- **Active** (on Start): FT distributed via Time Now delta, Plot awarded. Only one Active at a time. Late joins allowed.
- **Ended** (on End): Read-only. Permanent.

**Participant records**: `{player_id, character_id, additional_contribution: bool}`. No `distributed` flag — see [downtime.md](downtime.md) for rationale.

**Event auto-capture**: Events generated while a session is Active are automatically tagged with that session's ID.

### Stories / Arcs

Narrative threads:
- `name`: string
- `summary`: text
- `owners`: list of typed references to Characters, Groups, or Locations — managed via sub-resource API. **Mixed owner types allowed** (e.g., a Story owned by both a PC and a Group).
- `status`: enum — `active`, `completed`, `abandoned`. **GM free-sets** — no transition rules.
- `parent`: optional reference to another Story (nestable sub-arcs)
- `tags`: list of strings — freeform
- `entries`: list of narrative entries (see below)
- `notes`: text
- `visibility_overrides`: optional list of player IDs granted visibility by GM (overrides bond-graph rules)

**Story visibility** is bond-graph driven, computed on read. See [feed.md](feed.md) for the unified visibility model. Stories default to `familiar` visibility level.

**Narrative entries**: Structured narrative progress records:

```
{
  id: string,
  text: string,
  author_id: ref (user),
  character_id?: ref,
  session_id?: ref,
  event_id?: ref,
  game_object_refs?: [],
  created_at: datetime,
  updated_at?: datetime,
  updated_by?: ref,
  is_deleted: bool,
  deleted_by?: ref
}
```

**Story creation**: GM-only. Players contribute via entries, not Story creation.

**Entry access**: **See = write.** If a player can see a Story (via the visibility model), they can add entries to it. Players edit own entries, GM edits any. Soft-delete for removals.

---

## Decisions

### Three Game Object Types

- **Decision**: Game Objects are exactly three types: Characters, Groups, and Locations. These are the things that exist "in the fiction." Clocks, Sessions, and Stories are System Entities — tracking tools, not world entities.
- **Rationale**: Clean conceptual model. Game Objects are the nodes in the bond graph. System Entities are organizational/tracking mechanisms that serve the game but don't have narrative identity.
- **Implications**: Bond targets are always Game Objects. System Entities have their own API patterns but don't participate in the bond graph or presence model.

### Characters Unify PCs and NPCs

- **Decision**: NPCs are Characters without a player login assigned. Same entity, tiered detail level. A `detail_level` field (`full` or `simplified`) determines which fields are active.
- **Rationale**: In the fiction, PCs and NPCs are the same kind of thing — beings in the world. The system should reflect this. The detail difference is about player interaction, not ontology.
- **Implications**: Single Character table with optional fields. NPCs participate in the bond graph identically to PCs. Auth determines what a user can do, not the Character's type.

### NPC Detail Level — Skip Meters and Skills

- **Decision**: Simplified (NPC) Characters have name, description, notes, attributes blob, and 7 Bond slots. They skip: resource meters (Stress, FT, Plot, Gnosis), Skills, Magic Stats, Magic Effects, and Core/Role Traits.
- **Rationale**: NPCs don't use the proposal workflow or dice mechanics. The GM needs maximum flexibility. Mechanical fields are unnecessary overhead.
- **Implications**: API returns null/omitted fields for simplified Characters. Bond slots are the NPC's primary structural feature.

### PC Bond Slots — 8

- **Decision**: Full (PC) Characters have 8 Bond slots. NPCs retain 7.
- **Rationale**: PCs will almost always bond to their party Group, which serves as the hub for main-quest Stories, the default starred feed, etc. The 8th slot ensures PCs aren't penalized for this expected bond.
- **Implications**: Updates character-core.md, bonds.md. Trauma can consume at most 8 PC slots. Character Stress max can decrease from 9 to 1. NPC slot count unchanged at 7.

### Group Traits — Flat Descriptive Slots

- **Decision**: Groups have 10 descriptive trait slots — freeform name + description, no enforced categories. No charges, no dice bonuses.
- **Rationale**: The previous Culture/Training/Asset categories added complexity without clear benefit. The GM names traits however they want.
- **Implications**: Single `group_trait` slot_type. See [traits.md](traits.md) for authoritative spec.

### Group Bond Types — Relations, Holdings, and Members

- **Decision**: Groups have three bond categories: Relations (7 slots, Group↔Group, bidirectional), Holdings (unlimited, Group→Location), and Members (derived from Character→Group bonds). All descriptive.
- **Rationale**: Relations cap at 7 to keep Groups focused. Holdings are unlimited for territorial flexibility. Members are unlimited because a Group can have any number of members.
- **Implications**: A Character operating at Group scale gets their own single-member Group to participate in Relations.

### Location Feature Traits — 5 Interchangeable Slots

- **Decision**: Locations have 5 Feature Trait slots — all interchangeable, no typed sub-slots. Categories (atmosphere, danger, etc.) are naming conventions, not enforced.
- **Rationale**: Enforcing sub-types constrains the GM without adding value. 5 slots is enough.
- **Implications**: Single `feature_trait` slot_type. See [traits.md](traits.md) for authoritative spec.

### Location Bonds — Unlimited

- **Decision**: Locations have unlimited bond slots to any Game Object. Descriptive only.
- **Rationale**: Locations are hubs — many things connect to them. An artificial cap would be frustrating. Bonds replace the old curated affiliation lists.
- **Implications**: Location bonds participate in the bond-distance presence graph.

### Location List — Flat Parent Filter

- **Decision**: Location list API uses `?parent={id}` for direct children only. No tree query or depth parameter.
- **Rationale**: Simplest implementation. Client builds tree by making multiple requests if needed. For 4–6 players, the Location count is small enough.
- **Implications**: No `GET /locations/{id}/subtree` endpoint.

### Bond-Distance Presence Replaces Curated Lists

- **Decision**: Location presence ("who's here") and Character locations ("where might they be") are computed from the bond graph using hop distance: 1-hop = Commonly, 2-hop = Often, 3-hop = Sometimes. Replaces curated affiliation lists and `common_locations`.
- **Rationale**: The bond graph already encodes all relationships. Deriving presence from it eliminates redundant data and creates an elegant dual-use model (information visibility + presence proximity). Mirrors the event visibility system.
- **Implications**: No manual "who's here" maintenance. Computed on read. Bond graph does double duty.

### Unified Bond Concept

- **Decision**: All relationships between Game Objects are Bonds. PC Bonds have full mechanical depth (stress, degradation, +1d). All other bonds are descriptive (active/retired only). One concept, varying richness.
- **Rationale**: Keeps the mental model simple — "Bonds connect things." The mechanical depth varies because only PCs use the proposal/dice system. UI can render all bond types consistently.
- **Implications**: Single bond table with optional mechanical fields (stress, degradation, is_trauma) that are only populated for PC bonds. Bond type/context determines which fields are relevant.

### Soft Delete Excludes from Bond Graph

- **Decision**: Soft-deleted Game Objects are excluded from bond-graph traversal. They don't participate in bond-distance visibility, presence, feed, or story visibility computations.
- **Rationale**: Deleted entities shouldn't influence the active game world. Removing them from the graph ensures clean visibility and presence computations.
- **Implications**: Bond-graph queries must filter `is_deleted = false` on traversal. Bonds to deleted entities still exist but are dead ends during traversal.

### No Cascade Soft-Delete

- **Decision**: Soft-deleting a Game Object does NOT cascade to associated records (Clocks, Story entries, etc.). They remain accessible independently.
- **Rationale**: Associated records may have standalone value. Cascading creates unexpected data loss. The GM can clean up manually if desired.
- **Implications**: Clock `associated_with` may point to a deleted entity. Story entries remain even if the Story's owner is deleted.

### GM Ownership of World Objects

- **Decision**: Groups, Locations, and NPC Characters are created and managed exclusively by the GM. Players have read-only access.
- **Rationale**: The GM controls the game world narrative. Players interact with world objects through their characters and the proposal system.
- **Implications**: All CRUD endpoints for these objects require GM authorization.

### Single Character Attributes Blob

- **Decision**: All Characters have a freeform `attributes` JSON blob. For NPCs, this is the primary place for mechanical info (traits, stats, abilities). For PCs, it's available for GM notes.
- **Rationale**: Maximum flexibility for the GM. NPCs don't need structured mechanical fields.
- **Implications**: Attribute data is opaque to the system. No validation beyond "valid JSON".

### Bidirectional Bond Labels

- **Decision**: Bidirectional bonds carry `source_label` and `target_label` fields, allowing each side to describe the relationship in its own terms.
- **Rationale**: Real relationships are often perceived differently by each party.
- **Implications**: Bond creation/editing must handle two labels. API returns the appropriate label based on viewing perspective.

### Soft Delete for All Game Objects

- **Decision**: All Game Objects use soft delete via `is_deleted`. No hard deletes. Per-type lifecycle fields are independent.
- **Rationale**: References must remain valid. Soft delete preserves history.
- **Implications**: List endpoints filter `is_deleted = false` by default.

### Draft Session Hard Delete

- **Decision**: Draft Sessions use hard delete. Active/Ended sessions are permanent.
- **Rationale**: Draft sessions have no downstream references. Hard delete keeps the database clean.
- **Implications**: `DELETE /sessions/{id}` returns 400 if not Draft. Exception to the general soft-delete rule.

### Faction → Group Rename

- **Decision**: "Faction" renamed to "Group" project-wide.
- **Rationale**: "Group" is more inclusive — covers factions, guilds, families, crews, and any organization.
- **Implications**: All specs, glossary, and API routes updated.

### CRUD/GM Action Split

- **Decision**: REST CRUD endpoints (POST/GET/PATCH/DELETE) handle structural operations only: creating objects, soft-deleting, and editing non-mechanical fields (name, description, notes). All mechanical state changes (meters, skills, attributes, bonds, traits, effects, clocks, tier, parent_id) go through `POST /api/v1/gm/actions`. No write sub-resource endpoints for bonds, traits, or clocks on game object routes.
- **Rationale**: Clean separation of concerns. CRUD is for object lifecycle and metadata; GM actions are for game-state-changing operations that produce events. Eliminates redundant endpoints.
- **Implications**: POST (creation) is the one exception — accepts all fields including mechanical ones (setup). See [actions.md](actions.md) for the full CRUD/GM split definition.

### Clock Association — Any Game Object

- **Decision**: Clocks can be associated with any single Game Object (Character, Group, or Location) via polymorphic reference (`associated_type` + `associated_id`), or exist standalone with no association.
- **Rationale**: Clocks are used for Group projects (most common), but also for Character personal goals and Location-based events. One optional polymorphic reference covers all cases.
- **Implications**: Replaces the old `group_id` field with `associated_type`/`associated_id`. Clock list endpoint filters by association.

### Clock Completion — Computed + Auto-Propose

- **Decision**: Clock completion is computed on read (`progress >= segments`). No stored flag. When completion is detected, the system auto-generates a `resolve_clock` proposal in pending state.
- **Rationale**: Computed avoids stale flags. Auto-generation ensures the GM always sees completed clocks requiring resolution.
- **Implications**: resolve_clock auto-generation must be idempotent — only generate if no pending or approved `resolve_clock` proposal exists for that `clock_id`. One resolve_clock proposal per clock, ever. Once resolved (approved), further advances (soft cap) do not generate new proposals. GM handles ongoing narrative via direct actions.

### Clock Soft Cap

- **Decision**: Clock progress can exceed the segment count. The GM can advance past completion.
- **Rationale**: Allows over-achievement tracking. The clock remains flagged as completed.
- **Implications**: No validation rejecting `progress > segments`.

### Clock Segment Sizes

- **Decision**: Any positive integer. Default 5.
- **Rationale**: Full flexibility for the GM.
- **Implications**: Validation: `segments > 0`.

### Clock Dual Route Access

- **Decision**: Group project clocks accessible via both `/groups/{id}/clocks/{clock_id}` and `/clocks/{id}`.
- **Rationale**: Convenience for both group-focused and cross-group workflows.
- **Implications**: Single clock table with optional association fields.

### Clock Creation — Both Routes, Fixed Association

- **Decision**: Clocks can be created via `POST /api/v1/clocks` (standalone, with optional `associated_type`/`associated_id` in body) or `POST /api/v1/groups/{id}/clocks` (sugar — auto-sets association to that Group). Association is fixed at creation — cannot be changed via PATCH.
- **Rationale**: Both routes are convenient for different workflows. Fixed association avoids complexity around re-parenting clocks and the events they've already generated.
- **Implications**: No `associated_type`/`associated_id` fields accepted on PATCH. To change association, delete and recreate.

### Unlimited Location Nesting

- **Decision**: No system-imposed depth limit on Location hierarchy.
- **Rationale**: The GM knows their world.
- **Implications**: API and UI must handle arbitrary nesting.

### Story Creation — GM Only

- **Decision**: Only the GM can create Stories. Players contribute via entries.
- **Rationale**: Stories are world-level narrative structures. GM manages the narrative arc; players contribute content within it.
- **Implications**: `POST /stories` is GM-only.

### Story Status — Free-Set by GM

- **Decision**: Story status (active/completed/abandoned) can be set to any value at any time by the GM. No transition rules.
- **Rationale**: Narrative arcs don't follow a predictable lifecycle. The GM needs full flexibility to mark stories as they see fit.
- **Implications**: No status validation beyond valid enum values.

### Story Mixed Owners — Union Visibility

- **Decision**: A Story can have owners of any type (Character, Group, Location) in any combination. Visibility is the union of all owner rules — if one owner is a Group, anyone bonded to that Group can see the Story, even if another owner is a PC.
- **Rationale**: Mixed ownership reflects real narrative threads that involve multiple entities. Union visibility ensures the broadest reasonable access.
- **Implications**: Visibility computation must iterate all owners and take the union of visible players.

### Story Entry Access — See = Write

- **Decision**: If a player can see a Story (via the unified visibility model), they can add entries to it. Players edit own entries, GM edits any.
- **Rationale**: Narrative collaboration works best when contributors can add to stories they're involved in. The visibility model already gates access appropriately.
- **Implications**: Entry creation checks visibility, not just ownership.

### Story GM Visibility Override

- **Decision**: GM can manually grant visibility to specific players, overriding the bond-graph computation. Same pattern as event visibility override.
- **Rationale**: Sometimes the GM wants a player to see a Story for narrative reasons, even without a bond-graph path.
- **Implications**: Story has a `visibility_overrides` list of player IDs.

### Story Freeform Tags

- **Decision**: Optional list of freeform string tags. No predefined vocabulary.
- **Rationale**: Flexible enough for any campaign.
- **Implications**: API supports filtering by tag.

### Story Embedded Narrative Entries

- **Decision**: Stories have an embedded `entries` array with structured narrative records and audit trail.
- **Rationale**: Denormalized for easy display. Serves both `work_on_project` proposals and GM additions.
- **Implications**: Story objects grow over time.

### Story Owners Sub-resource

- **Decision**: Story owners managed via `POST/DELETE /stories/{id}/owners` with `{type, id}`.
- **Rationale**: Consistent sub-resource pattern.
- **Implications**: Separate owner records table.

### Group Tier Unbounded

- **Decision**: `tier` is any non-negative integer. No upper bound.
- **Rationale**: GM decides the power scale.
- **Implications**: Informational only — no tier-based game mechanics.

### Clock Annotations via Event Log

- **Decision**: Clock adjustments recorded as Events with annotation metadata. No denormalized history on Clock.
- **Rationale**: Event log is already the audit trail.
- **Implications**: Clock history = filtered event query.

### Event Auto-Capture to Active Session

- **Decision**: Events generated during Active session auto-tag with session ID.
- **Rationale**: Eliminates manual session tagging for the common case.
- **Implications**: Event creation logic checks for Active session.

### Deferred Narrative Resolution (Design Principle)

- **Decision**: Named design principle. Game state intentionally left ambiguous until narratively observed.
- **Rationale**: Tabletop RPGs are collaborative fiction. The system supports potential/fuzzy state.
- **Implications**: Affects Character locations (bond-distance presence), Group projects (undefined until clock completion), and other domains.

---

## API Endpoints

### Characters (PCs and NPCs)
- `GET /api/v1/characters` — list (filters: `?detail_level=`, `?has_player=`, `?is_deleted=false` default)
- `GET /api/v1/characters/{id}` — detail with bonds, traits, bond-distance locations, and feed
- `POST /api/v1/characters` — create (GM). Accepts all fields including mechanical ones (meters, skills, etc.).
- `PATCH /api/v1/characters/{id}` — update name, description, notes only (GM or owner for notes/description). Mechanical fields (meters, skills, attributes, etc.) via `POST /api/v1/gm/actions`.
- `DELETE /api/v1/characters/{id}` — soft delete (GM)

### Groups
- `GET /api/v1/groups` — list (filters: `?is_deleted=false` default)
- `GET /api/v1/groups/{id}` — detail with clocks, traits, bonds, computed members, and feed
- `POST /api/v1/groups` — create (GM). Accepts all fields including tier.
- `PATCH /api/v1/groups/{id}` — update name, description, notes only (GM). Tier, traits, bonds, clocks via `POST /api/v1/gm/actions`.
- `DELETE /api/v1/groups/{id}` — soft delete (GM)

### Clocks (System Entity)
- `GET /api/v1/clocks` — list all clocks (filters: `?associated_type=`, `?associated_id=`, `?is_deleted=false` default)
- `GET /api/v1/clocks/{id}` — detail
- `POST /api/v1/clocks` — create clock (GM). Optional `associated_type`/`associated_id` in body for association.
- `POST /api/v1/groups/{id}/clocks` — create clock auto-associated with this Group (GM). Sugar for `POST /clocks` with association pre-set.
- `PATCH /api/v1/clocks/{id}` — update name, notes, segments (GM). Association is fixed at creation. Progress changes via `POST /api/v1/gm/actions` (`modify_clock`).
- `DELETE /api/v1/clocks/{id}` — soft delete (GM)

### Locations
- `GET /api/v1/locations` — list (filters: `?parent={id}`, `?is_deleted=false` default)
- `GET /api/v1/locations/{id}` — detail with traits, bonds, bond-distance presence, and feed
- `POST /api/v1/locations` — create (GM). Accepts all fields including parent.
- `PATCH /api/v1/locations/{id}` — update name, description, notes only (GM). Parent, traits, bonds via `POST /api/v1/gm/actions`.
- `DELETE /api/v1/locations/{id}` — soft delete (GM)

### Stories (System Entity)
- `GET /api/v1/stories` — list (filters: `?status=active`, `?tag=`, `?owner=`, `?is_deleted=false` default). **Visibility-filtered** per authenticated user.
- `GET /api/v1/stories/{id}` — detail with entries and owners (visibility check)
- `POST /api/v1/stories` — create (GM)
- `PATCH /api/v1/stories/{id}` — update (GM)
- `DELETE /api/v1/stories/{id}` — soft delete (GM)
- `POST /api/v1/stories/{id}/owners` — add an owner (GM)
- `DELETE /api/v1/stories/{id}/owners/{type}/{owner_id}` — remove an owner (GM)
- `POST /api/v1/stories/{id}/entries` — add a narrative entry (visible players or GM)
- `PATCH /api/v1/stories/{id}/entries/{entry_id}` — edit an entry (own or GM)
- `DELETE /api/v1/stories/{id}/entries/{entry_id}` — soft-delete an entry (own or GM)

### Sessions (System Entity)
(Fully defined in [downtime](downtime.md))
- `POST /api/v1/sessions` — create Draft (GM)
- `GET /api/v1/sessions` — list
- `GET /api/v1/sessions/{id}` — detail with participants
- `PATCH /api/v1/sessions/{id}` — update (GM, Draft or Active only)
- `DELETE /api/v1/sessions/{id}` — hard delete (GM, Draft only)
- `POST /api/v1/sessions/{id}/start` — start session (GM)
- `POST /api/v1/sessions/{id}/end` — end session (GM)
- `POST /api/v1/sessions/{id}/participants` — register for session
- `DELETE /api/v1/sessions/{id}/participants/{player_id}` — remove from session
- `PATCH /api/v1/sessions/{id}/participants/{player_id}` — update contribution flag
- `GET /api/v1/sessions/{id}/timeline` — events during this session

### Feed (cross-cutting)
See [feed.md](feed.md) for feed endpoints:
- `GET /api/v1/{type}/{id}/feed` — per-Game Object feed
- `GET /api/v1/me/feed` — complete feed across all bonds
- `GET /api/v1/me/feed/starred` — starred Game Objects only

---

## Open Questions

_All resolved._

1. ~~**Session participant `distributed` flag**~~: **Resolved** — No flag needed. See [downtime.md](downtime.md) — re-adding re-distributes; GM corrects via direct actions if needed.
2. ~~**`resolve_clock` idempotency**~~: **Resolved** — One resolve_clock proposal per clock, ever. Only generate if no pending or approved resolve_clock exists for that clock_id. Further soft-cap advances don't generate new proposals.
3. ~~**Story entry schema mismatch**~~: **Resolved** — Added `author_id` to the embedded entry format, reconciled with data-model.md.
4. ~~**Clock creation via sub-resource**~~: **Resolved** — Both routes: `POST /clocks` (standalone or with association) and `POST /groups/{id}/clocks` (auto-associates). Association is fixed at creation — cannot be changed via PATCH.

---

## Implications for Other Specs

| Spec | Implication |
|------|-------------|
| [character-core](character-core.md) | ✅ PC Bond slots = 8. NPCs = 7. Aligned. |
| [bonds](bonds.md) | ✅ PC Bond slots = 8. NPCs = 7. Aligned. |
| [feed](feed.md) | ✅ Unified Feed concept. Aligned. |
| [events](events.md) | ✅ Unified visibility model. Aligned. |
| [traits](traits.md) | ✅ Group traits 10 flat, Location Feature traits 5. Aligned. |
| [actions](actions.md) | ✅ Clean CRUD/GM split. resolve_clock auto-generated on clock completion (one per clock, ever). |
| [architecture/data-model](../architecture/data-model.md) | ✅ Clock polymorphic association. Story `visibility_overrides`. `starred_objects` table. PC bond slots 8. |

---

_Last updated: 2026-03-14 (added cross-reference to events.md Meter Boundary Patterns for clock completion)_
