# Glossary

Canonical definitions for domain terms used in this project. When a term appears in specs, it means exactly what's defined here.

---

## How to Use This Glossary

- **When reading specs**: If a term seems unclear, check here first
- **When writing specs**: Use terms exactly as defined; add new terms as needed
- **During interrogation**: The agent will add terms that emerge from discussion

---

## Terms

### Game Object
An entity that exists "in the fiction" — a node in the game world. Exactly three types: **Character**, **Group**, and **Location**. All Game Objects share common fields: `id`, `name`, `description`, `is_deleted`, `created_at`, `updated_at`, plus type-specific fields. Game Objects are connected by Bonds. All Game Objects use soft delete (`is_deleted` flag) — deleted objects are hidden from lists but remain accessible via direct lookup, and references to them stay valid. Clocks, Sessions, and Stories are **System Entities**, not Game Objects — they are tracking/organizational tools that don't participate in the bond graph.

### Character
A Game Object representing a being in the fiction — both player characters (PCs) and non-player characters (NPCs). Characters have a `detail_level` field: **full** (PC) or **simplified** (NPC). Two creation paths: NPCs are created by the GM via `POST /api/v1/characters` (name only required); PCs are created by the player during invite redemption via `POST /api/v1/game/join` (player provides character name, all mechanical fields default to 0). All Characters share: name, description, notes, and freeform `attributes` JSON blob. **Full (PC)** Characters have **8 Bond slots** (targeting any Game Object) with mechanical depth (stress, degradation, +1d), plus resource meters (Stress, FT, Plot, Gnosis), Skills (8), Magic Stats (5), Magic Effects, Core Traits (2 slots), and Role Traits (3 slots). **Simplified (NPC)** Characters have **7 Bond slots** with descriptive-only Bonds (no stress, no mechanics) and no meters, skills, magic, or Core/Role traits. Players can edit their own character's name, description, and notes directly. The GM is a Player with full visibility, configuration, and proposal approval capabilities.

### NPC
A Character without a player login assigned. Has `detail_level = simplified`. Same entity type as a PC — just with fewer active fields. Participates fully in the bond graph. See **Character**.

### Group
A Game Object representing an organization, crew, family, guild, or other group in the game world. Has a power tier (any non-negative integer), project clocks, and notes. Groups have **10 descriptive trait slots** (freeform, no enforced categories — see [traits.md](domains/traits.md)). Groups have two bond categories: **Relations** (7 slots, Group↔Group, bidirectional with source/target labels) and **Members** (unlimited, Character↔Group). All Group bonds are descriptive (no stress, no degradation). A Character powerful enough to operate at Group scale gets their own single-member Group to participate in Relations. Group project outcomes follow Deferred Narrative Resolution.

### Clock (System Entity)
A progress tracker (Blades in the Dark-style) — a **System Entity**, not a Game Object. Has a configurable number of segments (any positive integer, default 5). Clocks can be associated with any single Game Object (Character, Group, or Location) via polymorphic reference, or exist standalone. Created via `POST /api/v1/clocks` (standalone or with association) or `POST /api/v1/groups/{id}/clocks` (auto-associates with Group). Association is fixed at creation — cannot be changed. Group project clocks are the most common pattern — accessible via both the Group sub-resource and standalone endpoint. Completion is computed on read (`progress >= segments`). When completion is detected, the system **auto-generates a `resolve_clock` proposal** in pending state — one per clock, ever (idempotent: only if no pending or approved resolve_clock exists for that clock_id). GM can advance past segment count (soft cap); further advances after resolution don't generate new proposals. Clock adjustments are recorded via the Event log with annotation metadata.

### Location
A Game Object representing a place in the game world. Locations form a nestable hierarchy with unlimited depth. Locations have **Feature Traits** (5 descriptive slots — physical characteristics, atmosphere, dangers) and **unlimited bonds** to any Game Object. Presence ("who's here") is computed via **Bond-Distance Presence** — derived from the bond graph, not curated lists. Locations can bond outward to Characters, Groups, and other Locations.

### Session (System Entity)
A **System Entity** (not a Game Object) recording a single play session. Strictly forward lifecycle: **Draft → Active → Ended** (no undo or reopen). Key fields: `time_now` (abstract campaign time counter, GM-set), `status`, `date`, `summary`, `notes`, and a participant list. Only one Active session at a time. Draft sessions are editable and hard-deletable. Active sessions allow edits to summary/notes and late-joining participants. Ended sessions are read-only. On **Start**: FT distributed via Time Now delta, Plot awarded (+1/+2). On **End**: status transitions. Characters store session IDs for bidirectional history lookups.

### Story (Arc) (System Entity)
A **System Entity** (not a Game Object) tracking a narrative thread. Stories have owners (Characters, Groups, or other entities — managed via sub-resource API), a status (active, completed, abandoned), optional freeform tags, an embedded `entries` list for structured narrative progress, and can nest into sub-arcs via a parent reference. Entry editability: players edit own entries, GM edits any, soft-delete for removals. Player projects use Stories as the tracking object.

### Stress
A meter on a Character representing accumulated harm and pressure. Range 0–9 (effective max decreases by 1 per Trauma; computed as `9 - count(trauma bonds)`). When Stress hits max, the character gains a Trauma and Stress resets to 0. Healed via the "Rest" downtime action (3 base + up to +3 from modifiers, costs 1 Free Time).

### Trauma
The consequence of maxing character Stress. When Stress hits its effective max, the system auto-generates a `resolve_trauma` proposal (similar to `resolve_clock` for clock completion). The GM fills in which bond becomes the trauma and the trauma description. On approval: the existing Bond in the chosen slot retires to Past (`is_active = false`, history preserved). A new Bond instance is created with `is_trauma = true`, trauma-specific name/description, no target, and fresh charges (5). Each Trauma reduces the character's effective Stress max by 1. Fixable via GM direct action (GM chooses outcome — blank slot, new bond, etc.). If all Bonds are already Trauma, the GM handles narratively.

### Free Time
A resource meter (0–20) on a Character, spent on downtime activities (1 FT per action). Gained automatically at Session Start via Time Now delta: `session.time_now - character.last_session_time_now`. Also gained via Find Time (3 Plot → 1 FT). Carries over between sessions. Capped at 20 (excess lost).

### Plot
A resource meter on a Character. Nominal range 0–5, but can temporarily exceed 5 from any source (session income, GM awards). **Clamped to 5 at Session End** — players have the Active session window to convert excess via Find Time. Gained at Session Start: +1 per session participated, +2 if "Additional Contribution" checked (meta-game reward). GM can also award bonus Plot. Spent on proposals: each Plot places a **guaranteed success** (a 6) before rolling — not an extra die, but a guaranteed result. Can also be used flexibly (surviving impossible odds, narrative tweaks) at GM discretion. No cap on Plot spend per proposal. Declared on submission. Can be converted to FT via Find Time (3 Plot → 1 FT).

### Gnosis
A resource meter (0–23) on a Character. The primary magical resource, spent as sacrifice in Magic Actions and Charge Actions. Converted to additional dice via a tiered table (diminishing returns: N dice costs N×(N+1)/2 Gnosis). Regained via downtime activity.

### Meter
A bounded numeric value with a defined range. Used for Stress, trait charges, clock progress, and other trackable quantities. Meter mutations in the event log carry an `op` tag (`meter.delta` or `meter.set`) and an optional `clamped` flag when a boundary is hit. See [events.md](domains/events.md) for the operation type catalog and meter boundary patterns.

### Resource Meter
A meter that functions as a spendable/gainable currency — can be consumed by actions and replenished through gameplay. Free Time, Plot, and Gnosis are resource meters.

### Operation Type
A classification tag (`op`) on each entry in an event's `changes` dict. Three values: **`field.set`** (non-numeric or unbounded field assignment), **`meter.delta`** (bounded numeric adjusted by a signed amount), **`meter.set`** (bounded numeric set to an absolute value). Set by the Python code creating the event. Makes the event log queryable by mutation kind without introducing a DSL. See [events.md](domains/events.md).

### Meter Boundary
The condition when a meter hits its min or max value. Some meters have hardcoded boundary behaviors — side effects that fire automatically (e.g., Trauma on max Stress, bond degradation on max bond stress, clock auto-proposal on completion). When a boundary is hit, the change entry gains `"clamped": true`. See [events.md](domains/events.md) for the full boundary catalog.

### Compound Consequence
A boundary trigger that causes additional mutations within the same event. The canonical example is **Trauma**: when Stress hits max, the system retires a bond, creates a trauma bond, and resets stress — all recorded in a single event. Preserves the "one event per action" rule. See [events.md](domains/events.md).

### Trait Template
A GM-created catalog entry defining a Core or Role Trait. Has a name, description, and type (`core` or `role`). Type is immutable after creation — Core templates fill Core slots, Role templates fill Role slots. Exists independently of any character — multiple characters can share the same Trait Template. Editing a template's name or description propagates to all characters referencing it. Soft-deleting a template does NOT cascade to instances — existing trait instances keep their `template_id` reference and remain functional, but the template is hidden from catalog lists. A character can only have one active instance of a given template. Players can propose new templates via the "New Trait" downtime action — on GM approval, the system automatically creates a Trait Template in the catalog and links the instance. Managed via standard REST CRUD: `GET/POST /api/v1/trait-templates`, `GET/PATCH/DELETE /api/v1/trait-templates/{id}` (all GM-only). Bonds do not use Trait Templates; they reference game objects instead.

### Trait Instance
A per-character record linking to either a Trait Template (for Core/Role Traits) or a game object (for Bonds). Holds character-specific state: charges (Core/Role) or stress (Bonds), `is_active` flag, and an event history stream. The unified model shared by Core Traits, Role Traits, and Bonds.

### Past/Retired
The state of a Trait Instance, Bond, or Magic Effect that has been replaced, sacrificed, or retired (via downtime action, Trauma, sacrifice, or GM action). Marked `is_active = false`. Remains on the character sheet in a "Past" section with full event history preserved and viewable, but cannot be used mechanically.

### Core Trait
One of a Character's two defining-quality Trait Instance slots. Links to a Trait Template from the GM-created catalog. Has a charge meter (0–5). When invoked on a proposal, costs 1 charge and grants +1d to the dice pool. Can be referenced narratively without charge cost. New traits start at full charge (5). Slots may be blank. Traits are added by GM direct action and can be replaced via the "New Trait" downtime action. Replaced traits move to Past.

### Role Trait
One of a Character's three learned-ability Trait Instance slots. Same structure and mechanics as Core Traits (links to Trait Template, charge 0–5, +1d bonus, 1 charge per invocation).

### Charge
A meter (0–5) on a Trait that is spent (1 per invocation) to activate its +1d bonus. Replenished via the "Recharge Trait" direct player action (full restore on one trait, costs 1 Free Time).

### Modifier Stacking
The rule governing how many modifiers a player can select on a single proposal: at most 1 Core Trait (+1d), 1 Role Trait (+1d), and 1 Bond (+1d), for a maximum of +3d on top of the base skill dice pool.

### Bond
The unified relationship primitive connecting Game Objects. Every relationship in the system is a Bond — between Characters, Groups, Locations, or any combination. All bonds share common fields: id, source (type + id), target (type + id), source_label, target_label, description, is_active, bidirectional flag. **Mechanical depth varies by context**: PC Bonds (on full Characters) have charges (0–5, conceptually same as trait charges), degradation, and +1d on proposals (8 slots). NPC Bonds, Group bonds (Relations/Holdings), and Location bonds are descriptive only (active/retired, no mechanics). Bond depth for PCs is captured by accumulated fiction, not a numeric level. **Slot model**: Count-based (not indexed) — system enforces max active bonds per owner type, bonds referenced by ID. At most one active bond per (source, target) pair. Slot type is auto-inferred from owner/target types. Source always consumes a slot (hard limit); target gets a soft-limit warning for bidirectional bonds. Bidirectional bonds appear in both sides' bond lists with no distinction (API normalizes perspective). Only active bonds participate in traversal. The bond graph drives both **event visibility** and **presence proximity**. All traits and bonds live in one fully unified table with a `slot_type` discriminator. A Character's bond to a Group IS their Group membership (derived, not stored as a separate type). See [bonds.md](domains/bonds.md) for authoritative spec.

### Bond Charges
A charge meter on a Bond (base max 5). Conceptually the same as trait charges — a measure of how much the bond can be drawn upon before it strains. Lost from GM narrative actions or −1 when GM decides a proposal bond use strains it (via `bond_strained` flag). At 0 charges: charges reset to effective max, degradation count increments by 1 (effective max decreases), GM narrates consequence. Restored fully via "Maintain Bond" direct player action. GM can reverse degradation via direct action. DB column: `charges`.

### Bond Degradation
A count on a Bond tracking how many times its charges have hit 0. Effective bond charge max = `5 - degradation_count`. At 5 degradations (effective max 0), GM handles narratively. DB column: `degradations`.

### Skill
One of exactly 8 canonical abilities hardcoded in code: Awareness, Composure, Influence, Finesse, Speed, Power, Knowledge, Technology. The same list for all characters. Each Skill has a level (0–3) that equals the base dice pool size for related actions. All characters have all 8 skills at different levels. Skill levels increase via "Work on Project" downtime action — player targets a Story/Arc for the skill being trained. GM resolves (and applies level change via direct action) when the narrative warrants it.

### Magic Stat
One of five hardcoded schools of magic: Being, Wyrding, Summoning, Enchanting, Dreaming. Level (0–5) IS the base dice pool for magic actions using that stat. XP meter (flat 5 XP per level, GM awards directly) tracks progress toward next level. All Magic Stats start at level 0 for new characters.

### Magic Action
A proposal action type for performing freeform magic. Player provides Intention (text), Symbolism (text), and Sacrifice (a list of entries — can combine Gnosis, Stress, Free Time, Bond/Trait sacrifice, and Other freely in one action). Player suggests a Magic Stat; GM has final say. Dice pool = Magic Stat level + sacrifice dice (tiered) + use modifiers (up to +3d). GM reviews and creates exactly one Magic Effect on the character's sheet as the outcome. GM interprets the roll to set effect name, description, power_level (1–5), and initial charges.

### Charge Action
A variant of Magic Action used to recharge a charged Magic Effect or boost a permanent item. Same workflow (intention, symbolism, sacrifice) but targets an existing effect. On charged effects: restores charges and can increase max charges beyond original (power_level fixed at creation). On permanent effects: increases power_level (within 1–5 scale). GM interprets roll to determine outcome. On approval, GM provides `{charges_added?: int, power_boost?: int}` in `gm_overrides` — mutually exclusive based on target effect type.

### Magic Effect
The outcome of a Magic Action, created by the GM on a character's sheet. Three types: **instant** (one-time, not tracked), **charged** (persistent, power_level 1–5, charges_current/charges_max unbounded, each use costs 1 charge, player-initiated direct use without proposal with optional narrative), and **permanent** (always-active, no charges, power_level 1–5, primarily from Enchanting). Max 9 active effects per character (charged + permanent; instants don't count). Players can self-retire effects (no approval needed). Charged effects are recharged via Charge Action.

### Sacrifice (Magic)
Resources spent to power a Magic Action or Charge Action, stored as a **list of entries** (can combine freely). Converted to Gnosis equivalent: Gnosis (1:1), Stress (1 = 2 Gnosis, standard Stress rules apply — can trigger Trauma), Free Time (1 = 3 + lowest Magic Stat), Bond/Trait sacrifice (10 Gnosis, goes to Past), Other (freeform text, GM assigns Gnosis value during review). Distinct from *Using* a trait/bond (+1d modifier). Hidden GM "style" bonus added separately.

### Style Bonus
A hidden GM-only Gnosis modifier added during Magic Action review. Rewards creative narrative, good symbolism. Not visible to the player.

### Action (Unified)
A typed, validated input that produces an Event row as output. All state changes in the system are actions. Three paths: **Player Proposals** (approval gate — submit, GM reviews, approve/reject), **GM Actions** (direct event creation via `POST /api/v1/gm/actions`), and **Player Direct Actions** (no approval needed — `find_time`, `use_effect`, `retire_effect`, `recharge_trait`, `maintain_bond`). See [actions.md](domains/actions.md) for the authoritative spec.

### Proposal
A player-submitted request to change game state, requiring GM approval. Three categories: **Actions** (session play: `use_skill`, `use_magic`, `charge_magic`), **Downtime Actions** (between sessions: `regain_gnosis`, `work_on_project`, `rest`, `new_trait`, `new_bond`), and **System Proposals** (auto-generated: `resolve_clock`, `resolve_trauma`). All downtime actions auto-cost 1 Free Time. Submitted via `POST /api/v1/proposals`. Workflow: submit (player writes narrative, system validates + calculates) → GM reviews + rolls at table → approve (optional narrative override + optional overrides + optional rider event, system auto-applies all consequences) or reject (note, player revises in place). Players can edit both pending and rejected proposals — auto-recalculates on PATCH. The `calculated_effect` is a typed structure per action type including both outcome and costs. GM overrides **replace** calculated values (not additive). On approval, if resources are insufficient, system returns 409 Conflict; GM retries with `force: true` to confirm. GM approval payload includes: `bond_strained` (boolean, +1 stress on modifier bond), `charges_added`/`power_boost` (for `charge_magic`). All GM approval-specific fields stored in `gm_overrides` JSON (only `force` is transient). One event generated per approval, plus an optional rider event (linked via `rider_event_id` FK on proposals table). Proposals have an `origin` field (`player` or `system`); system proposals have nullable `character_id`. The system does not record dice results — dice are physical, the narrative IS the outcome. Slot targeting is **count-based** (not indexed) — traits and bonds referenced by ID, with `retire_bond_id`/`retire_trait_id` when at max count. Players can hard-delete pending or rejected proposals via `DELETE /proposals/{id}` (GM can delete any non-approved proposal). Approved proposals are permanent. Proposals persist across sessions — no auto-cleanup.

### GM Action
A direct state-changing action performed by the GM, bypassing the proposal workflow. Submitted via `POST /api/v1/gm/actions` with typed payload (`action_type`, `targets`, `changes`, `narrative`, optional `visibility`). ~14 coarse action types: `modify_character`, `modify_group`, `modify_location`, `create_bond`, `modify_bond`, `retire_bond`, `create_trait`, `modify_trait`, `retire_trait`, `create_effect`, `modify_effect`, `retire_effect`, `award_xp`, `modify_clock`. Each action type has a default visibility level. **Reuses domain event types** (e.g., `character.stress_changed`, not `gm.modify_character`) — distinguished by `actor_type: "gm"`. **Integrity-only validation** — valid types, valid references, correct data types; no game-logic range enforcement. GM actions are the exclusive path for all mechanical state changes (meters, skills, bonds, traits, effects, clocks, tier, parent_id, attributes) — CRUD endpoints handle only structural fields (name, description, notes) + creation/deletion. See [actions.md](domains/actions.md).

### CRUD/GM Action Split
The architectural separation between REST CRUD endpoints and the GM actions endpoint. **CRUD endpoints** (POST/GET/PATCH/DELETE on game object routes) handle structural operations: creating objects, soft-deleting objects, and editing non-mechanical fields (name, description, notes). **GM actions** (`POST /api/v1/gm/actions`) handle all mechanical state changes: meters, skills, magic stats, attributes, bonds, traits, effects, clocks, tier, parent_id. No overlap. Creation (POST) is a setup exception — accepts all fields including mechanical ones. This split applies consistently across all game object types (Characters, Groups, Locations).

### Downtime
Not a distinct system mode. Downtime mechanics are embedded in the session lifecycle: FT is distributed at Session Start (via Time Now delta), group clocks are adjusted at Session End, and players can submit Downtime Action proposals whenever they have Free Time. All downtime actions cost 1 FT.

### Time Now
An abstract integer counter set by the GM on each Session. Represents the passage of campaign time. The difference between a character's `last_session_time_now` and the current Session's Time Now determines Free Time gained. GM controls pacing — a larger gap means more FT.

### Additional Contribution
A per-participant boolean flag on session registration. Represents a meta-game contribution (wrote session recap, brought snacks, helped organize, etc.). Awards +1 bonus Plot at Session Start (+2 total instead of +1). No in-fiction requirement.

### Player Direct Action
An action that bypasses the proposal workflow — the player triggers it directly and an Event is created immediately. Five types: `find_time` (3 Plot → 1 FT), `use_effect` (decrement charge on a Magic Effect), `retire_effect` (retire a Magic Effect), `recharge_trait` (restore trait charges to 5, costs 1 FT, requires narrative), `maintain_bond` (restore bond charges to effective max, costs 1 FT, requires narrative). See [actions.md](domains/actions.md).

### Find Time (Player Direct Action)
A direct player action (no proposal needed) that converts **3 Plot → 1 Free Time**. Can be done at any time. Prevents Plot waste at the 5 cap. Event logged. FT gained respects the 20 cap.

### Deferred Narrative Resolution
A core design principle: game state is intentionally left ambiguous until narratively observed. The system supports potential/fuzzy state alongside concrete state. Examples: Characters have bond-distance presence at Locations (not a pinned position) — their actual location is resolved at the table when someone looks for them. Group projects have mechanical progress (clock segments) but their outcomes are defined retroactively when the clock completes. This mirrors how GMs actually run games — not everything is decided upfront.

### System Entity
A tracking or organizational tool that exists outside the fiction. Includes **Clocks**, **Sessions**, and **Stories**. System Entities do not participate in the bond graph and are not Game Objects. They serve the game mechanically but don't have narrative identity as world entities.

### Bond-Distance Presence
A computed view derived from the bond graph, replacing curated affiliation lists and `common_locations`. For a Location: **Commonly present** (1-hop direct bond), **Often present** (2-hop bond-of-bond), **Sometimes present** (3-hop). Works bidirectionally — also computes a Character's locations: Common (1-hop), Familiar (2-hop), Known (3-hop). Computed on read (no caching). Uses the same Character-intermediary traversal as visibility. Only active bonds participate; Trauma bonds and soft-deleted Game Objects are dead ends.

### Group Trait (Descriptive)
One of a Group's 10 descriptive trait slots. Freeform name + description representing any defining characteristic — culture, training, assets, reputation, etc. No categories enforced, no charges, no dice bonuses. Simple replace lifecycle (GM overwrites directly, no Past/Retired pattern). Changes logged in the event log. Players can influence via `work_on_project` proposals. See [traits.md](domains/traits.md) for authoritative spec.

### Relations (Group Bond)
One of a Group's seven bond slots connecting to other Groups. Bidirectional with `source_label`/`target_label`. Descriptive only — no stress, no degradation. A Character operating at Group scale gets their own single-member Group to participate in Relations.

### Members (Derived)
Group membership is **derived from the bond graph**, not stored as a separate type. Any Character (PC or NPC) with a bond targeting a Group is a member. The Group's `members` list is computed by querying inbound Character bonds. A PC's bond to a Group uses one of their 8 Bond slots (with full stress mechanics) AND makes them a member. An NPC's bond to a Group uses one of their 7 slots (descriptive only) AND makes them a member.

### Holdings (Group Bond)
Unlimited bond slots on a Group connecting to Locations. Represents territorial control, properties, meeting places, sacred sites. Directional (Group → Location). Descriptive only — no stress, no degradation.

### Feature Trait (Location)
One of a Location's 5 descriptive trait slots representing physical characteristics, atmosphere, dangers, or notable qualities (e.g., "heavily fortified", "sacred ground", "bustling market"). All slots are interchangeable — categories are naming conventions, not enforced. No charges, no dice bonuses. Simple replace lifecycle (same as Group Traits). Players can influence via `work_on_project` proposals. See [traits.md](domains/traits.md) for authoritative spec.

### Detail Level
A field on Characters indicating the level of mechanical detail: **full** (PC — meters, skills, magic, Core/Role traits, mechanical bonds) or **simplified** (NPC — descriptive bonds only, no meters/skills/magic/traits). Determines which fields are active on the Character record.

### Soft Delete
The deletion model for most game objects. Setting `is_deleted = true` hides the object from list endpoints but preserves it for direct lookup. References to deleted objects remain valid (e.g., a Bond targeting a deleted NPC still resolves). Per-type lifecycle fields (e.g., Story status) are independent of the deletion flag. **Exception**: Draft Sessions use hard delete (no downstream references exist).

### Clock Adjustment Annotation
Metadata attached to a clock adjustment event. Includes freeform notes and optional links to events or game objects, explaining why the clock was advanced, delayed, or skipped. Stored on the Event record (not denormalized on the Clock object). Created during Active sessions when the GM adjusts group clocks.

### Event (Event Log Entry)
An immutable record of a state change. Fields: `id` (ULID, time-sortable), `type` (convention-based `{domain}.{action}` string), `actor` (typed ref: player/gm/system), `targets` (list of game object refs via `event_targets` table), `changes` (fully qualified entries using `{type}.{id}.{field}` keys where type = DB table name singular — each value carries `{op, before, after}` with an optional `clamped` flag; see Operation Type), `created_objects`/`deleted_objects` (object lifecycle lists), `narrative` (optional, from GM/player/system), `proposal_id` (optional back-ref), `session_id` (auto-captured from Active session; rider events inherit from parent), `visibility` (one of 7 levels — see Unified Visibility Model), `metadata` (freeform JSON for annotations/links), `created_at` (only timestamp — no separate `timestamp` column; ULID provides sort order). Events are append-only — never modified or deleted (except `visibility`, which the GM can override). One event per state-changing action, even compound changes — boundary-triggered mutations (e.g., Trauma) are recorded within the same event (see Compound Consequence). **Exception**: session start produces 3 separate events (`session.started` global, `session.ft_distributed` silent, `session.plot_distributed` silent). Three event types default to `silent` visibility: `session.ft_distributed`, `session.plot_distributed`, `clock.resolve_generated`. Story entries and user-level actions do not produce events.

### Event Log
The append-only collection of all Event records. Provides history and audit trail. State (not the event log) is the source of truth. Retained indefinitely — no cleanup or archival.

### Unified Visibility Model
The visibility model for all feed items (Events and Story entries). Seven levels: **global** (all see), **public** (3-hop bond graph), **familiar** (2-hop bond graph — default for Stories), **bonded** (1-hop direct bond), **private** (owner-scoped — union of actor's character + primary target's PC owner + GM), **gm_only** (GM only), **silent** (GM-only silent feed — bookkeeping). The `familiar` and `public` levels use **Character-intermediary** bond-graph traversal: after a non-Character node, the next hop must go through a Character (PC or NPC). PCs are valid intermediaries. All active bond types participate. Computed on read. GM can override per-Event (change visibility level) and per-Story (set `visibility_level` field and/or add player IDs to `visibility_overrides`). See [feed.md](domains/feed.md) for authoritative spec.

### Feed
A unified, visibility-filtered view of activity on Game Objects. Merges Events and Story entries into a single chronological stream using a **discriminated union** response shape (`type: "event"` or `type: "story_entry"`) with common fields (`id`, `type`, `timestamp`, `narrative`, `visibility`, `targets`, `is_own`) at the top level. A query pattern, not a stored entity — no new data model. Three player-facing endpoints: per-Game Object feed (`/{type}/{id}/feed`), complete personal feed (`/me/feed`, includes own actions with `is_own` flag), and starred feed (`/me/feed/starred`). Plus a GM-only silent feed. All endpoints use ULID cursor pagination (`?after=<ulid>&limit=N`, default 50, max 100) and support full filtering (`type`, `target_type`, `target_id`, `actor_type`, `session_id`, `since`, `until`). Rider events appear as separate feed items linked via `parent_event_id`. See [feed.md](domains/feed.md).

### Starring
A player feature for tracking Game Objects of interest. Stored in the `starred_objects` table (typed Game Object refs per user). The starred feed filters the complete personal feed to only starred objects.

### New Trait (Downtime Action)
A downtime activity where a player replaces an existing Core/Role Trait or fills a blank trait slot. Player specifies `{slot_type, template_id?, proposed_name?, proposed_description?, retire_trait_id?}` — `retire_trait_id` required when at max active count for that slot type. Submitted as a proposal for GM approval. New traits start at full charge (5). Old trait moves to Past.

### New Bond (Downtime Action)
A downtime activity where a player creates a new Bond or replaces an existing one. Player specifies the target Game Object and writes narrative fiction. If at max active bond count, player must also specify `retire_bond_id` (which existing bond to retire to Past). If under max, fills a blank slot. Submitted as a proposal for GM approval. Old bond (if retiring) moves to Past.

### Maintain Bond (Direct Player Action)
A direct player action (no GM approval needed) that fully restores a Bond's charges to effective max. Costs 1 Free Time. Does not reverse degradations. Player selects which bond to maintain and writes a narrative describing what their character does. Creates an event immediately. Formerly a downtime proposal; promoted to direct action because the outcome is fixed and requires no GM decision.

### Regain Gnosis (Downtime Action)
A downtime action that restores Gnosis to a character. Costs 1 Free Time. Formula: **3 Gnosis base + lowest Magic Stat level + up to +3 from trait/bond invocation** (standard stacking: 1 Core +1, 1 Role +1, 1 Bond +1). Submitted as a proposal. Trait charges spent as usual; bond may strain per GM decision.

### Recharge Trait (Direct Player Action)
A direct player action (no GM approval needed) that fully restores a Core or Role Trait's charges to 5. Costs 1 Free Time. Player selects which trait to recharge and writes a narrative describing what their character does. Creates an event immediately. No modifiers — fixed outcome. Formerly a downtime proposal; promoted to direct action because the outcome is fixed and requires no GM decision.

### Rest (Downtime Action)
A downtime action that heals character Stress. Costs 1 Free Time. Formula: **3 Stress healed base + up to +3 from trait/bond invocation** (standard stacking: 1 Core +1, 1 Role +1, 1 Bond +1). Heals 3–6 Stress per rest.

### Work on Project (Downtime Action)
A downtime action that progresses a personal project (Story/Arc). Costs 1 Free Time. Adds a narrative entry to the target Story. No mechanical calculation — the GM resolves the project when the fiction warrants it. Skill training uses this action, targeting a Story for the skill being trained.

### Session Action (Proposal Category)
A proposal submitted during session play. Three types: `use_skill`, `use_magic`, `charge_magic`. No automatic Free Time cost. Uses dice pool calculations with base + modifiers + Plot.

### Downtime Action (Proposal Category)
A proposal submitted during the downtime phase. Five proposal types: `regain_gnosis`, `work_on_project`, `rest`, `new_trait`, `new_bond`. All automatically cost 1 Free Time, deducted on approval. Two former downtime types (`recharge_trait`, `maintain_bond`) are now direct player actions — they still cost 1 FT but resolve immediately without GM approval.

### Resolve Trauma (System Proposal)
A system-generated proposal created automatically when a character's Stress hits its effective max (`9 - count(trauma_bonds)`). Pre-linked to the character. The GM fills in which bond becomes the trauma (`trauma_bond_id`) and the trauma name/description. On approval, the system retires the chosen bond to Past, creates a new trauma bond (`is_trauma = true`, no target, fresh charges), and resets Stress to 0 — all recorded in a single event (compound consequence). Parallels the `resolve_clock` pattern. Idempotent: only generated if no pending `resolve_trauma` proposal exists for that character.

### Resolve Clock (System Proposal)
A system-generated proposal created automatically when a clock reaches completion (progress >= segments). Pre-linked to the clock and its containing game objects (e.g., the Group that owns a project clock). The GM fills in narrative describing the outcome and optionally attaches a rider event to apply world state changes. Extends the Deferred Narrative Resolution principle — the clock tracked mechanical progress, the resolution is written when it completes.

### Rider Event
An optional GM direct-action event bundled atomically with a proposal approval. Same schema as any event (targets, changes, narrative). Used when the GM wants to narrate side effects alongside the approval — e.g., "your skill check succeeds AND the clock advances +2 AND this NPC reacts." Created in the same transaction as the approval event. Also used for clock resolution: the GM fills in the resolve_clock proposal and attaches a rider event with the world state changes.

### Calculated Effect
The system's pre-computed result of a proposal — a **typed structure per action type** including both outcome and all resource costs. E.g., `use_skill: {dice_pool: 4, modifiers: [...], costs: {trait_charges: [...], plot: 2}}`, `rest: {stress_healed: 5, costs: {free_time: 1}}`, `regain_gnosis: {gnosis_gained: 7, costs: {free_time: 1, trait_charges: [...]}}`. Displayed to the GM during review so they see exactly what will happen. The GM can override any field via `gm_overrides` — overrides **replace** (not add to) calculated values. On approval, the system auto-applies the (potentially overridden) calculated effect to game state. Auto-recalculated when a rejected proposal is revised.

### User (Player Account)
A person who interacts with the system. Has an ID (ULID), display name (1–50 chars, trimmed, non-empty, editable via `PATCH /api/v1/me`), role (`gm` or `player`), login code (plaintext, indexed), optional linked character ID, and active status. Starring stored in `starred_objects` table (not on User). The GM is a User with `role = gm` — not a separate entity. GM display name is shown as "GM [name]". GM can optionally own a character via `POST /api/v1/me/character`. Players are strictly 1:1 with characters. Account lifecycle tied to invite: new character requires new invite and new account (old deactivated). When deactivated, pending proposals are orphaned in place (GM decides their fate). GM can regenerate any user's login code (including their own); new magic link URL returned in response. Any user can refresh their own magic link via `POST /api/v1/me/refresh-link`. Auth: cookie-only (httpOnly, set by visiting magic link `/login/<code>` via `POST /api/v1/auth/login`). Auth errors: 401 (missing/invalid cookie) + 403 (insufficient role), both with JSON error body containing machine-readable `code` field. All users can see the player roster (GM callers also see `login_url` per player).

### Magic Link
A permanent login URL of the form `/login/<code>` where `<code>` is the user's login code. Visiting the link triggers `POST /api/v1/auth/login` which validates the code, sets an httpOnly cookie, and returns user info. For first-time visits (unconsumed invite), the login endpoint returns `{type: "invite"}` and the frontend shows a join form. After joining, the same link works as a permanent login. Users can refresh their link (generating a new code and invalidating the old one) via `POST /api/v1/me/refresh-link`. The GM can view all player links via the player roster and regenerate any player's link.

### Invite Code
A single-use ULID generated by the GM via `POST /api/v1/game/invites`. The invite's `id` IS the shareable code — no separate `code` column. The invite is **bare** — not pre-linked to a character. GM shares `/login/<id>` with the player. On first visit, `POST /api/v1/auth/login` detects the unconsumed invite and returns `{type: "invite"}`. The player then joins via `POST /api/v1/game/join` with `{code, character_name, display_name}`. The system atomically creates a full Character (all mechanical fields defaulting to 0), a User account (login code = the invite id), and links them. Sets the auth cookie. The same magic link now works as a permanent login. Consumed on redemption — cannot be reused. No expiry. GM can delete unconsumed invites.

---

### ULID
Universally Unique Lexicographically Sortable Identifier. The primary key format used by all tables. 26-character string, sortable by creation time, URL-safe. Generated in application code (Python `python-ulid` library). Stored as TEXT in SQLite.

### Slots Table
The unified database table containing all traits and bonds across all Game Object types. Uses a `slot_type` discriminator column with 9 values: `core_trait`, `role_trait`, `pc_bond`, `npc_bond`, `group_trait`, `group_relation`, `group_holding`, `feature_trait`, `location_bond`. Mechanical columns (stress, charge, etc.) are nullable — only populated for slot types that use them. See [data-model.md](architecture/data-model.md).

---

## Abbreviations

| Abbrev | Expansion |
|--------|-----------|
| PC | Player Character |
| NPC | Non-Player Character |
| GM | Game Master |
| MVP | Minimum Viable Product |
| TBD | To Be Determined |
| BitD | Blades in the Dark (reference game system) |
| DSL | Domain-Specific Language |
| ORM | Object-Relational Mapping |
| CRUD | Create, Read, Update, Delete |
| ULID | Universally Unique Lexicographically Sortable Identifier |
| FK | Foreign Key |
| PK | Primary Key |

---

_Last updated: 2026-03-18 (Phase 6 UX spec: updated Player Direct Action to 5 types; promoted Recharge Trait and Maintain Bond from downtime proposals to direct player actions; updated Downtime Action category. Previous: 2026-03-15 bond charges reframe.)_
