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
Any entity tracked in the system. All game objects share common fields: `id`, `name`, `description`, `is_deleted`, `created_at`, `updated_at`, plus type-specific fields. Types include: Character, NPC, Group, Clock, Location, Session, Story. All game objects use soft delete (`is_deleted` flag) — deleted objects are hidden from lists but remain accessible via direct lookup, and references to them stay valid. **Exception**: Draft Sessions use hard delete (no downstream references).

### Character (PC)
A player character — the in-game identity owned and controlled by a specific player. Has a full character sheet including Stress, Free Time, Plot, Traits, Bonds, Skills, Gnosis, Magic Stats, Magic Effects, and Notes.

### NPC
Non-player character — a GM-controlled character with a simplified record: name, description, freeform `attributes` JSON blob (replacing separate traits/stats), notes, lightweight bonds to other game objects, and a `common_locations` list with optional notes per entry (not a single pinned location — see Deferred Narrative Resolution). NPC detail merges `common_locations` with Location-targeting bonds for a unified location view. No charge mechanics or structured sheet.

### Group
An organization, crew, family, guild, or other group in the game world. (Renamed from "Faction" — the broader term covers all types of organizations.) Has a power tier (any non-negative integer), project clocks, lightweight bonds to other game objects, and notes. Territories represented via Group→Location bonds (no separate locations list). "Members" derived from inbound bonds (NPCs/objects with bonds targeting the Group). Group-to-Group bonds are bidirectional with source/target labels. Group project outcomes follow Deferred Narrative Resolution — progress is tracked mechanically via clocks, but what the project actually *was* may be resolved retroactively at completion.

### Clock
A progress tracker (Blades in the Dark-style) with a configurable number of segments (any positive integer, default 5). Clocks can be standalone or embedded in a Group as project clocks — accessible via both the Group sub-resource and standalone endpoint. When all segments are filled, the clock is flagged as completed and surfaced to the GM for narrative resolution — no automatic game state changes. Clock adjustments are recorded via the Event log with annotation metadata (notes, event refs, game object refs).

### Location
A place in the game world. Locations form a nestable hierarchy with unlimited depth (a district contains streets, a street contains buildings). Locations have curated `npcs` and `groups` affiliation lists (reference + optional note, e.g., `{npc_id, note: "bartender"}`), independent of the bond system. Location detail merges curated affiliations with inbound bonds for a complete presence view. Locations are bond targets only — they do not have outbound bonds.

### Session
A record of a single play session with a strictly forward lifecycle: **Draft → Active → Ended** (no undo or reopen). Key fields: `time_now` (abstract campaign time counter, GM-set), `status`, `date`, `summary`, `notes`, and a participant list. Only one Active session at a time. Draft sessions are editable and hard-deletable (exception to soft-delete rule). Active sessions allow edits to summary/notes and late-joining participants. Ended sessions are read-only. On **Start** (Draft → Active): FT distributed via Time Now delta, Plot awarded (+1 base, +2 with Additional Contribution), contribution flags locked. On **End** (Active → Ended): status transitions (clock adjustments happen individually during Active, not in the End call). Players self-register; GM can also manage participant list. Characters store session IDs for bidirectional history lookups.

### Story (Arc)
A narrative thread tracked by the system. Stories have owners (Characters, Groups, or other game objects — managed via sub-resource API), a status (active, completed, abandoned), optional freeform tags for categorization, an embedded `entries` list for structured narrative progress (from `work_on_project` proposals or GM additions — each entry has text, optional character/session/event refs, game object links, and full audit trail: updated_at, updated_by, is_deleted, deleted_by), and can nest into sub-arcs via a parent reference. Entry editability: players edit own entries, GM edits any, soft-delete for removals. Player projects use Stories as the tracking object; Group project outcomes may also resolve into Stories.

### Stress
A meter on a Character representing accumulated harm and pressure. Range 0–9 (effective max decreases by 1 per Trauma; computed as `9 - count(trauma bonds)`). When Stress hits max, the character gains a Trauma and Stress resets to 0. Healed via the "Rest" downtime action (3 base + up to +3 from modifiers, costs 1 Free Time).

### Trauma
The consequence of maxing character Stress. The existing Bond in the chosen slot retires to Past (`is_active = false`, history preserved). A new Bond instance is created with `is_trauma = true`, trauma-specific name/description, no target, and fresh stress values. Each Trauma reduces the character's effective Stress max by 1. Fixable via GM direct action (GM chooses outcome — blank slot, new bond, etc.). If all Bonds are already Trauma, the GM handles narratively.

### Free Time
A resource meter (0–20) on a Character, spent on downtime activities (1 FT per action). Gained automatically at Session Start via Time Now delta: `session.time_now - character.last_session_time_now`. Also gained via Find Time (3 Plot → 1 FT). Carries over between sessions. Capped at 20 (excess lost).

### Plot
A resource meter (0–5) on a Character. Gained at Session Start: +1 per session participated, +2 if "Additional Contribution" checked (meta-game reward). GM can also award bonus Plot. Spent on proposals: each Plot places a **guaranteed success** (a 6) before rolling — not an extra die, but a guaranteed result. Can also be used flexibly (surviving impossible odds, narrative tweaks) at GM discretion. No cap on Plot spend per proposal. Declared on submission. Can be converted to FT via Find Time (3 Plot → 1 FT).

### Gnosis
A resource meter (0–23) on a Character. The primary magical resource, spent as sacrifice in Magic Actions and Charge Actions. Converted to additional dice via a tiered table (diminishing returns: N dice costs N×(N+1)/2 Gnosis). Regained via downtime activity.

### Meter
A bounded numeric value with a defined range. Used for Stress, trait charges, clock progress, and other trackable quantities.

### Resource Meter
A meter that functions as a spendable/gainable currency — can be consumed by actions and replenished through gameplay. Free Time, Plot, and Gnosis are resource meters.

### Trait Template
A GM-created catalog entry defining a Core or Role Trait. Has a name, description, and type (`core` or `role`). Type is fixed — Core templates fill Core slots, Role templates fill Role slots. Exists independently of any character — multiple characters can share the same Trait Template. Editing a template propagates to all characters referencing it. A character can only have one active instance of a given template. Players can propose new templates via the "New Trait" downtime action (added to catalog on GM approval). Bonds do not use Trait Templates; they reference game objects instead.

### Trait Instance
A per-character record linking to either a Trait Template (for Core/Role Traits) or a game object (for Bonds). Holds character-specific state: charges (Core/Role) or stress (Bonds), `is_active` flag, and an event history stream. The unified model shared by Core Traits, Role Traits, and Bonds.

### Past/Retired
The state of a Trait Instance, Bond, or Magic Effect that has been replaced, sacrificed, or retired (via downtime action, Trauma, sacrifice, or GM action). Marked `is_active = false`. Remains on the character sheet in a "Past" section with full event history preserved and viewable, but cannot be used mechanically.

### Core Trait
One of a Character's two defining-quality Trait Instance slots. Links to a Trait Template from the GM-created catalog. Has a charge meter (0–5). When invoked on a proposal, costs 1 charge and grants +1d to the dice pool. Can be referenced narratively without charge cost. New traits start at full charge (5). Slots may be blank. Traits are added by GM direct action and can be replaced via the "New Trait" downtime action. Replaced traits move to Past.

### Role Trait
One of a Character's three learned-ability Trait Instance slots. Same structure and mechanics as Core Traits (links to Trait Template, charge 0–5, +1d bonus, 1 charge per invocation).

### Charge
A meter (0–5) on a Trait that is spent (1 per invocation) to activate its +1d bonus. Replenished via the "Recharge Trait" downtime action (full restore on one trait, costs 1 Free Time).

### Modifier Stacking
The rule governing how many modifiers a player can select on a single proposal: at most 1 Core Trait (+1d), 1 Role Trait (+1d), and 1 Bond (+1d), for a maximum of +3d on top of the base skill dice pool.

### Bond
A type of Trait Instance representing a meaningful relationship between a Character and a game object (PC, NPC, Group, Location, etc.). Inherits name/description from the target game object. Provides a flat +1d bonus when selected on a proposal. Has its own stress meter (0 to effective max) and degradation mechanic mirroring character Stress/Trauma. No bond level — bond depth is captured by its accumulated fiction stream. 7 Bond slots per character.

### Bond Stress
A stress meter on a Bond (base max 5). Accumulates from GM narrative actions or +1 when GM decides a proposal bond use strains it. At max: GM resets to 0, effective max decreases by 1 (degradation), GM narrates consequence. Healed fully via "Maintain Bond" downtime activity. GM can reverse degradation via direct action.

### Bond Degradation
A count on a Bond tracking how many times its stress has maxed out. Effective bond stress max = `5 - degradation_count`. At 5 degradations (effective max 0), GM handles narratively.

### Skill
One of exactly 8 canonical abilities hardcoded in code: Awareness, Composure, Influence, Finesse, Speed, Power, Knowledge, Technology. The same list for all characters. Each Skill has a level (0–3) that equals the base dice pool size for related actions. All characters have all 8 skills at different levels. Skill levels increase via "Work on Project" downtime action — player targets a Story/Arc for the skill being trained. GM resolves (and applies level change via direct action) when the narrative warrants it.

### Magic Stat
One of five hardcoded schools of magic: Being, Wyrding, Summoning, Enchanting, Dreaming. Level (0–5) IS the base dice pool for magic actions using that stat. XP meter (flat 5 XP per level, GM awards directly) tracks progress toward next level. All Magic Stats start at level 0 for new characters.

### Magic Action
A proposal action type for performing freeform magic. Player provides Intention (text), Symbolism (text), and Sacrifice (a list of entries — can combine Gnosis, Stress, Free Time, Bond/Trait sacrifice, and Other freely in one action). Player suggests a Magic Stat; GM has final say. Dice pool = Magic Stat level + sacrifice dice (tiered) + use modifiers (up to +3d). GM reviews and creates exactly one Magic Effect on the character's sheet as the outcome. GM interprets the roll to set effect name, description, power_level (1–5), and initial charges.

### Charge Action
A variant of Magic Action used to recharge a charged Magic Effect or boost a permanent item. Same workflow (intention, symbolism, sacrifice) but targets an existing effect. On charged effects: restores charges and can increase max charges beyond original (power_level fixed at creation). On permanent effects: increases power_level (within 1–5 scale). GM interprets roll to determine outcome.

### Magic Effect
The outcome of a Magic Action, created by the GM on a character's sheet. Three types: **instant** (one-time, not tracked), **charged** (persistent, power_level 1–5, charges_current/charges_max unbounded, each use costs 1 charge, player-initiated direct use without proposal with optional narrative), and **permanent** (always-active, no charges, power_level 1–5, primarily from Enchanting). Max 9 active effects per character (charged + permanent; instants don't count). Players can self-retire effects (no approval needed). Charged effects are recharged via Charge Action.

### Sacrifice (Magic)
Resources spent to power a Magic Action or Charge Action, stored as a **list of entries** (can combine freely). Converted to Gnosis equivalent: Gnosis (1:1), Stress (1 = 2 Gnosis, standard Stress rules apply — can trigger Trauma), Free Time (1 = 3 + lowest Magic Stat), Bond/Trait sacrifice (10 Gnosis, goes to Past), Other (freeform text, GM assigns Gnosis value during review). Distinct from *Using* a trait/bond (+1d modifier). Hidden GM "style" bonus added separately.

### Style Bonus
A hidden GM-only Gnosis modifier added during Magic Action review. Rewards creative narrative, good symbolism. Not visible to the player.

### Proposal
A player-submitted request to change game state. Two categories: **Actions** (session play: `use_skill`, `use_magic`, `charge_magic`) and **Downtime Actions** (between sessions: `regain_gnosis`, `recharge_trait`, `maintain_bond`, `work_on_project`, `rest`, `new_trait`, `new_bond`). All downtime actions auto-cost 1 Free Time. Workflow: submit (validated) → system calculates → GM reviews + rolls at table → approve (narrative + overrides, system auto-applies all consequences) or reject (note, player revises in place). GM can override any calculated value and force-approve even if resources are insufficient. One event generated per approval.

### Downtime
Not a distinct system mode. Downtime mechanics are embedded in the session lifecycle: FT is distributed at Session Start (via Time Now delta), group clocks are adjusted at Session End, and players can submit Downtime Action proposals whenever they have Free Time. All downtime actions cost 1 FT.

### Time Now
An abstract integer counter set by the GM on each Session. Represents the passage of campaign time. The difference between a character's `last_session_time_now` and the current Session's Time Now determines Free Time gained. GM controls pacing — a larger gap means more FT.

### Additional Contribution
A per-participant boolean flag on session registration. Represents a meta-game contribution (wrote session recap, brought snacks, helped organize, etc.). Awards +1 bonus Plot at Session Start (+2 total instead of +1). No in-fiction requirement.

### Find Time (Direct Player Action)
A direct player action (no proposal needed) that converts **3 Plot → 1 Free Time**. Can be done at any time. Prevents Plot waste at the 5 cap. Event logged. FT gained respects the 20 cap.

### Deferred Narrative Resolution
A core design principle: game state is intentionally left ambiguous until narratively observed. The system supports potential/fuzzy state alongside concrete state. Examples: NPCs have common locations (not a pinned position) — their actual location is resolved at the table when someone looks for them. Group projects have mechanical progress (clock segments) but their outcomes are defined retroactively when the clock completes. This mirrors how GMs actually run games — not everything is decided upfront.

### Lightweight Bond
A simplified Bond-shaped relationship on NPCs and Groups (not Locations — Locations are bond targets only). Fields: id, source (type + id), target (any game object), source_label, target_label (for bidirectional bonds), description, `is_active`, bidirectional flag. No stress meter, no degradation, no charge mechanics, no +1d modifier, no cap on number. Directionality depends on types involved: Group↔Group and NPC↔NPC are bidirectional; NPC→Group = membership; Group→NPC = special relationship; NPC/Group→Location = directional. Managed via sub-resource API with individual IDs. Distinct from PC Bonds (which are full Trait Instances with mechanical depth).

### Soft Delete
The deletion model for most game objects. Setting `is_deleted = true` hides the object from list endpoints but preserves it for direct lookup. References to deleted objects remain valid (e.g., a Bond targeting a deleted NPC still resolves). Per-type lifecycle fields (e.g., Story status) are independent of the deletion flag. **Exception**: Draft Sessions use hard delete (no downstream references exist).

### Clock Adjustment Annotation
Metadata attached to a clock adjustment event. Includes freeform notes and optional links to events or game objects, explaining why the clock was advanced, delayed, or skipped. Stored on the Event record (not denormalized on the Clock object). Created during Active sessions when the GM adjusts group clocks.

### Event (Event Log Entry)
An immutable record of a state change. Fields: `id`, `type` (convention-based `{domain}.{action}` string), `actor` (typed ref: player/gm/system), `targets` (list of game object refs), `changes` (keyed before/after pairs), `created`/`deleted` (object lifecycle lists), `narrative` (optional, from GM/player/system), `proposal_id` (optional back-ref), `session_id` (auto-captured from Active session), `visibility` (bond-distance level), `metadata` (freeform JSON for annotations/links), `timestamp`. Events are append-only — never modified or deleted (except `visibility`, which the GM can override). One event per state-changing action, even compound changes.

### Event Log
The append-only collection of all Event records. Provides history and audit trail. State (not the event log) is the source of truth. Retained indefinitely — no cleanup or archival.

### Bond-Distance Visibility
The event visibility model: events are visible to players based on their character's proximity in the bond graph. Six levels: **global** (all see), **gm_only** (GM only), **private** (actor + target owners), **bonded** (1-hop: direct bond to any target, the default), **familiar** (2-hop: bond-of-bond), **public** (3-hop). Both PC Bonds and lightweight bonds form the graph. Cached per character, invalidated on bond changes. GM can override any event's visibility.

### New Trait (Downtime Action)
A downtime activity where a player replaces an existing Core/Role Trait or fills a blank trait slot. Player selects the target slot, suggests a name/description, and writes narrative fiction. Submitted as a proposal for GM approval. New traits start at full charge (5). Old trait moves to Past.

### New Bond (Downtime Action)
A downtime activity where a player replaces an existing Bond or fills a blank bond slot. Player selects the target slot, the game object target, and writes narrative fiction. Submitted as a proposal for GM approval. Old bond moves to Past.

### Maintain Bond (Downtime Action)
A downtime action (renamed from "Heal Bond Stress") that fully restores a Bond's current stress to 0. Costs 1 Free Time. Does not reverse degradations. Player selects which bond to maintain.

### Regain Gnosis (Downtime Action)
A downtime action that restores Gnosis to a character. Costs 1 Free Time. Formula: **3 Gnosis base + lowest Magic Stat level + up to +3 from trait/bond invocation** (standard stacking: 1 Core +1, 1 Role +1, 1 Bond +1). Submitted as a proposal. Trait charges spent as usual; bond may strain per GM decision.

### Recharge Trait (Downtime Action)
A downtime action that fully restores a Core or Role Trait's charges to 5. Costs 1 Free Time. Player selects which trait to recharge. No modifiers — fixed outcome.

### Rest (Downtime Action)
A downtime action that heals character Stress. Costs 1 Free Time. Formula: **3 Stress healed base + up to +3 from trait/bond invocation** (standard stacking: 1 Core +1, 1 Role +1, 1 Bond +1). Heals 3–6 Stress per rest.

### Work on Project (Downtime Action)
A downtime action that progresses a personal project (Story/Arc). Costs 1 Free Time. Adds a narrative entry to the target Story. No mechanical calculation — the GM resolves the project when the fiction warrants it. Skill training uses this action, targeting a Story for the skill being trained.

### Action (Proposal Category)
A proposal submitted during session play. Three types: `use_skill`, `use_magic`, `charge_magic`. No automatic Free Time cost. Uses dice pool calculations with base + modifiers + Plot.

### Downtime Action (Proposal Category)
A proposal submitted during the downtime phase. Seven types: `regain_gnosis`, `recharge_trait`, `maintain_bond`, `work_on_project`, `rest`, `new_trait`, `new_bond`. All automatically cost 1 Free Time, deducted on approval.

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

---

_Last updated: 2026-03-02 (Game Objects second interrogation — Faction→Group rename, bond directionality model, location affiliations, story entry editability)_
