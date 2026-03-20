# Campaign Data

This directory contains the campaign's YAML data files. These files are the human-editable, version-control-friendly representation of everything in the game world — characters, factions, locations, sessions, and stories.

For the complete format reference, see [`docs/campaign-format.md`](../docs/campaign-format.md).

---

## What These Files Are

Each YAML file corresponds to a game object or system entity in the Wizards Engine database. The files are designed to be readable and editable by hand, and they use human-readable names for cross-references rather than database IDs.

When you run `wizards-campaign import`, the engine reads these files, validates them, and loads them into the database. When you run `wizards-campaign export`, it reads the database and writes fresh copies of these files.

---

## Directory Layout

```
campaign-data/
  meta.yaml              # Campaign name and format version
  trait-templates/       # Reusable Core and Role trait definitions
  locations/             # Locations in nested directory hierarchy
  characters/
    pcs/                 # Player characters (full mechanical detail)
    npcs/                # Non-player characters (simplified)
    entities/            # Supernatural beings (simplified)
  groups/                # Factions, organizations, crews
  clocks/                # Progress clocks
  users/                 # Player and GM accounts
  sessions/              # Session records (numbered for ordering)
  stories/               # Narrative story arcs
```

---

## How to Edit Campaign Data

### Adding a new NPC

1. Create a file in `characters/npcs/<slug>.yaml`. Use lowercase, hyphen-separated names.
2. Give it at minimum a `name` and optionally a `description`.
3. Add bonds to connect the NPC to other game objects using `{type, name}` references.
4. Run `wizards-campaign validate --input ./campaign-data/` to check for errors.

**Minimal NPC example**:

```yaml
name: The Stranger
detail_level: simplified
description: A figure seen near the warehouse before the blackout.
bonds:
  - name: Witnessed At
    target:
      type: location
      name: The Warehouse
```

### Adding a new PC

PC files live in `characters/pcs/` and require a full set of mechanical fields: `meters`, `skills`, `magic_stats`, plus lists for `core_traits`, `role_traits`, `bonds`, and `magic_effects`. See [`docs/campaign-format.md`](../docs/campaign-format.md) for the complete field reference and an example.

### Adding a location

Locations use directory nesting to represent parent-child hierarchy. A location named "Rebar" inside Las Vegas goes here:

```
locations/
  las-vegas/
    _location.yaml          # Already exists
    rebar/
      _location.yaml        # Create this file
```

The parent is inferred automatically from the directory structure. Name the `name` field in the YAML file exactly as you want it to appear in cross-references.

### Adding a group

Create `groups/<slug>.yaml`. Groups can have `traits` (descriptive), `relations` (group-to-group), and `holdings` (group-to-location).

### Adding a session

Create `sessions/<number>-<slug>.yaml`. Use a three-digit padded number (e.g. `028-the-earthquake.yaml`) so files sort correctly. The `number` field in the YAML must match.

### Editing existing entities

Edit the YAML field values directly. Cross-references use the `name` field of the target entity — if you rename an entity, update all references to it across every file.

---

## Validating Changes

Before importing, always validate:

```
uv run wizards-campaign validate --input ./campaign-data/
```

This runs a two-pass check:

1. **Schema pass** — validates every field against the expected types and allowed values.
2. **Reference pass** — checks that every cross-reference (`target.name`, `template`, `character`, etc.) points to an entity that actually exists.

Errors are printed to stderr in this format:

```
characters/npcs/harry.yaml:bonds[0].target.name: Unresolved reference: 'Jan' (type: character)
```

Fix the error indicated, then re-run until you see:

```
Campaign is valid. No errors found.
```

---

## Importing Into the Engine

Once validation passes, import into a fresh database:

```
uv run wizards-campaign import --input ./campaign-data/
```

To preview what would be created without touching the database:

```
uv run wizards-campaign import --input ./campaign-data/ --dry-run
```

To import into a database that already has data (adds alongside existing rows):

```
uv run wizards-campaign import --input ./campaign-data/ --force
```

The import is atomic — if anything fails, the database is left unchanged.

---

## Exporting From the Engine

To export the current database state back to YAML:

```
uv run wizards-campaign export --output ./campaign-data/
```

This overwrites the existing YAML files. Commit the result to version control to snapshot the campaign state.

---

## Key Rules to Remember

- **Names are cross-reference keys.** Every entity name must be unique within its type (characters, groups, locations, etc.). If you change a name, update every reference to it.
- **The `secrets` field is import-only.** On import, `secrets` content is appended to the `notes` column in the database. Export writes `notes` back, not a separate `secrets` field.
- **Location parents come from directory structure.** Do not set the `parent` field in `_location.yaml` unless you need to override what the directory structure implies.
- **Session files are ordered by their `number` field**, not by filename — but use numbered filenames anyway for clarity.
- **Stories nest children inline.** Sub-arcs go in the `children` list of their parent story YAML — no separate file needed.
- **Users get new login codes on every import.** Login codes are never stored in YAML. After importing, retrieve codes from the database or the API.

---

## Full Reference

See [`docs/campaign-format.md`](../docs/campaign-format.md) for:
- Complete field tables for every entity type
- Valid values for every enumerated field
- The 6-phase import ordering rules
- All CLI flags
- Secrets handling details
