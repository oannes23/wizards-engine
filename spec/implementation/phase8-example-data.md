# Epic 8.7 — Comprehensive Example Campaign Data

**Phase**: 8 — UI Cleanup & UX Modernization
**Depends on**: 7.1 (Campaign Import/Export), Phase 8 UI epics (for visual verification)
**Blocks**: None
**Parallel with**: All Phase 8 epics (independent data work)

---

## Overview

Enrich the importable example campaign data and create a post-import seeding script so that every aspect of the system is visible and exercisable in the UI. The current example data has rich structural entities (67+ characters, 19 groups, 29 locations, 28 sessions, 11 stories) but is missing clocks, varied mechanical states (low-charge traits, degraded bonds, trauma, diverse meter values), and all runtime-generated data (events, proposals, sessions in various states). This epic fills those gaps so a fresh import + seed produces a fully-populated system where every UI feature has data to display.

---

## Stories

| Story | Status | Completed |
|-------|--------|-----------|
| 8.7.1 — Enrich Importable YAML Data | 🟢 Complete | 2026-03-22 |
| 8.7.2 — Post-Import Event & Proposal Seeding Script | 🟢 Complete | 2026-03-22 |
| 8.7.3 — Seed Data Verification Checklist | 🟢 Complete | 2026-03-22 |

### Story 8.7.1 — Enrich Importable YAML Data

**Files to modify**:
- `campaign-data/clocks/` — add clock YAML files (currently empty, only `.gitkeep`)
- `campaign-data/characters/pcs/` — enrich PC YAML files with varied mechanical states
- `campaign-data/characters/npcs/` — ensure NPCs have varied bond configurations
- `campaign-data/groups/` — add group traits, relations, holdings where missing
- `campaign-data/locations/` — add feature traits and location bonds where missing
- `campaign-data/stories/` — add more story entries with varied authors, sessions, and visibility levels

**Spec refs**: [phase7-campaign-import-export.md](phase7-campaign-import-export.md) (YAML Schemas)

**Implementation notes**:
- **Clocks**: Create 6-8 clock files covering different states:
  - A clock near completion (e.g., 5/6 segments) associated with a group project
  - A clock at 0 progress (just started)
  - A clock at mid-progress associated with a character
  - A standalone clock not associated with any entity
  - A clock associated with a location
- **PC mechanical variety**: Ensure across the 7 PCs we have:
  - At least 1 PC with high stress (7+ out of 9) to trigger stress proximity alerts
  - At least 1 PC with a trauma bond (`is_trauma: true`) to show reduced effective stress max
  - At least 1 PC with degraded bonds (`degradations: 2+`) to show reduced effective charges
  - At least 1 PC with low-charge core traits (charge: 0 or 1)
  - At least 1 PC with low-charge role traits (charge: 1 or 2)
  - At least 1 PC with bonds at charge 0 (about to degrade)
  - At least 1 PC with all traits fully charged (for contrast)
  - Varied meter values: one PC near 0 Free Time, one with max Plot, one with high Gnosis, one with almost no Gnosis
  - Varied magic stats: at least one PC with level 3+ in a school, one with 0s across the board
  - Multiple magic effects per PC: at least one PC with 3+ effects (charged, permanent, passive variants)
- **NPC bonds**: Ensure NPCs have bonds to PCs, groups, and locations (not just PCs)
- **Group traits and relations**: Add `group_trait`, `group_relation`, and `group_holding` slots to groups that don't have them. Include varied charge levels.
- **Location features**: Add `feature_trait` slots to locations. Add `location_bond` slots connecting locations to characters and groups.
- **Stories**: Ensure at least 2 stories have 5+ entries each with:
  - Entries by different authors (GM, multiple players)
  - Entries referencing different sessions
  - Entries with character, group, and location associations
  - At least one completed story, one active story, one abandoned story
  - Tags on stories for filtering

**Acceptance criteria**:
1. `uv run wizards-campaign validate --input ./campaign-data/` passes with no errors
2. At least 6 clock files exist in `campaign-data/clocks/` with varied progress states
3. PC characters span the full range of mechanical states (high stress, low charges, trauma, degradation)
4. Groups have traits, relations, and holdings populated
5. Locations have feature traits and bonds
6. Stories have multiple entries with varied authors and associations
7. Import succeeds: `uv run wizards-campaign import --input ./campaign-data/` completes without errors

### Story 8.7.2 — Post-Import Event & Proposal Seeding Script

**Files to create**:
- `src/wizards_engine/campaign/seed_events.py` — script that generates realistic events and proposals via the internal API/services

**Files to modify**:
- `src/wizards_engine/campaign/cli.py` — add `seed-events` subcommand

**Spec refs**: [events.md](../domains/events.md) (Event Types), [actions.md](../domains/actions.md) (Action Types)

**Implementation notes**:
- The import system intentionally does not import events or proposals (they're runtime-generated). This script fills that gap by programmatically creating realistic sample data after an import.
- The script should work against a freshly imported database and create:
  - **Events of every type**: character.stress_changed, character.free_time_changed, character.plot_changed, character.gnosis_changed, bond.created, bond.degraded, bond.retired, trait.created, trait.recharged, trait.retired, effect.created, effect.used, effect.retired, clock.advanced, clock.completed, session.started, session.ended, proposal.submitted, proposal.approved, proposal.rejected, gm_action.* (various GM action types)
  - **Proposals in every state**: at least 2 pending (1 player, 1 system), 3 approved, 2 rejected. Cover different action types: use_skill, use_magic, rest, work_on_project, new_trait, new_bond, recharge_trait, maintain_bond, resolve_clock, resolve_trauma
  - **Session states**: ensure at least 1 draft session, 1 active session, and multiple ended sessions exist
  - **Story entries**: add story entries via the API with narrative text, varied visibility levels
  - **GM actions**: exercise multiple GM action types to generate events: modify_character, create_bond, modify_bond, create_trait, award_xp, modify_clock
  - **Rider events**: create at least one event with a `parent_event_id` (rider event)
  - **Varied visibility**: events with silent, gm_only, private, bonded, familiar, public, and global visibility levels
  - **Event targets**: events targeting characters, groups, locations, and clocks
  - **Temporal spread**: events spread across multiple sessions and timestamps so the feed has depth
- The script should use the internal service layer (not HTTP API) for efficiency, operating within a database session
- CLI command: `uv run wizards-campaign seed-events [--db-url sqlite:///path]`
- Should be idempotent or at least safe to run on an already-seeded database (check for existing events before creating)

**Acceptance criteria**:
1. `uv run wizards-campaign seed-events` runs successfully after a fresh import
2. At least one event of every major event type is created
3. Proposals exist in pending, approved, and rejected states
4. Events span multiple sessions and timestamps
5. Events have varied visibility levels (silent through global)
6. Events target characters, groups, locations, and clocks
7. At least one rider event (parent_event_id populated) exists
8. The GM dashboard shows pending proposals, stress proximity alerts, and near-completion clocks after seeding
9. The feed shows a rich history with varied event types and actors
10. The script is documented in the campaign README

### Story 8.7.3 — Seed Data Verification Checklist

**Files to create**:
- `campaign-data/VERIFICATION.md` — checklist of what to verify after import + seed

**Implementation notes**:
- A human-readable checklist document that lists every UI feature and what example data should be visible for it
- Organized by view/tab: Queue, Event Feed, Game Objects, Character Detail, Sessions, Proposals
- For each feature, lists what specific data should be visible and what to look for
- Serves as both a QA document and a demo guide

**Checklist sections**:
- **GM Queue**: PC cards with varied meter levels, low-charge indicators visible on at least 2 PCs, stress proximity alert on at least 1 PC, Groups section with active clocks
- **Event Feed**: Events of 5+ different types visible, story entries visible, proposals visible, filters reduce results, sort changes order
- **Game Objects — Characters**: PCs and NPCs both present, PC/NPC filter works, varied descriptions, star functionality
- **Game Objects — Groups**: Groups with tiers 1-5, groups with active clocks, groups with varied activity levels
- **Game Objects — Locations**: Nested hierarchy visible, parent references shown
- **Character Detail**: Full description visible, skills table populated, Core and Role traits separated, traits with varied charges (0-5), bonds with degradation, trauma bonds, magic effects, events feed at bottom
- **Sessions**: Draft, Active, and Ended sessions visible, participant lists populated, timelines have events
- **Proposals**: Pending proposals in queue, approved and rejected proposals in history
- **Feed (Player)**: Visibility-filtered events, story entries, varied actor types

**Acceptance criteria**:
1. Verification checklist document exists at `campaign-data/VERIFICATION.md`
2. Every UI view/tab has at least 3 verification items listed
3. Each item describes specific data to look for (not vague)
4. After running import + seed, following the checklist confirms all items are visible

---

## Notes

- 8.7.1 (YAML enrichment) can start immediately — no dependency on other Phase 8 work
- 8.7.2 (seeding script) depends on 8.7.1 (enriched data must exist to generate meaningful events against it)
- 8.7.3 (verification checklist) can be written alongside 8.7.1 and updated after 8.7.2
- This epic is particularly valuable for Phase 8 UI work — developers can import + seed and immediately see all UI features with real-looking data
- The seeding script should be reusable for future QA and demo purposes
- Consider whether the anonymized example campaign (Story 7.1.8) should also be updated to match the enriched data
