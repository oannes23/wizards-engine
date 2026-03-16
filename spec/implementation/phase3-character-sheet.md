# Epic 3.1 — Character Sheet Model

**Phase**: 3 — Characters
**Depends on**: Epic 2.3 (Bonds & Presence)
**Blocks**: Epic 3.2 (Traits & Effects), Epic 3.3 (PC Bond Mechanics)
**Parallel with**: None (blocks 3.2 and 3.3)

---

## Overview

Complete the character sheet model: full character creation via invite flow, invite management, GM self-play character, and the enhanced character detail response with all mechanical fields, computed values, and session history. This Epic bridges auth (invites) and the character system.

---

## Stories

| Story | Status | Completed |
|-------|--------|-----------|
| 3.1.1 — Full Character Creation (Invite Flow) | 🟢 Complete | 2026-03-16 |
| 3.1.2 — Invite Management | 🟢 Complete | 2026-03-16 |
| 3.1.3 — GM Character + Link Refresh | 🟢 Complete | 2026-03-16 |
| 3.1.4 — Character Detail Response (Full Sheet) | 🟢 Complete | 2026-03-16 |

### Story 3.1.1 — Full Character Creation (Invite Flow)

**Files to create**:
- `src/wizards_engine/api/routes/game.py` — `POST /api/v1/game/join`
- `src/wizards_engine/services/onboarding.py` — atomic join logic
- `tests/test_join.py`

**Spec refs**: [auth.md](../domains/auth.md) (invite flow, bare invites, join endpoint), [character-core.md](../domains/character-core.md) (PC creation, sensible defaults)

**Acceptance criteria**:
- `POST /api/v1/game/join` accepts `{code, character_name, display_name}`
- Validates the invite code: exists, unconsumed. Returns 404 `invite_not_found` for all invalid cases (doesn't leak whether code exists)
- Atomically in one transaction:
  - Marks invite as consumed (`is_consumed = true`)
  - Creates a User with `role = "player"`, `login_code` = the invite code, `is_active = true`
  - Creates a Character with `detail_level = "full"`, `name` = character_name
  - All mechanical fields default to 0: `stress=0, free_time=0, plot=0, gnosis=0, last_session_time_now=0`
  - Skills JSON initialized with all 8 skills at level 0
  - Magic stats JSON initialized with all 5 stats at level 0, xp 0
  - Links User → Character via `user.character_id`
- Sets httpOnly cookie with the login code (same as auth cookie)
- Returns 201 with user info (id, display_name, role, character_id)
- After join, the same invite code works as a permanent login (via `POST /auth/login`)

### Story 3.1.2 — Invite Management

**Files to create**:
- `src/wizards_engine/api/routes/invites.py` — invite endpoints
- `src/wizards_engine/schemas/invite.py` — request/response models
- `tests/test_invites.py`

**Spec refs**: [auth.md](../domains/auth.md) (invite management, bare invites)

**Acceptance criteria**:
- `POST /api/v1/game/invites` — GM only. Generates a bare invite with ULID as the code. Returns 201 with invite code + magic link URL (`/login/<code>`).
- `GET /api/v1/game/invites` — GM only. Lists all invite codes (consumed and unconsumed).
- `DELETE /api/v1/game/invites/{id}` — GM only. Deletes an unconsumed invite. Returns 204. Returns 400/409 if invite is already consumed.
- Invite `id` IS the shareable code (no separate code column)

### Story 3.1.3 — GM Character + Link Refresh

**Files to modify**:
- `src/wizards_engine/api/routes/me.py` — add `POST /api/v1/me/character`, `POST /api/v1/me/refresh-link`
- `src/wizards_engine/api/routes/players.py` — add `POST /api/v1/players/{id}/regenerate-token`
- `tests/test_gm_character.py`
- `tests/test_link_refresh.py`

**Spec refs**: [auth.md](../domains/auth.md) (GM self-play, link refresh, token regeneration)

**Acceptance criteria**:
- `POST /api/v1/me/character` — GM only. Accepts `{name}`. Creates a full Character (all defaults to 0) and links to GM. If GM already has a character, old character stays as ownerless. Returns 201.
- `POST /api/v1/me/refresh-link` — any authenticated user. Generates new login code via `secrets.token_urlsafe(32)`. Old link stops working. Updates cookie. Returns new magic link URL.
- `POST /api/v1/players/{id}/regenerate-token` — GM only. Generates new login code for the target player. Returns new magic link URL. Old link stops working immediately.

### Story 3.1.4 — Character Detail Response (Full Sheet)

**Files to modify**:
- `src/wizards_engine/api/routes/characters.py` — enhance `GET /characters/{id}` response
- `src/wizards_engine/schemas/character.py` — full sheet response model
- `tests/test_character_detail.py`

**Spec refs**: [character-core.md](../domains/character-core.md) (sheet API, computed values, session history, traits/bonds grouping)

**Acceptance criteria**:
- Full characters (`detail_level = "full"`) return:
  - All base fields: name, description, notes, attributes, detail_level
  - Resource meters: stress, free_time, plot, gnosis
  - Skills JSON (all 8 skills with levels)
  - Magic stats JSON (all 5 stats with level + xp)
  - Computed values:
    - `effective_stress_max`: `9 - count(trauma bonds)`
    - `active_magic_effects_count`: count of charged + permanent effects (vs cap of 9)
    - `active_trait_count`: filled Core + Role trait slots (vs total 5)
    - `active_bond_count`: filled bond slots (vs total 8 for PCs)
  - `session_ids`: list of session IDs from `session_participants` join table
  - Traits grouped: `{active: [...], past: [...]}`
  - Bonds grouped: `{active: [...], past: [...]}` (includes bidirectional inbound, perspective-normalized)
  - Bond-distance locations: `{common: [...], familiar: [...], known: [...]}`
  - Magic effects: active and past lists
- Simplified characters (`detail_level = "simplified"`) return:
  - Base fields only: name, description, notes, attributes, detail_level
  - Bonds (active/past, descriptive only)
  - Bond-distance locations
  - No meters, skills, magic stats, traits, effects, or session history
- Per-bond computed value: `effective_bond_stress_max = 5 - stress_degradations` (PC bonds only)

---

## Notes

- Traits are returned here but creation/management is in Epic 3.2
- PC bond stress mechanics are in Epic 3.3
- Magic effect management is in Epic 3.2
- The full sheet response is the most complex response in the system
