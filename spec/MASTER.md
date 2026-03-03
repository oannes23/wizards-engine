# Wizards Engine — Spec Master Index

## How This Document Works

This is the central index for all design specifications. Each area links to its detailed spec doc.

**Status indicators:**
- 🔴 Not started — needs initial interrogation
- 🟡 In progress — has content, needs deepening
- 🟢 Complete — no open questions remain
- 🔄 Needs revision — downstream decisions may have invalidated something

**Workflow:**
1. Run `/interrogate spec/domains/<area>` to deepen any spec
2. Answer questions until the agent has no more to ask
3. Agent updates the spec doc, glossary, and this index
4. Repeat for next area

---

## Core Principle

> **Mutable state + append-only event log. No DSL — all game logic is hardcoded in Python. API-first REST backend for a single narrative TTRPG campaign.**

---

## Scope

### MVP 0
- TBD — to be defined during interrogation (likely: core loop — character sheets + proposals + GM approval)

### MVP 1
- TBD — to be defined during interrogation (likely: downtime, magic, world management)

See [mvp-scope.md](architecture/mvp-scope.md) for full details.

---

## Architecture Specs

| Area | Doc | Status | Notes |
|------|-----|--------|-------|
| System Overview | [overview.md](architecture/overview.md) | 🟡 | Populated from engine.md — actors, principles, tech stack, non-goals. 🔄 **Needs addition**: Deferred Narrative Resolution as a named design principle. |
| Data Model | [data-model.md](architecture/data-model.md) | 🔄 | Entity types, relationships, persistence stack. Open Qs: ID strategy, polymorphic refs. **Needs revision**: unified Trait/Bond instance model, Trait Template catalog, polymorphic bond targets, shared base fields (`is_deleted`), lightweight bond model with directionality, NPC `attributes` blob, Story entries with audit trail, event auto-capture logic, Location curated affiliations. |
| MVP Scope | [mvp-scope.md](architecture/mvp-scope.md) | 🟡 | Light touch — scope decisions deferred to after domain interrogation. |

---

## Domain Specs

<!-- Order by conceptual dependency: primitives first, composites later -->

| Area | Doc | Status | Key Open Questions |
|------|-----|--------|-------------------|
| Game Objects | [game-objects.md](domains/game-objects.md) | 🟢 | All resolved (31 decisions). Soft delete (Draft sessions hard-delete exception), lightweight bonds on NPCs/Groups (not Locations), bond directionality model (Group↔Group/NPC↔NPC bidirectional, NPC→Group=membership, Group→NPC=special, Locations=targets only), quantum NPC locations with notes, deferred narrative resolution, story entries with full audit trail + edit/soft-delete, clock annotations via events, event auto-capture, group tier unbounded, clock segments any positive int (default 5), unlimited location nesting, clock dual route access, location curated affiliations + computed presence, NPC merged location view, group computed members, story owners sub-resource, bidirectional bond labels (source/target), lightweight bond IDs + sub-resource API. **Faction → Group rename** (project-wide). |
| Character Core | [character-core.md](domains/character-core.md) | 🟢 | All questions resolved. 🔄 **Note**: needs `last_session_time_now` field and `session_ids` list. Plot: +1/+2 per session (Additional Contribution), guaranteed 6. FT via Time Now delta. Rest heals 3+mods. |
| Traits | [traits.md](domains/traits.md) | 🟢 | All questions resolved. Updated with unified Trait/Bond architecture, Trait Template catalog, Past/Retired concept. |
| Bonds | [bonds.md](domains/bonds.md) | 🟢 | All resolved. 🔄 **Note**: "Heal Bond Stress" renamed to "Maintain Bond" in proposals spec. Bond directionality model affects bond-distance visibility graph. |
| Magic System | [magic-system.md](domains/magic-system.md) | 🟢 | All resolved — deepened with: combined sacrifice list, Stress→Trauma cascade, GM-interpreted effects (power 1–5), player effect use/retire, Charge Action split (charges vs power), Regain Gnosis formula. |
| Proposals | [proposals.md](domains/proposals.md) | 🟢 | All resolved — 10 action types (3 Actions + 7 Downtime), all cost 1 FT for downtime, formulas defined, GM full override, mutate-in-place revision, Plot = guaranteed 6, projects use Story/Arc. |
| Downtime | [downtime.md](domains/downtime.md) | 🟢 | All resolved (19 decisions) — session lifecycle (Draft→Active→Ended), FT via Time Now delta, Plot +1/+2, Find Time, late joins, one Active at a time, forward-only lifecycle, per-clock adjustments, bidirectional session-character refs. |
| Events | [events.md](domains/events.md) | 🟢 | All resolved (17 decisions). Keyed before/after changes, convention-based `{domain}.{action}` types, one event per action, bond-distance visibility (6 levels: global/gm_only/private/bonded/familiar/public), actor typed ref, targets list, generic metadata, proposal_id back-ref, session auto-capture, no undo for MVP, retain forever. |
| Auth | [auth.md](domains/auth.md) | 🟡 | Token format, expiry, GM setup flow, player-character mapping. |

---

## Suggested Interrogation Order

1. `architecture/overview` — establish system context
2. `domains/game-objects` — NPCs, Groups, Clocks, Locations, Sessions, Stories
3. `domains/character-core` — base character sheet
4. `domains/traits` — trait mechanics
5. `domains/bonds` — relationship mechanics (needs game-objects done first)
6. `domains/magic-system` — magic subsystem
7. `domains/proposals` — core gameplay loop
8. `domains/downtime` — between-session phase
9. `domains/events` — event log details
10. `domains/auth` — permissions and onboarding
11. `architecture/data-model` — solidify after domains are clear
12. `architecture/mvp-scope` — cut scope last

---

## Implementation Specs

### MVP 0

| Epic | Doc | Status | Blocked By |
|------|-----|--------|------------|
| Overview | [overview.md](implementation/mvp-0/overview.md) | 🔴 | Domain specs |

### MVP 1

| Epic | Doc | Status | Blocked By |
|------|-----|--------|------------|
| Overview | [overview.md](implementation/mvp-1/overview.md) | 🔴 | MVP 0 complete |

---

## Dependency Graph

```
game-objects (primitive)        events (primitive)        auth (primitive)
    │                               │                       │
    ├──> character-core             │                       │
    │       │                       │                       │
    │       ├──> traits             │                       │
    │       │       │               │                       │
    │       ├──> bonds              │                       │
    │       │       │               │                       │
    │       └──> magic-system       │                       │
    │               │               │                       │
    │       ┌───────┘               │                       │
    │       ▼                       │                       │
    └──> proposals <────────────────┘───────────────────────┘
            │
            ▼
         downtime
```

---

## Recent Changes

### 2026-03-02: Game Objects Second Interrogation — Bond Directionality + Group Rename

- Game Objects re-interrogated — 14 new decisions (31 total):
- **Faction → Group rename**: Project-wide rename. "Group" is more inclusive (covers guilds, families, crews, etc.). All specs, glossary, API endpoints updated. All downstream specs flagged 🔄 for rename.
- **Bond directionality model**: Group↔Group and NPC↔NPC are bidirectional (one record, both see). NPC→Group = membership (inbound bonds). Group→NPC = special relationship. NPC/Group→Location = directional. **Locations are targets only** — no outbound bonds.
- **Bidirectional bond labels**: `source_label` / `target_label` fields on bidirectional bonds. Each side sees its own wording.
- **Lightweight bond IDs + sub-resource API**: Each bond has unique ID, managed via `POST/PATCH/DELETE /{type}/{id}/bonds/{bond_id}`.
- **Drop Group locations list**: Territorial control via Group→Location bonds. No separate `locations` field.
- **Location curated affiliations**: `npcs` and `groups` lists with optional notes (e.g., `{npc_id, note: "bartender"}`). Independent of bonds.
- **Location computed presence**: Detail merges curated affiliations + inbound bonds. Bond-derived entries flagged.
- **NPC common_locations with notes**: Entries are `{location_id, note?}`.
- **NPC merged location view**: Detail merges common_locations + Location-targeting bonds.
- **Group members computed on detail**: Derived from inbound bonds.
- **Clock dual route access**: Group project clocks accessible via both sub-resource and standalone endpoint.
- **Story entry editability**: Players edit own, GM edits any. Soft-delete with full audit trail (updated_at, updated_by, is_deleted, deleted_by).
- **Story owners sub-resource**: `POST/DELETE /stories/{id}/owners` with `{type, id}`.
- **Draft session hard delete**: Exception to soft-delete rule (no downstream references).
- Updated glossary: Group (renamed from Faction), NPC, Location, Story, Lightweight Bond, Soft Delete, Clock, Clock Adjustment Annotation, Deferred Narrative Resolution, Downtime, Game Object, Session
- All specs flagged 🔄 for Faction → Group rename
- Data model flagged 🔄 — bond directionality, location affiliations, story audit trail

### 2026-03-01: Events Interrogation Complete

- Events status: 🟡 → 🟢 — all 8 open questions resolved + 9 additional decisions (17 total)
- **Changes field**: Keyed before/after pairs — `{field: {before: X, after: Y}}`. Dotted paths for cross-object fields. Separate `created`/`deleted` lists.
- **No undo for MVP**: GM corrects via direct actions. Before/after data preserves option for future undo.
- **Convention-based types**: `{domain}.{action}` naming (e.g., `character.stress_changed`, `clock.advanced`). No enum, no category field.
- **One event per action**: Compound changes (proposal approval affecting multiple objects) produce a single event.
- **Bond-distance visibility**: 6 levels — `global`, `gm_only`, `private`, `bonded` (1-hop, default), `familiar` (2-hop), `public` (3-hop). Bond graph includes both PC Bonds and lightweight bonds. Cached per character, invalidated on bond changes. GM can override any event's visibility.
- **Targets as list**: All affected game objects listed. First element is primary.
- **Actor typed ref**: `{type: 'player'|'gm'|'system', id?: string}`.
- **Proposal back-ref**: Optional `proposal_id` field on events.
- **Generic metadata**: Freeform JSON for clock annotations, event links, future extensions.
- **Narrative from GM + system**: GM provides for approvals/direct actions. System auto-generates for lifecycle events.
- **Session auto-capture**: From game-objects spec, integrated here.
- **Retain forever**: No cleanup or archival.
- Added glossary terms: Bond-Distance Visibility
- Updated glossary: Event, Event Log
- Bonds spec flagged 🔄 — bond changes invalidate visibility cache
- Auth spec flagged 🔄 — event visibility is bond-distance based, not role-based
- Data Model spec flagged 🔄 — event model with changes/created/deleted/targets/metadata/visibility/actor

### 2026-03-01: Game Objects Interrogation Complete

- Game Objects status: 🟡 → 🟢 — all 6 open questions resolved + 11 new decisions (17 total)
- **Deferred Narrative Resolution** — named as a core design principle. Game state is intentionally left ambiguous until narratively observed. Applies to NPC locations (quantum), Group projects (retroactive resolution), and potentially other domains.
- **Quantum NPC locations**: NPCs have `common_locations` list (not a pinned location). They exist in a probability smear across common locations.
- **Unified lightweight bonds on all game objects**: NPCs, Groups, and Locations all get a `bonds` list. Replaces old Group `relationships` field and Location `groups`/`npcs` references. Bond-shaped (target, name, description, is_active) but no stress/charge mechanics. *(Note: subsequently revised — Locations lost bonds in the 2026-03-02 second interrogation.)*
- **Bidirectional Group bonds**: One record per pair, both groups see the same label.
- **Single NPC `attributes` blob**: Merged separate traits + stats fields into one freeform JSON blob.
- **Soft delete for all game objects**: Base `is_deleted` flag. References remain valid. Per-type lifecycle fields are independent.
- **Clock segments**: Any positive integer, default 5. No constrained set.
- **Unlimited Location nesting**: No system-imposed depth limit.
- **Group tier**: Any non-negative integer. No upper bound.
- **Story freeform tags**: Optional string list for categorization.
- **Story embedded narrative entries**: `entries` array with text + optional linkage fields (character, session, event, game object refs).
- **Clock annotations via Event log**: No denormalized history on Clock. Annotations are event metadata.
- **Event auto-capture to Active session**: Auto-tag with override capability.
- **Clock completion flags**: System flags, GM resolves narratively. Group projects have deferred outcomes.
- Session model integrated from downtime spec.
- Added glossary terms: Deferred Narrative Resolution, Lightweight Bond, Soft Delete
- Updated glossary: Game Object, NPC, Group, Clock, Location, Story, Clock Adjustment Annotation
- Architecture overview flagged 🔄 — needs Deferred Narrative Resolution as design principle
- Architecture data-model flagged 🔄 — shared base fields, lightweight bond model, NPC attributes blob, Story entries

### 2026-03-01: Downtime Third Pass — Lifecycle Edge Cases

- Downtime spec deepened with 7 additional edge case decisions (19 total decision blocks):
- **Session mutability**: GM can edit summary/notes in Draft + Active. Only Ended is read-only.
- **No clawback**: Removing a participant from Active doesn't reverse distributed FT/Plot.
- **Forward-only lifecycle**: No undo (Active→Draft) or reopen (Ended→Active). Mistakes via GM direct actions.
- **Draft-only deletion**: Only Draft sessions can be deleted. Active/Ended are permanent.
- **Contribution flag locks on Start**: Must be set before Start or at moment of late join.
- **Per-clock adjustments**: Clock changes happen individually during Active, not bundled in End Session. End Session just transitions status.
- **Bidirectional session-character refs**: Characters store session IDs for easy history lookups.
- Character Core flagged 🔄 — needs `session_ids` list.
- API endpoints updated: `DELETE /sessions/{id}` (Draft only), `PATCH` works on Active, End Session has no payload.

### 2026-03-01: Downtime Follow-up — Edge Cases

- Downtime spec deepened with 3 edge case decisions:
- **Late joins**: Players can join Active sessions and receive FT + Plot immediately (same distribution logic)
- **Session concurrency**: Only one Active session at a time. System enforces — must End before Starting another. Multiple Draft sessions allowed.
- **Time Now validation**: Must be >= previous session's Time Now. Equal allowed (0 FT delta). Negative rejected. First session unconstrained.
- Updated Session Participants section: registration works on Draft and Active sessions

### 2026-03-01: Downtime Interrogation Complete

- Downtime status: 🟡 → 🟢 — all 8 open questions resolved
- **No downtime mode**: downtime mechanics embedded in session lifecycle. No trigger endpoint.
- **Session lifecycle: Draft → Active → Ended**:
  - Start Session: distributes FT (Time Now delta) + Plot (+1 base, +2 with Additional Contribution)
  - End Session: GM adjusts group clocks with annotations (notes + event/game object links)
- **Time Now**: abstract campaign time counter, GM-set per session. FT = `session.time_now - character.last_session_time_now`
- **FT carries over, capped at 20**: persistent meter, excess lost
- **Plot income**: +1/+2 per session at start, participants only. Additional Contribution = meta-game reward
- **Player self-registration**: players add themselves to draft sessions, GM can also manage
- **Find Time**: direct player action, 3 Plot → 1 FT, no approval needed
- **No activity limit**: just FT cost
- **Clock adjustments**: default +1 at end session, GM can adjust each with annotations
- Added glossary terms: Time Now, Additional Contribution, Find Time, Clock Adjustment Annotation, Downtime Action (category), Recharge Trait, Rest, Work on Project
- Updated glossary: Session, Free Time, Plot, Downtime
- Game Objects spec flagged 🔄 — Session model massively expanded
- Character Core flagged 🔄 — needs `last_session_time_now` field
- Proposals spec flagged 🔄 — Find Time is a direct action (not a proposal type)

### 2026-03-01: Proposals Interrogation Complete

- Proposals status: 🟡 → 🟢 — all 10 open questions resolved
- **10 action types** in two categories:
  - Actions (session): `use_skill`, `use_magic`, `charge_magic`
  - Downtime (1 FT auto-cost): `regain_gnosis`, `recharge_trait`, `maintain_bond`, `work_on_project`, `rest`, `new_trait`, `new_bond`
- **Downtime structural rule**: all downtime actions cost 1 FT automatically
- **Rest** is a new downtime action: heals 3 Stress base + up to +3 from trait/bond modifiers
- **Maintain Bond** renamed from "Heal Bond Stress" — same mechanic (full heal to 0)
- **Skill training via projects**: uses `work_on_project` targeting a Story/Arc. GM resolves when ready.
- **Player projects use Story/Arc** — narrative entries, not segmented clocks. No segment target.
- **GM full override**: can modify any calculated value, force-approve even if resources insufficient
- **Revision = mutate in place**: rejected proposals updated, status back to pending
- **Binary approve/reject**: no "request changes" state
- **Validated on submit, deducted on approval**: re-validates on approval, GM can force
- **Unlimited concurrent proposals**: re-validation handles conflicts
- **One event per approval**: comprehensive changes field
- **Plot = guaranteed success**: each Plot spent = guaranteed 6 before rolling (not +1d)
- **Common + extras data model**: shared fields + JSON details per action type
- **Skill Action**: player selects skill + modifiers + narrative. GM approves with full outcome.
- **No timeout for MVP**
- Added glossary terms: Action, Downtime Action, Rest, Recharge Trait, Work on Project, Maintain Bond
- Updated glossary: Proposal, Plot, Stress, Skill, Charge
- Downtime spec flagged 🔄 — all activity types now defined with formulas
- Events spec flagged 🔄 — one event per approval pattern
- Bonds spec flagged 🔄 — "Heal Bond Stress" renamed to "Maintain Bond"
- Game Objects spec flagged 🔄 — Stories need narrative entry support for player projects
- Character Core flagged 🔄 — Plot is guaranteed success not outcome tier, Rest formula defined

### 2026-03-01: Magic System Deepening — Implementation Details

- Magic System re-interrogated — 13 new implementation-affecting decisions
- **Combined sacrifice**: Players can mix any sacrifice types in one action. Proposal stores a list of sacrifice entries (`{type, amount, target?}`).
- **Stress sacrifice → Trauma**: Standard Stress rules apply. Voluntary Stress sacrifice can trigger Trauma cascade.
- **Effect creation GM-interpreted**: GM interprets dice roll to set name, description, power_level (1–5), initial charges. No formula.
- **Magic Stats start at 0**: All characters begin with level 0 in all 5 stats. Progression via GM XP awards only.
- **Power_level scale 1–5**: Both charged and permanent effects use a 1–5 power scale.
- **Charges unbounded**: No system cap on charges. GM sets freely. Current/max pair.
- **Charge Action split**: Charged effects = charges only (restore + increase max). Permanent effects = power_level boost only.
- **One effect per action**: A Magic Action always produces exactly one effect.
- **Player initiates effect use**: Direct charge decrement, optional narrative, no GM approval.
- **Player can self-retire effects**: No proposal needed to retire. Frees cap space.
- **Regain Gnosis formula**: 1 FT = 3 base + lowest Magic Stat + up to +3 from trait/bond invocation.
- **"Other" sacrifice**: GM assigns Gnosis value during standard proposal review step.
- Added glossary term: Regain Gnosis (Downtime Action)
- Updated glossary terms: Magic Action, Charge Action, Magic Effect, Sacrifice, Magic Stat
- Proposals spec flagged 🔄 — sacrifice list model, GM effect creation during approval
- Downtime spec flagged 🔄 — Regain Gnosis formula now defined

### 2026-02-26: Magic System Interrogation Complete

- Magic System status: 🟡 → 🟢 — all 8 open questions resolved
- **Freeform sacrifice-driven magic**: no spell list. Players describe intention + symbolism + sacrifice. GM creates Magic Effects as outcomes.
- **Magic Stats hardcoded**: Being, Wyrding, Summoning, Enchanting, Dreaming. Level = base dice pool. Flat 5 XP/level, GM awards.
- **Sacrifice system**: Gnosis (1:1), Stress (1=2), Free Time (1=3+lowest stat), Bond/Trait sacrifice (10, destroyed). Tiered Gnosis→dice conversion.
- **Sacrifice vs Use**: Sacrificing destroys (goes to Past, 10 Gnosis). Using = standard +1d modifier.
- **Two action types**: Magic Action (create effects) and Charge Action (recharge/boost effects)
- **Three effect types**: instant, charged (direct use, no proposal), permanent (Enchanting)
- **Effect cap**: 9 active per character. Style bonus: hidden GM modifier.
- Added glossary terms: Magic Action, Charge Action, Sacrifice, Style Bonus
- Updated glossary: Gnosis, Magic Stat, Magic Effect, Past/Retired
- Removed glossary: Permanent Effect (merged into Magic Effect)
- Proposals spec flagged 🔄 — needs Magic Action and Charge Action as new proposal types

### 2026-02-26: Traits Follow-up — Catalog Architecture

- Resolved Trait Template catalog interaction model: pick from catalog OR propose new (added on approval)
- Template edits propagate to all characters referencing them
- Type binding: fixed on template (core/role), enforced on slot assignment
- No duplicate templates per character
- Updated glossary: Trait Template

### 2026-02-26: Bonds Interrogation Complete

- Bonds status: 🔄 → 🟢 — all 8 open questions resolved plus upstream integration
- **Bond level removed** — bond depth is captured by accumulated fiction stream, not a number
- **Bond stress**: 0–5, degradation mechanic mirroring character Stress/Trauma. Healed fully via downtime.
- **Unified Trait/Bond architecture**: Bonds are a type of Trait Instance. Shared instance model with Core/Role Traits.
- **Trait Template catalog**: GM-created library of trait definitions. Characters pick from catalog. Multiple characters can share templates.
- **Past/Retired concept**: replaced Traits and Bonds move to Past section (is_active=false), history preserved
- **Trauma creates new instance**: old bond retires to Past, new trauma bond occupies slot
- Added glossary terms: Trait Template, Trait Instance, Past/Retired, Bond Degradation, New Bond, Heal Bond Stress
- Updated glossary terms: Bond (no level, stress mechanic), Bond Stress (degradation), Trauma (new instance model), Core Trait, Role Trait
- Removed glossary term: Bond Level
- Traits spec flagged 🔄 — needs revision for unified architecture, catalog, Past concept
- Data Model spec flagged 🔄 — needs unified Trait/Bond model, Trait Template catalog

### 2026-02-26: Traits Interrogation Complete

- Traits status: 🟡 → 🟢 — all 6 open questions resolved
- Key decisions: 1 charge per +1d invocation, full initial charge (5), narrative free invoke, blank trait slots allowed, "New Trait" downtime action for replacement, per-trait charge reset
- **Modifier stacking rule**: 1 Core Trait + 1 Role Trait + 1 Bond per proposal, each +1d, max +3d total
- Bond provides flat +1d (same as traits) — Bond level purpose needs resolution in Bonds spec
- Added glossary terms: Modifier Stacking, New Trait (Downtime Action)
- Updated glossary terms: Core Trait, Role Trait, Charge, Bond
- Bonds spec updated to 🔄 (flat +1d changes Bond level's role)
- Proposals and Downtime specs noted with new decisions

### 2026-02-26: Character Core Interrogation — Follow-up Round

- Resolved remaining design gaps: post-Trauma Stress reset (to 0), exact skill list (8 skills), computed values in API, max-Trauma edge case (GM narrative), initial meter values (GM-set), character lifecycle (active only)
- Skill list finalized: Awareness, Composure, Influence, Finesse, Speed, Power, Knowledge, Technology
- Updated glossary: Stress (reset to 0), Skill (exact 8), Trauma (all-Trauma edge case)

### 2026-02-25: Character Core Interrogation Complete

- Character Core status: 🟡 → 🟢 — all 7 open questions resolved
- Key decisions: Stress 0–9 with Trauma consequence, Plot session income + outcome tier upgrade, Skills as shared canonical list (hardcoded, downtime-only growth), minimal character fields, GM creates characters, single full-sheet API endpoint
- Added **Trauma** to glossary — consequence of maxing Stress, replaces a Bond
- Updated glossary terms: Stress, Plot, Skill
- Bonds spec flagged 🔄 — needs revision for Trauma mechanic (`is_trauma` flag on Bond model)
- Downstream implications noted for Downtime (stress healing + skill growth) and Proposals (Plot spend)

### 2026-02-24: Ingested engine.md into Spec Structure

- Populated glossary with ~25 domain terms
- Populated architecture/overview.md (actors, principles, tech stack, non-goals)
- Populated architecture/data-model.md (all entities, fields, relationships)
- Updated architecture/mvp-scope.md (deferred scope decisions to interrogation)
- Created 9 domain specs from engine.md content:
  - game-objects, character-core, traits, bonds, magic-system
  - proposals, downtime, events, auth
- All specs set to 🟡 (in progress — content exists, needs interrogation)
- Open questions flagged per domain for interrogation

### 2026-02-24: Project Initialized

- Created initial spec structure
- Key decisions pending: all

---

## Glossary

See [glossary.md](glossary.md) for canonical definitions of all terms.

---

## Last Updated
_2026-03-02 — Game Objects second interrogation: bond directionality, location affiliations, story entry editability, Faction→Group rename._
