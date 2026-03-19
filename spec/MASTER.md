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

**Single MVP, phased build.** No MVP 0/1 split — the full system is the target. Implementation is organized as 6 phases:

1. **Foundation** — Auth, DB, API skeleton, test fixtures
2. **World** — Game objects (NPCs, Groups, Locations, Stories, Clocks)
3. **Characters** — Full character sheet, traits, bonds, magic effects
4. **Actions** — Unified action system (proposals, GM actions, player direct actions), events, magic, rider events
5. **Sessions** — Session lifecycle, downtime, FT/Plot distribution, invites
6. **Web UI** — Basic mobile-friendly frontend

See [mvp-scope.md](architecture/mvp-scope.md) for full details.

---

## Architecture Specs

| Area | Doc | Status | Notes |
|------|-----|--------|-------|
| System Overview | [overview.md](architecture/overview.md) | 🟢 | All resolved. Deployment: self-hosted VPS. UI: same process. Pagination: ULID cursor. API conventions: separate doc. |
| API Conventions | [api-conventions.md](architecture/api-conventions.md) | 🟢 | All resolved. **Updated 2026-03-13**: FastAPI framework. Bare responses, nested error format, snake_case naming, PATCH omit/null semantics, ISO 8601 timestamps, ULID-order sorting, 404 for authz, same-origin CORS. **Verified 2026-03-16**: Custom HTTPException handler convention documented. |
| Data Model | [data-model.md](architecture/data-model.md) | 🟢 | All resolved. **Updated 2026-03-14**: events.changes value structure updated: added op tag (field.set/meter.delta/meter.set) and optional clamped flag. |
| MVP Scope | [mvp-scope.md](architecture/mvp-scope.md) | 🟢 | All resolved. Single MVP, 6-phase build. |

---

## Domain Specs

<!-- Order by conceptual dependency: primitives first, composites later -->

| Area | Doc | Status | Key Open Questions |
|------|-----|--------|-------------------|
| Game Objects | [game-objects.md](domains/game-objects.md) | 🟢 | All resolved. **Updated 2026-03-14**: Added cross-reference to events.md Meter Boundary Patterns for clock completion. **Verified 2026-03-17**: Aligned with Phase 2–4 implementation. Story `notes` field removed (not in model); `visibility_level` column added to field list. Participant record corrected (`session_id`/`character_id`, no `player_id`). Character POST semantics corrected (creates `simplified` only; full characters via invite flow). |
| Character Core | [character-core.md](domains/character-core.md) | 🟢 | All resolved. **Updated 2026-03-14**: Added cross-reference to events.md Meter Boundary Patterns for Stress/Trauma compound consequence. **Verified 2026-03-16**: Aligned with Phase 3 implementation. |
| Traits | [traits.md](domains/traits.md) | 🟢 | All resolved. **Updated 2026-03-13**: Trait template CRUD endpoints (standard REST, GM-only). Auto-catalog on new_trait approval. Template propagation (name/desc only, type immutable, soft-delete orphans). **Verified 2026-03-16**: Aligned with Phase 3 implementation. Note: `DELETE /trait-templates/{id}` is idempotent in code (re-deleting returns 204 silently); spec says 204 but does not specify idempotency — code is stricter (better). |
| Bonds | [bonds.md](domains/bonds.md) | 🟢 | All resolved. **Updated 2026-03-14**: Added cross-reference to events.md Meter Boundary Patterns for bond stress boundary behavior. **Verified 2026-03-16**: Aligned with Phase 3 implementation. `apply_bond_strain` resets charges to new effective max after degradation (not to 0). `reverse_degradation` does not auto-restore charges — separate `restore_bond_charges` call required. `retire_effect` is idempotent (no guard on already-inactive). |
| Magic System | [magic-system.md](domains/magic-system.md) | 🟢 | All resolved. **Updated 2026-03-13**: Effect use body ({narrative?: string}). charge_magic approval outcome (charges_added/power_boost in gm_overrides). **Verified 2026-03-16**: Aligned with Phase 3 implementation. `retire_effect` service function is idempotent (retires without checking current is_active state). |
| Actions | [actions.md](domains/actions.md) | 🟢 | All resolved. **Verified 2026-03-16**: Corrected `calculated_effect` schemas to match implementation (field names, structure). GM Action Validation updated — code clamps meters to documented ranges rather than allowing arbitrary values. |
| Downtime | [downtime.md](domains/downtime.md) | 🟢 | All resolved. Time Now defaults documented (default 0, GM can override at creation). **Verified 2026-03-16**: GM may call find-time on behalf of any character. find-time validates detail_level = full (422 not_a_pc). Session start error codes documented. Session end error code (session_not_active) and late-join event details (session.participant_added: global, character as primary target, changes include free_time/last_session_time_now/plot) documented against Stories 5.1.2–5.1.3. |
| Events | [events.md](domains/events.md) | 🟢 | All resolved. **Verified 2026-03-16**: Clarified `GET /events/{id}` returns 404 for silent events for all callers including GM. session.participant_added default visibility (global) added against Story 5.1.2. |
| Feed | [feed.md](domains/feed.md) | 🟢 | All resolved. **Verified 2026-03-16**: GM silent feed excludes story entries. POST /me/starred idempotency (200 if already starred, 201 on new star) and DELETE /me/starred idempotency documented. |
| Auth | [auth.md](domains/auth.md) | 🟢 | All resolved. **Updated 2026-03-12**: Major auth model redesign — magic link + cookie auth (no Bearer tokens). Bare invite flow synced with character-core. Plaintext login code storage. Cookie-only API auth. Player self-edit display name (PATCH /me). GM character via POST /me/character. Player self-refresh link. Login endpoint POST /auth/login. No explicit deactivation endpoint. **Verified 2026-03-16**: Login response `type` discriminator and cookie max_age documented. |
| Web UI | [web-ui.md](domains/web-ui.md) | 🟢 | Full UX specification for Phase 6. Technology stack (Pico CSS + Alpine.js), navigation architecture, complete screen inventory (40+ screens), interaction flows, component definitions, information hierarchy, table-flow design principles, API additions. Spec changes: `narrative` optional on session actions; `recharge_trait` and `maintain_bond` promoted to direct player actions. |

---

## Design Ambiguity Analysis

Design ambiguities that would cause real friction during implementation, organized by severity.

### BLOCKING: Can't Build Without Deciding

#### ~~1. No Dice/Outcome Framework~~ ✅ RESOLVED
Resolved in proposals.md (2026-03-05): Narrative only — no dice values or outcome tiers recorded. Typed `calculated_effect` schemas per action type (outcome + costs). GM writes narrative, optionally overrides calculated values (replacement semantics). System tracks mechanical state changes, not roll outcomes.

#### ~~2. Polymorphic Reference Strategy~~ ✅ RESOLVED
Resolved in data-model.md (2026-03-05): Hybrid approach — type+id columns inline for single refs, association tables for list refs.

#### ~~3. MVP Scope~~ ✅ RESOLVED
Resolved in mvp-scope.md (2026-03-04): Single MVP, 6-phase build.

### FRICTION: Implementable But Arbitrary Choices Required

#### ~~4. Event Visibility Cache~~ ✅ RESOLVED
Resolved in mvp-scope.md (2026-03-04): Compute-on-read, no cache. Add cache only if slow.

#### ~~5. Clock Completion Surfacing~~ ✅ RESOLVED
Resolved in game-objects.md (2026-03-04): Computed `is_completed` on read. Auto-generates `resolve_clock` proposal.

#### ~~6. Trait Template Propagation Semantics~~ ✅ RESOLVED
Resolved in traits.md (2026-03-13): Propagate name/description only. Type is immutable. Soft-delete template orphans instances (instances keep reference, template hidden from catalog). See [traits.md](domains/traits.md).

#### 7. Lightweight Bond Directionality — Implementation Complexity
**Affects**: game-objects

Intricate directionality rules: bidirectional bonds mean creating/deleting two records atomically. The "membership" semantic for NPC→Group is implicit in direction. Already decided and specified — just noting this is the most complex piece of game-objects to implement. Plan extra time and good test coverage.

#### 8. Story Entry Audit Trail
**Affects**: game-objects

Story entries have `updated_by`, `deleted_by`, `is_deleted` fields with player-edit-own + GM-edit-any rules — essentially a mini CMS.

**Pragmatic recommendation**: Start with simple append-only entries (no edit, no delete). Add edit/delete later if actually needed during play.

### COSMETIC: Won't Matter Until Someone Asks

- **GM Decision Frameworks**: Multiple specs defer to "GM decides" for strain triggers, trauma negotiation, clock outcomes, etc. This is intentional — narrative flexibility. No implementation impact.
- **Charge Ranges on Magic Effects**: "Charges are unbounded" — just an integer field. GM sets reasonable values.
- **NPC Attributes Blob Schema**: Deliberately freeform JSON. No implementation impact.

---

## Recommended Next Steps

### ~~Priority 1: Resolve Remaining Blocking Issue~~ ✅ RESOLVED
~~1. **`/interrogate spec/domains/proposals.md`**~~ — Resolved (2026-03-05, expanded 2026-03-07). Typed `calculated_effect` schemas, rider events, `resolve_clock`, player-written narratives, GM override semantics all decided. Renamed to actions.md — unified action system (proposals, GM actions, player direct actions).

### ~~Priority 1: Resolve Open Questions in overview.md~~ ✅ RESOLVED
All resolved (2026-03-05): deployment model (self-hosted VPS), UI serving (same process), pagination (ULID cursor), real-time (deferred, polling for MVP).

### ~~Priority 3: Propagate Stale Decisions~~ ✅ RESOLVED
All propagation complete as of 2026-03-14. All specs aligned.

---

## Suggested Interrogation Order

1. `architecture/overview` — establish system context
2. `domains/game-objects` — NPCs, Groups, Clocks, Locations, Sessions, Stories
3. `domains/character-core` — base character sheet
4. `domains/traits` — trait mechanics
5. `domains/bonds` — relationship mechanics (needs game-objects done first)
6. `domains/magic-system` — magic subsystem
7. `domains/actions` — core gameplay loop (renamed from proposals)
8. `domains/downtime` — between-session phase
9. `domains/events` — event log details
10. `domains/auth` — permissions and onboarding
11. `architecture/data-model` — solidify after domains are clear
12. `architecture/mvp-scope` — cut scope last

---

## Implementation Specs

Implementation uses a **6-phase build order** (see [mvp-scope.md](architecture/mvp-scope.md)). Epic/Story breakdown is in [`spec/implementation/`](implementation/README.md).

**20 Epics, 78 Stories** across 7 phases (5 complete + Phase 5.5 backend additions + Phase 6 Web UI).

| Phase | Epic | File | Stories | Status |
|-------|------|------|---------|--------|
| 1 | 1.1 — Scaffolding & DB | [phase1-scaffolding-db.md](implementation/phase1-scaffolding-db.md) | 4 | 🟢 |
| 1 | 1.2 — Auth & API Skeleton | [phase1-auth-api-skeleton.md](implementation/phase1-auth-api-skeleton.md) | 6 | 🟢 |
| 2 | 2.1 — Game Object CRUD | [phase2-game-object-crud.md](implementation/phase2-game-object-crud.md) | 4 | 🟢 |
| 2 | 2.2 — System Entities | [phase2-system-entities.md](implementation/phase2-system-entities.md) | 5 | 🟢 |
| 2 | 2.3 — Bonds & Presence | [phase2-bonds-presence.md](implementation/phase2-bonds-presence.md) | 3 | 🟢 |
| 3 | 3.1 — Character Sheet Model | [phase3-character-sheet.md](implementation/phase3-character-sheet.md) | 4 | 🟢 |
| 3 | 3.2 — Traits & Magic Effects | [phase3-traits-effects.md](implementation/phase3-traits-effects.md) | 3 | 🟢 |
| 3 | 3.3 — PC Bond Mechanics | [phase3-pc-bond-mechanics.md](implementation/phase3-pc-bond-mechanics.md) | 2 | 🟢 |
| 4 | 4.1 — Event Log | [phase4-event-log.md](implementation/phase4-event-log.md) | 3 | 🟢 |
| 4 | 4.2 — GM Actions | [phase4-gm-actions.md](implementation/phase4-gm-actions.md) | 3 | 🟢 |
| 4 | 4.3 — Proposal Workflow | [phase4-proposal-workflow.md](implementation/phase4-proposal-workflow.md) | 5 | 🟢 |
| 4 | 4.4 — Feed System | [phase4-feed-system.md](implementation/phase4-feed-system.md) | 4 | 🟢 |
| 5 | 5.1 — Session Lifecycle | [phase5-session-lifecycle.md](implementation/phase5-session-lifecycle.md) | 5 | 🟢 |
| 5.5 | 5.5 — Pre-UI API Additions | [phase55-api-additions.md](implementation/phase55-api-additions.md) | 6 | 🟢 |
| 6 | 6.1 — SPA Foundation & Auth | [phase6-spa-foundation.md](implementation/phase6-spa-foundation.md) | 5 | 🟢 |
| 6 | 6.2 — Player Character & Direct Actions | [phase6-player-character.md](implementation/phase6-player-character.md) | 4 | 🔴 |
| 6 | 6.3 — Proposal System | [phase6-proposal-system.md](implementation/phase6-proposal-system.md) | 5 | 🔴 |
| 6 | 6.4 — World Browser & Feed | [phase6-world-browser.md](implementation/phase6-world-browser.md) | 4 | 🔴 |
| 6 | 6.5 — GM Tools & Session Management | [phase6-gm-tools.md](implementation/phase6-gm-tools.md) | 5 | 🔴 |
| 6 | 6.6 — Polish & Integration | [phase6-polish.md](implementation/phase6-polish.md) | 3 | 🔴 |

---

## Dependency Graph

```
game-objects (primitive)        events (primitive)        auth (primitive)
    │                               │                       │
    ├──> character-core             │                       │
    │       │                       │                       │
    │       ├──> traits             │                       │
    │       │       │               │                       │
    │       ├──> bonds ─────────────┤                       │
    │       │       │               │                       │
    │       └──> magic-system       │                       │
    │               │               │                       │
    │       ┌───────┘               │                       │
    │       ▼                       │                       │
    └──> actions <──────────────────┘───────────────────────┘
            │
            ▼
         downtime

    game-objects ──> bonds ──> events ──> feed <── auth
```

---

## Recent Changes

### 2026-03-18: Web UI UX Specification Complete

- **web-ui.md created** — full UX specification for Phase 6 Web UI. Covers technology stack (Pico CSS v2 + Alpine.js v3, no build step), authentication/onboarding flows, navigation architecture (player mobile/desktop, GM mobile/desktop), complete screen inventory (40+ screens across 3 roles), key interaction flows (3-step proposal submission, GM review queue, direct actions, progressive disclosure character sheet), component definitions, information architecture, table-flow design principles, polling strategy, and proposed API additions.
- **Spec changes propagated**:
  - `actions.md`: `narrative` now optional (nullable) for session action proposals (`use_skill`, `use_magic`, `charge_magic`). `recharge_trait` and `maintain_bond` promoted from downtime proposals to direct player actions (require narrative, cost 1 FT, immediate resolution).
  - `downtime.md`: Downtime proposal types reduced from 7 to 5. Two new direct action endpoints documented.
  - `glossary.md`: Updated Player Direct Action (5 types), Recharge Trait, and Maintain Bond entries.
  - `walkthrough.md`: Updated to reflect optional narrative on session actions and direct actions for recharge_trait/maintain_bond.
- **implementation/README.md**: Added Phase 5.5 — API Additions section tracking 6 backend stories needed before/alongside Phase 6.

### 2026-03-10: Propagation Sweep — CRUD/GM Split, Character-intermediary Rename, GM Event Types

### 2026-03-10: Downtime Interrogation Complete

- **downtime.md marked 🟢 Complete** — all 5 open questions resolved.
- **Plot overflow**: Plot can exceed 5 from any source. Clamped to 5 at Session End. Players use Find Time to convert excess during Active session.
- **Participant registration**: `POST /sessions/{id}/participants` body: `{character_id, additional_contribution?: false}`.
- **No distributed flag**: Re-adding a participant to an Active session re-distributes. GM corrects via direct actions.
- **Find Time**: Empty request body. Always 3 Plot → 1 FT.
- **Time Now defaults**: New characters default `last_session_time_now = 0`. First session `time_now` unconstrained.
- **Implications**: character-core.md Plot range description needs update (overflow behavior). Session End logic must clamp Plot.

### 2026-03-10: Propagation Sweep

- **Propagated decisions from actions.md (2026-03-10) and bonds.md (2026-03-07)** across 8 specs.
- **CRUD/GM split applied to all game object specs**: Removed write sub-resource endpoints for bonds (`POST/PATCH/DELETE /{type}/{id}/bonds`) and clocks (`POST/PATCH /groups/{id}/clocks`). PATCH narrowed to name/desc/notes only. All mechanical changes via `POST /gm/actions`. POST (creation) still accepts all fields.
- **Character-intermediary rename**: "NPC-intermediary" → "Character-intermediary" in feed.md, events.md, bonds.md. PCs are valid intermediaries.
- **GM event types cleanup**: Removed `gm.direct_action` from events.md event type catalog. GM actions reuse domain event types (e.g., `character.stress_changed`) with `actor_type: "gm"`.
- **Open questions resolved** (8 total across specs):
  - character-core.md #5: `attributes` not player-editable (GM actions only)
  - traits.md #2, #3: GM trait management via POST /gm/actions
  - magic-system.md #1: action types canonicalized to `use_magic`/`charge_magic`
  - magic-system.md #3: XP award via POST /gm/actions with `award_xp`
  - downtime.md #1: session_ids contradiction resolved (join table query, no field on Character)
  - downtime.md #4: clock adjustment via POST /gm/actions with `modify_clock`
- **Open question count reduced**: From 34 to 26 across all 🔄 specs.
- Updated: game-objects.md, character-core.md, traits.md, bonds.md, events.md, feed.md, magic-system.md, downtime.md, MASTER.md.

### 2026-03-07: Actions Interrogation — Unified Action System (renamed from Proposals)

- **proposals.md renamed to actions.md** — expanded scope to cover all state-changing operations.
- **Unified Action System**: All state changes are "actions" — typed, validated inputs that produce Event rows. Three paths: player proposals (approval gate), GM actions (direct), player direct actions (no approval).
- **Count-based slots**: Both traits and bonds use count-based models (not indexed ordinals). Items referenced by ID. `new_bond` uses `{target_type, target_id, retire_bond_id?}`. `new_trait` uses `{slot_type, template_id?, retire_trait_id?}`.
- **GM Actions endpoint**: `POST /api/v1/gm/actions` with typed payload. ~14 action types with per-type default visibility. Same event output as proposal approvals.
- **Player Direct Actions**: `find_time`, `use_effect`, `retire_effect` — no proposal needed, direct event creation.
- **Rider event FK**: `rider_event_id` column on proposals table (not inline JSON).
- **gm_overrides persistence**: All GM approval fields (actual_stat, style_bonus, effect_details, charges_added, power_boost, bond_strained) in `gm_overrides` JSON. Only `force` is transient.
- **Style bonus timing**: Applied at approval only via gm_overrides. Player-facing `calculated_effect` never includes it.
- **work_on_project narrative**: Proposal's `narrative` field IS the story entry text. On approval: `text = gm_narrative ?? narrative`.
- **API logical fields**: Request/response bodies use separate top-level fields. API layer maps to/from physical `selections` JSON column.
- **Canonical submission endpoint**: `POST /api/v1/proposals` only. Removed `POST /characters/{id}/actions/{action}` from character-core.md.
- **Modifier shape**: Submission uses bare IDs (`{core_trait_id?, role_trait_id?, bond_id?}`), calculated_effect enriches to `[{id, type, name}]`.
- Cross-spec updates: character-core.md (removed actions endpoint), traits.md (count-based slots), data-model.md (rider_event_id, field mapping).
- 3 new open questions: GM action `changes` shapes per type, validation depth for retire checks, event type catalog for GM actions.

### 2026-03-05: Proposals Interrogation — All 6 Open Questions Resolved

- Proposals status: 🔄 → 🟢 — all 6 open questions resolved.
- **Re-validation warning**: 409 Conflict + `force: true` retry. Two-step explicit mechanism when player can no longer afford costs at approval time.
- **Pending proposal edits**: Players can PATCH both pending and rejected proposals. Auto-recalculates. Pending stays pending; rejected reverts to pending.
- **Charge magic approval outcome**: GM specifies `charges_added` (integer, for charged effects) and optional `power_boost` (integer, for permanent effects). Delta-based, not replacement.
- **Bond strain flag**: `bond_strained: true` boolean in GM approval payload. Auto-applies +1 stress to the bond modifier.
- **Slot index semantics**: 0-indexed fixed ordinals. Core Traits 0–1, Role Traits 0–2, Bonds 0–7.
- **Physical field mapping**: Cross-reference to data-model.md only — no inline duplication.
- GM Approval Payload expanded with `charges_added`, `power_boost`, `bond_strained`, `force` fields.
- Updated glossary: Proposal (pending edits, 409+force, bond_strained, slot ordinals).
- **Implications**: magic-system.md may need `charge_magic` approval outcome noted. data-model.md `proposals` table may need `force` handling documented in API conventions.

### 2026-03-05: Data Model Interrogation Complete — Full Rewrite

- Data Model status: 🔄 → 🟢 — complete rewrite, all 6 open questions resolved + 9 new decisions.
- **ULID primary keys**: All tables use ULID (26-char, sortable by creation time, stored as TEXT).
- **Hybrid polymorphic strategy**: Type+id columns inline for single refs (Bond source/target, Clock association). Association tables for list refs (`event_targets`, `story_owners`).
- **Unified `slots` table**: Single table for all traits and bonds. 9 `slot_type` values: `core_trait`, `role_trait`, `pc_bond`, `npc_bond`, `group_trait`, `group_relation`, `group_holding`, `feature_trait`, `location_bond`. Nullable mechanical columns.
- **Skills/Magic Stats as JSON**: Two JSON columns on `characters` table for the fixed known sets. No separate tables.
- **Story entries as separate table**: `story_entries` with per-entry soft-delete, `updated_by`, permissions.
- **Session participants as join table**: `session_participants` with `additional_contribution` flag.
- **Starred objects as separate table**: `starred_objects` (consistent with association table pattern).
- **Rider events as separate Event rows**: `parent_event_id` FK on `events` table (self-referential).
- **Calculated effect schemas deferred**: Typed per action_type, exact schemas defined during implementation.
- **18 tables total**: users, invites, characters, groups, locations, trait_templates, slots, magic_effects, clocks, sessions, session_participants, stories, story_entries, story_owners, events, event_targets, proposals, starred_objects.
- Design Ambiguity items #2 (polymorphic refs), #3 (MVP scope), #4 (visibility cache), #5 (clock completion) marked ✅ RESOLVED.
- Updated recommended next steps.

### 2026-03-05: Character Core Propagation Update

- Character Core status: 🔄 → 🟢 — all upstream decisions propagated.
- **PC bond slots → 8**: Updated throughout (was 7). NPCs remain at 7.
- **No Trauma cap**: All 8 PC bonds can be Trauma. Stress min = 1 with 8 Traumas.
- **Session history via join table**: Removed `session_ids` from Character. Session history queried from `session_participants`.
- **No `player_id` on Character**: User.character_id references Character, not the reverse. detail_level determined by creation context.
- **Skills/magic_stats as JSON**: Noted JSON storage per data-model.md.
- Updated glossary: Members (PC bonds 8).

### 2026-03-05: Events Major Propagation Update

- Events status: 🔄 → 🟢 — major rewrite propagating upstream decisions.
- **Unified 7-level visibility**: Replaced old 6-level system. Added `silent`. Redefined `private`, `familiar`, `public`. References feed.md as authoritative.
- **Compute-on-read**: Removed cached visibility model. Compute per-request.
- **Rider events**: Added concept — separate Event rows with `parent_event_id` FK.
- **Physical schema alignment**: `actor_type`/`actor_id` columns, `event_targets` association table, matching data-model.md.
- **Unified character event types**: Removed `npc.*` prefix. NPCs use `character.*` types.
- **`silent` default visibility**: Added for system bookkeeping events.

### 2026-03-05: Auth Propagation Update

- Auth status: 🔄 → 🟢 — feed/starring features propagated.
- **Feed endpoints**: Added `/me/feed`, `/me/feed/starred`, `/me/feed/silent` to API table.
- **Starring API**: Added `/me/starred` (GET/POST/DELETE).
- **Silent feed**: GM-only access noted in permission model.
- **Unified visibility**: Updated visibility filtering decision to reference feed.md 7-level model.
- **data-model alignment**: User/Invite/starred_objects table definitions aligned.

### 2026-03-05: Bonds Propagation Update

- Bonds status: 🔄 → 🟢 — all upstream decisions propagated.
- **PC bond slots → 8**: Updated throughout (was 7). NPCs remain at 7.
- **NPC-intermediary traversal for presence**: Same algorithm as visibility. One traversal, two uses.
- **Soft-deleted exclusion**: Explicit in traversal constraints.
- **Visibility reference → feed.md**: Replaced events.md references.
- **data-model.md implications resolved**: `slots` table with `pc_bond`/`npc_bond` slot_types.

### 2026-03-04: Game Objects Fourth Interrogation — Feed, Unified Visibility, Clock Updates

- Game Objects re-interrogated — 15+ new decisions:
- **PC Bond slots → 8**: PCs get 8 bond slots (was 7). NPCs remain at 7. The 8th slot accounts for the expected party Group bond.
- **Feed concept (new spec)**: Unified Feed = merged Events + Story entries per Game Object, visibility-filtered by bond-graph proximity. A query pattern, not a stored entity.
- **Unified 7-level visibility**: Replaces the old 6-level event visibility. New levels: `silent` (GM-only audit), `gm_only`, `private` (owner-scoped), `bonded` (1-hop), `familiar` (2-hop, default for Stories), `public` (3-hop), `global`. `familiar` and `public` use NPC-intermediary bond-graph traversal.
- **NPC-intermediary traversal**: Bond-graph hops must alternate through NPCs. You can't traverse two Groups or two Locations. NPCs are the social connective tissue.
- **Story visibility**: Bond-graph driven, computed on read. Owner-based: PC-owned = private, NPC/Group/Location-owned = familiar. Mixed owners = union visibility. GM can override via `visibility_overrides`.
- **Story entry access: See = Write**: If you can see a Story, you can add entries.
- **Story creation: GM-only. Status: free-set by GM.
- **Starring**: Simple list of typed Game Object refs on User record. Starred feed = personal feed filtered to starred objects.
- **Three feed endpoints**: Per-Game Object, complete personal, starred personal. Plus GM-only silent feed.
- **Clock association → polymorphic**: Any Game Object (Character, Group, Location) via `associated_type`/`associated_id`. Replaces old `group_id`.
- **Clock completion → auto-generate resolve_clock**: System creates pending proposal when completion detected. Idempotent.
- **Clock soft cap**: GM can advance past segment count.
- **Clock completion computed**: No stored `is_completed` flag.
- **Soft-deleted excluded from bond graph**: Dead ends during traversal.
- **No cascade soft-delete**: Deleting a Game Object doesn't cascade to Clocks/entries.
- **Location list: flat parent filter only**.
- Created new spec: feed.md (Feed, unified visibility, starring)
- Updated glossary: Character (8 PC bonds), Bond (8 PC slots), Clock (polymorphic, auto-resolve), User (starred). Added: Feed, Starring, Unified Visibility Model. Replaced: Bond-Distance Visibility.
- character-core.md flagged 🔄 — PC bonds 8
- bonds.md flagged 🔄 — PC bonds 8, soft-delete exclusion, NPC-intermediary traversal
- events.md flagged 🔄 — unified 7-level visibility, silent level, reference feed.md
- auth.md flagged 🔄 — starred_game_objects, /me/feed endpoints, silent feed GM role
- data-model.md flagged 🔄 — Clock polymorphic, User starred, Story visibility_overrides

### 2026-03-04: Traits Revision — Authoritative Trait Spec

- Traits status: 🔄 → 🟢 — major revision as the authoritative trait spec for all types.
- **traits.md covers all trait types**: PC Core/Role, Group descriptive, and Location Feature. One spec, one source of truth.
- **Group traits simplified**: Replaced Culture (2) / Training (3) / Asset (5) categories with **10 flat descriptive slots**. No enforced categories. Freeform name + description.
- **Location Feature traits**: 5 interchangeable slots confirmed. All generic, no typed sub-slots.
- **Freeform descriptive traits**: Group and Location traits do NOT use the Trait Template catalog. GM types name + description directly. No reuse mechanism.
- **Simple replace lifecycle**: Group/Location traits have no Past/Retired pattern. GM overwrites or clears directly. Changes logged in event log (before/after) for audit trail.
- **Player influence via work_on_project**: Players can propose Group trait changes (for Groups they're members of) and Location Feature trait changes (for Locations they're bonded to) via `work_on_project` downtime action. No new proposal types needed.
- **Simplified slot_types**: Single `group_trait` replaces culture_trait + training_trait + asset_trait. Single `feature_trait` for Locations.
- Updated glossary: Group (10 flat trait slots), Feature Trait (interchangeable, player influence). Replaced Culture Trait + Training Trait + Asset Trait with single Group Trait entry.
- game-objects.md flagged 🔄 — Group traits simplified, reference traits.md as authoritative.
- data-model.md flagged 🔄 — simplified slot_type catalog.

### 2026-03-04: Bonds Revision — Authoritative Bond Spec

- Bonds status: 🔄 → 🟢 — major rewrite as the authoritative bond spec
- **Unified bond concept**: All relationships are Bonds. One concept, varying mechanical depth. bonds.md is the single source of truth.
- **Fully unified table**: All traits AND bonds in one table with `slot_type` discriminator. Complete catalog deferred to data-model.md.
- **Derived membership**: Group members = Characters with bonds targeting the Group. Not a stored type. PC bond to Group = membership (dual purpose).
- **Group Holdings**: New bond category (Group → Location, unlimited, descriptive). Covers territories, properties, meeting places.
- **Bond-distance presence**: Moved from game-objects.md to bonds.md (it's about bond graph traversal).
- **NPC membership same as PC**: Consistent rule — any Character bond to a Group = membership.
- game-objects.md updated: Bond section replaced with reference to bonds.md. Group bonds updated with Holdings and derived Members.
- Updated glossary: Bond (unified table reference), Members (derived), added Holdings.
- Traits spec flagged 🔄 — shares unified table, needs alignment.
- Data Model spec flagged 🔄 — complete slot_type catalog needed.

### 2026-03-04: Character Core Revision — Unified Character Model

- Character Core status: 🔄 → 🟢 — aligned with unified Game Object model
- **Unified Character entity**: PCs and NPCs are the same entity with `detail_level` field (`full` or `simplified`). NPCs = Characters without a player.
- **detail_level fixed at creation**: Auto-determined from `player_id` presence. No promotion/demotion.
- **Single API endpoint**: `GET /characters` with filters (`?detail_level=`, `?has_player=`). No separate NPC endpoints.
- **NPC bond cap**: 7 slots, same as PCs. Uniform model.
- **Player departure**: No special mechanism. GM handles narratively.
- **Removed**: References to separate NPC model, `common_locations` (replaced by bond-distance presence).
- **Added**: `attributes` JSON blob on all Characters, detail_level field, bond sub-resource endpoints.

### 2026-03-04: Game Objects Third Interrogation — Unified Game Object Model

- Game Objects spec major restructuring — unified model:
- **3 Game Object types**: Characters, Groups, Locations. These are the "things in the fiction" — nodes in the bond graph.
- **System Entities** (NOT Game Objects): Clocks, Sessions, Stories. Tracking/organizational tools that don't participate in the bond graph.
- **NPCs are Characters**: NPCs are Characters with `detail_level = simplified` (no meters, skills, magic, or Core/Role traits). Same entity, tiered detail. PCs have `detail_level = full`.
- **Unified Bond concept**: All relationships are Bonds. PC Bonds have full mechanics (stress, degradation, +1d, 7 slots). All other bonds are descriptive (active/retired only).
- **Group trait types** (descriptive only): Culture (2), Training (3), Asset (5). No charges, no dice bonuses.
- **Group bond types**: Relations (7, Group↔Group, bidirectional) and Members (unlimited, Character↔Group). Descriptive only.
- **Location Feature Traits** (5, descriptive): Physical characteristics, atmosphere, dangers, notable qualities.
- **Location Bonds** (unlimited): To any Game Object. Descriptive only.
- **Bond-Distance Presence**: Replaces curated affiliation lists and `common_locations`. Presence at a Location computed from bond graph: Commonly present (1-hop), Often present (2-hop), Sometimes present (3-hop). Works bidirectionally for Character locations. Same graph as event visibility.
- **Powerful individuals**: A Character operating at Group scale gets their own single-member Group to participate in Relations.
- Updated glossary: Game Object, Character, NPC, Group, Location, Bond, Session, Story, Clock, Deferred Narrative Resolution, Bond-Distance Visibility
- Added glossary terms: System Entity, Bond-Distance Presence, Culture Trait, Training Trait, Asset Trait, Feature Trait, Relations, Members, Detail Level
- Removed glossary term: Lightweight Bond (now just Bond)
- Character Core flagged 🔄 — NPCs are Characters, remove separate model, add detail_level
- Bonds flagged 🔄 — unified bond concept, remove Lightweight Bond, add Group/Location bond categories
- Traits flagged 🔄 — Group descriptive traits, Location Feature traits
- Data Model flagged 🔄 — unified Character table, unified Bond table, Group traits, Location traits, bond-distance presence

### 2026-03-04: MVP Scope Interrogation Complete

- MVP Scope status: 🟡 → 🟢 — all 4 open questions resolved + 9 new decisions
- **Single MVP, phased build**: No MVP 0/1 split. Full system is the target. 6-phase build order: Foundation → World → Characters → Actions → Sessions → Web UI.
- **Rider events**: GM can optionally attach a bundled direct-action event when approving a proposal. Fires atomically. Used for side effects and clock resolution.
- **`resolve_clock` proposal type**: System auto-generates when a clock completes. Pre-linked to clock + containing game objects. GM fills narrative + optional rider event.
- **`resolve_trauma` proposal type**: System auto-generates when character Stress hits effective max. GM fills in which bond becomes Trauma and the trauma details. Parallels resolve_clock pattern.
- **12 action types total**: 3 session + 7 downtime + 2 system proposals.
- **Typed `calculated_effect`**: Each action type has a known schema for its pre-computed result. GM can override any field.
- **Player-written narratives**: Players write narrative on submission. GM usually just approves. Can edit or reject with note.
- **Simplified story entries**: Simple CRUD with soft-delete. `updated_at` + `updated_by` fields, no full audit trail.
- **Compute-on-read visibility**: No bond-distance cache. Compute per-request. Add cache only if slow.
- **Full test coverage**: Integration-heavy (pytest + httpx). Fixture DB with canonical seed data. Fresh DB per test.
- **Auth phasing**: Setup + middleware in Phase 1. Invites deferred to Phase 5. Seed test users.
- **Web UI as Phase 6**: API-first. Swagger UI during development. Basic mobile-friendly frontend for table use.
- Added glossary terms: Resolve Clock, Rider Event, Calculated Effect
- Updated glossary: Bond-Distance Visibility (compute-on-read, no cache)
- Proposals spec flagged 🔄 — needs rider events, typed calculated_effect, resolve_clock, player narratives
- Events spec flagged 🔄 — needs compute-on-read visibility, rider event concept
- Game Objects spec flagged 🔄 — story entry simplification, clock completion auto-proposal

### 2026-03-04: Spec Status Audit & Design Ambiguity Analysis

- All 9 domain specs confirmed 🟢. Architecture specs: overview 🟡, mvp-scope 🟡, data-model 🔄.
- **Terminology fix**: "Heal Bond Stress" → "Maintain Bond" aligned in bonds.md (4 occurrences).
- **Design principle added**: "Deferred Narrative Resolution" added to overview.md as a named architectural principle.
- **Ambiguity analysis**: Identified 3 blocking issues (no outcome framework, polymorphic refs, undefined MVP scope), 5 friction points, 3 cosmetic items. Added to MASTER.md.
- **Recommended next steps**: MVP scope interrogation (priority 1), data-model revision (priority 1), proposals approval UX interrogation (priority 2).
- Overview 🔄 flag cleared (Deferred Narrative Resolution added). Bonds 🔄 flag cleared (terminology aligned).

### 2026-03-04: Auth Interrogation Complete

- Auth status: 🟡 → 🟢 — all 8 open questions resolved + 6 additional decisions (14 total)
- **GM as privileged player**: GM is not a distinct entity — a player with unlimited privileges. Has display name (shown as "GM [name]"). Can optionally own and play a character using the same proposal workflow.
- **Token format**: Random 64-char hex string (`secrets.token_hex(32)`). No expiry. SHA-256 hashed server-side.
- **First-run setup**: One-time `POST /api/v1/setup` — creates GM account, returns token, locks permanently. No guard (trusted network).
- **Single-use invites**: Each invite pre-linked to a character. One invite = one character = one player account.
- **1:1 player-character mapping**: Strictly one player per character. New character requires new invite (old account deactivated).
- **GM token regen**: GM can force-regenerate any player's token (kick/reset).
- **No spectators for MVP**: Two roles only.
- **Player profile**: Display name only.
- **Event visibility**: Server-side filtering per bond-distance. GM sees all. GM can permanently override per-event visibility.
- **Identity endpoint**: `GET /api/v1/me` for client bootstrap.
- **GM self-play**: Same proposal workflow — must explicitly approve own proposals.
- Events spec flagged 🔄 — actor.type should handle GM as player subtype, per-event visibility override
- Data Model spec flagged 🔄 — needs User model and Invite model
- Proposals spec note: GM uses same workflow for own character, no special-casing

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
_2026-03-18 — Epic 6.1 (SPA Foundation & Auth) complete: all 5 stories done. Phase 6 Web UI implementation has begun. web-ui.md verified against implementation with notes on static file path, hash router pattern-matching, Alpine store isGm method, polling resume behavior, and sessionStorage invite code handoff. Previous: Epic 5.5 (Pre-UI API Additions) complete: all 6 stories done._
