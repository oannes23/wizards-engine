# GM Guide

Everything you need to run your game in Wizards Engine -- session workflow, proposal review, world building, and player management.

## GM Dashboard

Your home screen (`#/gm`) shows:

- **Pending proposals** -- system proposals first (clock resolutions, trauma), then player proposals oldest-first
- **PC resource summaries** -- quick view of all player characters' meters
- **Near-completion clocks** -- clocks approaching their segment count

## Session Workflow

Sessions are the structural backbone. They follow a strict lifecycle: **Draft -> Active -> Ended**.

### 1. Create a Draft Session

Navigate to Sessions and create a new session. Set:

- **Time Now** -- abstract campaign time counter (determines how much Free Time players receive)
- **Date** -- real-world session date (optional)
- **Summary** -- what the session is about

Players can self-register for the session and optionally check "Additional Contribution" (for writing recaps, bringing props, etc.) to receive bonus Plot.

### 2. Start the Session

Hit "Start Session." The system automatically distributes resources to all registered participants:

- **Free Time**: Each participant gains FT equal to the difference between this session's Time Now and their character's last session Time Now (capped at 20). Characters who missed sessions accumulate more FT.
- **Plot**: +1 per participant (+2 if they checked Additional Contribution). Plot can temporarily exceed the cap of 5.

Only one session can be Active at a time.

### 3. Active Play

During the session:

- Players submit proposals for session actions (Use Skill, Use Magic, Charge Magic) and downtime actions
- You review and resolve proposals from the queue
- You can adjust group clocks individually (the UI pre-fills +1 per clock as a suggestion)
- You can edit the session summary and notes

### 4. End the Session

Hit "End Session." The system:

- Clamps all participants' Plot to 5 (excess is lost)
- Transitions the session to Ended (read-only)
- Flags any completed clocks for your attention

**Tip**: Adjust clocks before ending. Clock adjustments are separate API calls during Active state -- End Session just finalizes.

### Late Joins

Players can join an Active session after it starts. Adding a late participant triggers immediate FT + Plot distribution for them using the same formula.

## Reviewing Proposals

Proposals appear in your review queue (`#/gm/queue`), sorted oldest-first. System proposals (clock resolution, trauma) appear at the top.

### Approve (Common Case)

Tap "Approve" for a one-tap default approval: no overrides, no rider event, no bond strain. The player's narrative becomes the event narrative. This is the fast path for most proposals.

### Approve with Overrides

Expand "Advanced" to access:

- **GM narrative** -- override the player's narrative with your own description of what happened
- **Cost overrides** -- waive or modify any calculated cost (e.g., set FT cost to 0)
- **Bond strain** -- toggle to apply +1 stress to the bond used as a modifier
- **Rider event** -- attach a side effect (NPC reaction, clock advance, world change) that fires atomically with the approval

For magic actions, you'll also see fields for the Magic Effect to create (name, description, type, power level, charges).

### Reject

Tap "Reject" and provide a note explaining what needs to change. The player can revise and resubmit the same proposal -- it stays as a single record.

### Force Approve

If a player can no longer afford a proposal's costs (e.g., another proposal consumed the same resources), approval returns a conflict. You can force-approve to override validation -- your authority trumps resource checks.

### System Proposals

The system auto-generates two types of proposals:

- **Resolve Clock** -- when a clock reaches completion. You provide the narrative outcome and optionally attach a rider event with world state changes.
- **Resolve Trauma** -- when a character's Stress hits its effective max. You choose which active bond becomes the Trauma, name it, and describe it. The system retires the old bond, creates the Trauma bond, and resets Stress to 0.

## GM Direct Actions

Access via GM Direct Actions (`#/gm/actions`). These bypass the proposal queue -- they validate and apply immediately.

### Character Changes

| Action | What it does |
|--------|-------------|
| `modify_character` | Change meters (Stress, FT, Plot, Gnosis), skill levels, magic stat levels/XP |
| `award_xp` | Grant Magic Stat XP to a character |

Values are clamped to valid ranges (not rejected), so typos won't break anything.

### Trait / Bond / Effect Lifecycle

| Action | What it does |
|--------|-------------|
| `create_trait` | Assign a Trait Template to a character slot |
| `modify_trait` | Change charges, name, or description |
| `retire_trait` | Deactivate a trait (moves to Past) |
| `create_bond` | Create a new bond between any game objects |
| `modify_bond` | Change bond charges, labels, or description |
| `retire_bond` | Deactivate a bond |
| `create_effect` | Create a Magic Effect on a character |
| `modify_effect` | Change power level or charges |
| `retire_effect` | Deactivate a Magic Effect |

### World Changes

| Action | What it does |
|--------|-------------|
| `modify_group` | Change a group's tier or notes |
| `modify_location` | Change a location's notes |
| `modify_clock` | Adjust clock progress or segments |

All GM actions create events in the log. Default visibility varies by type (most default to `gm_only` or `bonded`), but you can override visibility on any action.

## World Management

### Characters

- **PCs** are created when players join via invite links. You set them up afterward using GM actions.
- **NPCs** are simplified characters -- no meters, skills, or magic. 7 descriptive bond slots. Create from the World Builder.

### Groups

Organizations and factions with:
- Up to 10 descriptive traits
- Up to 7 relations to other groups
- Unlimited holdings (links to locations)
- A tier (power/influence level)

### Locations

Nestable hierarchy (a city contains districts, districts contain buildings). Each location has:
- Up to 5 feature traits
- Unlimited bonds to other game objects
- Bond-distance presence (who's commonly/often/sometimes here, computed from the bond graph)

### Stories

Narrative arcs visible to players based on bond-graph proximity. Stories have:
- Active / Completed / Abandoned status
- Owners (game objects associated with the story)
- Entries (narrative notes -- both you and players can write entries)
- Tags for organization
- Child stories (nested arcs)

Players can see stories they're connected to via the bond graph (default: 2-hop / "familiar" visibility). If they can see a story, they can write entries in it.

### Clocks

Progress bars associated with a game object (usually a group project). You adjust them during Active sessions. When a clock completes, the system generates a `resolve_clock` proposal for you to resolve narratively.

### Trait Templates

A catalog of reusable Core and Role Trait definitions. Create templates, then assign them to character slots via GM actions. Templates can be soft-deleted if no longer needed.

## Player Management

### Player Roster

View all players, their characters, and their login links from the roster (`#/gm/players`). Only you can see login URLs.

### Regenerating Login Links

If a player loses their link or you want to revoke access:
- Navigate to the roster and regenerate their token
- Share the new link -- the old one stops working immediately
- Not sharing the new link is effectively a soft ban

### Invites

- Create bare invite codes from the Invites screen
- Each invite generates a magic link URL to share with the player
- The invite code becomes the player's permanent login code on redemption
- Delete unconsumed invites if no longer needed

### Replacing a Character

If a player's character dies or needs replacement: create a new invite, share it. The old account is deactivated and the player joins fresh with a new character.

## Character Setup Checklist

After a player joins, their character sheet is all zeros. Set them up:

1. **Skills** -- set 8 skill levels (0-3 each) via `modify_character`
2. **Meters** -- set starting Gnosis and any other meters via `modify_character`
3. **Magic Stats** -- set starting levels (0-5) via `modify_character`
4. **Core Traits** (2 slots) -- assign from the Trait Template catalog via `create_trait`
5. **Role Traits** (3 slots) -- assign from the Trait Template catalog via `create_trait`
6. **Bonds** (up to 8 slots) -- create bonds to NPCs, groups, locations, and other PCs via `create_bond`
7. **Magic Effects** -- create any starting effects via `create_effect`

Each action logs an event, so the character's history starts from creation.
