# Epic 2.3 — Lightweight Bonds & Computed Relationships

**Phase**: 2 — World
**Depends on**: Epic 2.1 (Game Object CRUD) + Epic 2.2 (System Entities)
**Blocks**: Epic 3.1 (Character Sheet) — partially
**Parallel with**: None (depends on both 2.1 and 2.2)

---

## Overview

Implement the bond graph service layer (descriptive bonds only — PC bond mechanics come in Phase 3), bond display on game object detail endpoints, and the bond-distance presence computation. This Epic makes the bond graph operational and connects game objects via relationships.

---

## Stories

### Story 2.3.1 — Bond-Graph Service (Descriptive Bonds Only)

**Files to create**:
- `src/wizards_engine/services/bond.py` — bond creation, validation, auto-inference
- `tests/test_bond_service.py`

**Spec refs**: [bonds.md](../domains/bonds.md) (unified bond model, slot type auto-inference, directionality, slot limits, duplicate prevention), [data-model.md](../architecture/data-model.md) (slots table)

**Acceptance criteria**:
- Service can create bonds between any Game Objects via direct DB operations (not API — GM actions come in Phase 4)
- Auto-infers `slot_type` from owner type/detail_level and target type:
  - Full Character → any = `pc_bond`
  - Simplified Character → any = `npc_bond`
  - Group → Group = `group_relation`
  - Group → Location = `group_holding`
  - Location → any = `location_bond`
- Auto-infers `bidirectional` default from pairing type:
  - Character↔Character, Character↔Group, Group↔Group = bidirectional
  - All Location-involved = directional
  - GM can override at creation
- Enforces source slot limits (hard): 8 for PC bonds, 7 for NPC bonds, 7 for group relations, unlimited for holdings/location bonds
- Returns soft-limit warning for target when target is at capacity on bidirectional bonds (but allows creation)
- Prevents duplicate active bonds per (source, target) pair
- Sets `is_active = true` by default
- Supports setting `source_label`, `target_label`, `description`

### Story 2.3.2 — Bond Display on Game Object Detail

**Files to modify**:
- `src/wizards_engine/api/routes/characters.py` — enhance `GET /characters/{id}`
- `src/wizards_engine/api/routes/groups.py` — enhance `GET /groups/{id}`
- `src/wizards_engine/api/routes/locations.py` — enhance `GET /locations/{id}`
- `src/wizards_engine/services/bond.py` — bond query helpers
- `tests/test_bond_display.py`

**Spec refs**: [bonds.md](../domains/bonds.md) (inbound bond display, perspective-normalized labels, derived membership), [game-objects.md](../domains/game-objects.md) (group members)

**Acceptance criteria**:
- `GET /characters/{id}` includes bonds list: active bonds + past bonds, grouped separately (`{active: [...], past: [...]}`). Bidirectional inbound bonds merged into the list with labels normalized to the viewing entity's perspective.
- `GET /groups/{id}` includes:
  - `traits`: descriptive traits on the group (from slots where `slot_type = "group_trait"`)
  - `bonds`: group relations and holdings
  - `members`: computed list of Characters with a bond targeting this group (derived membership)
- `GET /locations/{id}` includes:
  - `traits`: feature traits (from slots where `slot_type = "feature_trait"`)
  - `bonds`: location bonds
- Bidirectional bonds appear on both the source's and target's bond lists
- Labels are perspective-normalized: source sees `source_label`, target sees `target_label` (swapped)
- Active and past bonds returned in separate groups

### Story 2.3.3 — Bond-Distance Presence

**Files to create**:
- `src/wizards_engine/services/presence.py` — bond-graph traversal algorithm for presence
- `tests/test_presence.py`

**Files to modify**:
- `src/wizards_engine/api/routes/characters.py` — add `locations` to character detail
- `src/wizards_engine/api/routes/locations.py` — add presence to location detail

**Spec refs**: [bonds.md](../domains/bonds.md) (bond-distance presence, Character-intermediary traversal, traversal constraints)

**Acceptance criteria**:
- Implements Character-intermediary traversal algorithm:
  - After a non-Character node (Group or Location), the next hop must go through a Character
  - PCs are valid intermediaries
  - First hop from starting node can go to any type
- Character detail includes `locations` grouped by proximity tier:
  ```json
  {"locations": {"common": [...], "familiar": [...], "known": [...]}}
  ```
  - Common (1-hop): Locations the Character is directly bonded to
  - Familiar (2-hop): Locations reachable through one Character intermediary
  - Known (3-hop): Locations reachable through two intermediaries
- Location detail includes presence by proximity tier:
  ```json
  {"presence": {"common": [...], "familiar": [...], "known": [...]}}
  ```
  - Characters at each tier based on hop distance
- Traversal respects exclusions:
  - `is_active = false` bonds excluded
  - `is_deleted = true` Game Objects excluded (dead ends)
  - `is_trauma = true` bonds excluded (no target, dead ends)
- Computed on read (no caching)

---

## Notes

- Only descriptive bonds at this stage — PC bond stress/degradation mechanics come in Epic 3.3
- Bond creation via API (GM actions) comes in Phase 4 — this Epic uses the service layer directly for testing
- The traversal algorithm is reused for event visibility filtering in Epic 4.1
- Test fixtures should create a small bond graph to verify traversal
