# UX Walkthrough — Narrative User Journeys

**Status**: 🟡 Draft (awaiting review)
**Purpose**: Validate that spec decisions produce a coherent, usable experience before implementation.
**Source**: Synthesized from all 14 domain/architecture specs.

---

## How to Read This Document

Each journey is a step-by-step walkthrough of what a user sees and does. Screens are described in terms of data and actions — not visual layout. API endpoints and spec references are noted inline for traceability.

---

## Part 1: Player Journey

### 1.1 — First Contact: The Magic Link

The GM sends you a URL via text message: `https://wizards.example/login/01HXYZ...`

You open it in your phone browser. The frontend calls `POST /api/v1/auth/login` with the code. The server recognizes an unconsumed invite and returns `{type: "invite"}`. No cookie is set yet.

**You see: A join form.** Two fields:
- **Your name** (display name — what other players see, 1–50 chars)
- **Character name** (your PC's name)

You fill in both and submit. The frontend calls `POST /api/v1/game/join` with `{code, character_name, display_name}`.

Behind the scenes, the system atomically:
- Creates your User account (login code = the invite code you just used)
- Creates a full Character with all mechanical fields at 0 (stress 0, FT 0, plot 0, gnosis 0, all 8 skills at level 0, all 5 magic stats at level 0)
- Links User → Character (1:1)
- Sets an httpOnly cookie in your browser

**You see: The app.** You're logged in. The same URL (`/login/01HXYZ...`) is now your permanent login link — bookmark it.

> **Spec refs**: [auth.md](domains/auth.md) — Bare Invite Flow, Magic Link Auth, Cookie-Only API Auth

---

### 1.2 — Your Character Sheet (Fresh)

You land on your character sheet (`GET /api/v1/characters/{id}`). Everything is at zero — the GM will set you up.

**You see:**

**Identity** (editable by you):
- Name: "Kael"
- Description: *(empty — you can write this anytime)*
- Notes: *(empty — your freeform scratchpad: inventory, personal reminders, anything)*

**Resource Meters** (all 0):
| Meter | Value | Max |
|-------|-------|-----|
| Stress | 0 | 9 |
| Free Time | 0 | 20 |
| Plot | 0 | 5 |
| Gnosis | 0 | 23 |

**Traits** (all blank slots):
- Core Traits: 2 empty slots
- Role Traits: 3 empty slots

**Bonds** (all blank):
- 8 empty bond slots

**Skills** (all level 0):
> Awareness 0, Composure 0, Influence 0, Finesse 0, Speed 0, Power 0, Knowledge 0, Technology 0

**Magic Stats** (all level 0, 0 XP):
> Being 0, Wyrding 0, Summoning 0, Enchanting 0, Dreaming 0

**Magic Effects**: None (cap: 0/9)

**Locations** (computed from bond graph):
- Common: *(none — no bonds yet)*
- Familiar: *(none)*
- Known: *(none)*

**Session History**: *(none)*

The GM will use `POST /api/v1/gm/actions` (with action types like `modify_character`, `create_trait`, `create_bond`) to set your initial skill levels, assign traits from the Trait Template catalog, establish your starting bonds, and set your starting meters. You don't need to understand any of this — the GM handles setup.

> **Spec refs**: [character-core.md](domains/character-core.md) — PC Creation, Sheet API; [traits.md](domains/traits.md) — Trait Setup; [bonds.md](domains/bonds.md) — Bond Lifecycle

---

### 1.3 — Your Character Sheet (After GM Setup)

After the GM finishes setup, your sheet has substance:

**Resource Meters**:
| Meter | Value | Max |
|-------|-------|-----|
| Stress | 0 | 9 |
| Free Time | 0 | 20 |
| Plot | 0 | 5 |
| Gnosis | 10 | 23 |

**Core Traits** (2/2 filled):
1. "Relentless" — 5/5 charges — *A defining quality: you never stop.*
2. "Empathic" — 5/5 charges — *You feel what others feel.*

**Role Traits** (3/3 filled):
1. "Street Alchemist" — 5/5 charges
2. "Gutter Runner" — 5/5 charges
3. "Silver Tongue" — 5/5 charges

**Bonds** (4/8 filled):
1. Mira (NPC) — *"My oldest friend"* — Stress: 0/5
2. The Ashen Circle (Group) — *"My crew, my family"* — Stress: 0/5
3. The Warrens (Location) — *"Where I grew up"* — Stress: 0/5
4. Dax (PC — another player's character) — *"We survived the Fall together"* — Stress: 0/5

**Skills**: Awareness 2, Composure 1, Influence 2, Finesse 1, Speed 2, Power 0, Knowledge 1, Technology 0

**Magic Stats**: Being 1, Wyrding 0, Summoning 0, Enchanting 0, Dreaming 1

**Locations** (computed from bonds):
- Common: The Warrens *(direct bond)*
- Familiar: The Forge *(Mira is bonded there)*, Guild Hall *(Ashen Circle holding)*
- Known: The Market District *(2 hops through other characters)*

---

### 1.4 — Browsing the World

You can read all public game objects.

**Characters** (`GET /api/v1/characters`):
- Filter by `?detail_level=full` (PCs only) or `?detail_level=simplified` (NPCs only)
- See any character's full sheet (within your visibility — everything for PCs and NPCs is readable)

**Groups** (`GET /api/v1/groups/{id}`):
- Name, description, tier, project clocks, 10 descriptive traits
- Computed members (all Characters bonded to this Group)
- Relations (Group↔Group bonds), Holdings (Group→Location bonds)

**Locations** (`GET /api/v1/locations`):
- Nestable hierarchy — filter by `?parent={id}` for children
- 5 Feature Traits (e.g., "Heavily Fortified", "Thick Fog", "Sacred Ground")
- Bond-distance presence: who's commonly/often/sometimes here (computed from bond graph)

**Stories** (`GET /api/v1/stories` — visibility-filtered):
- You only see Stories you're connected to via the bond graph (default: `familiar` = 2-hop)
- Active, completed, or abandoned status
- Entries — narrative progress notes (you can add entries to any Story you can see)

**Clocks** (`GET /api/v1/clocks`):
- Progress bars with segments
- Associated with a Game Object (usually a Group project)

**Player Roster** (`GET /api/v1/players`):
- Display names, roles, linked characters
- *(No login URLs — those are GM-only)*

> **Spec refs**: [game-objects.md](domains/game-objects.md), [feed.md](domains/feed.md) — Story Visibility

---

### 1.5 — Session Day: Joining a Session

The GM creates a Draft session. You see it listed (`GET /api/v1/sessions`).

**You see:**
- Session #5 — Status: Draft
- Date: 2026-03-14
- Time Now: 12 *(abstract campaign time — GM sets this)*
- Summary: "The crew investigates the disappearances in the Market District"

**You register** (`POST /api/v1/sessions/{id}/participants`):
```json
{
  "character_id": "01HKAEL...",
  "additional_contribution": true
}
```
You checked "Additional Contribution" because you wrote last session's recap. This gives you +2 Plot instead of +1 when the session starts.

The contribution flag is editable while the session is in Draft. Once the GM hits Start, it locks.

> **Spec refs**: [downtime.md](domains/downtime.md) — Session Participants, Additional Contribution

---

### 1.6 — Session Starts: Resources Arrive

The GM hits Start Session (`POST /api/v1/sessions/{id}/start`). The system automatically distributes resources to all registered participants:

**Free Time**: Your `last_session_time_now` was 8 (from session #4). This session's Time Now is 12. Delta = 4. Your FT goes from 3 → 7 (3 + 4, capped at 20).

**Plot**: You checked Additional Contribution, so you get +2 Plot. Your Plot goes from 1 → 3.

These changes happen silently — the distribution events have `silent` visibility (only the GM sees them in the silent feed). You just see your updated meters on your character sheet.

Only one session can be Active at a time. The session is now live.

> **Spec refs**: [downtime.md](domains/downtime.md) — Free Time Distribution, Plot Income, Session Start Decomposition

---

### 1.7 — Submitting a Proposal (Skill Action)

During the session, your character tries to sneak past guards. At the table, you describe what you're doing. Then you formalize it in the system.

**You submit a proposal** (`POST /api/v1/proposals`):
```json
{
  "character_id": "01HKAEL...",
  "action_type": "use_skill",
  "narrative": "Kael slips through the shadows along the canal wall, timing his movements to the rhythm of the guard patrol. He pulls his cloak tight and presses into the alcove as the lantern swings past.",
  "details": { "skill": "finesse" },
  "modifiers": {
    "role_trait_id": "01HGUTTER...",
    "bond_id": "01HWARRENS..."
  },
  "plot_spend": 1
}
```

**What you selected:**
- Skill: Finesse (level 1 → 1 base die)
- Role Trait: "Gutter Runner" (+1d, costs 1 charge)
- Bond: "The Warrens" (+1d — you know these streets)
- Plot: 1 (places one guaranteed 6 before rolling)

**The system calculates** and stores `calculated_effect`:
```
{
  dice_pool: 3,        // 1 (Finesse) + 1 (trait) + 1 (bond)
  modifiers: [...],
  costs: {
    trait_charges: [{trait_id: "01HGUTTER...", charge_cost: 1}],
    plot: 1
  }
}
```

Total: 3 dice + 1 guaranteed 6. The GM sees this, rolls 3 dice at the table, and decides the outcome.

Your proposal status is `pending`.

> **Spec refs**: [actions.md](domains/actions.md) — Proposal Workflow, Dice Pool Calculations, Modifier Stacking

---

### 1.8 — GM Approves Your Proposal

The GM reviews your proposal. They see your narrative, the dice pool calculation, and the costs. They roll at the table — it goes well.

The GM approves (`POST /api/v1/proposals/{id}/approve`):
```json
{
  "bond_strained": false,
  "rider_event": {
    "targets": [{"type": "character", "id": "01HNPCGUARD..."}],
    "changes": {"character.01HNPCGUARD.stress": {"op": "meter.delta", "before": 0, "after": 2}},
    "narrative": "The guard captain grows suspicious — someone has been here.",
    "visibility": "bonded"
  }
}
```

The GM didn't override your narrative (no `gm_narrative`), so your words become the event narrative. They attached a rider event — a side effect affecting an NPC guard.

**What happens automatically:**
- "Gutter Runner" charge: 5 → 4
- Plot: 3 → 2
- One event created: `proposal.approved` (your proposal, bonded visibility)
- One rider event created: NPC guard stress changed (linked via `parent_event_id`)
- Both auto-tagged with the Active session's ID

Your proposal status is now `approved`.

> **Spec refs**: [actions.md](domains/actions.md) — GM Approval Payload, Rider Events; [events.md](domains/events.md) — One Event Per Action

---

### 1.9 — Submitting a Magic Action

Later, you want to cast a spell. You describe the magic freeform — there's no spell list.

**You submit** (`POST /api/v1/proposals`):
```json
{
  "character_id": "01HKAEL...",
  "action_type": "use_magic",
  "narrative": "Kael draws a spiral in the dust with his finger, whispering the name of the Warrens into the pattern. The shadows twist and pool around him, forming a cloak of living darkness.",
  "details": {
    "intention": "Create a cloak of shadow that conceals me from sight",
    "symbolism": "Drawing the spiral — the Warrens' old ward-sign — as a channel for the shadow magic",
    "sacrifice_list": [
      {"type": "gnosis", "amount": 6},
      {"type": "stress", "amount": 1}
    ],
    "suggested_stat": "wyrding"
  },
  "modifiers": {
    "core_trait_id": "01HRELENT...",
    "bond_id": "01HWARRENS..."
  },
  "plot_spend": 0
}
```

**Sacrifice breakdown:**
- 6 Gnosis (direct, 1:1) = 6 Gnosis equivalent
- 1 Stress (1 Stress = 2 Gnosis equivalent) = 2 Gnosis equivalent
- Total: 8 Gnosis equivalent → tiered conversion → 3 sacrifice dice (6 Gnosis buys 3 dice, leaving 2 Gnosis worth — rounded or GM decides)

**Dice pool**: Wyrding 0 (level) + 3 (sacrifice dice) + 2 (modifiers: Core Trait + Bond) = 5 dice total

The GM reviews, may add a hidden style bonus for creative symbolism, rolls at the table, and decides the outcome.

If approved, the GM creates a Magic Effect on your sheet:
```json
{
  "effect_details": {
    "name": "Cloak of Living Darkness",
    "description": "Shadows wrap around you, making you nearly invisible in dim light.",
    "type": "charged",
    "power_level": 3,
    "charges_max": 4
  }
}
```

**Result on your sheet:**
- Gnosis: 10 → 4
- Stress: 0 → 1
- "Relentless" charge: 5 → 4
- New Magic Effect: "Cloak of Living Darkness" — 4/4 charges, power 3

> **Spec refs**: [magic-system.md](domains/magic-system.md) — Magic Action, Sacrifice, Effect Creation; [actions.md](domains/actions.md) — use_magic

---

### 1.10 — Using a Magic Effect (Direct Action)

You want to activate your Cloak of Living Darkness. This is a **direct player action** — no proposal needed, no GM approval.

`POST /api/v1/characters/{id}/effects/{effect_id}/use`:
```json
{
  "narrative": "Kael pulls the darkness around himself like a second skin."
}
```

One charge is decremented (4 → 3). An `magic.effect_used` event is logged with your narrative. Done.

If you no longer want an effect, you can self-retire it (`POST /characters/{id}/effects/{effect_id}/retire`) — also no approval needed. It moves to Past and frees cap space.

> **Spec refs**: [magic-system.md](domains/magic-system.md) — Direct Effect Use, Player Can Self-Retire

---

### 1.11 — Downtime: Spending Free Time

You have 7 FT. Downtime proposals can be submitted anytime you have FT — there's no "downtime mode."

**All downtime actions require a narrative** — a description of what your character is doing in the fiction to accomplish this. Even mundane activities need at least a sentence ("slept all day", "meditated by the canal"). The narrative is the proposal's `narrative` field and becomes part of the event log.

**Rest** (heal stress):
```json
{
  "action_type": "rest",
  "narrative": "Kael finds a quiet corner in the Warrens and sleeps for the first time in days.",
  "modifiers": { "bond_id": "01HWARRENS..." }
}
```
Calculated: 3 base + 1 (Bond modifier) = 4 Stress healed. Costs 1 FT.

**Recharge Trait** (restore charges):
```json
{
  "action_type": "recharge_trait",
  "narrative": "Kael spends the morning running the rooftop circuit — the old training route from when he first learned to move.",
  "details": { "trait_instance_id": "01HGUTTER..." }
}
```
"Gutter Runner" charges: 4 → 5. Costs 1 FT.

**Regain Gnosis** (recover magical energy):
```json
{
  "action_type": "regain_gnosis",
  "narrative": "Kael sits with Mira in the garden behind her shop, letting the silence settle. He feels the old currents stir.",
  "modifiers": { "core_trait_id": "01HEMPATHIC...", "bond_id": "01HMIRA..." }
}
```
Calculated: 3 base + 0 (lowest Magic Stat = Wyrding 0) + 2 (modifiers) = 5 Gnosis regained. Costs 1 FT.

**Maintain Bond** (heal bond stress):
```json
{
  "action_type": "maintain_bond",
  "narrative": "Kael walks the old paths through the Warrens alone, remembering why this place matters.",
  "details": { "bond_instance_id": "01HWARRENS..." }
}
```
The Warrens bond stress → 0. Costs 1 FT.

**New Bond** (add or replace):
```json
{
  "action_type": "new_bond",
  "narrative": "After everything that happened in the Market District, Kael realizes the shopkeeper Solin saved his life. That kind of debt doesn't go unforgotten.",
  "details": {
    "target_type": "character",
    "target_id": "01HSOLIN..."
  }
}
```
You have 4/8 bonds, so this fills a blank slot (no `retire_bond_id` needed). Costs 1 FT.

**Work on Project** (advance a Story):
```json
{
  "action_type": "work_on_project",
  "narrative": "Kael spends an evening practicing his awareness drills, watching the crowds from the rooftops.",
  "details": { "story_id": "01HSTORY_AWARENESS_TRAINING..." }
}
```
Adds your narrative as an entry to the Story. The GM resolves skill-ups when the fiction warrants it. Costs 1 FT.

All of these go through the proposal workflow — GM reviews and approves each one.

> **Spec refs**: [actions.md](domains/actions.md) — Downtime Actions; [downtime.md](domains/downtime.md) — No Downtime Mode

---

### 1.12 — Find Time (Direct Action)

You're at 5 Plot and a new session is about to start. Incoming Plot will push you above 5, and excess is clamped at Session End. Convert some now.

`POST /api/v1/characters/{id}/find-time` *(empty body)*

3 Plot → 1 FT. No proposal needed, no GM approval. Event logged.

You can do this multiple times (each converts exactly 3 Plot → 1 FT).

> **Spec refs**: [downtime.md](domains/downtime.md) — Find Time

---

### 1.13 — Your Feed

`GET /api/v1/me/feed` — your complete personal feed.

**You see a chronological stream** of events and story entries, filtered by your bond-graph visibility:
- `event` items: proposals approved, character changes, clock advances, session starts/ends
- `story_entry` items: narrative entries on Stories you can see

Each item has:
- `type`: `"event"` or `"story_entry"`
- `narrative`: the text of what happened
- `targets`: which Game Objects were involved
- `is_own`: true if you caused this
- `visibility`: the level this item was published at

**What you don't see**: `silent` events (bookkeeping), `gm_only` events, events involving entities beyond your 3-hop bond-graph reach.

**Filtering**: `?type=character.*` (character events only), `?session_id=...` (this session), `?target_id=...` (specific entity).

**Pagination**: ULID cursor — `?after=<ulid>&limit=50`. Response: `{items, next_cursor, has_more}`.

> **Spec refs**: [feed.md](domains/feed.md) — Feed Endpoints, Unified Visibility Model

---

### 1.14 — Starring and the Starred Feed

You want to track the Ashen Circle closely.

**Star it**: `POST /api/v1/me/starred` → `{type: "group", id: "01HASHEN..."}`

**Check your starred feed**: `GET /api/v1/me/feed/starred`

This returns the same feed items as `/me/feed`, but filtered to only events and story entries involving your starred Game Objects. A focused view.

**Manage stars**: `GET /api/v1/me/starred` (list), `DELETE /api/v1/me/starred/group/01HASHEN...` (unstar).

> **Spec refs**: [feed.md](domains/feed.md) — Starring API, Starred Feed

---

### 1.15 — Contributing to a Story

You can see the Story "The Market District Disappearances" (you're connected via bonds — familiar visibility). Since you can see it, you can write in it.

**Add an entry**: `POST /api/v1/stories/{id}/entries`
```json
{
  "text": "Kael notices the missing people all had one thing in common — they shopped at Solin's on the same day."
}
```

The entry appears in the Story and in feeds for anyone who can see this Story. You can edit your own entries; the GM can edit any.

> **Spec refs**: [game-objects.md](domains/game-objects.md) — Story Entry Access (See = Write)

---

### 1.16 — Refreshing Your Login Link

If you accidentally share your magic link or suspect it's compromised:

`POST /api/v1/me/refresh-link`

A new login code is generated, your cookie is updated, and the old link stops working immediately. You get back the new magic link URL — bookmark the new one.

> **Spec refs**: [auth.md](domains/auth.md) — Player Self-Refresh

---

## Part 2: GM Journey

### 2.1 — First-Run Setup

You start the server on your VPS. No database, no accounts — fresh.

`POST /api/v1/setup` with `{display_name: "Marcus"}`.

The system:
- Creates your GM account (role: `gm`)
- Generates a login code
- Sets the auth cookie
- Returns your magic link URL

**This endpoint locks permanently.** If anyone calls it again, it returns `409 Conflict`. The DB check (does a GM user exist?) is the lock.

**You see**: Your GM dashboard. You're displayed as "GM Marcus." Save your magic link — it's your permanent login.

> **Spec refs**: [auth.md](domains/auth.md) — First-Run Setup, GM as Privileged Player

---

### 2.2 — Inviting Players

**Generate an invite**: `POST /api/v1/game/invites`

The response includes the invite code (a ULID) and the magic link URL. You text the link to your player.

The invite is **bare** — not linked to a character yet. The player names their own character when they join.

**Manage invites**: `GET /api/v1/game/invites` (list consumed and unconsumed), `DELETE /api/v1/game/invites/{id}` (delete an unconsumed invite).

You generate 5 invites for your 5 players. Share the links via text, email, or however you like.

> **Spec refs**: [auth.md](domains/auth.md) — Bare Invite Flow, Invite & Character Lifecycle

---

### 2.3 — The Player Roster

`GET /api/v1/players`

As the GM, you see everything:

| Name | Role | Character | Login URL |
|------|------|-----------|-----------|
| GM Marcus | gm | *(none)* | /login/01H... |
| Alex | player | Kael | /login/01HXYZ... |
| Sam | player | Lyra | /login/01HABC... |
| Jordan | player | Thren | /login/01HDEF... |
| ... | ... | ... | ... |

Players see the same list but without the Login URL column.

If a player loses access, you can regenerate their token: `POST /api/v1/players/{id}/regenerate-token` — returns a new magic link to share with them. Their old link stops working immediately.

> **Spec refs**: [auth.md](domains/auth.md) — Player Roster Visibility, Token Regeneration

---

### 2.4 — World-Building: Creating Game Objects

**Create an NPC** (`POST /api/v1/characters`):
```json
{
  "name": "Solin the Shopkeeper",
  "description": "A nervous man with ink-stained fingers who runs a curiosity shop in the Market District."
}
```
Always `simplified` detail level. 7 descriptive bond slots, no meters or skills.

**Create a Group** (`POST /api/v1/groups`):
```json
{
  "name": "The Ashen Circle",
  "description": "A crew of street-level operators who look out for each other.",
  "tier": 1
}
```
10 descriptive trait slots, 7 Relations slots, unlimited Holdings.

**Create a Location** (`POST /api/v1/locations`):
```json
{
  "name": "The Warrens",
  "description": "A tangled network of alleys and rooftop paths in the old city.",
  "parent_id": "01HOLDCITY..."
}
```
5 Feature Trait slots, unlimited bonds, nestable hierarchy.

**Create a Clock** (`POST /api/v1/groups/{id}/clocks`):
```json
{
  "name": "Expanding Territory",
  "segments": 6
}
```
Auto-associated with the Group. Progress starts at 0.

**Create a Story** (`POST /api/v1/stories`):
```json
{
  "name": "The Market District Disappearances",
  "summary": "People have been vanishing from the Market District.",
  "tags": ["mystery", "market-district"],
  "owners": [{"type": "location", "id": "01HMARKET..."}]
}
```

All world objects are GM-only for creation and mechanical changes. Players have read-only access.

> **Spec refs**: [game-objects.md](domains/game-objects.md) — GM Ownership of World Objects

---

### 2.5 — Setting Up a Character

After a player joins, their sheet is all zeros. You set them up with GM actions (`POST /api/v1/gm/actions`):

**Set starting meters**:
```json
{
  "action_type": "modify_character",
  "targets": [{"type": "character", "id": "01HKAEL..."}],
  "changes": {"gnosis": 10, "skills": {"awareness": 2, "composure": 1, "influence": 2, "finesse": 1, "speed": 2, "knowledge": 1}},
  "narrative": "Kael's initial character setup."
}
```

**Create the Trait Template catalog** (if it doesn't exist yet):
`POST /api/v1/trait_templates` → `{name: "Relentless", description: "You never stop.", type: "core"}`

**Assign traits to the character**:
```json
{
  "action_type": "create_trait",
  "targets": [{"type": "character", "id": "01HKAEL..."}],
  "changes": {"template_id": "01HRELENT...", "slot_type": "core_trait"},
  "narrative": "Kael's defining quality: relentless."
}
```
Starts at 5/5 charges.

**Create bonds**:
```json
{
  "action_type": "create_bond",
  "targets": [{"type": "character", "id": "01HKAEL..."}],
  "changes": {"target_type": "character", "target_id": "01HMIRA...", "source_label": "My oldest friend", "target_label": "My wild card"},
  "narrative": "Kael and Mira go way back."
}
```
Bidirectional by default (Character↔Character). Both Kael and Mira see this bond in their bond lists.

> **Spec refs**: [actions.md](domains/actions.md) — GM Action Type Catalog; [traits.md](domains/traits.md) — Trait Template Catalog

---

### 2.6 — Managing Traits on World Objects

**Group traits** — set descriptive traits on the Ashen Circle:
```json
{
  "action_type": "create_trait",
  "targets": [{"type": "group", "id": "01HASHEN..."}],
  "changes": {"name": "Street Smart", "description": "The crew knows every back alley and shortcut in the old city.", "slot_type": "group_trait"},
  "narrative": "The Ashen Circle's defining trait."
}
```

**Location Feature traits** — set features on the Warrens:
```json
{
  "action_type": "create_trait",
  "targets": [{"type": "location", "id": "01HWARRENS..."}],
  "changes": {"name": "Labyrinthine", "description": "Outsiders get lost in minutes. Locals navigate by instinct.", "slot_type": "feature_trait"},
  "narrative": "The Warrens' defining feature."
}
```

Group and Location traits are freeform — no Trait Template catalog, just name + description. Simple replace when you want to change them (overwrite, no Past/Retired pattern).

> **Spec refs**: [traits.md](domains/traits.md) — Group Traits, Location Feature Traits

---

### 2.7 — Creating and Running a Session

**Create a Draft session** (`POST /api/v1/sessions`):
```json
{
  "time_now": 12,
  "date": "2026-03-14",
  "summary": "The crew investigates the disappearances in the Market District."
}
```

Time Now must be ≥ the last ended session's Time Now. The delta from each character's `last_session_time_now` determines FT.

**Players self-register** (or you add them). You can see and manage the participant list.

**Start the session** (`POST /api/v1/sessions/{id}/start`):
- System distributes FT and Plot to all registered participants
- Contribution flags lock
- Session goes Active (only one can be Active at a time)
- Three events generated: `session.started` (global), `session.ft_distributed` (silent), `session.plot_distributed` (silent)

**During the session**: Players submit proposals. You review and approve/reject them.

**Adjust clocks** — during the Active session, adjust group project clocks individually:
```json
{
  "action_type": "modify_clock",
  "targets": [{"type": "clock", "id": "01HCLOCK..."}],
  "changes": {"progress_delta": 2},
  "narrative": "The crew made major progress on expanding territory this session.",
  "metadata": {
    "notes": "Based on the successful infiltration of the trade guild.",
    "related_events": ["01HEVENT_INFILTRATION..."]
  }
}
```

**End the session** (`POST /api/v1/sessions/{id}/end`):
- Status transitions to Ended (read-only)
- All participants' Plot is clamped to 5

**Late joins**: If a player arrives late, add them to the Active session — they get FT/Plot immediately.

> **Spec refs**: [downtime.md](domains/downtime.md) — Session Lifecycle, Clock Adjustments; [events.md](domains/events.md) — Session Start Decomposition

---

### 2.8 — Reviewing and Approving Proposals

`GET /api/v1/proposals?status=pending`

**You see each proposal with**:
- Player's narrative (their description of what they're doing)
- Action type and selections (which skill/trait/bond, any sacrifice)
- `calculated_effect`: the pre-computed result (dice pool, costs, outcomes)

**For a simple approval** — the calculation looks right, you rolled the dice, it went fine:
```json
{
  "gm_narrative": null,
  "bond_strained": false
}
```
Player's narrative becomes the event narrative. Costs are auto-deducted. Done.

**For an approval with overrides** — the GM decides to modify the outcome:
```json
{
  "gm_narrative": "Kael's attempt partially succeeds — he gets through the gate but is noticed by the sentry.",
  "overrides": {"costs": {"gnosis": 3}},
  "bond_strained": true
}
```
The Gnosis cost is reduced from calculated to 3. The bond used as a modifier gets +1 stress.

**For a rejection**:
```json
{
  "rejection_note": "The guard captain wouldn't be there at this time of night — can you adjust the narrative?"
}
```
The player edits their proposal (PATCHes it), system recalculates, status reverts to `pending`.

**Force approval**: If the player can no longer afford the costs (spent resources on another proposal between submission and approval), the system returns `409 Conflict`. Retry with `"force": true` to override.

> **Spec refs**: [actions.md](domains/actions.md) — GM Approval Payload, Revision Flow, Resource Validation

---

### 2.9 — GM Direct Actions

Any mechanical state change goes through `POST /api/v1/gm/actions`. CRUD endpoints (PATCH) only handle name, description, and notes.

**Change a character's stress**:
```json
{
  "action_type": "modify_character",
  "targets": [{"type": "character", "id": "01HKAEL..."}],
  "changes": {"stress": 5},
  "narrative": "The explosion catches Kael off guard."
}
```

**Award Magic Stat XP**:
```json
{
  "action_type": "award_xp",
  "targets": [{"type": "character", "id": "01HKAEL..."}],
  "changes": {"magic_stat": "being", "xp": 2},
  "narrative": "Kael's connection to Being deepens."
}
```
Level-up is automatic when XP reaches the threshold (5 per level).

**Create a Magic Effect directly** (not via a Magic Action proposal):
```json
{
  "action_type": "create_effect",
  "targets": [{"type": "character", "id": "01HKAEL..."}],
  "changes": {"name": "Warded Cloak", "description": "An enchanted cloak that deflects minor hexes.", "type": "permanent", "power_level": 2},
  "narrative": "The enchanter in the market owed Kael a favor."
}
```

**Validation is integrity-only**: The system checks data types and valid references but not game-logic ranges. You can set Stress to 15 if the fiction demands it.

All GM actions produce events with `actor_type: "gm"` and domain event types (e.g., `character.stress_changed`, not `gm.modify_character`).

> **Spec refs**: [actions.md](domains/actions.md) — GM Actions, Integrity-Only Validation, GM Action Event Types

---

### 2.10 — Clock Completion and Resolution

A Group's project clock hits its segment count. The system automatically:
1. Creates a `clock.completed` event (bonded visibility)
2. Auto-generates a `resolve_clock` proposal in pending state
3. Creates a `clock.resolve_generated` event (silent — only you see this)

**You see the pending resolve_clock proposal**. It has:
- The clock details (name, associated Group)
- An auto-generated narrative stub
- `calculated_effect: {}` — nothing to compute; you define the outcome

**You approve with narrative and a rider event**:
```json
{
  "gm_narrative": "The Ashen Circle's territorial expansion succeeds — they now control the canal docks. Rival crews take notice.",
  "rider_event": {
    "targets": [{"type": "group", "id": "01HASHEN..."}, {"type": "location", "id": "01HDOCKS..."}],
    "changes": {"group.01HASHEN.tier": {"op": "meter.delta", "before": 1, "after": 2}},
    "narrative": "The Ashen Circle's tier increases as they claim the canal docks.",
    "visibility": "public"
  }
}
```

This is **Deferred Narrative Resolution** in action — the clock tracked mechanical progress, but the outcome was only defined when it completed.

The resolve_clock proposal is one-per-clock, ever. Further clock advances (soft cap) don't generate new proposals.

> **Spec refs**: [game-objects.md](domains/game-objects.md) — Clock Completion, Deferred Narrative Resolution; [actions.md](domains/actions.md) — resolve_clock

---

### 2.11 — The GM Feeds

**Your normal feed** (`GET /api/v1/me/feed`):
You see everything at all visibility levels — `global`, `public`, `familiar`, `bonded`, `private`, `gm_only`. All player activity, all world events.

**The silent feed** (`GET /api/v1/me/feed/silent`):
Bookkeeping events only — `session.ft_distributed`, `session.plot_distributed`, `clock.resolve_generated`. Your audit log for mechanical operations that shouldn't clutter the narrative feed.

**Per-object feeds** (e.g., `GET /api/v1/characters/{id}/feed`):
Everything involving that Game Object. Useful for reviewing a character's history before a session.

**The events API** (`GET /api/v1/events`):
Events-only, no story entries. Supports all the same filters. Useful for audit and debugging: `?type=character.*`, `?proposal_id=...`, `?actor_type=gm`.

**Visibility override**: You can change any event's visibility after the fact:
`PATCH /api/v1/events/{id}/visibility` → `{visibility: "global"}`
Make a secret event public for a dramatic reveal.

> **Spec refs**: [feed.md](domains/feed.md) — GM Silent Feed; [events.md](domains/events.md) — GM Override, Events API

---

### 2.12 — Story Management and Visibility

**Create a Story** with mixed owners:
```json
{
  "name": "The Pact Beneath the Market",
  "summary": "Something ancient stirs under the Market District.",
  "owners": [
    {"type": "location", "id": "01HMARKET..."},
    {"type": "character", "id": "01HSOLIN..."}
  ],
  "tags": ["horror", "market-district"]
}
```

**Visibility**: Stories default to `familiar` (2-hop). Anyone within 2 hops of the Market District OR Solin can see this Story (union of all owner rules). And they can write entries in it (see = write).

**Override visibility**:
`PATCH /api/v1/stories/{id}` with:
```json
{
  "visibility_level": "bonded",
  "visibility_overrides": ["01HPLAYER_JORDAN..."]
}
```
Now only players directly bonded to the Market District or Solin can see it — PLUS Jordan, who you've explicitly granted access regardless of bond proximity.

**Story status**: You can set it to `active`, `completed`, or `abandoned` at any time. No transition rules — you decide.

> **Spec refs**: [game-objects.md](domains/game-objects.md) — Stories; [feed.md](domains/feed.md) — Story Visibility, GM Override

---

### 2.13 — Handling Player Departure

A player leaves the group. No special system mechanism — you handle it:

1. **Regenerate their token** (don't share the new one — soft ban): `POST /api/v1/players/{id}/regenerate-token`
2. **Their character persists** — full detail, all history intact. You can leave it as-is or soft-delete it.
3. **Pending proposals are orphaned** — you can still approve/reject them.
4. **For a replacement player**: Generate a new invite. The old account is deactivated when the new player joins (if you choose to re-invite for a new character).

> **Spec refs**: [auth.md](domains/auth.md) — No Explicit Deactivation Endpoint, Player-Character Mapping

---

### 2.14 — GM Self-Play (Optional)

You want to play a character too.

`POST /api/v1/me/character` → `{name: "Voss"}`

This creates a full Character (all fields at 0) and links it to your GM account. You set it up with GM actions just like any other character.

**Your character uses the proposal workflow** — you must explicitly approve your own proposals. This maintains a clean audit trail. No shortcuts.

If you later create another character for yourself, the old one stays in the system as an ownerless full Character.

> **Spec refs**: [auth.md](domains/auth.md) — GM Self-Play, GM Character Endpoint

---

## Part 3: System Behaviors (Cross-Cutting)

### 3.1 — Bond-Graph Visibility

The bond graph drives what you see. Your character's bonds are your information network.

| Visibility Level | Who Sees | Example |
|-----------------|----------|---------|
| `global` | Everyone | "Session 5 has started" |
| `public` (3-hop) | Broad reach | A distant Group's trait change, through 3 Character-intermediary hops |
| `familiar` (2-hop) | Moderate reach | An NPC your friend knows. Stories default to this. |
| `bonded` (1-hop) | Close connections | Your bond partner's stress changed. Most events default to this. |
| `private` (0-hop) | Just you + GM | Your rejected proposal, your Find Time conversion |
| `gm_only` | GM only | Sensitive GM actions |
| `silent` | GM silent feed only | FT distribution math, auto-proposal generation |

**Traversal rule**: After a non-Character node (Group or Location), the next hop must go through a Character (PC or NPC). You can't jump Group → Group or Location → Location directly. Characters are the social connective tissue.

### 3.2 — API Response Shapes

**Single resource**: Returned directly, no envelope.
```json
GET /api/v1/characters/01H...
→ { "id": "01H...", "name": "Kael", ... }
```

**List**: Paginated with cursor.
```json
GET /api/v1/characters
→ { "items": [...], "next_cursor": "01H...", "has_more": true }
```

**Errors**: Nested structure with machine-readable code.
```json
→ { "error": { "code": "insufficient_free_time", "message": "Need 1 FT, have 0" } }
```

**Pagination**: All lists use `?after=<ulid>&limit=N` (default 50, max 100).

**Naming**: snake_case everywhere — URLs, JSON fields, everything.

> **Spec refs**: [api-conventions.md](architecture/api-conventions.md)

---

_Last updated: 2026-03-14_
