# Game Objects — Domain Specification

**Status**: 🟢 Complete
**Last interrogated**: 2026-03-02
**Last verified**: —
**Depends on**: None (primitive)
**Depended on by**: [character-core](character-core.md), [bonds](bonds.md), [events](events.md), [downtime](downtime.md)

---

## Overview

Everything tracked in the system is a game object. This domain defines the shared structure and the non-character object types: NPCs, Groups, Clocks, Locations, Sessions, and Stories/Arcs. Characters are covered in [character-core](character-core.md).

A core design principle is **Deferred Narrative Resolution** — game state is intentionally left ambiguous until narratively observed. NPCs have probable locations, not pinned ones. Group projects progress mechanically but their outcomes are defined retroactively. The system supports fuzzy/potential state alongside concrete state.

---

## Core Concepts

### Shared Game Object Fields

All game objects have:
- `id`: string (primary key)
- `name`: string
- `description`: string (optional)
- `is_deleted`: boolean (default false) — soft delete flag, shared across all types
- `created_at`: datetime
- `updated_at`: datetime

Plus type-specific fields.

### Soft Delete

- **All game objects** use soft delete via the `is_deleted` flag on the shared base.
- **Exception**: Draft Sessions use hard delete (no downstream references exist — no events, no distributions).
- Deleted objects are hidden from list endpoints by default but accessible via direct lookup.
- References to deleted objects remain valid — Bonds targeting a deleted NPC still resolve, they just point to a deleted entity.
- Per-type lifecycle fields (e.g., Story `status`) are independent of the deletion flag.

### Lightweight Bonds

NPCs and Groups can have a `bonds` list — lightweight Bond-shaped relationships to other game objects. These are the relationship primitive for non-Character objects.

**Fields per lightweight bond:**
- `id`: string — unique identifier (individually addressable)
- `source_type`: string — type of the owning object
- `source_id`: string — ID of the owning object
- `target_type`: string — type of the referenced game object
- `target_id`: string — ID of the referenced game object
- `source_label`: string — relationship label from the source's perspective (e.g., "allied with")
- `target_label`: string — relationship label from the target's perspective (for bidirectional bonds)
- `description`: string — freeform context
- `is_active`: boolean — supports Past/Retired pattern
- `bidirectional`: boolean — whether both sides see this bond
- Event history via the event log (no embedded history)

**Managed via sub-resource API**: `POST/PATCH/DELETE /{object-type}/{id}/bonds/{bond_id}`

**Differences from PC Bonds:**
- No stress meter or degradation mechanics
- No charge mechanics or +1d modifier
- No cap on number of bonds per object (PCs have 7 slots)
- Not Trait Instances — these are a simpler structure

**Design intent**: NPC/Group bonds should be vaguely Bond-shaped and function interchangeably in the UI and mental model, even though they lack the mechanical depth of PC Bonds.

### Bond Directionality Model

Lightweight bonds follow different directionality rules depending on the types involved:

| Source → Target | Direction | Notes |
|-----------------|-----------|-------|
| Group ↔ Group | Bidirectional | One record, both sides see it. `source_label` / `target_label` allow different wording per side. |
| NPC ↔ NPC | Bidirectional | Same as Group↔Group. One record, both see it. |
| NPC → Group | Directional | Represents **membership**. NPC owns the bond. Group's "members" list is derived from inbound bonds. |
| Group → NPC | Directional | Represents a **special relationship** (mentorship, alliance with a powerful individual). Group owns the bond. Distinct from membership. |
| NPC → Location | Directional | Represents presence/connection. NPC owns the bond. |
| Group → Location | Directional | Represents territorial control or presence. Group owns the bond. |
| Location → * | N/A | **Locations are targets only** — they do not have bonds. Presence at a Location is tracked via curated affiliation lists + inbound bond queries. |

**Membership semantics**: An NPC with a bond to a Group is considered a "member" of that Group. A Group with a bond to an NPC represents something different — a special, non-membership relationship (e.g., "mentors", "hunts", "owes a debt to"). This distinction is directional, not labeling.

### NPCs

Simplified character records controlled by the GM:
- `name`: string
- `description`: string
- `attributes`: JSON blob — freeform structure for traits, stats, abilities, and any other mechanical info the GM wants to track. No enforced schema.
- `notes`: text
- `common_locations`: list of `{location_id, note?}` — places the NPC might be found, with optional freeform notes (e.g., "works the night shift", "lives upstairs"). See Deferred Narrative Resolution.
- `bonds`: list of lightweight bonds to other game objects (other NPCs, Groups, Locations, Characters, etc.)

**Quantum location model**: NPCs are not pinned to a single location. They have a list of common locations representing where they *might* be — a probability smear. The NPC's actual location is resolved narratively when observed (e.g., during a session when a player looks for them). This is a deliberate design choice reflecting the deferred narrative resolution principle.

**Merged location view**: The NPC detail endpoint merges `common_locations` (curated list) with any Location-targeting bonds the NPC has, producing a unified "where to find this NPC" view. Bond-derived locations are flagged as such.

### Groups

Organizations, crews, families, guilds, and other groups in the game world (renamed from "Factions"):
- `name`: string
- `description`: string
- `tier`: non-negative integer — power/influence level. No upper bound. GM decides the scale.
- `project_clocks`: list of embedded Clock objects — ongoing group projects
- `bonds`: list of lightweight bonds to other game objects (other Groups, NPCs, Locations, Characters, etc.)
- `notes`: text

**Territories**: Group territorial control is represented via Group→Location bonds (e.g., `source_label: "controls"`, `target_label: "controlled by"`). No separate `locations` field.

**Members**: Derived from inbound bonds — any NPC (or other object) with a bond targeting this Group is considered a member. The Group detail endpoint includes a computed `members` list.

**Group bond model**: Group-to-Group relationships (alliances, rivalries, debts) are stored as bidirectional lightweight bonds. A single bond record between two Groups; both see the bond with their respective labels.

**Group projects and deferred resolution**: Project clocks track mechanical progress (segment fill), but the *outcome* of a project is intentionally left ambiguous until the clock completes. The GM may specify a project description upfront or leave it as a placeholder. At resolution time, the GM looks at accumulated context (events, bonds, narrative) and decides what the group was doing, then creates events that adjust game state (territorial bonds, game object mutations) and ties to a Story.

### Clocks

Progress trackers (BitD-style):
- `name`: string
- `segments`: positive integer — total segments. Any positive value allowed, default 5.
- `progress`: integer (0 to `segments`) — filled segments
- `associated_with`: optional reference to a Group, Story, or other game object
- `notes`: text

Clocks can be embedded in Groups (as project clocks) or exist independently. **Both access routes work**: embedded clocks are accessible via `/groups/{id}/clocks/{clock_id}` and the standalone `/clocks/{id}` endpoint. Single underlying table with optional `group_id`.

**Completion**: When `progress >= segments`, the clock is flagged as completed. System surfaces completed clocks to the GM. The GM resolves consequences narratively — typically creating events that adjust game state and linking to or creating a Story. No automatic game state changes on completion.

**Annotations**: Clock adjustments (advancement, regression, resets) are recorded via the Event log. Each clock adjustment event includes annotation metadata: freeform notes, event references, and game object references explaining why the change occurred. No denormalized annotation history on the Clock object itself.

### Locations

Places in the game world with nestable hierarchy:
- `name`: string
- `description`: string
- `parent`: optional reference to another Location — unlimited nesting depth
- `notes`: text
- `npcs`: list of `{npc_id, note?}` — curated NPC affiliations with optional freeform notes (e.g., "bartender", "regular patron")
- `groups`: list of `{group_id, note?}` — curated Group affiliations with optional freeform notes (e.g., "headquarters", "patrol route")

**No bonds on Locations**: Locations are bond targets, not bond sources. They don't have a `bonds` list.

**Computed presence**: The Location detail endpoint merges the curated `npcs` and `groups` affiliation lists with inbound bonds (NPCs and Groups that have bonds targeting this Location), producing a unified "who's here" view. Bond-derived entries are flagged as such.

**Hierarchy**: No system-imposed depth limit. A city can contain districts, which contain streets, which contain buildings, etc. Practical depth is left to the GM.

### Sessions

Records of play sessions with a strictly forward lifecycle: **Draft → Active → Ended**.

- `time_now`: integer — abstract campaign time counter (GM-set). See [downtime](downtime.md) for full semantics.
- `status`: enum — `draft`, `active`, `ended`
- `date`: date
- `summary`: text
- `notes`: text
- `participants`: list of participant records (see below)

**Lifecycle** (fully specified in [downtime](downtime.md)):
- **Draft**: Editable. **Hard deletable** (exception to soft-delete rule — no downstream references). Players self-register. GM sets time_now and details.
- **Active** (on Start): FT distributed via Time Now delta, Plot awarded (+1/+2 with Additional Contribution). GM can edit summary/notes. Late joins allowed with immediate distribution. Only one Active session at a time.
- **Ended** (on End): Read-only. Active/Ended sessions are permanent (cannot be deleted). Clock adjustments happen individually during Active, not in the End call.

**Participant records**: `{player_id, character_id, additional_contribution: bool, distributed: bool}`. Contribution flag locks on Start (or on late join after distribution).

**Time Now validation**: Must be >= previous session's Time Now. Equal allowed (0 FT delta). First session unconstrained.

**Event auto-capture**: Any event generated while a session is Active is automatically tagged with that session's ID. Callers can override with a specific session_id. When no session is Active, session_id is optional/null.

### Stories / Arcs

Narrative threads:
- `name`: string
- `summary`: text
- `owners`: list of typed references to Characters, Groups, or other game objects — managed via sub-resource API (`POST/DELETE /stories/{id}/owners`)
- `status`: enum — `active`, `completed`, `abandoned`
- `parent`: optional reference to another Story (nestable sub-arcs)
- `tags`: list of strings — freeform tags for categorization (e.g., "personal", "group", "world", "heist"). No predefined vocabulary.
- `entries`: list of narrative entries (see below)
- `notes`: text

**Narrative entries**: Stories have an embedded entries list for structured narrative progress (primarily from `work_on_project` proposals):

```
{
  id: string,              // unique identifier
  text: string,            // narrative content
  character_id?: ref,      // who wrote this entry (if player-initiated)
  session_id?: ref,        // which session this relates to
  event_id?: ref,          // linked event for audit trail
  game_object_refs?: [],   // optional links to related game objects
  created_at: datetime,
  updated_at?: datetime,   // set on edit
  updated_by?: ref,        // who last edited (player or GM)
  is_deleted: bool,        // soft delete for entries
  deleted_by?: ref         // who deleted the entry
}
```

**Entry editability**: Players can edit entries they created. The GM can edit any entry. Deletions are soft-deletes (`is_deleted = true`). Full audit trail tracked per entry.

**Player projects**: Use Stories as the tracking object. `work_on_project` proposals add narrative entries. The GM resolves the project (via direct action) when the fiction warrants it. No segmented clock — progress is narrative, not mechanical.

---

## Decisions

### GM Ownership of World Objects

- **Decision**: NPCs, Groups, Locations, and Stories are created and managed exclusively by the GM. Players have read-only access.
- **Rationale**: The GM controls the game world narrative. Players interact with world objects through their characters and the proposal system.
- **Implications**: All CRUD endpoints for these objects require GM authorization.

### Single NPC Attributes Blob

- **Decision**: NPC mechanical data (traits, stats, abilities) stored as a single freeform `attributes` JSON blob. No structured schema.
- **Rationale**: NPCs don't use the proposal workflow or dice mechanics. The GM needs maximum flexibility. A single blob is simpler than separate traits/stats fields and avoids schema debates for a freeform concept.
- **Implications**: NPC attribute data is opaque to the system. No validation beyond "valid JSON". Querying NPC attributes requires JSON field access.

### Quantum NPC Locations

- **Decision**: NPCs have a `common_locations` list (references to Locations with optional notes) rather than a single definite `location`. NPCs exist in a probability smear across their common locations until narratively observed.
- **Rationale**: Reflects the deferred narrative resolution principle. In fiction, NPCs move around — they have daily lives, routines, and go to and fro. Pinning them to one location is too rigid for narrative play.
- **Implications**: No "NPC is at Location X" queries — instead, "NPC is commonly found at Locations X, Y, Z". Location resolution happens at the table, not in the system.

### NPC Common Locations with Notes

- **Decision**: NPC `common_locations` entries are `{location_id, note?}` — each entry supports an optional freeform note (e.g., "works the night shift", "lives upstairs").
- **Rationale**: Symmetric with Location affiliation notes. Provides context for *why* an NPC is at a particular location without requiring a full bond.
- **Implications**: Slightly richer data model than plain references. Notes are optional and freeform.

### NPC Merged Location View

- **Decision**: The NPC detail endpoint merges `common_locations` (curated) with any Location-targeting bonds the NPC has, producing a unified "where to find this NPC" view. Bond-derived locations are flagged as such.
- **Rationale**: Complete location picture without manual duplication.
- **Implications**: Server-side join on NPC detail.

### Unified Lightweight Bonds on NPCs and Groups

- **Decision**: NPCs and Groups have a `bonds` list of lightweight bond objects targeting other game objects. Locations are bond targets only and do not have bonds. This replaces the previous design where all three types had bonds.
- **Rationale**: Relationships are universal — groups ally with groups, NPCs know NPCs, both connect to locations. Locations are passive — things exist *at* locations, but locations don't actively relate to things.
- **Implications**: Bond-shaped data appears at three levels: PC Bonds (Trait Instances with stress mechanics), lightweight bonds (on NPCs/Groups, no mechanics), and the bond concept in the glossary covers both. UI can render both types consistently.

### Lightweight Bond IDs and Sub-resource API

- **Decision**: Each lightweight bond has its own unique ID and is managed via sub-resource endpoints (e.g., `POST /npcs/{id}/bonds`, `PATCH /npcs/{id}/bonds/{bond_id}`, `DELETE /npcs/{id}/bonds/{bond_id}`).
- **Rationale**: Enables targeted bond updates without replacing the entire list. Consistent with other sub-resource patterns (story owners, session participants).
- **Implications**: Bond table with source_type/source_id + target_type/target_id. Individual CRUD operations per bond.

### Bond Directionality Model

- **Decision**: Lightweight bonds follow type-dependent directionality rules. Group↔Group and NPC↔NPC bonds are bidirectional (one record, both sides see it, with `source_label`/`target_label`). Cross-type bonds (NPC→Group, Group→NPC, NPC/Group→Location) are directional. NPC→Group represents membership; Group→NPC represents a special non-membership relationship. Locations are targets only.
- **Rationale**: Reflects real-world relationship semantics. A member belongs to a group (NPC→Group), but a group having a bond to an individual means something different (patronage, rivalry, etc.). Locations are passive containers.
- **Implications**: Bond deduplication needed for bidirectional bonds. Membership derived from inbound bonds. API must handle both directions for bidirectional bonds.

### Bidirectional Bond Labels

- **Decision**: Bidirectional bonds (Group↔Group, NPC↔NPC) carry `source_label` and `target_label` fields, allowing each side to describe the relationship in its own terms (e.g., source sees "reluctant allies", target sees "useful pawns").
- **Rationale**: Real relationships are often perceived differently by each party. A single shared label is too limiting.
- **Implications**: Bond creation/editing must handle two labels. API should return the appropriate label based on which side is viewing.

### Bidirectional Group Bonds

- **Decision**: Group-to-Group bonds are bidirectional. One bond record between A and B; both groups see the bond with their respective labels.
- **Rationale**: Group relationships are typically mutual ("A and B are allies"). Asymmetric perceptions are handled by different source/target labels.
- **Implications**: Bond deduplication needed — creating a bond from A→B should be visible from B's perspective too.

### Faction → Group Rename

- **Decision**: "Faction" renamed to "Group" project-wide — all specs, glossary, API endpoints (`/api/v1/groups/`).
- **Rationale**: "Group" is more inclusive — covers factions, guilds, families, crews, cults, companies, and any other organization. "Faction" implies political opposition, which is only one type.
- **Implications**: All specs, glossary entries, and API routes updated. Downstream specs flagged for revision.

### Drop Group Locations List

- **Decision**: Groups do not have a separate `locations` list. Territorial control is represented via Group→Location bonds (e.g., `source_label: "controls"`).
- **Rationale**: With the unified bond model, a separate locations list is redundant. Bonds already connect Groups to Locations with descriptive labels.
- **Implications**: Group territories queried via bond target filtering. Location detail shows Group presence via inbound bond queries + curated affiliations.

### Location Curated Affiliations

- **Decision**: Locations have `npcs` and `groups` affiliation lists — curated reference lists with optional notes (e.g., `{npc_id, note: "bartender"}`). These are independent of the bond system.
- **Rationale**: Not every NPC at a location has a meaningful bond to it. The GM needs a quick way to note "these NPCs are commonly here" without creating full bond records. Same for Groups.
- **Implications**: Location detail merges curated lists with inbound bonds for a complete presence view. Two sources of "who's here" truth that complement each other.

### Location Computed Presence

- **Decision**: The Location detail endpoint merges curated `npcs`/`groups` affiliation lists with inbound bonds (NPCs/Groups with bonds targeting this Location), producing a unified presence view. Bond-derived entries flagged as such.
- **Rationale**: Gives the GM a complete picture without manual duplication. Curated list = "always here." Inbound bonds = "connected to this place."
- **Implications**: Server-side join on Location detail. Bond-derived entries carry a flag distinguishing them from curated affiliations.

### Group Members Computed on Detail

- **Decision**: The Group detail endpoint includes a computed `members` list derived from all objects with bonds targeting this Group (primarily NPCs with NPC→Group membership bonds).
- **Rationale**: Membership is a natural inbound-bond query. Computing server-side saves the client from extra requests.
- **Implications**: Server-side reverse-bond lookup. Distinguished from the Group's own outbound bonds.

### Clock Segment Sizes

- **Decision**: Any positive integer allowed. Default 5.
- **Rationale**: Full flexibility for the GM. Standard BitD sizes (4, 6, 8) are common but shouldn't be enforced. Default 5 is a good middle ground.
- **Implications**: Validation: `segments > 0`. UI should handle variable segment counts.

### Clock Dual Route Access

- **Decision**: Group project clocks are accessible via both `/groups/{id}/clocks/{clock_id}` and the standalone `/clocks/{id}` endpoint. Single underlying storage.
- **Rationale**: Flexibility — the Group sub-resource is convenient when working with a specific group, the standalone route is useful for cross-group clock queries.
- **Implications**: Single clock table with optional `group_id`. Both routes perform the same operations.

### Unlimited Location Nesting

- **Decision**: No system-imposed depth limit on Location hierarchy.
- **Rationale**: The GM knows their world. A hard limit would be arbitrary and potentially frustrating.
- **Implications**: API and UI must handle arbitrary nesting. Tree rendering with lazy loading recommended.

### Story Freeform Tags

- **Decision**: Stories support an optional list of freeform string tags for categorization. No predefined vocabulary.
- **Rationale**: Flexible enough for any campaign. The GM can establish their own tagging conventions.
- **Implications**: Tag list stored as JSON array. API supports filtering by tag.

### Story Embedded Narrative Entries

- **Decision**: Stories have an embedded `entries` array with structured narrative records. Each entry has text, optional character/session/event references, optional game object links, and full audit trail fields (updated_at, updated_by, is_deleted, deleted_by).
- **Rationale**: Denormalized for easy display. Linked to events for audit. Serves both `work_on_project` proposals and GM-initiated narrative additions.
- **Implications**: Story objects grow over time. Entries support edit and soft-delete with per-entry audit tracking.

### Story Entry Editability

- **Decision**: Players can edit entries they created. GM can edit any entry. Deletions are soft-deletes with `deleted_by` tracking. Full audit trail per entry (updated_at, updated_by, is_deleted, deleted_by).
- **Rationale**: Players should be able to fix their own writing. GM needs full control. Soft delete preserves history.
- **Implications**: Entry edit authorization checks character_id against the requesting player. Edit events logged.

### Story Owners Sub-resource

- **Decision**: Story owners (polymorphic references to Characters, Groups, etc.) are managed via sub-resource API: `POST/DELETE /stories/{id}/owners` with `{type, id}` per record.
- **Rationale**: Consistent with other sub-resource patterns (bonds, session participants). Avoids replacing the full owner list on each update.
- **Implications**: Separate owner records table. Individual add/remove operations.

### Soft Delete for All Game Objects

- **Decision**: All game objects use soft delete via a base `is_deleted` flag. No hard deletes. **Exception**: Draft Sessions use hard delete (no downstream references). Per-type lifecycle fields (Story status) are independent.
- **Rationale**: References must remain valid. A Bond targeting a deleted NPC should still resolve to that NPC's data. Soft delete is simple and preserves history.
- **Implications**: All list endpoints filter `is_deleted = false` by default. Direct lookup endpoints return deleted objects (with a deleted flag visible). No cascade logic needed.

### Draft Session Hard Delete

- **Decision**: Draft Sessions use hard delete instead of soft delete. Active and Ended sessions are permanent and cannot be deleted.
- **Rationale**: Draft sessions have no downstream references — no events, no FT distributions, no participant history. Hard delete keeps the database clean. Once a session is Started (Active), it has side effects and must be preserved.
- **Implications**: `DELETE /sessions/{id}` returns 400 if session is not in Draft status. Exception to the general soft-delete rule.

### Group Tier Unbounded

- **Decision**: Group `tier` is any non-negative integer. No upper bound.
- **Rationale**: The GM decides the power scale for their campaign. Imposing a range (e.g., 0–5) would be arbitrary.
- **Implications**: Validation: `tier >= 0`. No tier-based game mechanics in the system (tier is informational).

### Clock Annotations via Event Log

- **Decision**: Clock adjustments are recorded as Events with annotation metadata (notes, event references, game object references). No denormalized annotation history on the Clock object.
- **Rationale**: The event log is already the audit trail. Duplicating annotation data on the Clock adds complexity without benefit. Clock history = filtered event query.
- **Implications**: Clock adjustment events need a rich `changes` field supporting notes and polymorphic references. Events spec needs to accommodate this.

### Event Auto-Capture to Active Session

- **Decision**: Events generated while a Session is Active are automatically tagged with that session's ID. Callers can override with a specific session_id. When no session is Active, session_id is optional/null.
- **Rationale**: Eliminates manual session tagging for the common case (most events happen during active play). Override supports edge cases (GM makes changes between sessions, or attributes an event to a different session).
- **Implications**: Event creation logic checks for an Active session and auto-fills session_id if not provided. Events spec needs to reflect this.

### Clock Completion Flags for GM

- **Decision**: When a clock reaches its segment count, the system flags it as completed and surfaces it to the GM. No automatic game state changes. The GM resolves consequences narratively.
- **Rationale**: Reflects deferred narrative resolution. Clock completion means "something happened" — what that something is depends on context that only the GM can interpret.
- **Implications**: Completed clock detection at the point of clock mutation. GM notification mechanism (API response flag, or dashboard indicator). GM creates events to record the resolution.

### Deferred Narrative Resolution (Design Principle)

- **Decision**: Documented as a named design principle applicable project-wide. Game state is intentionally left ambiguous until narratively observed.
- **Rationale**: Tabletop RPGs are collaborative fiction. The system should support potential/fuzzy state, not just concrete state. This mirrors how GMs actually run games — they don't decide everything upfront.
- **Implications**: Affects NPC locations (quantum), Group projects (undefined until clock completion), and potentially other domains. Should be referenced in architecture/overview.md and added to the glossary.
- **Examples**:
  - **NPC locations**: NPC has common_locations [Tavern, Market, Guild Hall]. When a player looks for the NPC, the GM decides where they are based on narrative context.
  - **Group projects**: Group has a project clock at 3/5 with a placeholder description. At 5/5, the GM looks at recent events, the group's bonds and goals, and decides what the project was and what it produced.

---

## API Endpoints

### NPCs
- `GET /api/v1/npcs` — list (filters: `?location_id=`, `?is_deleted=false` default)
- `GET /api/v1/npcs/{id}` — detail with bonds, common locations, and merged location view
- `POST /api/v1/npcs` — create (GM)
- `PATCH /api/v1/npcs/{id}` — update (GM)
- `DELETE /api/v1/npcs/{id}` — soft delete (GM, sets `is_deleted = true`)
- `POST /api/v1/npcs/{id}/bonds` — add a bond (GM)
- `PATCH /api/v1/npcs/{id}/bonds/{bond_id}` — update a bond (GM)
- `DELETE /api/v1/npcs/{id}/bonds/{bond_id}` — deactivate a bond (GM)

### Groups
- `GET /api/v1/groups` — list (filters: `?is_deleted=false` default)
- `GET /api/v1/groups/{id}` — detail with clocks, bonds, and computed members
- `POST /api/v1/groups` — create (GM)
- `PATCH /api/v1/groups/{id}` — update (GM)
- `DELETE /api/v1/groups/{id}` — soft delete (GM)
- `POST /api/v1/groups/{id}/bonds` — add a bond (GM)
- `PATCH /api/v1/groups/{id}/bonds/{bond_id}` — update a bond (GM)
- `DELETE /api/v1/groups/{id}/bonds/{bond_id}` — deactivate a bond (GM)
- `POST /api/v1/groups/{id}/clocks` — add a project clock (GM)
- `PATCH /api/v1/groups/{id}/clocks/{clock_id}` — advance/modify a clock (GM, generates event with annotations)

### Clocks
- `GET /api/v1/clocks` — list all clocks including group project clocks (filters: `?associated_with=`, `?group_id=`, `?is_deleted=false` default)
- `GET /api/v1/clocks/{id}` — detail
- `POST /api/v1/clocks` — create standalone clock (GM)
- `PATCH /api/v1/clocks/{id}` — advance or modify any clock (GM, generates event with annotations)
- `DELETE /api/v1/clocks/{id}` — soft delete (GM)

### Locations
- `GET /api/v1/locations` — list (filters: `?parent={id}` for hierarchy, `?is_deleted=false` default)
- `GET /api/v1/locations/{id}` — detail with curated affiliations and computed presence (merged NPC/Group lists)
- `POST /api/v1/locations` — create (GM)
- `PATCH /api/v1/locations/{id}` — update including curated npcs/groups lists (GM)
- `DELETE /api/v1/locations/{id}` — soft delete (GM)

### Stories
- `GET /api/v1/stories` — list (filters: `?status=active`, `?tag=`, `?owner=`, `?is_deleted=false` default)
- `GET /api/v1/stories/{id}` — detail with entries and owners
- `POST /api/v1/stories` — create (GM)
- `PATCH /api/v1/stories/{id}` — update including status changes (GM)
- `DELETE /api/v1/stories/{id}` — soft delete (GM)
- `POST /api/v1/stories/{id}/owners` — add an owner (GM, `{type, id}`)
- `DELETE /api/v1/stories/{id}/owners/{type}/{owner_id}` — remove an owner (GM)
- `POST /api/v1/stories/{id}/entries` — add a narrative entry
- `PATCH /api/v1/stories/{id}/entries/{entry_id}` — edit an entry (own entries or GM)
- `DELETE /api/v1/stories/{id}/entries/{entry_id}` — soft-delete an entry (own entries or GM)

### Sessions
(Fully defined in [downtime](downtime.md))
- `POST /api/v1/sessions` — create a Draft session (GM)
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

---

## Open Questions

None — all questions resolved.

---

## Implications for Other Specs

| Spec | Implication |
|------|-------------|
| [character-core](character-core.md) | Characters are a game object type; share the common fields pattern including `is_deleted`. Need `last_session_time_now` field and `session_ids` list (from downtime). 🔄 **Rename**: Faction → Group. |
| [bonds](bonds.md) | PC Bonds remain Trait Instances with stress mechanics. Lightweight bonds on NPCs/Groups are a simpler model. Bond targets include deleted objects (soft delete preserves references). 🔄 **Rename**: Faction → Group. Bond directionality model affects bond-distance visibility graph. |
| [events](events.md) | 🔄 Events auto-tag to Active session. Clock adjustment events need annotation support. Session timeline is a filtered event query. **Rename**: Faction → Group. |
| [downtime](downtime.md) | Session lifecycle fully defined there. Clock adjustments happen during Active via individual calls. Group project completion flags surface to GM. 🔄 **Rename**: Faction → Group. |
| [proposals](proposals.md) | Player projects use Stories (narrative entries, no segmented clock). `work_on_project` adds entries to the Story object. 🔄 **Rename**: Faction → Group. |
| [traits](traits.md) | 🔄 **Rename**: Faction → Group in any references. |
| [magic-system](magic-system.md) | 🔄 **Rename**: Faction → Group in any references. |
| [auth](auth.md) | 🔄 **Rename**: Faction → Group in any references. |
| [architecture/overview](../architecture/overview.md) | 🔄 Deferred Narrative Resolution should be documented as a named design principle. **Rename**: Faction → Group. |
| [architecture/data-model](../architecture/data-model.md) | 🔄 Shared base fields (`is_deleted`). Lightweight bond model with directionality. NPC `attributes` blob. Story entries with audit trail. Clock default segments. Event auto-capture. Location curated affiliations. **Rename**: Faction → Group. |
| [architecture/mvp-scope](../architecture/mvp-scope.md) | 🔄 **Rename**: Faction → Group. |

---

_Last updated: 2026-03-02 (second interrogation — bond directionality model, location curated affiliations, story entry editability, Faction→Group rename, 14 new decisions for 31 total)_
