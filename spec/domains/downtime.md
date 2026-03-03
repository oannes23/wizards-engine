# Downtime — Domain Specification

**Status**: 🟢 Complete
**Last interrogated**: 2026-03-01
**Last verified**: —
**Depends on**: [proposals](proposals.md), [game-objects](game-objects.md), [character-core](character-core.md)
**Depended on by**: None

---

## Overview

Downtime is not a distinct system mode — it's the natural result of the session lifecycle. Free Time is distributed automatically when sessions start (based on a Time Now delta), and players can submit downtime proposals whenever they have Free Time. Group clocks are adjusted when sessions end. The session lifecycle replaces the concept of a "downtime trigger."

---

## Core Concepts

### Session Lifecycle

Sessions are the structural backbone. They have three states: **Draft → Active → Ended**.

**1. Draft**
- GM creates a session, sets **Time Now** (abstract campaign time counter), date, and optional summary/notes.
- Players **self-register** for the session (optionally checking "Additional Contribution").
- GM can also add/remove players from the participant list.
- Session is fully editable in Draft state. Draft sessions can be deleted.

**2. Start Session (Draft → Active)**
GM hits "Start Session". The system automatically:
- **Distributes Free Time**: For each registered participant, computes `current_time_now - character.last_session_time_now` and adds that amount to the character's Free Time meter (capped at 20). Updates `character.last_session_time_now` to the current Session's Time Now.
- **Awards Plot**: Each participant receives **1 Plot** (or **2 Plot** if they checked "Additional Contribution"). Plot is capped at 5.

**3. Session Play (Active)**
- Players submit Actions (`use_skill`, `use_magic`, `charge_magic`) as proposals.
- Players can also submit Downtime Actions at any time if they have Free Time.
- The GM reviews and resolves proposals.
- GM can edit session summary and notes during Active state.
- GM adjusts group clocks individually during Active (in preparation for ending).

**4. End Session (Active → Ended)**
GM hits "End Session". The system:
- Transitions session status to **Ended** (read-only — no further edits to summary, notes, or participants).
- Clock adjustments happen **before** End Session via individual clock mutation calls during Active state (see Group Clock Adjustments below). End Session simply finalizes.
- Any completed clocks (progress >= segments) are **flagged and surfaced** to the GM for narrative follow-up.

### Time Now

An abstract integer counter set by the GM on each Session. Represents the passage of campaign time. The difference between a character's last session Time Now and the current session's Time Now determines how much Free Time they receive.

- **Not real dates** — purely abstract. GM controls pacing.
- **Higher delta = more FT**: A character who misses sessions accumulates a larger delta and gets more FT (capped at 20).
- **Stored on Session**: Each Session record has a `time_now` field.
- **Tracked on Character**: Each Character has a `last_session_time_now` field, updated on session participation.

### Free Time Distribution

FT is computed automatically at Session Start:

```
ft_gained = session.time_now - character.last_session_time_now
character.free_time = min(character.free_time + ft_gained, 20)
character.last_session_time_now = session.time_now
```

- First session: Character's `last_session_time_now` is set by the GM at character creation (or defaults to 0).
- FT **carries over** between sessions. Unspent FT persists on the meter.
- FT is **capped at 20**. Excess from the Time Now delta is lost.

### Plot Income

Plot is awarded at Session Start to registered participants:

- **Base**: +1 Plot per session participated
- **Additional Contribution**: +2 Plot if the player checked the contribution flag (meta-game reward: wrote recap, brought props, helped organize)
- **Capped at 5**: Plot cannot exceed 5

### Find Time (Direct Player Action)

Players can convert **3 Plot → 1 Free Time** at any time. This is a direct player action (not a proposal — no GM approval needed). System converts resources and logs an event.

Use case: A player near the Plot cap (5) can Find Time before a session starts to avoid wasting incoming Plot.

FT gained from Find Time respects the 20 cap.

### Downtime Actions

Players can submit Downtime Action proposals **at any time** they have Free Time — there is no "downtime window" or mode. All downtime actions cost 1 FT automatically (deducted on approval).

Seven Downtime Action types (defined in [proposals](proposals.md)):

| Type | Effect | Supports Modifiers |
|------|--------|-------------------|
| `regain_gnosis` | 3 + lowest Magic Stat + mods (0–3) Gnosis | Yes |
| `recharge_trait` | Restore selected trait to 5 charges | No |
| `maintain_bond` | Heal selected bond's stress to 0 | No |
| `work_on_project` | Narrative note on target Story/Arc | No |
| `rest` | 3 + mods (0–3) Stress healed | Yes |
| `new_trait` | Replace/fill a trait slot | No |
| `new_bond` | Replace/fill a bond slot | No |

**No activity limit** beyond FT cost. Players can submit as many downtime proposals as they can afford.

### Group Clock Adjustments

During Active state (typically as the session wraps up), the GM adjusts group project clocks individually:

- **Individual calls**: Each clock is adjusted via a separate API call (not bundled into End Session).
- **Default**: each clock starts with a suggested +1 tick.
- **GM adjusts**: GM can change the tick amount for each clock (including 0 or negative values).
- **Annotations**: Each adjustment can include:
  - **Notes**: freeform text explaining why the clock changed
  - **Event links**: references to Event records from the session
  - **Game object links**: references to game objects (Characters, NPCs, Groups, etc.) involved in the change
- **Completion**: If a clock reaches its segment count, the system flags it. GM handles consequences narratively via direct actions.
- **Timing**: Adjustments happen during Active state. End Session just transitions the status — it does not include clock adjustments in its payload.

### Session Participants

Sessions have a participant list tracking who played:

- **Player self-registration**: Players add themselves to a Draft or Active session
- **GM management**: GM can add/remove any player
- **Late joins**: Adding a participant to an Active session triggers immediate FT + Plot distribution for that participant
- **Additional Contribution flag**: Per-participant boolean, set on registration. **Locks on Start** — must be set before the session starts (or at the moment of late join). Cannot be changed after distribution.
- **Character link**: Each participant entry links to the Player and their Character
- **Session history on Character**: Characters store a list of session IDs they've participated in, enabling easy history lookups from either direction.

---

## Decisions

### No Downtime Mode

- **Decision**: There is no "downtime mode" or tracked system state. Downtime mechanics are embedded in the session lifecycle. Players can submit downtime proposals anytime they have FT.
- **Rationale**: Removes artificial constraints. FT distribution happens at session start, clock ticks at session end. No need for a separate downtime trigger or phase.
- **Implications**: No `POST /api/v1/downtime/trigger` endpoint. No `GET /api/v1/downtime/status` endpoint. Session start/end replaces the downtime trigger entirely.

### Time Now Delta for FT

- **Decision**: FT is computed from the difference between the current Session's Time Now and the Character's `last_session_time_now`. Distributed at Session Start to participants.
- **Rationale**: Automatically handles absent players (they get more FT to catch up). GM controls pacing via Time Now values. No manual FT distribution needed.
- **Implications**: Session model needs `time_now` field. Character model needs `last_session_time_now` field. FT capped at 20.

### Session Lifecycle: Draft → Active → Ended

- **Decision**: Sessions have three states. Draft is editable (participants register, GM sets details). Start distributes FT and Plot. End adjusts group clocks.
- **Rationale**: Clear lifecycle with distinct actions at each transition. Draft allows preparation before committing to FT distribution.
- **Implications**: Session model needs a `status` field and participant list. Two GM actions: Start and End.

### Plot Income with Additional Contribution

- **Decision**: Participants receive 1 Plot at session start (2 if "Additional Contribution" checked). Capped at 5. Additional Contribution is a meta-game reward (wrote recap, helped organize, etc.).
- **Rationale**: Incentivizes real-world engagement with the game beyond showing up. Bonus Plot is meaningful but not game-breaking. Cap prevents hoarding.
- **Implications**: Session participant model needs `additional_contribution` boolean. Plot distribution logic at session start.

### Find Time (3 Plot → 1 FT)

- **Decision**: Direct player action. Convert 3 Plot to 1 Free Time at any time. No proposal or GM approval needed. Event logged.
- **Rationale**: Prevents Plot waste at the 5 cap. Gives players agency over resource management. Low-friction conversion.
- **Implications**: Dedicated endpoint. Validates Plot >= 3 and FT < 20. Not a proposal action type — a direct player action like using a Magic Effect.

### FT Carries Over, Capped at 20

- **Decision**: Free Time persists between sessions. New FT from Time Now delta is added up to the 20 cap. Excess is lost.
- **Rationale**: Carrying over rewards planning. The cap prevents excessive hoarding from long absences.
- **Implications**: FT meter is just a persistent number on the Character. No reset or expiry logic needed.

### Group Clock GM-Adjusted Ticks

- **Decision**: At End Session, group clocks get a default +1 but the GM can adjust each (up/down/skip). Adjustments include optional annotations (notes + event/game object links).
- **Rationale**: Player actions during the session may accelerate, delay, or prevent group progress. The GM reflects this in the clock adjustments. Annotations create a rich narrative history of why groups progressed or didn't.
- **Implications**: End Session UI shows all clocks with adjustment controls. Clock mutation model needs annotation support (notes + polymorphic refs).

### No Activity Limit

- **Decision**: No limit on downtime activities beyond FT cost. Players can submit as many as they can afford.
- **Rationale**: FT is already the limiting resource. Additional caps add complexity without value.
- **Implications**: No per-session activity counter needed.

### Player Self-Registration

- **Decision**: Players self-register for sessions (with optional Additional Contribution flag). GM can also manage the participant list. Both can add/remove.
- **Rationale**: Reduces GM overhead for session setup while preserving GM authority.
- **Implications**: Session participant endpoints need both player and GM access.

### Late Joins to Active Sessions

- **Decision**: Players can join an Active session after it has started. When a late-joining participant is added, the system runs the same distribution logic: FT via Time Now delta and Plot (+1/+2 with Additional Contribution).
- **Rationale**: Real sessions have late arrivals. Denying FT/Plot for being late would be punitive. The same formula applies regardless of when you join.
- **Implications**: The `POST /api/v1/sessions/{id}/participants` endpoint must work on both Draft and Active sessions. Adding a participant to an Active session triggers FT + Plot distribution for that participant immediately.

### One Active Session at a Time

- **Decision**: Only one session can be in Active state at any given time. The system enforces this — the GM must End the current session before Starting another.
- **Rationale**: Prevents confusion about which session is "current." FT/Plot distribution and clock adjustments assume a single active context. Multiple active sessions would create ambiguous state.
- **Implications**: `POST /api/v1/sessions/{id}/start` must check for existing Active sessions and reject if one exists. Multiple Draft sessions can coexist.

### Time Now Validation

- **Decision**: A Session's Time Now must be greater than or equal to the previous session's Time Now. Equal values are allowed (producing 0 FT delta). Negative deltas are rejected by the system.
- **Rationale**: Time Now represents forward-moving campaign time. A 0 delta is valid (back-to-back sessions with no in-fiction time passing). Going backwards would break the FT model.
- **Implications**: `POST /api/v1/sessions` and `PATCH /api/v1/sessions/{id}` must validate `time_now >= most_recent_ended_session.time_now`. Edge case: first session has no constraint.

### Session Mutability by State

- **Decision**: GM can edit session summary and notes in both Draft and Active states. Only Ended sessions are fully read-only.
- **Rationale**: The GM often needs to add notes during play (tracking narrative beats, session recap). Locking on Start would be unnecessarily restrictive.
- **Implications**: `PATCH /api/v1/sessions/{id}` accepts updates for Draft and Active sessions. Rejects updates for Ended sessions.

### No Resource Clawback on Participant Removal

- **Decision**: Removing a participant from an Active session does not reverse FT or Plot that was already distributed. The removal only affects the participant list.
- **Rationale**: Clawback adds complexity and creates confusing negative deltas. In practice, removing someone from a session is rare and the GM can manually adjust via direct actions if needed.
- **Implications**: `DELETE /api/v1/sessions/{id}/participants/{player_id}` only removes the participant record. No resource changes.

### Forward-Only Session Lifecycle

- **Decision**: Session lifecycle is strictly forward: Draft → Active → Ended. No undo (Active → Draft) or reopen (Ended → Active). Mistakes are corrected via GM direct actions on characters and clocks.
- **Rationale**: Reversing Start would require clawing back distributed FT/Plot from all participants. Reversing End would require undoing clock adjustments. Both are complex and error-prone. GM direct actions provide a simpler correction path.
- **Implications**: No reverse-transition endpoints. The GM has full authority to manually adjust any character or clock state.

### Draft-Only Session Deletion

- **Decision**: Only Draft sessions can be deleted. Active and Ended sessions are permanent records.
- **Rationale**: Draft sessions have no side effects (no resources distributed, no clock adjustments). Active and Ended sessions have generated events and state changes — deleting them would leave orphaned references.
- **Implications**: `DELETE /api/v1/sessions/{id}` only works when `status = draft`. Returns error for Active or Ended.

### Additional Contribution Flag Locks on Start

- **Decision**: The Additional Contribution flag on a participant record is editable only while the session is in Draft state. It locks when the session starts (or immediately on late join to an Active session, after distribution).
- **Rationale**: Plot distribution uses the flag value at the moment of distribution. Allowing changes after distribution would create inconsistency between what was given and what the record shows.
- **Implications**: `PATCH /api/v1/sessions/{id}/participants/{player_id}` rejects contribution flag changes if the session is Active and the participant already received distribution. Draft sessions allow changes freely.

### Per-Clock Adjustments, Then End

- **Decision**: Clock adjustments are made via individual API calls during the Active session, not as part of the End Session payload. End Session simply transitions the status to Ended.
- **Rationale**: Separating clock adjustments from the End transition gives the GM flexibility to adjust clocks at any point during the session wrap-up. It also simplifies the End Session endpoint.
- **Implications**: Clock adjustment uses the existing clock mutation endpoints (see [game-objects](game-objects.md)) with annotation support. `POST /api/v1/sessions/{id}/end` has no payload — it just transitions the status.

### Bidirectional Session-Character References

- **Decision**: Characters store a list of session IDs they've participated in, in addition to Sessions storing their participant list. This enables easy history lookups from either direction.
- **Rationale**: Common query: "what sessions has this character been in?" Without bidirectional refs, this requires scanning all sessions. With a small group this is manageable, but the ref list is cheap to maintain.
- **Implications**: Character model needs a `session_ids` list (or a join table query). Updated when a participant is added or removed.

---

## API Endpoints

### Session Lifecycle
- `POST /api/v1/sessions` — create a Draft session (GM: sets time_now, date, summary)
- `GET /api/v1/sessions/{id}` — session detail with participants, clocks status
- `PATCH /api/v1/sessions/{id}` — update session details (GM, Draft or Active only; Ended is read-only)
- `DELETE /api/v1/sessions/{id}` — delete a session (GM, Draft only)
- `POST /api/v1/sessions/{id}/start` — start session (GM): distributes FT + Plot to participants, locks contribution flags. Rejects if another session is Active.
- `POST /api/v1/sessions/{id}/end` — end session (GM): no payload, just transitions to Ended. Clock adjustments happen separately during Active.

### Session Participants
- `POST /api/v1/sessions/{id}/participants` — register for session (player or GM adds)
- `DELETE /api/v1/sessions/{id}/participants/{player_id}` — remove from session (player self-remove or GM)
- `PATCH /api/v1/sessions/{id}/participants/{player_id}` — update contribution flag

### Direct Player Actions
- `POST /api/v1/characters/{id}/find-time` — convert 3 Plot → 1 FT (player, no approval)

### Downtime Proposals
All downtime actions are submitted as proposals via `POST /api/v1/proposals` (see [proposals](proposals.md)).

---

## Implications for Other Specs

| Spec | Implication |
|------|-------------|
| [game-objects](game-objects.md) | 🔄 Session model significantly expanded: `time_now`, `status` (draft/active/ended), participant list with contribution flag. Clock mutation annotations. Stories support narrative entries from `work_on_project`. |
| [character-core](character-core.md) | 🔄 Character needs `last_session_time_now` field and `session_ids` list. Plot mechanic clarified: +1/+2 per session, capped at 5. FT distribution via Time Now delta. |
| [proposals](proposals.md) | 🔄 Find Time is a new direct player action (not a proposal type). Session start/end replace the concept of a downtime trigger. |
| [events](events.md) | Session start (FT + Plot distribution), session end (clock adjustments), Find Time, and player registration all generate events. |
| [auth](auth.md) | Players can self-register for sessions and trigger Find Time. Session start/end are GM-only. |
| [architecture/data-model](../architecture/data-model.md) | 🔄 Session model needs major expansion. Session participant join table. Clock mutation annotation model. `last_session_time_now` on Character. |

---

_Last updated: 2026-03-01 (third pass — lifecycle edge cases)_
