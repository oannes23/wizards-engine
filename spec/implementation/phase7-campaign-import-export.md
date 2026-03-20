# Epic 7.1 — Campaign Import/Export & Notes Ingestion

**Phase**: 7 — Campaign Data
**Depends on**: Phases 1–6 complete (all 20 epics, 52 stories)
**Blocks**: None (standalone tooling)
**Parallel with**: None

---

## Overview

Add a YAML-based campaign import/export system (k8s gitops style) and convert the existing game notes into importable YAML data files. Enables campaign portability and bootstraps the current campaign's state into the engine.

This is a CLI-only tool — no new API endpoints. All data maps to existing tables (no schema changes). The only new dependency is PyYAML.

---

## YAML Directory Structure

```
campaign/
  meta.yaml                        # Campaign metadata
  users/
    gm.yaml
    player-alice.yaml
  trait-templates/
    unstoppable.yaml
    street-savvy.yaml
  characters/
    pcs/
      alexander.yaml               # Full character with inline traits/bonds/effects
    npcs/
      the-owner.yaml               # Simplified character with inline bonds
    entities/
      shovel.yaml                   # Supernatural beings (as simplified characters)
  groups/
    moloch-society.yaml             # Inline traits, relations, holdings
  locations/
    las-vegas/                      # Directory nesting = location hierarchy
      _location.yaml               # The location itself
      lane-23/
        _location.yaml
    planes/
      _location.yaml
      the-city/
        _location.yaml
  clocks/
    consolidate-power.yaml
  sessions/
    001-hoover-dam-attack.yaml      # Numbered for ordering
  stories/
    blackout-murders.yaml           # Inline entries and owners
```

### Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Cross-references | Name-based strings | Human-readable, editable, git-diff friendly |
| Slots | Inline in owner YAML | Keeps related data together (a PC file has all its bonds/traits) |
| Location hierarchy | Directory nesting | Immediately visible in filesystem; `_location.yaml` convention |
| Events/Proposals | Export-only, not imported | Too large for human editing; not needed for campaign seeding |
| Name uniqueness | Required within entity type | Simple collision detection; GM renames to resolve |
| CLI framework | argparse (stdlib) | No new dependency beyond PyYAML |
| New dependency | `pyyaml` | Standard YAML library |
| Module location | `src/wizards_engine/campaign/` | Standalone tool, not an API service |
| Items from notes | Mapped to character `attributes` or `notes` | No items table in engine; items are narrative, tracked via bonds/notes |
| Secrets handling | `secrets` YAML field → appended to `notes` column | GM-only field already exists in the API visibility model |

### Import Dependency Order (6 phases)

```
Phase 1: trait_templates, locations (topological sort for parent-child)
Phase 2: groups, characters (core fields only, no slots)
Phase 3: all slots (traits, bonds, holdings, relations, features), magic_effects
Phase 4: clocks (need game objects for optional association)
Phase 5: users (need characters for player→character FK)
Phase 6: sessions (need characters for participants), stories (need users+characters+sessions)
```

---

## Stories

| Story | Status | Completed |
|-------|--------|-----------|
| 7.1.1 — YAML Schemas & Directory Scaffold | 🔴 Not started | — |
| 7.1.2 — Name Resolver & Validation | 🔴 Not started | — |
| 7.1.3 — Campaign Exporter | 🔴 Not started | — |
| 7.1.4 — Campaign Importer | 🔴 Not started | — |
| 7.1.5 — CLI & Round-Trip Tests | 🔴 Not started | — |
| 7.1.6 — Notes Ingestion & Campaign Data | 🔴 Not started | — |
| 7.1.7 — Documentation | 🔴 Not started | — |

**Parallelism**: 7.1.1 → 7.1.2 → {7.1.3, 7.1.4} parallel → 7.1.5. Story 7.1.6 can start after 7.1.1 (needs schemas). Story 7.1.7 can start after 7.1.5.

```
7.1.1 Schemas ──> 7.1.2 Resolver ──┬──> 7.1.3 Exporter ──┐
                                    └──> 7.1.4 Importer ──┼──> 7.1.5 CLI + Round-Trip
                                                           │
7.1.1 Schemas ──────────────────────> 7.1.6 Notes Data ───┘

7.1.5 CLI ──> 7.1.7 Documentation
```

---

### Story 7.1.1 — YAML Schemas & Directory Scaffold

**Files to create**:
- `src/wizards_engine/campaign/__init__.py`
- `src/wizards_engine/campaign/schemas.py` — Pydantic models for all YAML entity types
- `src/wizards_engine/campaign/ordering.py` — Import ordering constants, location topological sort
- `campaign-data/` — directory structure with `.gitkeep` files
- `tests/test_campaign_schemas.py`

**Files to modify**:
- `pyproject.toml` — add `pyyaml>=6.0,<7.0` dependency

**Spec refs**: [data-model.md](../architecture/data-model.md), [glossary.md](../glossary.md)

**Key Pydantic models**:
- `CampaignMeta` — engine_version, campaign_name, format_version
- `UserYaml` — display_name, role, character (name ref)
- `TraitTemplateYaml` — name, type (core/role), description
- `TargetRef` — `{type: str, name: str}` for bond targets
- `PCBondYaml` — name, target (TargetRef), description, labels, charges, degradations, is_trauma
- `NPCBondYaml` — name, target (TargetRef), description, labels, bidirectional
- `PCTraitYaml` — template (name ref), charge, is_active
- `MagicEffectYaml` — name, description, effect_type, power_level, charges
- `PCCharacterYaml` — name, detail_level=full, meters, skills, magic_stats, inline core_traits/role_traits/bonds/magic_effects
- `NPCCharacterYaml` — name, detail_level=simplified, attributes, inline bonds
- `GroupTraitYaml` — name, description
- `GroupRelationYaml` — name, target (group name), labels, bidirectional
- `GroupHoldingYaml` — name, target (location name), description
- `GroupYaml` — name, description, tier, inline traits/relations/holdings
- `LocationYaml` — name, description, inline features/bonds
- `ClockYaml` — name, segments, progress, associated_with (optional TargetRef)
- `SessionParticipantYaml` — character (name ref), additional_contribution
- `SessionYaml` — number, status, time_now, date, summary, participants
- `StoryEntryYaml` — text, author (display_name ref), character (name ref), session (number ref)
- `StoryYaml` — name, summary, status, tags, owners, entries, children (nested)

**Acceptance criteria**:
- All Pydantic models validate correct YAML structures and reject invalid ones
- `ordering.py` defines the 6-phase import order as constants
- Location topological sort handles `parent_id` chains correctly
- `campaign-data/` directory scaffold exists with proper subdirectories
- `pyyaml` added to dependencies
- ~20 tests covering valid/invalid schema validation

---

### Story 7.1.2 — Name Resolver & Reference Validation

**Files to create**:
- `src/wizards_engine/campaign/resolver.py` — `NameResolver` class (register, resolve, resolve_target_ref)
- `src/wizards_engine/campaign/validators.py` — two-pass validation (schema pass + reference pass)
- `src/wizards_engine/campaign/exceptions.py` — `DuplicateNameError`, `UnresolvedReferenceError`, `CampaignValidationError`
- `tests/test_campaign_resolver.py`
- `tests/test_campaign_validators.py`

**Key patterns to reference**:
- `src/wizards_engine/services/exceptions.py` — follow existing exception hierarchy pattern
- `src/wizards_engine/services/bond.py` — polymorphic type/id resolution patterns

**Acceptance criteria**:
- `NameResolver.register(entity_type, name, ulid)` detects duplicate names within same type
- `NameResolver.resolve(entity_type, name)` returns ULID or raises `UnresolvedReferenceError`
- `NameResolver.resolve_target_ref({type, name})` handles polymorphic target references
- Schema validation pass loads all YAML files via the Pydantic models from 7.1.1
- Reference validation pass checks: bond targets exist, trait template references exist, user→character links valid, session participants exist, story owners/authors exist, clock associations exist, location parents exist
- Returns structured error list: `[{file_path, field, error_message}]`
- ~25 tests covering happy path, duplicates, missing references, circular parents

---

### Story 7.1.3 — Campaign Exporter

**Files to create**:
- `src/wizards_engine/campaign/exporter.py` — `CampaignExporter` class
- `tests/test_campaign_exporter.py`

**Key patterns to reference**:
- `src/wizards_engine/models/slot.py` — all 9 slot_types, owner_type/owner_id polymorphism
- `src/wizards_engine/services/bond.py` — bond display logic, perspective normalization
- `src/wizards_engine/services/character.py` — detail assembly pattern
- `tests/fixtures.py` — `seed_data()` for test setup

**Architecture**:
```python
class CampaignExporter:
    def __init__(self, db: Session, output_dir: Path): ...
    def export_all(self) -> ExportResult: ...
    # Internal: builds name registry (id→name), then exports each entity type
    # Slots are queried by owner and inlined into owner YAML
    # Locations are walked parent-first to build directory tree
    # ULIDs are NEVER written to YAML — all refs are name-based
```

**Acceptance criteria**:
- Exports entire DB to YAML directory matching the structure from 7.1.1
- Characters split into `pcs/` and `npcs/` based on `detail_level`
- All slots (traits, bonds, effects) inlined in their owner's file
- Active and past/retired slots in separate sections
- Location hierarchy reflected in directory nesting
- Cross-references use human-readable names only (no ULIDs anywhere)
- Sessions include participant character names
- Stories include entries with author display names
- `meta.yaml` includes engine version and timestamp
- Exported files pass schema validation from 7.1.1
- `ExportResult` returns entity counts by type
- ~25 tests using `seed_data()` fixture

---

### Story 7.1.4 — Campaign Importer

**Files to create**:
- `src/wizards_engine/campaign/importer.py` — `CampaignImporter` class
- `tests/test_campaign_importer.py`

**Key patterns to reference**:
- `tests/fixtures.py` — `seed_data()` is the canonical reference for creating valid entities with correct FK ordering; importer must follow this exact insertion pattern
- `src/wizards_engine/models/slot.py` — slot_type discriminator, owner_type/owner_id
- `src/wizards_engine/services/bond.py` — slot limit constants (8 PC bonds, 7 NPC bonds, 2 core traits, 3 role traits, 10 group traits, 7 group relations, 5 feature traits)

**Architecture**:
```python
class CampaignImporter:
    def __init__(self, db: Session, input_dir: Path): ...
    def import_all(self, dry_run=False, force=False) -> ImportResult: ...
    # Validates first (fail-fast), then creates entities in 6-phase order
    # Fresh ULIDs for every entity (never import IDs from YAML)
    # NameResolver tracks name→ULID mappings during import
    # Transaction: entire import succeeds or rolls back
```

**Acceptance criteria**:
- Reads YAML directory and populates DB following 6-phase dependency order
- All entities get fresh ULIDs via `python-ulid`
- Cross-references resolved via `NameResolver`
- Validation runs before any DB writes
- Refuses non-empty database unless `force=True`
- PC characters created with `detail_level="full"` and all meter/skill/magic fields
- NPC characters created with `detail_level="simplified"` and null meters
- All 9 slot types created correctly with proper `slot_type`, `owner_type`, `owner_id`
- PC bond mechanical fields (charges, degradations, is_trauma) populated
- Magic effects linked to characters with correct effect_type
- Users created with generated login codes (via `secrets.token_urlsafe`)
- Sessions created with status and participants
- Stories created with owners, entries, and nested children
- Clocks with optional game object association
- `secrets` YAML field appended to `notes` with separator
- Transaction: all-or-nothing (rollback on any error)
- `ImportResult` returns entity counts, warnings list
- ~30 tests covering all entity types, error cases, rollback

---

### Story 7.1.5 — CLI Interface & Round-Trip Tests

**Files to create**:
- `src/wizards_engine/campaign/cli.py` — argparse CLI
- `tests/test_campaign_cli.py`
- `tests/test_campaign_roundtrip.py`
- `tests/fixtures/campaign/` — small valid YAML campaign for test fixtures

**Files to modify**:
- `pyproject.toml` — add `[project.scripts]` entry: `wizards-campaign = "wizards_engine.campaign.cli:main"`

**CLI commands**:
```
uv run wizards-campaign export --output ./campaign-data/
uv run wizards-campaign import --input ./campaign-data/ [--dry-run] [--force]
uv run wizards-campaign validate --input ./campaign-data/
```

**Acceptance criteria**:
- All 3 commands work via `uv run wizards-campaign <cmd>`
- `--dry-run` shows what would be created without committing
- `--force` allows import into non-empty database
- `--db` overrides default database path
- Clear error output on validation failure (file path, field, message)
- Success summary shows entity counts by type
- Round-trip test: seed DB → export → import into fresh DB → compare all entity counts and field values
- Round-trip validates: cross-references intact, location hierarchy preserved, slot assignments correct, mechanical values preserved
- Exit codes: 0 success, 1 validation failure, 2 runtime error
- ~20 tests (12 CLI, 8 round-trip)

---

### Story 7.1.6 — Notes Ingestion & Campaign Data Files

**Source material** (read-only, in `wizards-notes/`):
- `spec/characters/pcs/*.md` — 7 PC files
- `spec/characters/npcs/*.md` — 51 NPC files
- `spec/characters/entities/*.md` — 13 supernatural being files
- `spec/factions/*.md` — 20 faction files
- `spec/locations/**/*.md` — 34 location files
- `spec/items/*.md` — 23 item files
- `spec/sessions/*.md` — 28 session files
- `spec/stories/*.md` — 12 story arc files
- `spec/magic/*.md` — magic system docs

**Files to create** (in `campaign-data/`):
- `meta.yaml`
- `users/*.yaml` — 1 GM + 7 player files
- `trait-templates/*.yaml` — trait templates extracted from PC notes
- `characters/pcs/*.yaml` — 7 PC YAML files with full mechanical data
- `characters/npcs/*.yaml` — 51 NPC files as simplified characters
- `characters/entities/*.yaml` — 13 supernatural beings as simplified characters
- `groups/*.yaml` — 20 faction→group YAML files
- `locations/**/_location.yaml` — 34 locations in hierarchy
- `clocks/*.yaml` — any active clocks mentioned in notes
- `sessions/*.yaml` — 28 session records
- `stories/*.yaml` — 12 story arcs with entries

**Conversion approach**: LLM-assisted (notes are too irregular and verbose for scripted parsing). Each entity type is converted in a focused session:
1. Provide the YAML schema (from 7.1.1) + 2-3 completed examples
2. Provide the raw markdown notes
3. LLM produces valid YAML with rewritten/condensed descriptions
4. Run `wizards-campaign validate` to catch errors
5. GM reviews for accuracy

**Key mapping rules**:
- Notes `## Secrets` sections → YAML `secrets` field
- Notes affiliations/relationships → YAML bonds with appropriate `target` refs
- Notes faction members → character bonds targeting the group
- Items → described in character `attributes` or `notes` (no items table)
- PC magic disciplines → `magic_stats` (levels estimated from narrative if not explicit)
- Faction "Known Members" → characters with bonds to that group
- Location hierarchy from notes directory structure → YAML directory nesting
- Session "PCs present" → session `participants` list

**Acceptance criteria**:
- All entities from notes are represented as YAML files
- Descriptions are condensed/rewritten (not verbatim note dumps)
- `secrets` fields populated from `## Secrets` sections
- All cross-references use consistent names across files
- `wizards-campaign validate` passes with zero errors
- PC mechanical data is complete (stats, skills, magic_stats, bonds with charges)
- NPCs have appropriate detail for simplified characters
- Location hierarchy matches campaign geography
- Group membership is bidirectionally consistent (character bond → group, group members list)
- `wizards-campaign import` succeeds into an empty database

---

### Story 7.1.7 — Documentation

**Files to create**:
- `docs/campaign-format.md` — complete YAML format reference (all fields, all entity types)
- `campaign-data/README.md` — quick-start guide for editing campaign data
- `campaign-data/examples/` — minimal valid campaign (2-3 entities per type) for reference

**Acceptance criteria**:
- Format reference documents every YAML field for every entity type
- Includes directory structure diagram
- Documents cross-reference naming convention
- Documents import ordering and dependency rules
- Documents CLI commands and all flags
- Documents secrets handling
- README explains how to edit/extend campaign data files
- Example campaign passes validation and imports successfully

---

## Verification Plan

1. **Schema tests**: `uv run pytest tests/test_campaign_schemas.py` — valid/invalid YAML validation
2. **Resolver tests**: `uv run pytest tests/test_campaign_resolver.py` — name registration/resolution
3. **Validator tests**: `uv run pytest tests/test_campaign_validators.py` — two-pass validation
4. **Exporter tests**: `uv run pytest tests/test_campaign_exporter.py` — DB→YAML correctness
5. **Importer tests**: `uv run pytest tests/test_campaign_importer.py` — YAML→DB correctness
6. **CLI tests**: `uv run pytest tests/test_campaign_cli.py` — command-line interface
7. **Round-trip tests**: `uv run pytest tests/test_campaign_roundtrip.py` — export→import→compare
8. **Full validation**: `uv run wizards-campaign validate --input ./campaign-data/` — zero errors
9. **Full import**: `uv run wizards-campaign import --input ./campaign-data/` into empty DB — success
10. **Full suite**: `uv run pytest` — all existing + new tests pass

---

## Critical Reference Files

- `src/wizards_engine/models/slot.py` — unified Slot model, 9 slot_types, polymorphic ownership
- `src/wizards_engine/models/character.py` — PC vs NPC detail_level distinction
- `tests/fixtures.py` — `seed_data()` canonical entity creation ordering
- `src/wizards_engine/services/bond.py` — slot limits, auto-inference rules, bond creation logic
- `src/wizards_engine/models/story.py` — Story/StoryOwner/StoryEntry multi-table entity
- `src/wizards_engine/db.py` — engine/session setup pattern
- `wizards-notes/spec/characters/_schema.md` — notes schema for characters
- `wizards-notes/spec/factions/_schema.md` — notes schema for factions

---

## Notes

- **No new API endpoints**: This is a CLI-only tool, not exposed via FastAPI
- **No schema changes**: All data maps to existing tables; items become character notes/attributes
- **PyYAML only new dependency**: Everything else uses stdlib or existing deps
