# Bonds — Domain Specification

**Status**: 🟢 Complete
**Last interrogated**: 2026-03-07
**Last verified**: 2026-03-16
**Depends on**: [game-objects](game-objects.md), [character-core](character-core.md)
**Depended on by**: [actions](actions.md), [downtime](downtime.md), [events](events.md)

---

## Overview

**Bonds are the connections between Game Objects.** Every relationship in the system — between Characters, Groups, and Locations — is represented as a Bond. Bonds are a unified concept with a single data model and varying mechanical depth depending on context.

All bonds share the same base fields. PC Bonds (on full Characters) add charges, degradation, and dice bonuses. All other bonds are descriptive — they track relationships without mechanical depth.

The bond graph drives two computed systems (same traversal algorithm, different uses):
- **Unified Visibility** — who can see which events and story entries (see [feed.md](feed.md))
- **Bond-Distance Presence** — who is present at which locations (defined below)

Both systems use the **Character-intermediary traversal rule**: after a non-Character node (Group or Location), the next hop must go through a Character (PC or NPC). You can't traverse through two Groups or two Locations consecutively. PCs are valid intermediaries — and richer than NPCs since they can connect to other Characters. Soft-deleted Game Objects, inactive bonds, and Trauma bonds (no target) are excluded from traversal (dead ends).

---

## Unified Bond Model

### Shared Bond Fields

All bonds, regardless of type, have:

```
{
  id: string,                // unique identifier
  source_type: string,       // type of owning Game Object (character/group/location)
  source_id: string,         // ID of owning Game Object
  target_type: string,       // type of referenced Game Object
  target_id: string,         // ID of referenced Game Object
  source_label: string,      // relationship label from source's perspective
  target_label: string,      // relationship label from target's perspective (bidirectional)
  description: string,       // freeform context
  is_active: boolean,        // supports Past/Retired pattern
  bidirectional: boolean     // whether both sides see this bond
}
```

### PC Bond Additional Fields

Full (PC) Characters' bonds additionally have:
- `charges`: integer (0 to effective max) — current bond charges. Conceptually the same as trait charges — a measure of how much the bond can be drawn upon before it strains. Physical DB column: `stress`.
- `degradation_count`: integer — count of times charges have hit 0 (effective max charges = `5 - degradation_count`). Physical DB column: `stress_degradations`.
- `is_trauma`: boolean — true if this slot holds a Trauma instead of a relationship

These fields are null/absent on all non-PC bonds.

> **Design note**: Bonds and traits share the "charges" concept. Both start at 5 and deplete through use. The key difference: traits at 0 charges simply can't be invoked for the +1d bonus. Bonds at 0 charges trigger **degradation** — the effective max drops by 1, and the GM narrates a consequence. This makes bond depletion more dramatic than trait depletion.

---

## Bond Categories

### By Owner Type

| Category | Owner | Target | Slots | Direction | Mechanics |
|----------|-------|--------|-------|-----------|-----------|
| **PC Bond** | Full Character | Any Game Object | 8 | Varies (see below) | Charges, degradation, +1d, Trauma |
| **NPC Bond** | Simplified Character | Any Game Object | 7 | Varies (see below) | Descriptive only |
| **Group Relation** | Group | Group | 7 | Bidirectional | Descriptive only |
| **Group Holding** | Group | Location | Unlimited | Directional | Descriptive only |
| **Location Bond** | Location | Any Game Object | Unlimited | Directional | Descriptive only |

### Directionality Rules

Default bidirectionality is auto-inferred from the pairing type. The GM can override on creation.

| Pairing | Default Direction | Notes |
|---------|-------------------|-------|
| Character ↔ Character | Bidirectional | One record, both see. `source_label`/`target_label` for each perspective. Includes PC↔PC bonds. |
| Character ↔ Group | Bidirectional | Character bond = membership in the Group (see Derived Membership). |
| Group ↔ Group (Relations) | Bidirectional | One record, both groups see with their respective labels. |
| Character → Location | Directional | Character connected to a place. Source owns the bond. |
| Group → Location (Holdings) | Directional | Group presence/control at a place. Group owns the bond. |
| Location → Location | Directional | Geographic connection (path, overlooks, adjacent). |
| Location → Character/Group | Directional | Notable association. Location owns the bond. |

**Default rule**: Character↔Character, Character↔Group, and Group↔Group = bidirectional. All Location-involved bonds = directional. GM can override at creation.

### Inbound Bond Display

Bidirectional bonds appear in **both** the source's and target's bond lists with **no distinction**. The API normalizes the perspective — the viewing entity sees their label. The client doesn't need to track owned vs inbound.

### Bond Slot Limits

| Owner | Limit | Enforcement | Notes |
|-------|-------|-------------|-------|
| Full Character (PC) | 8 | Count-based | Max 8 active bonds. No fixed slot indices. Trauma consumes against the count. Blank slots allowed. The 8th slot accounts for the expected party Group bond. |
| Simplified Character (NPC) | 7 | Count-based | Max 7 active bonds. Same count-based model as PCs. |
| Group Relations | 7 | Count-based | Group↔Group only. |
| Group Holdings | Unlimited | — | Group→Location only. |
| Location Bonds | Unlimited | — | To any Game Object. |

### Slot Accounting for Bidirectional Bonds

When a bidirectional bond is created (e.g., PC-A bonds to NPC-B), the **source always consumes a slot**. The target receives a **soft-limit warning** if they are at capacity, but the GM can exceed the target's slot limit. Only one database record is created; the source owns it.

- **Source**: Always consumes a slot (hard enforcement).
- **Target**: Soft limit — system warns GM if target is full, but allows creation.
- This means an NPC can appear to "have" more than 7 bonds if multiple characters bond to them.

### Duplicate Bond Prevention

At most **one active bond** per (source, target) pair. The system prevents creation of a second bond to the same target. To change the relationship, use "New Bond" to replace it or the GM edits the existing bond.

### Slot Type Auto-Inference

When the GM creates a bond, the system auto-infers `slot_type` from context:

| Owner | Target | Inferred slot_type |
|-------|--------|--------------------|
| Full Character | Any | `pc_bond` |
| Simplified Character | Any | `npc_bond` |
| Group | Group | `group_relation` |
| Group | Location | `group_holding` |
| Location | Any | `location_bond` |

No GM input required — the system determines the type from the owner's type/detail_level and the target type.

---

## Derived Membership

**Group membership is derived from the bond graph, not stored as a separate type.**

When a Character (PC or NPC) has a bond targeting a Group, that Character is a **member** of the Group. The Group's `members` list is computed by querying: "all bonds where target = this Group and source_type = character."

- A PC's bond to a Group uses one of their 8 Bond slots (with full charges mechanics)
- An NPC's bond to a Group uses one of their 7 Bond slots (descriptive only)
- The Group does not store a separate membership record
- The Group detail endpoint computes and returns the member list

**Design intent**: One bond, dual purpose — the Character's bond IS their membership. This keeps the model simple and the bond graph connected. A powerful individual operating at Group scale gets their own single-member Group to participate in Group Relations.

---

## PC Bond Mechanics (Full Characters Only)

### Bond Charges

Bond charges are the bond equivalent of trait charges — a measure of how much the relationship can be drawn upon before it strains:

- **Range**: 0 to effective max (base 5, decreases with degradations)
- **Loses charges from**: GM narrative actions, or −1 when GM decides a proposal bond use strains it (via `bond_strained` flag on approval)
- **At 0 charges**: GM resets charges to the new effective max (`5 - new_degradation_count`), increments degradation count by 1 (effective max decreases), narrates consequence. Both mutations happen in a single compound operation. Recorded as `meter.set` (charge reset) + `meter.delta` (degradation increment) in the event. See [events.md](events.md) Meter Boundary Patterns.
- **Restoration**: "Maintain Bond" downtime activity fully restores current charges to effective max (`5 - degradation_count`). Costs 1 FT. Does not reverse degradations.
- **Degradation reversal**: GM can reverse a degradation via direct action (decrement degradation count). Does **not** automatically adjust the current charge value — a follow-up "Maintain Bond" or direct charge set is needed to restore charges after reversal.
- **At 0 effective max** (5 degradations): GM handles narratively — no additional mechanical rule

> **Physical DB columns**: Bond charges map to the `stress` column and degradations to `stress_degradations` in the `slots` table. The column names reflect the original "bond stress" terminology; the conceptual reframe to "charges" aligns bonds with traits without requiring a schema change.

### +1d Bonus on Proposals

When a Bond is selected on a proposal, it provides a flat **+1d** to the dice pool. Unlike traits, using a bond does not automatically cost a charge — the GM decides whether the use strains the relationship (via `bond_strained` flag), which costs 1 charge.

Per the Modifier Stacking rule (see [traits.md](traits.md)), a proposal can include at most 1 Core Trait + 1 Role Trait + 1 Bond = max +3d.

If the GM decides the bond use strains the relationship, −1 bond charge is applied.

### Trauma

When a character's Stress hits max, they gain a Trauma which occupies a Bond slot:

1. The existing Bond in the chosen slot is **retired** (`is_active = false`) and moves to the "Past" section. Full event history preserved.
2. A new Bond instance is created in the slot with `is_trauma = true`, trauma-specific name/description (negotiated between GM and player), no target reference, and fresh charge/degradation values (charges = 5, degradations = 0).
3. Character Stress resets to 0.
4. Character effective Stress max decreases by 1 (computed: `9 - count(active trauma bonds)`).

**Fixing Trauma**: GM direct action. The GM chooses what happens — can blank the slot, create a new bond, etc. No automatic restoration of the original bond. The trauma instance retires to Past, slot becomes blank (or GM fills it immediately).

### Past/Retired Bonds

When a Bond is replaced (by Trauma, "New Bond" downtime action, or GM action), the old Bond instance is marked `is_active = false`. It remains on the character sheet in a "Past" section:
- Full event history preserved and viewable
- Cannot be selected for proposals (+1d bonus)
- Serves as a narrative record of the character's relationship history

### Bond Lifecycle (PC Bonds)

1. **Created**: GM adds a bond via direct action, pointing to a Game Object target. Starts with charges = 5 (full), degradations = 0.
2. **Active**: Available for use in proposals. Charges deplete from narrative events and GM-decided strain on proposal use.
3. **Depleted**: Bond charges at 0 triggers degradation. Charges reset to (new) effective max, max decreases.
4. **Replaced**: Player submits "New Bond" downtime action or bond becomes Trauma. Old bond retires to Past.
5. **Retired/Past**: `is_active = false`. Viewable history, no mechanical use.
6. **Trauma**: `is_trauma = true`. Occupies a slot, reduces character Stress max, fixable via GM action.

---

## Bond-Distance Presence

Presence at a Location is **computed from the bond graph**, using hop-distance traversal. This replaces the old curated affiliation lists and `common_locations`.

### How It Works

For a Location, the system traverses the bond graph outward using the **Character-intermediary traversal rule** (same algorithm as visibility — see [feed.md](feed.md)):

| Proximity | Hops | Label | Example |
|-----------|------|-------|---------|
| Commonly present | 1-hop | Direct bond | Character bonded to the Location |
| Often present | 2-hop | Through Character | Character bonded to an NPC/PC who is bonded to the Location |
| Sometimes present | 3-hop | 3 degrees | Character → Character → Group/Location → another Character bonded to the Location |

**Character-intermediary constraint**: After a non-Character node (Group or Location), the next hop must go through a Character (PC or NPC). You can't traverse through two Groups or two Locations consecutively. The first hop from any starting node can go to any type. Characters (both PCs and NPCs) are the social connective tissue.

### Bidirectional

The same model works in reverse — for a Character, the system computes:
- **Common locations** (1-hop): Locations the Character is directly bonded to
- **Familiar locations** (2-hop): Locations reachable through one Character intermediary
- **Known locations** (3-hop): Locations reachable through two intermediaries (Character-alternating)

### Traversal Constraints

- **Only active bonds participate** (`is_active = true`). Past/Retired bonds are excluded from traversal.
- **Trauma bonds are dead ends**: Explicitly excluded from traversal — they have no target and don't connect to the graph.
- **Soft-deleted Game Objects are excluded** from traversal. Their bonds exist but are dead ends.
- **All active bond types participate**: PC bonds (mechanical), NPC bonds (descriptive), Group bonds (Relations, Holdings), Location bonds. The traversal doesn't care about mechanical depth.
- **Computed on read** (no caching). SQLite handles it for 4–6 players.

### What It Replaced

1. ~~Location curated `npcs`/`groups` affiliation lists~~ → Bond-distance presence
2. ~~NPC `common_locations` list~~ → Character bond-distance to Locations
3. Manual "who's here" tracking → Automatic from bond graph

### Shared Algorithm with Visibility

The bond graph does double duty — **one traversal algorithm, two applications**:
- **Unified Visibility**: Who can see which events and story entries (see [feed.md](feed.md))
- **Bond-Distance Presence**: Who is present at which locations

Both use the same Character-intermediary hop-distance model. Both computed on read.

---

## Unified Table Architecture

All traits and bonds live in a single unified table with a `slot_type` discriminator. This includes:
- **Traits**: Core Traits, Role Traits, Group Traits (10 flat slots), Location Feature Traits (5 slots)
- **Bonds**: PC Bonds, NPC Bonds, Group Relations, Group Holdings, Location Bonds

The complete slot_type catalog and column details are specified in [data-model.md](../architecture/data-model.md). Domain specs (this document and [traits.md](traits.md)) describe the logical model.

**Why unified**: All slot types share common patterns — they have an owner, a name/description, an active/retired status, and varying mechanical fields. A single table with nullable mechanical columns is simpler than multiple tables with identical base structures.

---

## Decisions

### Unified Bond Concept

- **Decision**: All relationships between Game Objects are Bonds. One concept, varying mechanical depth. PC Bonds have charges/degradation/+1d. All others are descriptive (active/retired only).
- **Rationale**: Keeps the mental model simple — "Bonds connect things." UI renders all bond types consistently. The bond graph works as one connected structure.
- **Implications**: Single bond model with optional mechanical fields. Bond type/context determines which fields are relevant.

### Fully Unified Table (Traits + Bonds)

- **Decision**: All traits and bonds live in one table with a `slot_type` discriminator. Covers Core/Role Traits, all bond types, Group traits, and Location Feature traits.
- **Rationale**: All slot types share common patterns (owner, name, description, active/retired). One table is simpler than many tables with identical bases. Nullable columns for type-specific fields.
- **Implications**: data-model.md owns the complete slot_type catalog. Queries use slot_type filtering. Performance is fine for 4–6 players.

### bonds.md Is the Authoritative Bond Spec

- **Decision**: This document is the single source of truth for the entire Bond concept — all bond types, directionality, bond-distance presence, and PC-specific mechanics.
- **Rationale**: Bonds are a cross-cutting concept. Having one authoritative reference prevents fragmentation across specs.
- **Implications**: game-objects.md and character-core.md reference this spec for bond details.

### PC Bond to Group = Membership

- **Decision**: A Character's bond targeting a Group IS their membership in that Group. One bond, dual purpose — uses a bond slot (with full mechanics for PCs) AND registers as a Group member.
- **Rationale**: Keeps the bond graph connected. No redundant records. Membership is a natural interpretation of the bond relationship.
- **Implications**: Group `members` list is a derived query, not stored. "Any Character with a bond targeting this Group" = member. Works for both PCs (mechanical bonds) and NPCs (descriptive bonds).

### Derived Membership (Not a Stored Type)

- **Decision**: Group membership is computed from the bond graph: all Characters with a bond targeting the Group. No separate `group_member` bond type or record.
- **Rationale**: One bond per relationship, no duplication. The Character owns the bond; the Group sees it as membership. Clean and simple.
- **Implications**: Group detail endpoint computes the member list via query. Membership changes = bond changes.

### NPC Membership Same as PC

- **Decision**: When an NPC bonds to a Group, that bond IS their membership, same as PCs. Consistent rule across all Characters.
- **Rationale**: NPCs are Characters. Same entity, same bond model, same membership semantics.
- **Implications**: NPC bonds use the same table as PC bonds. Group membership query doesn't care about detail_level.

### Group Holdings (Group→Location Bonds)

- **Decision**: Groups have a third bond category called "Holdings" for bonds to Locations. Unlimited slots, directional, descriptive. Covers territories, properties, meeting places, sacred sites.
- **Rationale**: Groups need direct connections to Locations that aren't mediated through Members. "Holdings" is evocative and covers the dominant use cases.
- **Implications**: Group detail endpoint shows Holdings alongside Relations and computed Members. `slot_type` in the unified table.

### No Bond Level

- **Decision**: Bond level is removed from the model. Bonds provide a flat +1d on proposals regardless of any "strength" metric.
- **Rationale**: The meaningful depth of a bond is captured by its accumulated fiction — the stream of narrative paragraphs from actions involving the bond.
- **Implications**: Simplifies the model. Bond "strength" is emergent from play.

### Bond Charge Range and Degradation

- **Decision**: Bond charges range from 0 to effective max (base 5, minus degradation count). At 0 charges: charges reset to full, degradation count increments, GM narrates consequence. At 0 effective max (5 degradations): GM handles narratively.
- **Rationale**: Mirrors the trait charge pattern — bonds and traits share the "charges" concept. Bonds add a degradation penalty at 0 that traits lack, making bond depletion more consequential.
- **Implications**: Bond model uses `stress` and `stress_degradations` columns (PC bonds only). Conceptually "charges" and "degradation count."

### Bond Charge Sources

- **Decision**: Bond charges are lost from GM narrative actions and optionally −1 when GM decides a proposal bond use strains it (via `bond_strained` flag).
- **Rationale**: GM retains control over when bonds are strained. Risk/reward tradeoff.
- **Implications**: Proposal approval includes a `bond_strained` flag.

### Bond Charge Restoration

- **Decision**: "Maintain Bond" downtime activity fully restores current bond charges to effective max. Costs 1 FT. Does not reverse degradations.
- **Rationale**: Full restore keeps the downtime action simple and impactful. Mirrors "Recharge Trait" for traits.
- **Implications**: GM can separately reverse degradation via direct action.

### Blank Bond Slots

- **Decision**: Bond slots can be blank. Characters don't need all 8 (PC) or 7 (NPC) bonds at creation.
- **Rationale**: Allows bonds to form organically during play.
- **Implications**: Bond setup is via GM direct action post-creation. Players fill bonds via "New Bond" downtime action.

### Bond CRUD Pattern

- **Decision**: GM creates bonds via direct action. Players replace/fill bonds via "New Bond" downtime action (proposal workflow).
- **Rationale**: All player-initiated changes go through proposals.
- **Implications**: No dedicated bond CRUD endpoints for players.

### Polymorphic Targets

- **Decision**: Bond targets can reference any Game Object type (Character, Group, Location).
- **Rationale**: Relationships aren't limited to other characters.
- **Implications**: Polymorphic reference via target_type + target_id. Bond inherits name/description from target.

### Bond Slot Counts

- **Decision**: PCs have **8 bond slots** (mechanical). NPCs have **7 bond slots** (descriptive). The 8th PC slot accounts for the expected party Group bond.
- **Rationale**: PCs need one more slot than NPCs because one slot is typically used for the party Group membership bond. NPCs don't need this expectation.
- **Implications**: Trauma can consume at most 8 slots (PCs only). Character Stress max can decrease by at most 8 (from 9 to 1). See [character-core.md](character-core.md).

### Character-Intermediary Traversal (renamed from NPC-Intermediary)

- **Decision**: Both visibility and presence traversals use the same Character-intermediary rule: after a non-Character node (Group or Location), the next hop must go through a Character (PC or NPC). The first hop from any starting node can go to any type. PCs are valid intermediaries — richer than NPCs since PCs can connect to other Characters.
- **Rationale**: Models real-world information and social flow. Characters (PCs and NPCs) are the social connective tissue. One algorithm for both uses simplifies implementation.
- **Implications**: Traversal algorithm must track node types during hop expansion. See [feed.md](feed.md) for the authoritative visibility rules. Rename across all specs from "NPC-intermediary" to "Character-intermediary."

### Soft-Deleted Excluded from Traversal

- **Decision**: Soft-deleted Game Objects (`is_deleted = true`) are excluded from bond-graph traversal. Their bonds exist in the database but are dead ends during hop expansion.
- **Rationale**: Deleted entities shouldn't influence who can see what or where someone appears to be present.
- **Implications**: Traversal queries must filter `is_deleted = false` on intermediate nodes.

### Bidirectional Bond Labels

- **Decision**: Bidirectional bonds carry `source_label` and `target_label`, allowing each side its own perspective.
- **Rationale**: Real relationships are often perceived differently by each party.
- **Implications**: API returns the appropriate label based on viewing perspective.

### Count-Based Slots (Not Indexed)

- **Decision**: Bond slots are count-based, not indexed. The system enforces a maximum number of active bonds per owner type but assigns no fixed ordinal positions. Bonds are referenced by ID.
- **Rationale**: Indexed slots add complexity with no gameplay benefit. Count-based is simpler and lets bonds be referenced by their unique ID.
- **Implications**: Proposals reference bonds by `bond_id`, not `slot_index`. Display ordering is by creation time. The proposals spec needs updating — `slot_index` references should become `bond_id` or `retire_bond_id`.

### Source-Owned Slot Accounting with Soft Target Limit

- **Decision**: The source always consumes a slot (hard enforcement). Bidirectional bonds count against the target's slot limit as a soft warning — the GM can exceed it.
- **Rationale**: One record, one hard constraint. Targets (especially NPCs) may be bonded to by many characters; a hard limit would be overly restrictive and require the GM to manage NPC slot counts.
- **Implications**: NPCs can appear to have more bonds than their slot limit via inbound bidirectional bonds. The slot limit is a guide for the GM, not a hard cap on visibility.

### Bidirectionality Default Rules

- **Decision**: Character↔Character, Character↔Group, and Group↔Group bonds default to bidirectional. All Location-involved bonds default to directional. GM can override at creation.
- **Rationale**: People and organizations have mutual relationships. Location associations are naturally one-way (a character is connected to a place, not vice versa — Locations have their own unlimited outbound bonds).
- **Implications**: Auto-inferred from pairing type. `bidirectional` field is optional on creation.

### No Duplicate Active Bonds

- **Decision**: At most one active bond per (source, target) pair. System prevents creation of a second active bond to the same target.
- **Rationale**: One bond per relationship. Different facets are captured in the bond's labels and description, not separate bonds.
- **Implications**: Validation on bond creation. "New Bond" replaces the relationship if you want to change the target.

### Slot Type Auto-Inferred

- **Decision**: When creating a bond, the system auto-determines `slot_type` from the owner's type/detail_level and the target type. No GM input needed.
- **Rationale**: The mapping is deterministic — there's no case where the GM would need to choose a different slot type.
- **Implications**: Bond creation API doesn't expose `slot_type` as a field.

### Inbound Bonds Merged in API

- **Decision**: Bidirectional bonds appear in both the source's and target's bond lists with no owned/inbound distinction. The API normalizes perspective — the viewing entity sees their label.
- **Rationale**: Simplest client experience. The bond is the same relationship from both sides.
- **Implications**: Bond list endpoints return owned + inbound bidirectional bonds in one list. `source_label`/`target_label` are swapped based on viewer.

### Active-Only Traversal

- **Decision**: Only active bonds (`is_active = true`) participate in bond-graph traversal. Past/Retired bonds are excluded.
- **Rationale**: Retired relationships shouldn't influence current visibility or presence.
- **Implications**: Traversal queries must filter `is_active = true`.

### Trauma Bonds Excluded from Traversal

- **Decision**: Trauma bonds are explicitly excluded from bond-graph traversal — they are dead ends. They have no target and don't connect to the graph.
- **Rationale**: Trauma represents a broken connection. It occupies a slot mechanically but shouldn't influence the social graph.
- **Implications**: Traversal algorithm skips bonds where `is_trauma = true` (or equivalently, where `target_id` is null).

### New Bond Proposal UX

- **Decision**: Player specifies the target Game Object for "New Bond" downtime action. If at max active bond count, they must also specify `retire_bond_id` (which bond to retire). If under max, `retire_bond_id` is optional (fills a blank slot).
- **Rationale**: Player-centric UX — "I want a bond to X" is the primary intent. Retirement is only required when at capacity.
- **Implications**: Proposals spec needs `target_type`, `target_id`, and optional `retire_bond_id` in selections for `new_bond` action type.

---

## API Endpoints

### Bond Management (GM Actions)

All bond creation, modification, and deactivation is handled via `POST /api/v1/gm/actions` with action types `create_bond`, `modify_bond`, and `retire_bond`. See [actions.md](actions.md) for the full GM action type catalog.

Bond detail is returned inline on Game Object detail endpoints (e.g., `GET /api/v1/characters/{id}` includes all bonds).

#### Bond Creation Fields (via `create_bond` GM action)

| Field | Required | Default | Notes |
|-------|----------|---------|-------|
| `target_type` | Yes | — | `character`, `group`, or `location` |
| `target_id` | Yes | — | ID of target Game Object |
| `source_label` | No | `""` | Label from source's perspective |
| `target_label` | No | `""` | Label from target's perspective (bidirectional only) |
| `description` | No | `""` | Freeform context |
| `bidirectional` | No | Auto-inferred | Char↔Char, Char↔Group, Group↔Group = true; Location-involved = false |

`slot_type` is auto-inferred (see Slot Type Auto-Inference above). System validates: no duplicate active bond to the same target, source slot count within hard limit. If target is at capacity for a bidirectional bond, system returns a warning but allows creation.

### Character Sheet Integration

- `GET /api/v1/characters/{id}` — full sheet includes all bonds (active, trauma, and past/retired) plus bond-distance locations. Bidirectional inbound bonds are merged into the bond list with no distinction.

### Player Actions (via Proposals)

- **"New Bond"** downtime action: `POST /api/v1/proposals` — player specifies the target Game Object. If at max active bond count, must also specify `retire_bond_id` (which existing bond to retire to Past). If under max, `retire_bond_id` is optional.
- **"Maintain Bond"** downtime action: `POST /api/v1/proposals` — restore bond charges to effective max. Player specifies the bond by ID.

No dedicated bond CRUD endpoints for players — all player-initiated bond changes go through proposals. Bonds are referenced by ID, not by slot index.

---

## Implications for Other Specs

| Spec | Implication |
|------|-------------|
| [traits](traits.md) | Shares the unified `slots` table. Trait Template catalog for Core/Role traits. Group/Location traits are descriptive (no charges). Both traits and bonds now use the "charges" concept: traits spend charges for +1d; bonds lose charges when `bond_strained` is applied by the GM. Difference: bond charges at 0 trigger degradation; trait charges at 0 simply block invocation. |
| [game-objects](game-objects.md) | Bond-distance presence defined here. game-objects.md references this spec. Group Holdings as a bond category. |
| [character-core](character-core.md) | PCs have 8 Bond slots (mechanical). NPCs have 7 (descriptive). Trauma occupies bond slots (max 8). Character-to-Group bond = membership. |
| [actions](actions.md) | ✅ **Updated 2026-03-07**: Count-based bond model propagated. `new_bond` uses `{target_type, target_id, retire_bond_id?}`. Bond provides flat +1d. GM may apply −1 bond charge on approval via `bond_strained` flag. |
| [downtime](downtime.md) | "Maintain Bond" and "New Bond" downtime activities. Both cost 1 FT. New Bond now specifies target + optional retire_bond_id. Maintain Bond restores charges to effective max. |
| [feed](feed.md) | ✅ **Updated 2026-03-10**: Renamed "NPC-intermediary" to "Character-intermediary" throughout. PCs are valid intermediaries noted. |
| [events](events.md) | Bond changes logged as events. Visibility references feed.md. |
| [glossary](../glossary.md) | ✅ **Updated 2026-03-07**: Character-intermediary rename done. Action/GM Action/Player Direct Action terms added. Bond charges terminology should be reviewed for alignment with trait charges entry. |
| [architecture/data-model](../architecture/data-model.md) | Unified `slots` table with 9 slot_types. `pc_bond` (8 max), `npc_bond` (7 max). Nullable mechanical fields. Physical columns `stress` and `stress_degradations` store bond charges and degradation count respectively. See [data-model.md](../architecture/data-model.md). |

---

## Open Questions

None — all open questions resolved in 2026-03-07 interrogation.

---

_Last updated: 2026-03-16 (verified against Phase 3 implementation; clarified degradation-boundary behavior: charges reset to new effective max in single compound operation; degradation reversal does not auto-restore charges)_
