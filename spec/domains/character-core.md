# Character Core — Domain Specification

**Status**: 🟢 Complete
**Last interrogated**: 2026-02-26
**Last verified**: —
**Depends on**: [game-objects](game-objects.md)
**Depended on by**: [traits](traits.md), [bonds](bonds.md), [magic-system](magic-system.md), [proposals](proposals.md)

---

## Overview

Defines the base player character (PC) sheet — the central entity players interact with. Covers the character's resource meters (Stress, Free Time, Plot), Skills, Notes, and the overall sheet structure. Traits, Bonds, and Magic are broken out into their own domain specs.

---

## Core Concepts

### Character Ownership

Each Character (PC) is owned by a specific player. The owner can read their full sheet, edit notes directly, and submit proposals for mechanically significant changes.

### Resource Meters

Characters have three resource meters:

**Stress**
- Type: Meter
- Range: 0–9 (effective max decreases by 1 per Trauma; computed as `9 - count(trauma bonds)`)
- Tracks accumulated harm and pressure
- At max Stress: character gains a **Trauma** — negotiated between GM and player. Stress resets to 0 after Trauma is gained.
- Trauma replaces a Bond (sets `is_trauma` flag on the Bond, clears target/level, sets trauma name/description). See [bonds.md](bonds.md).
- If all Bonds are already Trauma and Stress hits max again, the GM handles narratively (no mechanical rule).
- Stress is healed via **downtime activity** (costs Free Time). See [downtime.md](downtime.md).

**Free Time**
- Type: Resource meter
- Range: 0–20
- Spent on downtime activities between sessions

**Plot**
- Type: Resource meter
- Range: 0–5
- 1 Plot gained per session automatically, plus GM bonus awards
- Spent to **upgrade outcome tier** on proposals (partial → full success, increased effect magnitude)
- No cap on Plot spend per proposal — players can stack freely

### Skills

Exactly 8 skills, **hardcoded in code** — the same list for all characters:

> Awareness, Composure, Influence, Finesse, Speed, Power, Knowledge, Technology

- All characters have all 8 skills at different levels (0–3)
- Skill level = base dice pool size for related actions
- Skill levels change during **downtime only** (costs Free Time). See [downtime.md](downtime.md).
- No "gaining" or "losing" skills — every character always has the full set

### Notes

- Freeform text field
- Used for inventory, narrative notes, personal reminders, anything the player wants to track
- Players can edit their own notes directly (no proposal needed)

---

## Decisions

### Stress Range and Consequences

- **Decision**: Stress ranges 0–9. Effective max decreases by 1 per Trauma (computed: `9 - count(trauma bonds)`). When Stress hits max, the character gains a Trauma and Stress resets to 0.
- **Rationale**: 0–9 gives enough granularity without excess bookkeeping. Trauma as the max-stress consequence creates meaningful narrative stakes. Resetting to 0 gives the character breathing room after the consequence fires.
- **Implications**: Trauma mechanic lives on the Bond model (`is_trauma` flag). Bonds spec needs revision to accommodate. Stress max is a computed value, not stored.

### Trauma Mechanic

- **Decision**: Trauma replaces a Bond — sets `is_trauma` flag, clears target/level, sets trauma name/description. Each Trauma reduces Stress max by 1. Trauma is fixable via GM direct action (converts Bond back, restores stress max).
- **Rationale**: Tying Trauma to Bonds creates a meaningful cost (you lose a relationship) and keeps the model simple (no separate Trauma entity).
- **Implications**: Bond model needs `is_trauma` flag plus trauma-specific fields. See [bonds.md](bonds.md).

### Plot Income and Spending

- **Decision**: 1 Plot gained per session automatically, plus GM bonus awards. Plot is spent to upgrade outcome tier on proposals (partial → full success, increased effect magnitude). No cap on Plot spend per proposal.
- **Rationale**: Automatic session income ensures steady accumulation. Uncapped spending lets players go big on moments that matter to them.
- **Implications**: Proposal resolution needs to account for Plot spend. See [proposals.md](proposals.md).

### Skill Model

- **Decision**: Exactly 8 skills hardcoded in code: Awareness, Composure, Influence, Finesse, Speed, Power, Knowledge, Technology. Same list for all characters. All characters have all skills at levels 0–3. Skill levels change during downtime only (costs Free Time).
- **Rationale**: A shared skill list simplifies the model (no skill CRUD). Downtime-only growth keeps skill changes deliberate and paced. 8 skills covers the needed design space without bloat.
- **Implications**: Skill list is defined in code, not in DB. Downtime activities include skill training. See [downtime.md](downtime.md).

### Skill Level Cap

- **Decision**: Skills are capped at level 3.
- **Rationale**: Keeps the dice pool bounded. Level 3 represents mastery.
- **Implications**: Skill advancement beyond 3 is not possible through normal means.

### Player Direct-Edit Fields

- **Decision**: Players can directly edit `notes` and `description` on their own character without a proposal. All mechanical fields (meters, skills, traits, bonds) require proposals or GM action.
- **Rationale**: Notes and description are narrative bookkeeping with no mechanical impact. Requiring proposals for them would create unnecessary friction.
- **Implications**: The PATCH endpoint needs owner-check authorization for notes/description. All other fields go through the proposal workflow or GM direct action.

### Character Fields

- **Decision**: Minimal character fields: `name`, `description`, `notes` (plus standard game object fields from [game-objects.md](game-objects.md)). No concept or portrait fields.
- **Rationale**: Keep the model lean. Flavor information lives in description and notes.
- **Implications**: No image handling needed at the API level.

### Character Creation

- **Decision**: GM creates characters — enters name, description, initial skill levels, initial meter values (Stress, Free Time, Plot), and assigns to a player. Traits and Bonds are set up separately per their domain specs.
- **Rationale**: GM controls campaign setup. GM-set initial meters allow flexibility (e.g., starting a campaign with some Free Time). Separating character creation from trait/bond setup keeps the workflow modular.
- **Implications**: POST endpoint is GM-only. Player assignment and all initial values are part of the creation payload.

### Sheet API

- **Decision**: Single endpoint, full sheet — `GET /characters/{id}` returns everything (meters, skills, traits, bonds, magic stats, magic effects) plus computed/derived values (e.g., effective Stress max).
- **Rationale**: The sheet is always viewed as a whole. A single endpoint avoids multiple round-trips and simplifies the frontend. Including computed values saves the client from duplicating game logic.
- **Implications**: The response payload is large but bounded. No partial-sheet endpoints needed. Response includes both raw stored values and computed values.

### Character Lifecycle

- **Decision**: Characters are always active. No inactive/retired/dead status flag. Retirement or death is purely narrative — the GM simply stops using the character.
- **Rationale**: With 4–6 players, character lifecycle management is unnecessary complexity. The GM can handle it narratively.
- **Implications**: No soft-delete or archive mechanism needed. Character list always returns all characters.

### Max Trauma Edge Case

- **Decision**: If all Bonds are already Trauma and a character hits max Stress again, the GM handles it narratively (retirement, death, etc.). No additional mechanical rule.
- **Rationale**: This is an extreme edge case that should feel like a dramatic narrative moment, not a mechanical formula.
- **Implications**: No code needed to handle this case beyond normal Stress tracking.

### Initial Meter Values

- **Decision**: GM sets all initial meter values (Stress, Free Time, Plot) as part of character creation. No hardcoded defaults.
- **Rationale**: Gives the GM flexibility to start characters in different states depending on the campaign's needs.
- **Implications**: All meter fields are required in the character creation payload.

---

## API Endpoints

### Characters
- `GET /api/v1/characters` — list all PCs
- `GET /api/v1/characters/{id}` — get full character sheet
- `POST /api/v1/characters` — create new PC
- `PATCH /api/v1/characters/{id}` — update character fields (GM or owner for notes)
- `POST /api/v1/characters/{id}/actions/{action}` — submit a character action as proposal

---

## Implications for Other Specs

| Spec | Implication |
|------|-------------|
| [traits](traits.md) | Core and Role Traits attach to Characters |
| [bonds](bonds.md) | 🔄 Bond model needs `is_trauma` flag. Trauma replaces Bond target/level with trauma name/description. Trauma reduces Stress max. |
| [magic-system](magic-system.md) | Gnosis, Magic Stats, and Magic Effects attach to Characters |
| [proposals](proposals.md) | Plot spend upgrades outcome tier. No cap per proposal. Proposals are submitted by Characters; resource meters change via approved proposals. |
| [downtime](downtime.md) | 🔄 Stress healing + skill level growth are downtime activities costing Free Time. Free Time is spent during downtime. |
| [events](events.md) | Character state changes are logged as events |

---

_Last updated: 2026-02-26_
