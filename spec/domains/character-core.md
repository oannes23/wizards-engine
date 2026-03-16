# Character Core — Domain Specification

**Status**: 🟢 Complete
**Last interrogated**: 2026-03-12
**Last verified**: —
**Depends on**: [game-objects](game-objects.md), [auth](auth.md)
**Depended on by**: [traits](traits.md), [bonds](bonds.md), [magic-system](magic-system.md), [actions](actions.md)

---

## Overview

Defines the **Character** Game Object — the unified entity representing all beings in the fiction, both player characters (PCs) and non-player characters (NPCs). Characters have a `detail_level` that determines which fields are active:

- **Full (PC)**: A Character linked to a User account. Has the complete character sheet: resource meters, skills, magic, traits, and **8 mechanical bond slots**. Created by the player during invite redemption.
- **Simplified (NPC)**: A Character with no User account linked. Has name, description, notes, attributes blob, and **7 descriptive bond slots**. No meters, skills, magic, or Core/Role traits. Created by the GM via `POST /api/v1/characters`.

The `detail_level` is fixed at creation. Two separate creation paths enforce this: invite redemption → `full`; GM direct creation → `simplified`.

Traits, Bonds, and detailed Magic mechanics are broken out into their own domain specs.

---

## Core Concepts

### Character Identity

All Characters (PCs and NPCs) share:
- Standard Game Object fields: `id`, `name`, `description`, `is_deleted`, `created_at`, `updated_at`
- `notes`: freeform text
- `attributes`: JSON blob — freeform GM notes, NPC mechanical info, or anything the GM wants to track. No enforced schema.
- `detail_level`: `full` or `simplified` — fixed at creation
- Bond slots targeting any Game Object (Character, Group, or Location) — **8 for full (PC)**, **7 for simplified (NPC)**

### Detail Level

| Field | Full (PC) | Simplified (NPC) |
|-------|-----------|-------------------|
| name, description, notes | Yes | Yes |
| attributes (JSON blob) | Yes | Yes |
| Bonds (8 slots PC / 7 NPC) | Mechanical (stress (conceptually "bond charges"), degradation, +1d) | Descriptive only (active/retired) |
| Core Traits (2 slots) | Yes (charges, +1d) | No |
| Role Traits (3 slots) | Yes (charges, +1d) | No |
| Stress (0–9) | Yes | No |
| Free Time (0–20) | Yes | No |
| Plot (0–5) | Yes | No |
| Gnosis (0–23) | Yes | No |
| Skills (8, levels 0–3) | Yes | No |
| Magic Stats (5, levels 0–5) | Yes | No |
| Magic Effects (cap 9) | Yes | No |
| last_session_time_now | Yes | No |

**Design intent**: NPCs are mechanically lightweight but participate in the bond graph as first-class entities. Their bonds define who they know, where they go, and what groups they belong to. NPC mechanical info (if needed) lives in the freeform `attributes` blob.

### Character Ownership

- **Full (PC)**: Owned by a specific player (1:1 mapping). The owner can read their full sheet, edit name/description/notes directly, and submit proposals for mechanically significant changes.
- **Simplified (NPC)**: No player owner. Controlled exclusively by the GM. Players have read-only access.

### Resource Meters (Full Characters Only)

**Stress**
- Type: Meter
- Range: 0–9 (effective max decreases by 1 per Trauma; computed as `9 - count(trauma_bonds)`)
- With 8 bond slots, max possible Traumas = 8 (Stress max drops to 1). No cap on Trauma count.
- Tracks accumulated harm and pressure
- At max Stress: the system auto-generates a `resolve_trauma` proposal (analogous to `resolve_clock` for clock completion). The GM fills in which bond becomes the trauma and the trauma description. On approval, the system retires the chosen bond, creates a trauma bond in its place, and resets Stress to 0. This is a **compound consequence** — all mutations (stress delta, bond retirement, trauma creation, stress reset) are recorded in a single event. See [events.md](events.md) Meter Boundary Patterns.
- Trauma replaces a Bond (sets `is_trauma` flag on the Bond, clears target/level, sets trauma name/description). See [bonds.md](bonds.md).
- If all 8 Bonds are already Trauma and Stress hits max again, the GM handles narratively (no mechanical rule).
- Healed via **Rest** downtime action: **3 base + up to +3 from trait/bond modifiers** (standard stacking: 1 Core Trait +1, 1 Role Trait +1, 1 Bond +1). Costs 1 FT. See [actions.md](actions.md).

**Free Time**
- Type: Resource meter
- Range: 0–20
- Carries over between sessions; capped at 20 (excess lost)
- **Gained at session start**: `session.time_now - character.last_session_time_now` (Time Now delta). See [downtime.md](downtime.md).
- **Also gained via Find Time**: 3 Plot → 1 FT (direct player action, no proposal needed). See [downtime.md](downtime.md).
- Spent on downtime activities between sessions (all downtime actions cost 1 FT)

**Plot**
- Type: Resource meter
- Nominal range: 0–5, but can temporarily exceed 5 from any source (session income, GM awards). **Clamped to 5 at Session End** — players have the Active session window to convert excess via Find Time.
- Income: **+1 per session** participated, **+2 if Additional Contribution** flagged. GM can also award bonus Plot.
- Spending: each Plot spent = **guaranteed 6** before rolling (not an extra die — a guaranteed result). See [actions.md](actions.md).
- Also convertible to FT via **Find Time** (3 Plot → 1 FT). See [downtime.md](downtime.md).
- No cap on Plot spend per proposal — players can stack freely

**Gnosis**
- Type: Resource meter
- Range: 0–23
- Primary magical resource, spent as sacrifice in Magic Actions and Charge Actions
- Regained via **Regain Gnosis** downtime action: **3 base + lowest Magic Stat level + up to +3 from trait/bond modifiers** (standard stacking). Costs 1 FT. See [actions.md](actions.md).
- The unusual max of 23 is a deliberate lore-driven design choice
- See [magic-system.md](magic-system.md) for sacrifice conversion table and full mechanics

### Skills (Full Characters Only)

Exactly 8 skills, **hardcoded in code** — the same list for all full Characters:

> Awareness, Composure, Influence, Finesse, Speed, Power, Knowledge, Technology

- All full Characters have all 8 skills at different levels (0–3)
- Stored as a JSON column on Character: `{awareness: 2, composure: 1, ...}`. See [data-model.md](../architecture/data-model.md).
- Skill level = base dice pool size for related actions
- Skill levels change during **downtime only** (costs Free Time). See [downtime.md](downtime.md).
- No "gaining" or "losing" skills — every full Character always has the full set

### Magic Stats (Full Characters Only)

The five schools/aspects of magic:

> **Being, Wyrding, Summoning, Enchanting, Dreaming**

Each has:
- `level`: 0–5 — determines the base dice pool for magic actions using that stat
- `xp`: meter, flat 5 XP per level — tracks progress toward the next level. **XP resets to 0 on level-up; excess does not carry over.**

Stored as a JSON column on Character: `{being: {level: 0, xp: 3}, wyrding: {...}, ...}`. See [data-model.md](../architecture/data-model.md).

All Magic Stats start at level 0 for new characters. **XP is awarded by the GM directly** — no automatic gain from magic use or downtime study. GM controls all Magic Stat progression.

See [magic-system.md](magic-system.md) for full mechanics (dice pools, sacrifice, actions).

### Magic Effects (Full Characters Only)

Magic Effects are outcomes of Magic Actions, created by the GM on the character's sheet. Three types:

- **Instant**: One-time effects, not tracked on the sheet (logged as events). Don't count toward cap.
- **Charged**: Persistent on sheet. Fields: `name`, `description`, `power_level` (1–5), `charges_current`, `charges_max`. Player uses directly (no proposal needed, costs 1 charge).
- **Permanent**: Always-active, no charge meter. Fields: `name`, `description`, `power_level` (1–5). Created primarily via Enchanting.

**Effect cap**: Max **9 active effects** (charged + permanent; instants don't count). Players can **self-retire** effects directly (no proposal needed — frees cap space). Retired effects move to Past.

See [magic-system.md](magic-system.md) for creation mechanics, Charge Actions, and sacrifice system.

### Notes

- Freeform text field (available on all Characters)
- Used for inventory, narrative notes, personal reminders, anything the player/GM wants to track
- Players can edit their own notes directly (no proposal needed)
- GM can edit any Character's notes

---

## Decisions

### Unified Character Entity

- **Decision**: PCs and NPCs are the same entity type (Character) with a `detail_level` field: `full` (PC) or `simplified` (NPC). NPCs are Characters without a player login assigned.
- **Rationale**: In the fiction, PCs and NPCs are the same kind of thing — beings in the world. The system should reflect this. The detail difference is about player interaction, not ontology.
- **Implications**: Single Character table with optional fields. NPCs participate in the bond graph identically. One GET endpoint with filters.

### Detail Level Fixed at Creation

- **Decision**: `detail_level` is fixed at creation and never changes. Determined by creation path: invite redemption → `full`; GM direct creation → `simplified`. Character does not store a `player_id` — the User record references the Character via `User.character_id`.
- **Rationale**: Keeps the model simple. Converting between detail levels would require complex field migration (adding/removing meters, skills, magic). If a player leaves, the GM handles it outside the system.
- **Implications**: No promotion/demotion API. To convert an NPC to a PC, create a new full Character and transfer relevant data manually.

### Two Creation Paths

- **Decision**: NPCs and PCs are created through separate endpoints. NPCs: `POST /api/v1/characters` (GM only, always `simplified`). PCs: created atomically during invite redemption via `POST /api/v1/game/join` (player provides character name, always `full`). No `detail_level` field in any request body — the path determines the type.
- **Rationale**: Eliminates ambiguity about how detail_level is determined. The creation context IS the endpoint. NPCs are world-building (GM); PCs are player onboarding (invite flow).
- **Implications**: `POST /api/v1/characters` is NPC-only. The invite endpoint in auth handles PC creation. See [auth.md](auth.md) for invite flow details.

### NPC Creation — Name Only Required

- **Decision**: Creating an NPC requires only `name`. Description, notes, and attributes are all optional.
- **Rationale**: Minimal friction for world-building. The GM can flesh out NPCs incrementally.
- **Implications**: `POST /api/v1/characters` accepts `{name, description?, notes?, attributes?}`.

### PC Creation — Sensible Defaults

- **Decision**: When a PC is created (during invite redemption), only `name` is required from the player. All mechanical fields default to 0: stress=0, free_time=0, plot=0, gnosis=0, all 8 skills at level 0, all 5 magic stats at level 0 / xp 0. The GM customizes initial values afterward via GM actions.
- **Rationale**: Players shouldn't need to understand the mechanical system to create their character. The GM sets up the character sheet after creation.
- **Implications**: No meter/skill fields in the redemption payload. GM uses `POST /api/v1/gm/actions` with `modify_character` to set initial values.

### New PC First Session — Delta from Default

- **Decision**: New full Characters default `last_session_time_now = 0`. On first session participation, the standard FT formula applies: `session.time_now - 0 = session.time_now` FT gained (capped at 20). The GM can override `last_session_time_now` at creation for mid-campaign character introductions.
- **Rationale**: A sensible starting grant — a character joining session 1 with `time_now = 5` gets 5 FT. The GM controls pacing via their choice of Time Now values and can override the default for late-joining characters.
- **Implications**: No special-case logic for first session. Standard FT formula handles it. GM uses `modify_character` direct action to set `last_session_time_now` higher if the default grant would be too large.

### Player Departure — GM Handles It

- **Decision**: No special system mechanism for player departure. GM decides: soft-delete the Character, leave it as-is (full detail but no active player), or create a new invite for a replacement player.
- **Rationale**: With 4–6 players, this is a rare event best handled narratively. Over-engineering a workflow for it adds complexity with minimal value.
- **Implications**: A full Character can exist without an active player account. The system doesn't enforce that every full Character has an active player.

### Bond Slot Counts

- **Decision**: PCs have **8 bond slots** (mechanical: stress (conceptually "bond charges"), degradation, +1d). NPCs have **7 bond slots** (descriptive only). The 8th PC slot accounts for the expected party Group bond.
- **Rationale**: PCs need one more slot than NPCs because one slot is typically used for the party Group membership bond. NPCs don't need this expectation baked in.
- **Implications**: PC bonds use `slot_type = pc_bond` (8 max). NPC bonds use `slot_type = npc_bond` (7 max). See [data-model.md](../architecture/data-model.md).

### Stress Range and Consequences

- **Decision**: Stress ranges 0–9. Effective max decreases by 1 per Trauma (computed: `9 - count(trauma bonds)`). When Stress hits max, the system auto-generates a `resolve_trauma` proposal. The GM resolves it via the proposal workflow (selecting which bond becomes the trauma and filling in the trauma description). On approval, the chosen bond is retired as a trauma and Stress resets to 0.
- **Rationale**: 0–9 gives enough granularity without excess bookkeeping. Trauma as the max-stress consequence creates meaningful narrative stakes. Resetting to 0 gives the character breathing room after the consequence fires. Using the proposal workflow keeps the GM in control without requiring out-of-band negotiation.
- **Implications**: Trauma mechanic lives on the Bond model (`is_trauma` flag). Stress max is a computed value, not stored.

### Trauma Mechanic

- **Decision**: Trauma replaces a Bond — sets `is_trauma` flag, clears target, sets trauma name/description. Each Trauma reduces Stress max by 1. Trauma is fixable via GM direct action.
- **Rationale**: Tying Trauma to Bonds creates a meaningful cost (you lose a relationship) and keeps the model simple (no separate Trauma entity).
- **Implications**: Bond model needs `is_trauma` flag plus trauma-specific fields. See [bonds.md](bonds.md).

### No Trauma Cap

- **Decision**: All 8 PC bond slots can become Trauma. No cap. Stress max can drop to 1 (with 8 Traumas). If all bonds are Trauma and Stress hits max again, GM handles narratively.
- **Rationale**: This is an extreme edge case that should feel like a dramatic narrative moment. Capping would add artificial complexity.
- **Implications**: Stress effective max formula: `9 - count(trauma_bonds)`, minimum 1 with 8 Traumas. No code needed beyond normal Stress tracking for the max-trauma edge case.

### Plot Income and Spending

- **Decision**: +1 Plot per session participated, +2 if Additional Contribution flagged. GM can also award bonus Plot. Plot is spent as **guaranteed 6s** before rolling. Also convertible to FT via Find Time (3 Plot → 1 FT). No cap on Plot spend per proposal.
- **Rationale**: Automatic session income ensures steady accumulation. Guaranteed 6s make Plot feel decisive. Uncapped spending lets players go big on moments that matter.
- **Implications**: Proposal resolution needs to account for Plot spend. Find Time is a direct player action.

### Skill Model

- **Decision**: Exactly 8 skills hardcoded in code. Same list for all full Characters. Levels 0–3. Change during downtime only. Stored as a JSON column on Character (`{awareness: 2, composure: 1, ...}`).
- **Rationale**: A shared skill list simplifies the model (no skill CRUD). JSON storage is natural for a fixed known set. Downtime-only growth keeps skill changes deliberate and paced.
- **Implications**: Skill list and validation defined in code. No separate database table.

### Skill Level Cap

- **Decision**: Skills are capped at level 3.
- **Rationale**: Keeps the dice pool bounded. Level 3 represents mastery.
- **Implications**: Skill advancement beyond 3 is not possible through normal means.

### Player Direct-Edit Fields

- **Decision**: Players can directly edit `name`, `description`, and `notes` on their own character without a proposal. All mechanical fields (including `attributes`) require proposals or GM action.
- **Rationale**: Name, description, and notes are narrative bookkeeping with no mechanical impact. `attributes` is a GM-managed blob for tracking mechanical info and should not be player-editable.
- **Implications**: PATCH endpoint accepts `name`, `description`, `notes` — owner-check authorization. `attributes` changes via `POST /api/v1/gm/actions` with `modify_character`.

### Character Fields

- **Decision**: All Characters: `name`, `description`, `notes`, `attributes` (JSON blob), `detail_level`. Full Characters additionally: `last_session_time_now`, plus resource meters, `skills` (JSON), `magic_stats` (JSON), magic effects, traits, and bonds (with mechanical depth). Plus standard Game Object fields. Session history is queried from the `session_participants` join table (not stored on Character).
- **Rationale**: Keep the model lean. `attributes` provides a flexible extension point. `last_session_time_now` tracks FT delta. Session history via join table avoids denormalization.
- **Implications**: API returns null/omitted fields for simplified Characters. No image handling needed.

### Sheet API

- **Decision**: Single endpoint, full sheet — `GET /characters/{id}` returns everything relevant to the Character's detail level, plus computed/derived values, plus bond-distance locations, plus session history (as ID list), plus both active and past/retired traits and bonds (grouped separately).
- **Rationale**: The sheet is always viewed as a whole. A single endpoint avoids multiple round-trips. Past items are part of the character's story.
- **Implications**: Response payload varies by detail_level. Full Characters return a large but bounded payload.

**Computed values included in response (Full Characters only):**

| Field | Formula |
|-------|---------|
| `effective_stress_max` | `9 - count(trauma_bonds)` |
| `active_magic_effects_count` | Count of charged + permanent effects (vs cap of 9) |
| `active_trait_count` | Filled Core + Role Trait slots (vs total 5: 2 Core + 3 Role) |
| `active_bond_count` | Filled Bond slots (vs total 8 for PCs, 7 for NPCs) |
| Per-bond: `effective_bond_stress_max` | `5 - stress_degradations` |

**Bond-distance locations (all Characters):**

```json
{
  "locations": {
    "common": [{"id": "...", "name": "..."}],
    "familiar": [{"id": "...", "name": "..."}],
    "known": [{"id": "...", "name": "..."}]
  }
}
```

Nested by distance tier: common (1-hop), familiar (2-hop), known (3-hop).

**Session history (Full Characters only):**

```json
{
  "session_ids": ["session_ulid_1", "session_ulid_2", ...]
}
```

ID list only. Client fetches session details separately if needed.

**Traits and bonds grouping:**

Active and past/retired items are returned grouped separately:

```json
{
  "traits": {
    "active": [...],
    "past": [...]
  },
  "bonds": {
    "active": [...],
    "past": [...]
  }
}
```

### Character Creation

- **Decision**: Two separate creation paths. NPCs: `POST /api/v1/characters` (GM only, `name` required, all else optional). PCs: created during invite redemption via `POST /api/v1/game/join` (player provides character name + display name). All mechanical fields default to 0. GM customizes initial values afterward via GM actions.
- **Rationale**: Separating the paths eliminates ambiguity. Players create their own character identity; the GM sets up the mechanical sheet.
- **Implications**: No separate PC creation endpoint. The invite flow in auth.md handles PC creation atomically with account creation. `POST /api/v1/characters` is NPC-only.

### Character Lifecycle

- **Decision**: Characters are always active. No inactive/retired/dead status flag. Retirement or death is purely narrative — the GM simply stops using the character.
- **Rationale**: With 4–6 players, character lifecycle management is unnecessary complexity.
- **Implications**: No soft-delete or archive mechanism needed beyond the standard Game Object `is_deleted`.

### Session History via Join Table

- **Decision**: Character session history is queried from the `session_participants` join table, not stored as a denormalized list on Character. No `session_ids` field on Character. Returned as an ID list in the character detail response.
- **Rationale**: The join table already exists for tracking participants and contribution flags. Querying it is simple and avoids sync issues.
- **Implications**: Character sheet API includes session history derived from `session_participants` as a list of session IDs.

---

## API Endpoints

### Characters — NPC Creation (GM Only)
- `POST /api/v1/characters` — create an NPC (always `simplified`). Required: `name`. Optional: `description`, `notes`, `attributes`.

### Characters — Listing and Detail
- `GET /api/v1/characters` — list all Characters. Filters: `?detail_level=full|simplified`, `?has_player=true|false`, `?include_deleted=true` (default excludes deleted), `?name=` (partial match). Pagination: `?after=<ulid>&limit=N` (ULID cursor, default 50, max 100). Sorted by ULID order (creation time, newest first).
- `GET /api/v1/characters/{id}` — get Character detail (full sheet for PCs, simplified view for NPCs; includes bond-distance locations, session history as ID list, active + past traits/bonds grouped separately)

### Characters — Updates and Deletion
- `PATCH /api/v1/characters/{id}` — update name, description, notes (GM can edit any; owner can edit their own). All mechanical fields (meters, skills, attributes, bonds, traits, effects) via `POST /api/v1/gm/actions`.
- `DELETE /api/v1/characters/{id}` — soft delete (GM only)

### Characters — Actions
- Character proposals: submitted via `POST /api/v1/proposals` with `character_id` in the body (see [actions.md](actions.md))
- Bond/trait/effect management: via `POST /api/v1/gm/actions` (see [actions.md](actions.md))

### PC Creation (via Invite Flow)
- `POST /api/v1/game/join` — redeem invite code, create User account + full Character atomically. See [auth.md](auth.md).

---

## Implications for Other Specs

| Spec | Implication |
|------|-------------|
| [auth](auth.md) | **Major change**: Invite flow now creates the Character atomically with the User account. Invites are bare (no pre-linked character). `POST /api/v1/game/join` accepts character name + display name + invite code. `invites` table no longer needs `character_id` at creation — it's set on redemption. |
| [traits](traits.md) | Core and Role Traits attach to full Characters only (2 Core + 3 Role slots). Charge mechanic (0–5). Trait invocation on proposals (+1d, costs 1 charge). NPCs have no trait slots. |
| [bonds](bonds.md) | PCs have 8 Bond slots (mechanical: stress (conceptually "bond charges"), degradation, +1d). NPCs have 7 (descriptive only). Bond model has `is_trauma` flag. Max 8 Traumas (Stress min = 1). |
| [magic-system](magic-system.md) | Gnosis, Magic Stats, and Magic Effects attach to full Characters only. Stress sacrifice in Magic Actions can trigger Trauma. |
| [actions](actions.md) | Only full Characters submit proposals via `POST /proposals`. Plot spend = guaranteed 6s. Rest heals 3+mods Stress. All downtime actions cost 1 FT. GM actions via `POST /gm/actions`. |
| [downtime](downtime.md) | FT gained via Time Now delta (full Characters only). New PCs get 0 FT on first session (last_session_time_now set to session.time_now). Plot +1/+2 per session. Find Time (3 Plot → 1 FT). Skill growth via work_on_project. |
| [events](events.md) | Character state changes are logged as events. One event per approval. NPC bond changes also logged. |
| [game-objects](game-objects.md) | Characters are one of three Game Object types. Unified model with detail_level. Bond-distance presence computed from Character bonds. |
| [data-model](../architecture/data-model.md) | `invites` table: `character_id` nullable (set on redemption, not creation). Characters table unchanged. |

---

## Open Questions

_None — all open questions resolved during 2026-03-12 interrogation._

---

_Last updated: 2026-03-15 (trauma now auto-generates resolve_trauma proposal via workflow — GM fills in bond and description, system retires bond and resets Stress on approval; XP resets to 0 on Magic Stat level-up, no carry-over; added "bond charges" parenthetical to bond stress references)_
