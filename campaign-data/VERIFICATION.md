# Example Campaign — Seed Data Verification Checklist

Run the following two commands, then work through this checklist to confirm every UI
feature has data to display:

```
uv run wizards-campaign import --input ./campaign-data/
uv run wizards-campaign seed-events
```

Check each item as you confirm it is visible. An unchecked item means either the
feature is broken or the seed data is missing something.

---

## GM Queue

The GM Queue is the default landing view. It shows PC status cards, stress alerts,
and active group clocks.

### PC Status Cards

- [ ] All seven PCs are visible (Lysara, Enyo, Theron, Korinna, Mikkos, Orestes, Selene)
- [ ] Each card shows the PC's stress / free time / plot / gnosis meters with numeric values
- [ ] Meter bars reflect varied levels — cards do not all look the same:
  - Korinna's Stress bar is nearly full (8/9)
  - Selene's Free Time shows 0 (fully depleted)
  - Mikkos's Gnosis shows 6 (highest among PCs)
  - Orestes's Gnosis shows 7 and Free Time shows 1
- [ ] At least two PC cards show a low-charge indicator on a trait (Korinna: Blood-Speaker at 1, Seer at 0; Selene: Shadow-Walker at 1)
- [ ] Korinna's card shows a stress proximity alert (stress 8 out of 9, one step from max)
- [ ] Trauma bond indicator is visible on Korinna's card — the "Arkos's Debt" bond is marked as a trauma bond, reducing her effective stress maximum

### Group Clocks

- [ ] The Groups section of the queue shows at least two active clocks:
  - "Aelion's Diminishment" at 5/8 segments (associated with Aelion the character)
  - "Iron Compact Regional Consolidation" at 3/6 segments (associated with Iron Compact)
- [ ] At least one clock shows near-completion visual emphasis (Aelion's Diminishment at 5/8)
- [ ] Clock segment counts and progress bars are clearly readable

### Pending Proposals

- [ ] At least two pending proposals are listed (one player-submitted, one system-generated)
- [ ] Each proposal card shows the action type and submitting character name
- [ ] The GM can open a proposal and see its full narrative text and proposed outcome

---

## Event Feed (GM view)

The Event Feed shows the full event history with filtering and sorting controls.

### Event Type Variety

- [ ] Events of at least five distinct types are visible in the default feed:
  - Character meter changes (e.g., "Korinna's Stress increased to 8")
  - Bond events (e.g., "Lysara's bond 'Complicated History' degraded")
  - Trait events (e.g., "Theron's Hero-Blooded trait recharged to 5")
  - Clock events (e.g., "Aelion's Diminishment advanced to 5/8")
  - Session events (e.g., "Session 3: The Ford at Night ended")
- [ ] Proposal events are visible (at least one approved proposal, one rejected)
- [ ] GM action events are visible (at least one character modification, one clock advance)
- [ ] Story entry events appear in the feed (story text is readable inline or via expand)
- [ ] At least one rider event is visible (indented or visually distinct as a sub-event)

### Filter Controls

- [ ] Filtering by event type reduces the feed — selecting "bond events" hides meter changes
- [ ] Filtering by character shows only events involving that character (test with Korinna)
- [ ] Filtering by session shows only events from that session number
- [ ] Visibility filter is present — GM can see all visibility levels (silent through global)
- [ ] Clearing filters restores the full feed

### Sort Controls

- [ ] Default sort is newest-first; oldest event is at the bottom
- [ ] Switching to oldest-first moves Session 1 events to the top
- [ ] Sort and filter work together without resetting each other

---

## Game Objects — Characters

The Characters tab in the Game Objects browser shows PCs and NPCs.

### PC List

- [ ] All seven PCs are listed: Lysara, Enyo, Theron, Korinna, Mikkos, Orestes, Selene
- [ ] Each PC entry shows their name and a brief description excerpt
- [ ] PC entries display star/favorite controls
- [ ] Stress level or status summary is visible on PC list entries

### NPC List

- [ ] NPCs are present: Aelion, Drakos, Herald Kassian, Magistra Vaela, Myrtos, Phila
- [ ] Entity characters appear separately or are labeled: The Moirai, The Dream Hound, Iron Voice
- [ ] NPC descriptions are populated (not empty placeholders)

### Filter Controls

- [ ] Toggling the PC filter shows only the seven PCs
- [ ] Toggling the NPC filter shows only NPC entries (including entities)
- [ ] Clearing the filter shows all characters together
- [ ] Search by name narrows results (test: typing "kor" finds Korinna)

### Detail Navigation

- [ ] Clicking any PC opens their Character Detail view
- [ ] Clicking any NPC opens their detail view with description

---

## Game Objects — Groups

The Groups tab shows all factions with tier indicators and clock associations.

### Group Variety

- [ ] At least four groups are listed: Iron Compact, Keepers of the Sacred Fire, Troikas Resistance, The Scattered Chorus, Olympian Assembly
- [ ] Tier values span a range — Iron Compact shows tier 4, Keepers shows tier 2
- [ ] Group descriptions are populated and clearly distinguish each group's identity

### Group Traits

- [ ] Groups with traits show those traits in their entry or detail view:
  - Iron Compact shows "Iron Discipline," "Divine Legitimacy Claim," and "Intelligence Network"
  - Keepers of the Sacred Fire shows "The Archive" and "Cell Network"
- [ ] Trait descriptions are readable

### Group Relations

- [ ] At least one group shows a relation to another group (Iron Compact's "Target for Elimination" relation to Keepers of the Sacred Fire)
- [ ] Relation direction is indicated (which group holds the relation to which target)

### Group Holdings

- [ ] Iron Compact shows its two holdings: "Iron Works at Argos Ford" (location) and "Administrative Compound" (location)
- [ ] Holdings link or reference the associated location by name

### Clock Associations

- [ ] Iron Compact's clock ("Iron Compact Regional Consolidation" at 3/6) is visible on the group entry or detail
- [ ] Clock progress is shown with a segment bar

---

## Game Objects — Locations

The Locations tab shows the world geography with nested hierarchy.

### Location Hierarchy

- [ ] Top-level regions are visible: The Known World, The Divine Realm, The Dream Road
- [ ] Nested child locations are accessible under their parent:
  - The Known World contains Argos and Troikas
  - Argos contains Argos Ford as a sub-location
  - The Divine Realm contains Olympos Peak and The Undermarsh
- [ ] Parent location name is displayed on child location entries

### Location Content

- [ ] Location descriptions are populated (test: Argos and Argos Ford have distinct descriptions)
- [ ] Locations with character bonds display those associations (Korinna's "Territorial Awareness" bond to The Undermarsh; Selene's "Hometown Obligation" bond to Argos)
- [ ] Locations with group holdings show the associated group (Argos Ford shows Iron Compact's Iron Works holding)

---

## Character Detail — Lysara

Open Lysara's character detail page. This PC has the richest trait and effect configuration
and serves as the primary verification subject for the Character Detail view.

### Header and Description

- [ ] Full name "Lysara" is displayed prominently
- [ ] The full description text is visible — the oracle seeress background paragraph is readable
- [ ] Stress / Free Time / Plot / Gnosis meters show Lysara's values (2 / 4 / 3 / 4)

### Skills Table

- [ ] All eight skills are displayed: Awareness, Composure, Influence, Finesse, Speed, Power, Knowledge, Technology
- [ ] Lysara's values match the YAML: Awareness 3, Composure 2, Influence 2, Finesse 1, Speed 1, Power 1, Knowledge 3, Technology 0

### Magic Stats

- [ ] All five schools are displayed: Being, Wyrding, Summoning, Enchanting, Dreaming
- [ ] Lysara's levels show: Being 1, Wyrding 2, Summoning 0, Enchanting 1, Dreaming 1

### Core and Role Traits

- [ ] Core traits are visually separated from role traits
- [ ] Two core traits visible: "Seer" (charge 4) and "Oath-Keeper" (charge 5)
- [ ] One role trait visible: "Dream-Walker" (charge 3)
- [ ] Charge pips or numeric value is displayed for each trait

### Bonds

- [ ] All five of Lysara's bonds are listed:
  - "Fellow Wanderer" to The Scattered Chorus — charges 5
  - "Uneasy Alliance" to Theron — charges 4
  - "Recruited Contact" to Enyo — charges 4
  - "Complicated History" to Drakos — charges 2, degradations 2
  - "Sworn to Illuminate" to Keepers of the Sacred Fire — charges 4
- [ ] "Complicated History" shows 2 degradations visually (reduced effective charges)
- [ ] Bond targets link or display the target's name and type (character/group)

### Magic Effects

- [ ] All three magic effects are listed: "Oracle Trance" (permanent), "Fate-Thread Sight" (instant), "Dream Passage" (charged)
- [ ] Effect types are labeled (permanent / instant / charged)
- [ ] "Dream Passage" shows its charge state: 2 of 3 charges remaining
- [ ] Power level is displayed for each effect

### Events Feed

- [ ] An events feed section is visible at the bottom of Lysara's detail page
- [ ] At least three events referencing Lysara appear (meter changes, bond events, trait events from the seed script)

---

## Character Detail — Korinna (Stress and Trauma Verification)

Open Korinna's character detail page to verify the trauma and high-stress states.

### Stress and Trauma

- [ ] Stress meter shows 8 (near maximum of 9)
- [ ] A stress proximity alert or visual warning is shown at this level
- [ ] The "Arkos's Debt" bond to The Dream Hound is marked as a trauma bond (`is_trauma: true`)
- [ ] The trauma bond indicator reduces or annotates the displayed stress maximum (trauma bond lowers effective max by 1)
- [ ] "Obligation Unwanted" bond to The Scattered Chorus shows 3 degradations — the highest degradation count in the dataset

### Low-Charge Traits

- [ ] Core trait "Blood-Speaker" shows charge 1 — low-charge visual indicator present
- [ ] Core trait "Seer" shows charge 0 and `is_active: false` — zero-charge state is clearly distinguished from inactive
- [ ] Role trait "Dream-Walker" shows charge 2

### Magic Effects

- [ ] "Shade Summoning" shows 1 of 3 charges remaining (lowest charge ratio in the data)
- [ ] Three distinct effect types are shown: permanent (Whisper-Hearing), charged (Shade Summoning), instant (Death-Sense)

---

## Character Detail — Selene (Zero-Charge and Depleted Meter Verification)

### Depleted States

- [ ] Free Time shows 0 (fully depleted)
- [ ] Gnosis shows 1 (near-zero)
- [ ] "Hometown Obligation" bond to Argos shows charge 0 — at-degradation threshold
- [ ] "Adversarial Claim" bond to Iron Compact shows charge 0 and 2 degradations
- [ ] Role trait "Shadow-Walker" shows charge 1

---

## Sessions View

The Sessions view shows all session records across their lifecycle states.

### Session State Variety

- [ ] At least one session in each state is visible:
  - Ended: Sessions 1–5 are all ended (road to Argos through Dream Road first walk)
  - Active: at least one session shows active state (created by the seed script)
  - Draft: Session 6 "Planning Session" is in draft state (no date or summary set)
- [ ] Each state is visually distinguished (e.g., draft sessions show a "draft" label, ended sessions show their end date)

### Session Details

- [ ] Clicking Session 1 ("The Road to Argos") shows:
  - Date: 2026-01-10
  - Summary: the road-to-Argos narrative with three participants (Lysara, Theron, Enyo)
  - Participant list with names and additional-contribution indicators
- [ ] Session 6 (draft) shows its planned agenda notes and empty participant list
- [ ] An active session (from seed data) shows it as in-progress with no end date

### Session Timeline

- [ ] An ended session's timeline or event list shows events that occurred during that session
- [ ] Events in the timeline are in chronological order

---

## Proposals View / GM Queue

Proposals appear both in the GM Queue (pending) and in a separate history view (approved and rejected).

### Pending Proposals

- [ ] At least two pending proposals appear in the queue
- [ ] Each proposal shows: submitting character, action type, brief description
- [ ] At least one pending proposal was submitted by a player character (e.g., use_skill or rest)
- [ ] At least one pending proposal was system-generated (resolve_clock or resolve_trauma)

### Approved Proposals

- [ ] The proposal history shows at least three approved proposals
- [ ] Approved proposals display the approving GM note or outcome narrative
- [ ] Action types covered include at least: use_skill, rest, new_bond or new_trait

### Rejected Proposals

- [ ] At least two rejected proposals appear in the history
- [ ] Rejected proposals display the rejection reason

### Proposal Detail

- [ ] Opening any proposal shows the full proposed action narrative
- [ ] The approval / rejection form is accessible for pending proposals (GM view)

---

## Feed (Player View)

Switch to a player account (e.g., log in as player-asha or player-dara) and view the
player-facing feed. This verifies visibility filtering.

### Visibility Filtering

- [ ] Events with `silent` visibility do not appear in the player feed
- [ ] Events with `gm_only` visibility do not appear in the player feed
- [ ] Events with `public` or `global` visibility appear for all players
- [ ] Events with `private` visibility appear only for the character's owning player
- [ ] Events with `bonded` visibility appear only for players whose characters have bonds to the event's subject character

### Story Entries

- [ ] At least one story entry is visible in the player feed
- [ ] Story entry text is readable inline
- [ ] Story entries are attributed to their author (GM or player name)

### Actor Variety

- [ ] Feed shows events attributed to different actor types: player characters (Lysara, Theron, Enyo), the GM, and the system (auto-generated events)
- [ ] Character names in event descriptions are readable and correctly identify the acting character

---

## Notes for QA and Demo

- The seven PCs were designed with deliberate mechanical variety. They should never look
  identical in the queue — if all cards show full meters and no warnings, something went wrong
  in import or seeding.
- Korinna is the "worst-off" PC: highest stress (8), lowest trait charges (0 and 1), trauma
  bond, barely-charged magic effect. She is the primary subject for stress-and-trauma UI tests.
- Selene is the "depleted resources" PC: zero free time, nearly zero gnosis, two at-floor bonds.
  She is the primary subject for zero-charge UI tests.
- Lysara has the richest magic effect configuration (permanent + instant + charged) and the
  most bonds. Use her for Character Detail completeness checks.
- The Iron Compact clock (3/6) and Aelion's Diminishment clock (5/8) are the two primary
  clocks to verify. Aelion's clock at 5/8 should show near-completion emphasis.

_Last updated: 2026-03-22_
