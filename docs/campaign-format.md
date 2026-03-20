# Campaign YAML Format Reference

Complete reference for the `campaign-data/` YAML format used by the `wizards-campaign` CLI tool.

---

## Contents

1. [Directory Structure](#directory-structure)
2. [Cross-Reference Naming Convention](#cross-reference-naming-convention)
3. [Import Ordering and Dependency Rules](#import-ordering-and-dependency-rules)
4. [CLI Commands](#cli-commands)
5. [Secrets Handling](#secrets-handling)
6. [Entity Reference](#entity-reference)
   - [meta.yaml](#metayaml)
   - [Trait Templates](#trait-templates)
   - [Locations](#locations)
   - [Characters — PC (Full)](#characters--pc-full)
   - [Characters — NPC / Entity (Simplified)](#characters--npc--entity-simplified)
   - [Groups](#groups)
   - [Clocks](#clocks)
   - [Users](#users)
   - [Sessions](#sessions)
   - [Stories](#stories)

---

## Directory Structure

```
campaign-data/
  meta.yaml                          # Campaign metadata (required)
  trait-templates/
    <slug>.yaml                      # One file per trait template
  locations/
    <region>/
      _location.yaml                 # The region itself
      <place>/
        _location.yaml               # A nested sub-location
  characters/
    pcs/
      <name>.yaml                    # Full (PC) character — meters, skills, magic
    npcs/
      <name>.yaml                    # Simplified (NPC) character
    entities/
      <name>.yaml                    # Supernatural beings (simplified character)
  groups/
    <slug>.yaml                      # One file per group/faction
  clocks/
    <slug>.yaml                      # One file per progress clock
  users/
    <slug>.yaml                      # One file per user account
  sessions/
    <number>-<slug>.yaml             # Numbered for ordering (e.g. 001-first-session.yaml)
  stories/
    <slug>.yaml                      # One file per story arc (children nested inline)
```

### Location Hierarchy Convention

Directory nesting directly represents the parent-child location hierarchy. Each location lives in its own directory and contains a file named `_location.yaml`. The importer infers the parent from the directory structure automatically.

```
locations/
  nevada/
    _location.yaml          # "Nevada" — top-level, no parent
    las-vegas/
      _location.yaml        # "Las Vegas" — parent inferred as "Nevada"
      lane-23/
        _location.yaml      # "Lane 23" — parent inferred as "Las Vegas"
```

A location with no children still gets a directory:

```
locations/
  planes/
    _location.yaml          # "Planes" — top-level
    the-city/
      _location.yaml        # "The City" — parent inferred as "Planes"
```

The `parent` field in a `_location.yaml` file is an override. Omit it and let the directory structure speak — use the field only when the directory structure cannot express the relationship accurately.

---

## Cross-Reference Naming Convention

All cross-references between entities use **human-readable names, not database IDs**. Names are **case-sensitive** and must match the `name` field of the target entity exactly.

For polymorphic references (bond targets, clock associations, story owners), a `{type, name}` object is used:

```yaml
target:
  type: character      # "character", "group", or "location"
  name: "Jan"
```

For same-type references (group relations target a group by name, session participants reference a character by name), a plain string is used:

```yaml
target: "Discordian Cabal"       # group relations: string name of the target group
character: "Alexander"           # session participants: string name of the character
```

**Name uniqueness is required within each entity type.** The importer raises an error if two characters (or two groups, etc.) share the same name.

---

## Import Ordering and Dependency Rules

The importer processes entities in six phases to satisfy foreign key dependencies. Within each phase, order does not matter.

| Phase | Entity Types | Dependency Reason |
|-------|-------------|-------------------|
| 1 | `trait_templates`, `locations` | No dependencies; locations use topological sort for parent-child ordering |
| 2 | `groups`, `characters` | Core fields only — no slots; no cross-dependencies within phase |
| 3 | `slots` (traits, bonds, features, relations, holdings), `magic_effects` | Owners (characters, groups, locations) must exist; bond targets must exist |
| 4 | `clocks` | Optional `associated_with` references any game object — all must exist |
| 5 | `users` | Optional `character` FK — characters must exist |
| 6 | `sessions`, `stories` | Sessions need character participants; stories need users, characters, and sessions |

The entire import runs in a single database transaction. If any step fails, all changes are rolled back.

**Location topological sort**: Within Phase 1, locations are sorted using Kahn's algorithm so parent locations are always created before their children, regardless of file order on disk.

---

## CLI Commands

The CLI is installed as `wizards-campaign` and invoked via `uv run`:

```
uv run wizards-campaign <command> [options]
```

### Export

```
uv run wizards-campaign export --output <dir> [--db <file>]
```

Dumps the entire database to a YAML directory tree. Creates `<dir>` if it does not exist.

| Flag | Short | Required | Description |
|------|-------|----------|-------------|
| `--output` | `-o` | yes | Output directory for YAML files |
| `--db` | — | no | Override SQLite database file path |

On success, prints a summary of entity counts and exits with code 0.

### Import

```
uv run wizards-campaign import --input <dir> [--dry-run] [--force] [--db <file>]
```

Validates and imports a YAML directory into the database.

| Flag | Short | Required | Description |
|------|-------|----------|-------------|
| `--input` | `-i` | yes | Input directory containing campaign YAML |
| `--dry-run` | — | no | Validate and count entities without writing to the database |
| `--force` | — | no | Allow import into a non-empty database (existing data is not deleted) |
| `--db` | — | no | Override SQLite database file path |

By default the importer refuses to run against a non-empty database. Use `--force` to add data alongside existing rows.

On success, prints a detailed count of all created entities and any warnings, then exits with code 0.

### Validate

```
uv run wizards-campaign validate --input <dir>
```

Runs two-pass validation (schema check then reference check) against the YAML directory. Does not require a database connection.

| Flag | Short | Required | Description |
|------|-------|----------|-------------|
| `--input` | `-i` | yes | Input directory to validate |

On success, prints "Campaign is valid. No errors found." and exits with code 0.

On failure, prints each error to stderr in the format `<file_path>:<field>: <message>` and exits with code 1.

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Validation failure (schema or reference errors in the YAML) |
| 2 | Runtime error (database error, I/O error, unexpected exception) |

### Database Path Resolution

The database path is resolved in this order:
1. `--db <file>` flag (if provided)
2. `WIZARDS_DB_PATH` environment variable
3. `wizards_engine.db` in the current working directory

---

## Secrets Handling

Any entity that has a `notes` field also accepts an optional `secrets` field. The `secrets` field is a GM-only narrative text block (equivalent to a `## Secrets` section in campaign notes).

On import, the `secrets` content is appended to the entity's `notes` column in the database with a separator:

```
<existing notes text>

---
SECRETS:
<secrets text>
```

If `notes` is null and `secrets` is provided, the database `notes` column contains only the secrets block (with separator). If `secrets` is null, `notes` is stored as-is.

The `secrets` field is never written back during export — it becomes part of `notes` in the database. This is intentional: once imported, secrets live in `notes` where the GM visibility rules already apply.

Entity types that support `secrets`: `PCCharacterYaml`, `NPCCharacterYaml`.

---

## Entity Reference

### meta.yaml

**File**: `meta.yaml` (required, at the root of the campaign directory)

Campaign-level metadata. Created automatically on export; required for any import.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `engine_version` | string | yes | Semantic version of the engine that produced this export (e.g. `"0.1.0"`) |
| `campaign_name` | string | yes | Human-readable campaign title |
| `format_version` | integer | no | YAML format schema version; defaults to `1` |

**Example**:

```yaml
engine_version: "0.1.0"
campaign_name: "Wizards of Las Vegas"
format_version: 1
```

---

### Trait Templates

**File**: `trait-templates/<slug>.yaml`

A Trait Template defines a reusable Core or Role Trait that can be assigned to PC character sheets. See [glossary: Trait Template](../spec/glossary.md) for the full definition.

| Field | Type | Required | Valid Values | Description |
|-------|------|----------|-------------|-------------|
| `name` | string | yes | — | Template name (must be unique across all trait templates) |
| `type` | string | yes | `"core"`, `"role"` | Determines which character slot type can reference this template |
| `description` | string | yes | — | Full description text |

**Example**:

```yaml
name: Scholar
type: core
description: >
  A dedicated seeker of knowledge and hidden truths. This character pursues
  understanding above all else, cataloguing the secrets of the magical world
  and leveraging information as their primary tool.
```

---

### Locations

**File**: `locations/<path>/_location.yaml`

A Location represents a place in the game world. See [glossary: Location](../spec/glossary.md).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Location name (must be unique across all locations) |
| `description` | string | no | Narrative description |
| `notes` | string | no | GM notes |
| `parent` | string | no | Name of the parent location (override; normally inferred from directory structure) |
| `features` | list | no | Inline feature trait slots (max 5); see [LocationFeature](#locationfeature) |
| `bonds` | list | no | Inline location bond slots (unlimited); see [LocationBond](#locationbond) |

#### LocationFeature

A descriptive trait describing a physical or atmospheric characteristic of the location (`feature_trait` slot).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Feature name |
| `description` | string | no | Description text |
| `is_active` | boolean | no | `true` for active; `false` for retired/past. Defaults to `true` |

#### LocationBond

A bond connecting this location to another game object (`location_bond` slot).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Bond name |
| `target` | TargetRef | yes | Polymorphic reference `{type, name}` to the target entity |
| `description` | string | no | Narrative description |
| `labels` | object | no | Perspective labels `{source: str, target: str}` |
| `is_active` | boolean | no | Defaults to `true` |

**Example** (`locations/las-vegas/_location.yaml`):

```yaml
name: Las Vegas
description: >
  The neon city in the Nevada desert — tourist surface, magical underbelly.
notes: >
  Las Vegas generates enormous gnosis through gambling and performance.
features:
  - name: Moloch Power Concentration
    description: The city's sacrificial capitalism paradigm feeds the Moloch egregore directly.
  - name: Magical Community Hub
    description: Lane 23, Taco Night at 8th and Fremont, and the Luxor serve as gathering points.
```

**Example with nested child** (directory structure):

```
locations/
  las-vegas/
    _location.yaml      # "Las Vegas"
    lane-23/
      _location.yaml    # "Lane 23" — parent automatically "Las Vegas"
```

---

### Characters — PC (Full)

**File**: `characters/pcs/<slug>.yaml`

A player character with full mechanical detail. See [glossary: Character](../spec/glossary.md).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Character name (must be unique across all characters) |
| `detail_level` | string | no | Always `"full"`; validated on import |
| `description` | string | no | Background / concept text |
| `notes` | string | no | GM notes |
| `secrets` | string | no | GM-only secrets; appended to `notes` on import (see [Secrets Handling](#secrets-handling)) |
| `attributes` | object | no | Freeform JSON blob for custom data (items, misc facts) |
| `meters` | object | no | `{stress, free_time, plot, gnosis}` — all integers, default 0 |
| `skills` | object | no | All 8 skills mapped to level 0–3; see [Skills](#skills) |
| `magic_stats` | object | no | All 5 magic disciplines, each with `{level, xp}`; see [Magic Stats](#magic-stats) |
| `core_traits` | list | no | Core trait slots (max 2); see [PCTrait](#pctrait) |
| `role_traits` | list | no | Role trait slots (max 3); see [PCTrait](#pctrait) |
| `bonds` | list | no | PC bond slots (max 8); see [PCBond](#pcbond) |
| `magic_effects` | list | no | Magic effects (max 9 active charged + permanent); see [MagicEffect](#magiceffect) |

#### Skills

The `skills` object must contain exactly these 8 keys, each mapped to an integer 0–3:

```yaml
skills:
  awareness: 3
  composure: 2
  influence: 1
  finesse: 2
  speed: 1
  power: 2
  knowledge: 3
  technology: 1
```

#### Magic Stats

The `magic_stats` object contains exactly these 5 keys, each mapped to a `{level, xp}` sub-object:

```yaml
magic_stats:
  being:      {level: 1, xp: 0}
  wyrding:    {level: 1, xp: 0}
  summoning:  {level: 0, xp: 0}
  enchanting: {level: 1, xp: 0}
  dreaming:   {level: 0, xp: 0}
```

#### Meters

The `meters` object contains exactly these 4 keys:

```yaml
meters:
  stress: 0
  free_time: 5
  plot: 2
  gnosis: 5
```

#### PCTrait

A core or role trait slot referencing a Trait Template by name.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `template` | string | yes | Name ref to the `TraitTemplate` (must match a file in `trait-templates/`) |
| `charge` | integer | no | Current charge count 0–5; defaults to 5 |
| `is_active` | boolean | no | `false` marks this slot as retired/past; defaults to `true` |

#### PCBond

A PC bond slot with full mechanical depth (`pc_bond` slot type). See [glossary: Bond](../spec/glossary.md).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Bond name / relationship label |
| `target` | TargetRef | yes | Polymorphic ref `{type, name}` to the bonded entity |
| `description` | string | no | Narrative description |
| `labels` | object | no | Perspective labels `{source: str, target: str}` |
| `charges` | integer | no | Bond charges 0–5; defaults to 5 |
| `degradations` | integer | no | Number of max-charge reductions (each degradation reduces effective max by 1); defaults to 0 |
| `is_trauma` | boolean | no | `true` if this is a Trauma bond; defaults to `false` |
| `is_active` | boolean | no | `false` marks this bond as retired/past; defaults to `true` |

#### MagicEffect

A magic effect attached to a PC character.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Effect name |
| `description` | string | yes | Full description |
| `effect_type` | string | yes | `"instant"`, `"charged"`, or `"permanent"` |
| `power_level` | integer | yes | Power level 1–5 |
| `charges` | object | conditional | Required for `effect_type: "charged"`: `{current: int, max: int}`; must be `null` or omitted for other types |
| `is_active` | boolean | no | `false` marks this effect as retired/past; defaults to `true` |

**Full PC example** (`characters/pcs/alexander.yaml`):

```yaml
name: Alexander
detail_level: full
description: >
  An Archivist-turned-Logovore and one of the Infinite Seven. A scholar who
  consumed forbidden data in his City past life.
notes: >
  Detection method: smell-based magical detection (developed).
secrets: >
  City past: Was an Archivist in The Tower who consumed a forbidden database.
attributes:
  magic_detection: smell-based
  moloch_mask: Owl
meters:
  stress: 0
  free_time: 5
  plot: 2
  gnosis: 5
skills:
  awareness: 3
  composure: 2
  influence: 1
  finesse: 2
  speed: 1
  power: 2
  knowledge: 3
  technology: 1
magic_stats:
  being:      {level: 1, xp: 0}
  wyrding:    {level: 1, xp: 0}
  summoning:  {level: 0, xp: 0}
  enchanting: {level: 1, xp: 0}
  dreaming:   {level: 0, xp: 0}
core_traits:
  - template: Scholar
    charge: 4
  - template: Navigator
    charge: 5
role_traits:
  - template: Logovore
    charge: 4
bonds:
  - name: Fellow Infinite Seven
    target:
      type: group
      name: The Infinite Seven
    description: Core member; City past and mortal present intertwined with the group.
    charges: 5
  - name: Knowledge Seeker
    target:
      type: character
      name: Jan
    description: Fellow Infinite Seven member; rival tension over the Floyd Lamb Park incident.
    charges: 3
    degradations: 1
magic_effects:
  - name: Smell-Based Magic Detection
    description: Can detect magic through scent.
    effect_type: permanent
    power_level: 2
  - name: Cloaking Magic
    description: Conceals magical activity from observers.
    effect_type: permanent
    power_level: 2
```

---

### Characters — NPC / Entity (Simplified)

**File**: `characters/npcs/<slug>.yaml` or `characters/entities/<slug>.yaml`

A non-player character or supernatural entity with simplified detail. Both subdirectories use the same schema. See [glossary: NPC](../spec/glossary.md).

The distinction between `npcs/` and `entities/` is organizational only — both are imported as `detail_level: "simplified"` characters.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Character name (must be unique across all characters) |
| `detail_level` | string | no | Always `"simplified"`; validated on import |
| `description` | string | no | Background / concept text |
| `notes` | string | no | GM notes |
| `secrets` | string | no | GM-only secrets; appended to `notes` on import |
| `attributes` | object | no | Freeform JSON blob (items, stats, miscellaneous data) |
| `bonds` | list | no | NPC bond slots (max 7); see [NPCBond](#npcbond) |

NPC characters have no meters, skills, magic stats, traits, or magic effects.

#### NPCBond

A descriptive bond slot without mechanical depth (`npc_bond` slot type).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Bond name / relationship label |
| `target` | TargetRef | yes | Polymorphic ref `{type, name}` to the bonded entity |
| `description` | string | no | Narrative description |
| `labels` | object | no | Perspective labels `{source: str, target: str}` |
| `bidirectional` | boolean | no | Whether both sides see this bond; defaults to `false` |
| `is_active` | boolean | no | `false` marks this bond as retired/past; defaults to `true` |

NPC bonds have no charges, degradations, or trauma flag.

**Example** (`characters/npcs/harry.yaml`):

```yaml
name: Harry
detail_level: simplified
description: >
  Elder statesman of the Las Vegas magical community. Owns Lane 23 bowling
  alley, leads the Discordian Cabal.
notes: Married to Jane 40+ years.
bonds:
  - name: Married To
    target:
      type: character
      name: Jane
    description: Married over 40 years.
    bidirectional: true
  - name: Leader
    target:
      type: group
      name: Discordian Cabal
    description: Elder and informal leader of the Discordian Cabal.
  - name: Lane 23 Owner
    target:
      type: location
      name: Lane 23
    description: Owns and wards Lane 23, seat of Discordian power.
```

---

### Groups

**File**: `groups/<slug>.yaml`

A Group represents an organization, faction, or crew. See [glossary: Group](../spec/glossary.md).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Group name (must be unique across all groups) |
| `description` | string | no | Description text |
| `tier` | integer | no | Power/influence level (any non-negative integer); defaults to 1 |
| `notes` | string | no | GM notes |
| `traits` | list | no | Inline group trait slots (max 10); see [GroupTrait](#grouptrait) |
| `relations` | list | no | Inline group relation slots (max 7); see [GroupRelation](#grouprelation) |
| `holdings` | list | no | Inline group holding slots (unlimited); see [GroupHolding](#groupholding) |

#### GroupTrait

A freeform descriptive trait for a group (`group_trait` slot).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Trait name |
| `description` | string | no | Description text |
| `is_active` | boolean | no | Defaults to `true` |

#### GroupRelation

A relation between this group and another group (`group_relation` slot).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Relation name |
| `target` | string | yes | Name of the target group (plain string, not a TargetRef) |
| `description` | string | no | Description text |
| `labels` | object | no | Perspective labels `{source: str, target: str}` |
| `bidirectional` | boolean | no | Whether both sides see this relation; defaults to `false` |
| `is_active` | boolean | no | Defaults to `true` |

#### GroupHolding

A holding connecting this group to a location (`group_holding` slot).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Holding name |
| `target` | string | yes | Name of the target location (plain string, not a TargetRef) |
| `description` | string | no | Description text |
| `is_active` | boolean | no | Defaults to `true` |

**Example** (`groups/moloch-society.yaml`):

```yaml
name: Moloch Society
description: >
  A secretive power structure of sacrificial capitalism controlling Las Vegas.
tier: 4
traits:
  - name: Animal Mask Hierarchy
    description: Members identified by animal masks during ceremonies.
  - name: Moloch Egregore
    description: Moloch is not a deity but a collective thoughtform fed by capitalism.
relations:
  - name: Adversarial
    target: Kali Yuga Supremacy
    description: KYS chaos threatens Moloch's ordered power structure.
holdings:
  - name: Initiation Mansion
    target: The Owner's Mansion
    description: The Owner's gated mansion where initiations and rituals occur.
```

---

### Clocks

**File**: `clocks/<slug>.yaml`

A progress clock for tracking ongoing threats, projects, or countdowns. See [glossary: Clock](../spec/glossary.md).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Clock name (must be unique across all clocks) |
| `segments` | integer | no | Total segments (any positive integer); defaults to 5 |
| `progress` | integer | no | Filled segments (0 to segments); defaults to 0 |
| `associated_with` | TargetRef | no | Optional polymorphic ref `{type, name}` to an associated game object |
| `notes` | string | no | GM notes |

**Example**:

```yaml
name: Consolidate Power
segments: 8
progress: 3
associated_with:
  type: group
  name: Moloch Society
notes: Chef Alonzo's power grab after the Session 27 earthquake.
```

---

### Users

**File**: `users/<slug>.yaml`

A user account for a player or GM.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `display_name` | string | yes | Player's display name (1–50 characters; used for cross-references in story entries) |
| `role` | string | yes | `"gm"` or `"player"` |
| `character` | string | no | Name ref to this user's linked character; `null` for the GM |

On import, each user is assigned a freshly generated login code via `secrets.token_urlsafe(32)`. Login codes are never stored in YAML.

**Examples**:

```yaml
# users/gm.yaml
display_name: "GM"
role: gm
character: null
```

```yaml
# users/player-alexander.yaml
display_name: "Player Alex"
role: player
character: "Alexander"
```

---

### Sessions

**File**: `sessions/<number>-<slug>.yaml`

A play session record. Files are named with a leading number for filesystem ordering (e.g. `001-hoover-dam-attack.yaml`). The number in the filename is not used by the importer — the `number` field in the YAML is authoritative.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `number` | integer | yes | Sequential session number (used for ordering and for story entry `session` references) |
| `status` | string | yes | `"draft"`, `"active"`, or `"ended"` |
| `time_now` | integer | no | Abstract campaign time counter; `null` if not set |
| `date` | string | no | Real-world date in ISO 8601 format (`YYYY-MM-DD`); `null` if not recorded |
| `summary` | string | no | Session summary text |
| `notes` | string | no | GM notes |
| `participants` | list | no | Characters who attended; see [SessionParticipant](#sessionparticipant) |

#### SessionParticipant

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `character` | string | yes | Name ref to the participating character |
| `additional_contribution` | boolean | no | Meta-game bonus flag (+1 extra Plot at session start); defaults to `false` |

**Example** (`sessions/001-hoover-dam-attack.yaml`):

```yaml
number: 1
status: ended
time_now: 1
date: null
summary: "The campaign begins at Hoover Dam, where the PCs are drawn by magical omens."
participants:
  - character: "Alexander"
    additional_contribution: false
  - character: "Jan"
    additional_contribution: false
```

---

### Stories

**File**: `stories/<slug>.yaml`

A narrative story arc. Children are nested inline — there is no separate file per child arc. See [glossary: Story](../spec/glossary.md).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Story name |
| `summary` | string | no | Summary text |
| `status` | string | no | `"active"`, `"completed"`, or `"abandoned"`; defaults to `"active"` |
| `tags` | list | no | Freeform tag strings |
| `owners` | list | no | Game objects that own this story; see [StoryOwner](#storyowner) |
| `entries` | list | no | Narrative entries in chronological order; see [StoryEntry](#storyentry) |
| `children` | list | no | Nested child story arcs (each is a full Story — recursive) |

#### StoryOwner

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | yes | `"character"`, `"group"`, or `"location"` |
| `name` | string | yes | Name ref to the owning game object |

#### StoryEntry

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `text` | string | yes | Narrative content |
| `author` | string | yes | Display name ref to the user who wrote this entry |
| `character` | string | no | Name ref to the character this entry is written from; `null` if not linked |
| `session` | integer | no | Session number ref to link this entry to a specific session; `null` if not linked |

**Example** (`stories/blackout-murders.yaml`):

```yaml
name: "Blackout Murders"
summary: "A serial killing spree in downtown Las Vegas during power outages."
status: active
tags: ["murder", "kys", "investigation"]
owners:
  - type: group
    name: "Kali Yuga Supremacy"
  - type: group
    name: "Cult Crimes Task Force"
entries:
  - text: "Green cloth loop found on Tegan's car at the Hoover Dam garage."
    author: "GM"
    character: null
    session: 1
  - text: "Earl found murdered on Fremont Street during a blackout."
    author: "GM"
    character: null
    session: 11
children: []
```

---

## PC vs NPC Distinction

| Aspect | PC (full) | NPC / Entity (simplified) |
|--------|-----------|---------------------------|
| File location | `characters/pcs/` | `characters/npcs/` or `characters/entities/` |
| `detail_level` | `"full"` | `"simplified"` |
| Meters | `stress`, `free_time`, `plot`, `gnosis` | None |
| Skills | 8 skills (0–3) | None |
| Magic stats | 5 disciplines with level/xp | None |
| Core traits | Up to 2 slots | None |
| Role traits | Up to 3 slots | None |
| Magic effects | Supported | None |
| Bonds | `pc_bond` type — charges, degradations, trauma | `npc_bond` type — descriptive only |
| Bond slot limit | 8 | 7 |
| `attributes` blob | Supported | Supported |
| `secrets` field | Supported | Supported |

The `entities/` subdirectory is a semantic label (supernatural beings, objects, etc.) — it uses the identical `NPCCharacterYaml` schema as `npcs/`.
