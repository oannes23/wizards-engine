# Engine Spec — Narrative TTRPG State Tracker

A backend state tracker for a single narrative-heavy, low-crunch tabletop RPG campaign. This is **not** a dice roller or virtual tabletop — all rolling happens at the physical table. The system tracks character sheets, game world state, and provides a proposal workflow for player actions. API-first REST backend designed for a small fixed group (4–6 players + 1 GM), with a simple mobile-friendly web UI to follow.

---

## Character Sheet

Each player character (PC) has the following structure:

### Stress
- **Type**: Meter
- **Range**: TBD (e.g., 0–9)
- Tracks accumulated harm and pressure.

### Free Time
- **Type**: Resource meter
- **Range**: 0–20
- Spent on downtime activities between sessions.

### Plot
- **Type**: Resource meter
- **Range**: 0–5
- Narrative currency for influencing the story.

### Core Traits (2)
Each has:
- `name`: string
- `description`: string
- `charge`: meter, 0–5

Core Traits represent the character's defining qualities. When a Core Trait is relevant, add **+1d** to the related dice pool. Charges are spent to activate the bonus and replenished during downtime.

### Role Traits (3)
Same structure as Core Traits:
- `name`: string
- `description`: string
- `charge`: meter, 0–5

Role Traits represent learned skills, professional abilities, or situational expertise. Same +1d bonus mechanic as Core Traits.

### Bonds (7)
Each has:
- `name`: string
- `target`: reference to another game object (Character, Faction, Location, etc.)
- `level`: integer
- `stress`: mini stress meter (range TBD)

Bonds represent meaningful relationships. Higher-level bonds provide stronger mechanical boosts when invoked in proposals. Bond stress accumulates from strain on the relationship and can be healed during downtime.

### Skills
- Named skills at levels 0–3
- Typically max ~5 skills per character
- Skill level = base dice pool size for related actions

### Gnosis
- **Type**: Resource meter
- **Range**: 0–23
- Magical/mystical resource. Gained through study, ritual, or downtime. Spent on magical effects.

### Magic Stats (5)
Each has:
- `name`: string
- `level`: meter, 0–5
- `xp`: meter (range TBD per level)

Magic Stats represent different schools or aspects of magic. Level determines capability; XP tracks progress toward the next level.

### Magic Effects
List of known magical abilities. Each has:
- `name`: string
- `description`: string
- `power_level`: integer
- `charge`: meter (range varies)

Some effects are **permanent** — they have a power level but no charge meter. Permanent effects are always active and don't need to be activated or recharged.

### Notes
- Freeform text field
- Used for inventory, narrative notes, personal reminders, anything the player wants to track

---

## Game Objects

Everything tracked in the system is a game object. Each has an `id`, `name`, `description`, `created_at`, `updated_at`, and type-specific fields.

### Characters (PCs)
Full character sheet as described above. Owned by a specific player.

### NPCs
Simplified character records:
- `name`: string
- `description`: string
- `traits`: list of key trait names/descriptions (freeform, no charge mechanics)
- `stats`: freeform key-value pairs for any relevant mechanical info
- `notes`: text
- `factions`: references to Faction objects
- `location`: reference to a Location object

### Factions
- `name`: string
- `description`: string
- `tier`: integer (power/influence level)
- `project_clocks`: list of embedded Clock objects (see below)
- `relationships`: list of `{ target: Faction ref, nature: string }` — how this faction relates to others
- `notes`: text

### Clocks
Standalone progress trackers (BitD-style):
- `name`: string
- `segments`: integer (total segments, e.g., 4, 6, 8)
- `progress`: integer (filled segments, 0 to `segments`)
- `associated_with`: optional reference to a Faction, Story, or other game object
- `notes`: text

Clocks can be embedded in Factions (as project clocks) or exist independently.

### Locations
- `name`: string
- `description`: string
- `parent`: optional reference to another Location (nestable hierarchy)
- `notes`: text
- `factions`: references to Factions present here
- `npcs`: references to NPCs found here

### Sessions
- `date`: date
- `summary`: text
- `notes`: text
- `events`: references to Event log entries from this session

### Stories / Arcs
- `name`: string
- `summary`: text
- `owners`: references to Characters, Factions, or other game objects involved
- `status`: enum — `active`, `completed`, `abandoned`
- `parent`: optional reference to another Story (nestable hierarchy for sub-arcs)
- `notes`: text

---

## Architecture

### Mutable State + Event Log

Game state is **mutable** — when an action is approved, the relevant game objects are updated directly. This is simpler than event sourcing and appropriate for a single-game system.

An **append-only event log** records every state change for history and audit:
- Activity feed ("what happened recently")
- Session timeline reconstruction
- Undo capability (replay backward)

**State is the source of truth**, not the event log. Events are the history.

### Proposal Workflow

Player actions that change game state go through a proposal system:

1. **Player submits a proposal**: selects an action type (e.g., "Gain Gnosis"), writes a narrative paragraph describing what their character does in-fiction, and selects relevant traits/bonds/magic stats to boost the effect.

2. **Effect calculation**: the system calculates the result based on base effect + modifiers from selected traits/bonds. Example: 3 Gnosis base + 1 from Magic Stat + 2 from Bond level = 6 Gnosis gained.

3. **GM review**: GM sees the proposal with narrative, selections, and calculated effect. Can approve, reject, or request changes.

4. **On approval**: state changes apply (resources spent, resources gained), event logged.

5. **On rejection**: no state changes. Player can revise and resubmit.

**GM actions bypass proposals** — the GM can directly modify any game state without approval.

Some simple player actions (like editing their notes field) also bypass proposals — only mechanically significant actions require GM approval.

### No DSL or Expression System

All game logic — schemas, calculations, effect modifiers, computed fields — is hardcoded in Python. No configuration language, no expression evaluator, no YAML-driven schemas. This keeps the system simple and debuggable.

### Persistence

- **SQLite** single-file database
- **SQLAlchemy** models for all game objects and events
- **Alembic** for schema migrations
- **Pydantic** for request/response validation

---

## Downtime System

BitD-inspired downtime between sessions:

### Triggering Downtime

The GM triggers a "downtime phase" for the group. When downtime begins:

1. All active **faction project clocks** tick forward (advance by 1 segment each).
2. Any clocks that complete trigger consequences — the GM resolves these narratively and updates game state.
3. Each PC receives **Free Time** to spend on downtime activities.

### Downtime Activities

Players spend Free Time on activities submitted as proposals. Each costs some amount of Free Time and may be boosted by relevant traits/bonds:

- **Reset Trait charges** — restore spent charges on Core or Role Traits
- **Heal Bond stress** — reduce accumulated stress on a Bond
- **Regain Gnosis** — study, meditate, or perform rituals to gain Gnosis
- **Work on a project** — advance a personal Clock
- **Other activities** — structure defined per activity, specifics TBD as the game develops

Each downtime activity follows the standard proposal workflow: player describes the fiction, selects modifiers, GM reviews and approves.

---

## Actions & State Changes

### Player Actions (via Proposals)
Mechanically significant actions that require GM approval:
- Downtime activities (spend Free Time, recharge Traits, heal Bonds, gain Gnosis)
- Narrative actions with trait/bond selections that boost effects
- Spending or gaining significant resources

### Player Actions (Direct)
Low-stakes bookkeeping that doesn't need approval:
- Update character notes
- Minor edits the GM has pre-approved

### GM Actions (Direct, No Approval)
The GM can do anything without a proposal:
- Advance clocks
- Create/modify NPCs, Locations, Factions
- Trigger downtime phase
- Create and manage Story arcs
- Record session notes
- Adjust any character or game state
- Approve or reject player proposals

### Event Recording
Every approved state change — whether from a proposal or a direct GM action — creates an event record in the log.

---

## Event Log

Every mutation to game state produces an event record:

- `id`: unique identifier
- `type`: what kind of change (e.g., "gnosis_gained", "clock_advanced", "npc_created")
- `actor`: who did it (player or GM)
- `target`: what game object was affected
- `changes`: what specifically changed (before/after or delta)
- `narrative`: optional text describing the fiction
- `session_id`: optional link to a Session
- `timestamp`: when it happened

### Uses
- **Activity feed**: show recent changes to all players
- **Session timeline**: reconstruct what happened during a session
- **Undo**: reverse a specific change by applying the inverse
- **Audit**: understand how the game reached its current state

Events are **read-only** after creation. They are never modified or deleted.

---

## REST API

All endpoints under `/api/v1/`. Standard CRUD patterns with action-specific sub-routes.

### Characters
- `GET /characters` — list all PCs
- `GET /characters/{id}` — get full character sheet
- `POST /characters` — create new PC
- `PATCH /characters/{id}` — update character fields (GM or owner)
- `POST /characters/{id}/actions/{action}` — submit a character action as proposal

### Factions
- `GET /factions` — list all
- `GET /factions/{id}` — get faction detail with clocks and relationships
- `POST /factions` — create
- `PATCH /factions/{id}` — update
- `POST /factions/{id}/clocks` — add a project clock
- `PATCH /factions/{id}/clocks/{clock_id}` — advance/modify a clock

### Clocks
- `GET /clocks` — list standalone clocks
- `POST /clocks` — create
- `PATCH /clocks/{id}` — advance or modify
- `DELETE /clocks/{id}` — remove

### Locations
- `GET /locations` — list (supports `?parent={id}` for hierarchy)
- `POST /locations` — create
- `PATCH /locations/{id}` — update
- `DELETE /locations/{id}` — remove

### NPCs
- `GET /npcs` — list
- `POST /npcs` — create
- `PATCH /npcs/{id}` — update
- `DELETE /npcs/{id}` — remove

### Stories
- `GET /stories` — list (supports `?status=active`)
- `POST /stories` — create
- `PATCH /stories/{id}` — update (including status changes)

### Sessions
- `GET /sessions` — list
- `POST /sessions` — create
- `PATCH /sessions/{id}` — update
- `GET /sessions/{id}/timeline` — events that occurred during this session

### Events
- `GET /events` — list with filtering (`?actor=`, `?type=`, `?target=`, `?session=`, `?since=`)
- `GET /events/{id}` — single event detail
- Read-only — events are never created directly via API

### Proposals
- `GET /proposals` — list (`?status=pending`)
- `POST /proposals` — submit a new proposal (player)
- `GET /proposals/{id}` — proposal detail with calculated effects
- `POST /proposals/{id}/approve` — approve and apply (GM)
- `POST /proposals/{id}/reject` — reject with optional reason (GM)
- `PATCH /proposals/{id}` — revise a rejected proposal (player)

### Downtime
- `POST /downtime/trigger` — start downtime phase (GM): ticks faction clocks, distributes Free Time
- `GET /downtime/status` — current downtime state (active/inactive, Free Time remaining per PC)
- Downtime actions are submitted as proposals via `/proposals`

### Game
- `GET /game` — game settings, player roster
- `PATCH /game` — update settings (GM)
- `POST /game/invite` — generate invite link/code (GM)
- `POST /game/join` — join with invite code (player)

---

## Auth

Simple authentication for a small, fixed group:

- **GM creates the game** and receives an admin token.
- **GM generates invite links/codes** for players.
- **Players join** with an invite code and set up a simple identity (display name + secret token).
- **Auth tokens** are passed via header (`Authorization: Bearer <token>`).

### Permissions
- **GM**: full read/write access to everything. Can approve/reject proposals.
- **Players**: can read all public game state (characters, factions, locations, NPCs, stories, sessions, events). Can modify their own character (notes, direct actions). Can submit and revise proposals for their own character.

No external auth provider needed — this is a trusted small group.

---

## Tech Stack

- **Python 3.11+**
- **FastAPI** — REST API framework
- **SQLAlchemy** — ORM for game objects and event log
- **Pydantic** — request/response validation, schema definitions
- **SQLite** — single-file database, simple deployment
- **Alembic** — database migrations
- **pytest** — testing
