# Magic System — Domain Specification

**Status**: 🟢 Complete
**Last interrogated**: 2026-03-13
**Last verified**: —
**Depends on**: [character-core](character-core.md), [traits](traits.md), [bonds](bonds.md)
**Depended on by**: [actions](actions.md), [downtime](downtime.md)

---

## Overview

The magic system is freeform and sacrifice-driven. Players describe their magical intention, explain its symbolism, and sacrifice resources to power it. The GM reviews and creates a Magic Effect on the character's sheet as the outcome. Magic integrates with the proposal workflow via two action types: Magic Action (create new effects) and Charge Action (recharge/boost existing effects).

---

## Core Concepts

### Gnosis

- Type: Resource meter
- Range: 0–23
- The primary magical resource, spent as sacrifice in Magic Actions and Charge Actions
- Regained via downtime activity (costs Free Time)
- The unusual max of 23 is a deliberate lore-driven design choice

### Magic Stats (5 per Character, Hardcoded)

The five schools/aspects of magic:

> **Being, Wyrding, Summoning, Enchanting, Dreaming**

Each has:
- `level`: 0–5 — determines the **base dice pool** for magic actions using that stat (like Skills for normal actions)
- `xp`: meter, flat 5 XP per level — tracks progress toward the next level. Resets to 0 on level-up (excess does not carry over).

**XP is awarded by the GM directly** — no automatic gain from magic use or downtime study. GM controls all Magic Stat progression.

### Magic Action (Proposal Type)

The core magical workflow. A player submits a Magic Action as a proposal with three components:

**1. Intention** (text paragraph)
What the character is trying to achieve with the magic.

**2. Symbolism** (text paragraph)
The in-fiction ritual, gesture, focus, or method that channels the magic.

**3. Sacrifice** (structured — **list of entries, can combine freely**)
Resources spent to power the magic. Players can combine multiple sacrifice types in a single action. All are converted to Gnosis equivalent and summed:

| Sacrifice Type | Gnosis Equivalent | Effect |
|---------------|-------------------|--------|
| Gnosis | 1:1 | Direct Gnosis spend (any amount) |
| Stress | 1 Stress = 2 Gnosis | Character takes Stress (standard Stress rules apply — can trigger Trauma) |
| Free Time | 1 FT = 3 + lowest Magic Stat | Spends Free Time |
| Bond sacrifice | 10 Gnosis | Bond goes to Past (destroyed) |
| Trait sacrifice | 10 Gnosis | Trait goes to Past (destroyed) |
| Other | GM sets value during review | Freeform text — player describes offering, GM assigns Gnosis value as part of proposal review |

**Combined sacrifice**: A single Magic Action can include any mix of the above (e.g., 5 Gnosis + 2 Stress + a Bond sacrifice). The proposal data model stores a **list** of sacrifice entries, each with a type and amount.

**Stress sacrifice and Trauma**: If voluntary Stress sacrifice pushes a character to their effective Stress max, Trauma triggers normally (Bond replaced, Stress resets to 0). This makes Stress sacrifice genuinely dangerous at high Stress levels.

In addition to sacrifice, the player may **Use** modifiers (standard stacking rule):
- 1 Core Trait (+1d, costs 1 charge)
- 1 Role Trait (+1d, costs 1 charge)
- 1 Bond (+1d, may strain per GM decision)

**Important distinction**: *Sacrificing* a Bond/Trait destroys it (10 Gnosis, goes to Past). *Using* a Bond/Trait is the standard +1d modifier (modest empowerment, not destroyed).

**Magic Stat selection**: Player suggests which of the 5 stats applies. GM has final say and can change it during review.

**Style bonus**: Hidden GM-only modifier. GM can add bonus Gnosis for narrative quality, creative symbolism, etc. Not visible to the player.

### Dice Pool Calculation

For a Magic Action:
1. **Base dice** = Magic Stat level (0–5)
2. **Sacrifice dice** = total Gnosis equivalent converted via tiered table (see below)
3. **Use modifiers** = up to +3d from Core/Role/Bond use
4. **Total** = base + sacrifice dice + use modifiers

**Tiered Gnosis-to-Dice Conversion** (diminishing returns):

| Additional Dice | Gnosis Cost (cumulative) |
|----------------|-------------------------|
| 1 | 1 |
| 2 | 3 |
| 3 | 6 |
| 4 | 10 |
| 5 | 15 |
| 6 | 21 |

Formula: N additional dice costs N×(N+1)/2 total Gnosis. These rates are approximate and may be tuned during playtesting.

### Charge Action (Proposal Type)

A variant of the Magic Action workflow used to:
- **Recharge** a charged Magic Effect (restore charges, or increase max charges beyond original)
- **Boost** a permanent effect's power_level (enchanters building stronger items)

Same structure as Magic Action (intention, symbolism, sacrifice, stat selection, style bonus) but also selects which existing Magic Effect is being charged/boosted. Goes through proposal workflow — GM reviews and approves.

**What a Charge Action can modify:**
- **Charged effects**: Restore charges and/or increase max charges. Power_level is fixed at creation — only charges change. A strong Charge Action can grow max charges beyond the original value.
- **Permanent effects**: Increase power_level (within the 1–5 scale). The primary way enchanters improve items.

**Outcome determination**: Like Magic Actions, the GM interprets the dice roll results and decides how many charges to restore/add or how much to boost power_level. No formula — GM judgment.

### Magic Effects

Magic Effects are the **outcomes** of Magic Actions, created by the GM on the character's sheet. One Magic Action always produces exactly **one** Magic Effect (or one instant outcome). Three types:

**Instant Effects**
- One-time effects that resolve immediately
- Not tracked persistently on the sheet (logged as events)
- Do not count toward the effect cap

**Charged Effects**
- Persistently tracked on the character sheet
- Fields: `name`, `description`, `power_level` (1–5), `charges_current`, `charges_max` (unbounded)
- Each use costs 1 charge — **player initiates directly, no proposal needed** (pre-approved when created)
- Player can optionally add narrative text when using an effect (stored in event log, not required)
- At 0 charges: stays on sheet, can be recharged via Charge Action
- Can be recharged via Charge Action (proposal workflow) — can also increase max charges beyond original
- Power_level is fixed at creation — Charge Actions only affect charges, not power

**Permanent Effects**
- Always-active, infinite use, no charge meter
- Created primarily via the **Enchanting** Magic Stat
- Fields: `name`, `description`, `power_level` (1–5)
- Represent magic items, ongoing enchantments, persistent transformations
- Can be boosted (power_level increased, within 1–5 scale) via Charge Action

### Effect Cap

Characters can have at most **9 active Magic Effects** on their sheet (charged + permanent). Instant effects don't count. To add a new effect beyond the cap, an existing one must be retired. **Players can self-retire** their own effects directly (no proposal needed — removing power requires no GM gate). GM can also retire effects via direct action.

### Past/Retired Effects

Like Traits and Bonds, retired Magic Effects move to the Past section of the character sheet. Event history preserved, no mechanical use.

---

## Decisions

### Hardcoded Magic Stats

- **Decision**: The 5 Magic Stats are hardcoded: Being, Wyrding, Summoning, Enchanting, Dreaming.
- **Rationale**: Like Skills, a fixed set simplifies the model and ensures consistency across the campaign.
- **Implications**: Defined in code. All characters have all 5 stats at levels 0–5.

### Magic Stat Level = Base Dice

- **Decision**: Magic Stat level IS the base dice pool for magic actions using that stat. Not an additive modifier — it replaces the skill role for magical actions.
- **Rationale**: Magic Stats are the magical equivalent of Skills. Level 0 = no base, level 5 = strong base.
- **Implications**: Magic actions use Magic Stat level instead of Skill level as the base.

### XP System

- **Decision**: Flat 5 XP per level. GM awards XP directly. No automatic gain. XP resets to 0 when a Magic Stat gains a level — excess does not carry over.
- **Rationale**: GM controls progression pacing. Flat rate is simple. 5 XP per level provides granular progress (25 total for 0→5). Reset-to-0 is simpler to track than overflow.
- **Implications**: Magic Stat model needs an `xp` field. Level-up is triggered when XP reaches threshold. No overflow accounting needed.

### Freeform Magic Model

- **Decision**: Magic is freeform — players describe intention and symbolism rather than selecting from a spell list. Magic Effects are outcomes created by the GM, not pre-defined abilities.
- **Rationale**: Matches the narrative-heavy, low-crunch design. Encourages creative magic use.
- **Implications**: No spell list or effect catalog in the system. The Magic Action proposal is the creation mechanism.

### Sacrifice-Driven Power

- **Decision**: Magic power comes from sacrifice. Players spend Gnosis, take Stress, spend Free Time, or sacrifice Bonds/Traits — all converted to Gnosis at fixed rates, then converted to dice via a tiered table.
- **Rationale**: Magic should feel costly and meaningful. The sacrifice/power tradeoff is the central tension.
- **Implications**: Conversion rates defined (see table above). Trait/Bond sacrifice follows the standard "goes to Past" pattern.

### Sacrifice vs Use Distinction

- **Decision**: Bonds and Traits can be either *Sacrificed* (destroyed, 10 Gnosis equivalent) or *Used* (+1d modifier, standard stacking). Two distinct options on the same action.
- **Rationale**: Creates a meaningful choice between modest empowerment and dramatic sacrifice.
- **Implications**: Magic Action proposal UI needs both "sacrifice" and "use" sections for traits/bonds.

### Style Bonus

- **Decision**: GM can add a hidden bonus Gnosis amount for narrative quality during proposal review. Not visible to the player.
- **Rationale**: Rewards creative, well-described magic without revealing the exact mechanical boost.
- **Implications**: Proposal resolution includes a GM-only "style" field.

### Gnosis Range 0–23

- **Decision**: Gnosis has a maximum of 23.
- **Rationale**: Specific to the game's magical economy. The unusual max is a deliberate design choice tied to in-world lore.
- **Implications**: Gnosis is a substantial resource. At the max tiered cost, 21 Gnosis buys 6 additional dice.

### Effect Types

- **Decision**: Three Magic Effect types: instant (one-time, not tracked), charged (persistent, uses deplete charges), and permanent (always-active, no charges, primarily from Enchanting).
- **Rationale**: Covers the full range of magical outcomes — from a burst of fire to an enchanted sword.
- **Implications**: Effect model needs a type discriminator. Charged effects need a charge meter. Permanent effects have power_level but no charges.

### Direct Effect Use

- **Decision**: Using a charged Magic Effect is direct — player spends a charge, effect activates. No proposal needed. Pre-approved when the effect was created.
- **Rationale**: Effects represent magical capabilities the character already has. Requiring a proposal for each use would be too much friction.
- **Implications**: Effect use is a simple charge decrement + event log. No GM review.

### Effect Cap of 9

- **Decision**: Characters can have at most 9 active Magic Effects (charged + permanent). Instant effects don't count.
- **Rationale**: Prevents unbounded sheet growth. 9 is generous enough for a diverse magical portfolio.
- **Implications**: Adding beyond the cap requires retiring an existing effect.

### Charge Action

- **Decision**: Recharging effects and boosting permanent items uses the Charge Action — same workflow as Magic Action (intention, symbolism, sacrifice) but targeting an existing effect.
- **Rationale**: Recharging is itself an act of magic, not a simple resource transaction. Same cost structure applies.
- **Implications**: Charge Action is a distinct proposal action type. Enchanters use this to build increasingly powerful items.

### Player Suggests Stat, GM Decides

- **Decision**: Player suggests which Magic Stat applies to a Magic Action. GM has final say and can change it during review.
- **Rationale**: Player has the initial creative framing, but the GM interprets what school of magic the action actually falls under.
- **Implications**: Proposal includes a `suggested_stat` field. GM can override in the review step.

### Combined Sacrifice

- **Decision**: Players can combine any mix of sacrifice types in a single Magic Action (e.g., Gnosis + Stress + Bond sacrifice). All converted to Gnosis equivalent and summed.
- **Rationale**: Allows dramatic, multi-resource magical expenditure. The proposal stores a list of sacrifice entries rather than a single choice.
- **Implications**: Sacrifice field in proposal data model is an array of `{type, amount, target?}` entries. Total Gnosis equivalent is computed server-side.

### Stress Sacrifice Triggers Trauma

- **Decision**: If voluntary Stress sacrifice pushes a character to their effective max, Trauma triggers normally (Bond replaced, Stress resets to 0).
- **Rationale**: Standard Stress rules apply universally. Stress sacrifice should feel genuinely dangerous, not safe. This creates high-stakes magical moments.
- **Implications**: Stress sacrifice processing must check for Trauma trigger after applying Stress. Edge case: sacrifice could cause Trauma mid-Magic-Action resolution.

### Effect Creation is GM-Interpreted

- **Decision**: The GM creates the Magic Effect by interpreting the dice roll results. GM writes the description (informed by the player's intention and roll outcome), sets power_level (1–5), and sets initial charges based on roll results. No system formula.
- **Rationale**: Keeps the GM as the narrative arbiter. Dice inform the outcome, but the GM shapes the fiction.
- **Implications**: No server-side effect generation. The approval step includes a form for the GM to fill in effect details.

### Magic Stats Start at Zero

- **Decision**: All Magic Stats start at level 0 for new characters. Progression is entirely through GM XP awards.
- **Rationale**: Magic power is earned through play, not assigned at creation. Consistent with the GM-controlled progression model.
- **Implications**: Character creation does not include Magic Stat level allocation. Initial XP is 0.

### Power Level Scale 1–5

- **Decision**: Magic Effect power_level uses a 1–5 scale for both charged and permanent effects.
- **Rationale**: Mirrors other bounded scales in the system (Skills 0–3, Magic Stats 0–5). Gives the GM clear calibration without excessive granularity.
- **Implications**: Power_level field is an integer 1–5. GM sets it at creation. Charge Actions can increase it on permanent effects only.

### Charges Are Unbounded

- **Decision**: Charged effects have no system-imposed cap on charges. GM sets initial charge count freely. Implementation uses a current/max pair.
- **Rationale**: Keeps the system flexible for GM judgment. Some effects may warrant 3 charges, others 20.
- **Implications**: Charge fields: `charges_current` (int), `charges_max` (int). Both modifiable by GM direct action and Charge Actions.

### Charge Actions Can Increase Max Charges

- **Decision**: A Charge Action can increase a charged effect's max charges beyond its original value, in addition to restoring current charges. Represents magical reinvestment strengthening the effect.
- **Rationale**: Allows charged effects to grow over time, rewarding continued magical investment.
- **Implications**: Charge Action outcome includes both charges restored and potential max increase. GM decides during approval.

### Charge Actions on Charged vs Permanent

- **Decision**: Charge Actions on charged effects affect charges only (restore + increase max). Charge Actions on permanent effects increase power_level only. Power_level on charged effects is fixed at creation.
- **Rationale**: Clean separation — charged effects grow in capacity, permanent effects grow in strength. Different investment paths.
- **Implications**: Charge Action resolution logic branches on target effect type.

### Charge Magic Approval Outcome

- **Decision**: On `charge_magic` approval, the GM provides `{charges_added?: int, power_boost?: int}` in `gm_overrides`. For charged effects: `charges_added` restores that many charges (current increases, and if current would exceed max, max increases to match). For permanent effects: `power_boost` increases `power_level` (within the 1–5 scale). Fields are mutually exclusive based on target effect type.
- **Rationale**: Explicit fields make the GM's intent clear. Separate fields for the two effect types avoid ambiguity.
- **Implications**: System validates that the correct field is provided for the target effect type. `charges_added` can grow `charges_max` beyond the original value.

### Effect Use Request Body

- **Decision**: `POST /characters/{id}/effects/{effect_id}/use` takes `{narrative?: string}`. Player can optionally describe what they're doing with the effect. No target or context fields.
- **Rationale**: Effects are self-contained — the narrative is freeform flavor. Target/context tracking would add complexity without clear benefit for a narrative-first system.
- **Implications**: Event logged with optional narrative text. No validation beyond charge > 0.

### One Effect Per Magic Action

- **Decision**: A single Magic Action always produces exactly one Magic Effect (or one instant outcome). Multiple effects require multiple actions.
- **Rationale**: Keeps the action→outcome relationship simple and predictable. One proposal, one result.
- **Implications**: No multi-effect creation flow needed.

### Player Initiates Effect Use

- **Decision**: Players initiate charged effect use directly — click "use", system decrements 1 charge, event logged. No GM approval needed.
- **Rationale**: Effects are pre-approved at creation. Requiring GM review for each use would create too much friction for an ability the character already has.
- **Implications**: Dedicated endpoint for effect use. Player can optionally add narrative text (stored in event). Event type: `effect_use`.

### Player Can Self-Retire Effects

- **Decision**: Players can retire their own Magic Effects directly without a proposal or GM approval. Effect moves to Past.
- **Rationale**: Retirement removes power, it doesn't add it. No GM gate needed for voluntary power reduction.
- **Implications**: Dedicated endpoint or action for effect retirement. Frees cap space for new effects.

### Regain Gnosis Formula

- **Decision**: The "Regain Gnosis" downtime activity costs 1 Free Time and restores: **3 Gnosis base + lowest Magic Stat level + up to +3 from trait/bond invocation** (standard stacking: 1 Core Trait +1, 1 Role Trait +1, 1 Bond +1).
- **Rationale**: Base mirrors the Free Time sacrifice conversion rate. Lowest Magic Stat ensures even non-specialists can recover. Trait/bond stacking rewards investment.
- **Implications**: Server-side calculation. Trait charges are spent as usual. Bond may strain per GM decision. Goes through proposal workflow like other downtime activities.

---

## API Endpoints

Magic is accessed via the character sheet and proposal system:

- `GET /api/v1/characters/{id}` — full sheet includes Gnosis, Magic Stats (with XP), and all Magic Effects (active and past)
- Magic Action: submitted as a proposal via `POST /api/v1/proposals` (action type: `use_magic`)
- Charge Action: submitted as a proposal via `POST /api/v1/proposals` (action type: `charge_magic`)
- Effect use (charged): `POST /api/v1/characters/{id}/effects/{effect_id}/use` — player-initiated, decrements 1 charge, logs event. Body: `{narrative?: string}` (optional freeform description of the use).
- Effect retire: `POST /api/v1/characters/{id}/effects/{effect_id}/retire` — player-initiated, moves to Past, frees cap space. Empty body.
- "Regain Gnosis" downtime: submitted as a proposal via `POST /api/v1/proposals`
- GM actions (award XP, create/edit/retire effects, modify Gnosis): via `POST /api/v1/gm/actions` with action types `award_xp`, `create_effect`, `modify_effect`, `retire_effect`, `modify_character`. See [actions.md](actions.md).

---

## Implications for Other Specs

| Spec | Implication |
|------|-------------|
| [actions](actions.md) | 🔄 Two new action types: Magic Action and Charge Action. Sacrifice is a list of entries (combined freely). Magic Action has unique structure (intention, symbolism, sacrifice list). Style bonus is GM-only field. GM creates effect during approval (name, description, power_level, charges). |
| [downtime](downtime.md) | 🔄 "Regain Gnosis" formula defined: 1 FT = 3 base + lowest Magic Stat + up to +3 from trait/bond use. Charge Action can also be done during downtime. |
| [traits](traits.md) | Traits can be *Sacrificed* (destroyed, goes to Past, 10 Gnosis) in Magic Actions. Distinct from *Using* a trait (+1d). Traits can also be invoked on Regain Gnosis for +1 Gnosis. |
| [bonds](bonds.md) | Bonds can be *Sacrificed* (destroyed, goes to Past, 10 Gnosis) in Magic Actions. Distinct from *Using* a bond (+1d). Bonds can also be invoked on Regain Gnosis for +1 Gnosis. |
| [character-core](character-core.md) | Gnosis, Magic Stats (with XP, all start at 0), and Magic Effects are sub-entities of the Character sheet. Stress can be voluntarily taken as sacrifice (can trigger Trauma). Players can directly use and retire effects. |
| [events](events.md) | Magic Actions, Charge Actions, effect use (with optional narrative), effect retirement, Gnosis changes, XP awards, and sacrifice events are all logged. |
| [architecture/data-model](../architecture/data-model.md) | 🔄 Magic Effect model (three types, power_level 1–5, charges current/max unbounded), Magic Stat model (with XP, starts at 0), sacrifice as array of entries. |

---

## Open Questions

_All resolved._

1. ~~**Action type name mismatch**~~: **Resolved** — `use_magic` and `charge_magic` are the canonical action type names (per [actions.md](actions.md) action type catalog). This spec's API section references updated accordingly.
2. ~~**Magic Effect `use` request body**~~: **Resolved** — Body is `{narrative?: string}`. Optional freeform description. No target or context fields.
3. ~~**XP award endpoint**~~: **Resolved** — GM awards Magic Stat XP via `POST /api/v1/gm/actions` with action type `award_xp`. Level-up is automatic when XP reaches the threshold (5 per level). See [actions.md](actions.md).
4. ~~**Magic Effect creation on `charge_magic` approval**~~: **Resolved** — GM provides `{charges_added?: int, power_boost?: int}` in `gm_overrides`. `charges_added` for charged effects (can grow max), `power_boost` for permanent effects. Mutually exclusive based on effect type.

---

_Last updated: 2026-03-15 (added XP reset-to-0 on level-up clarification)_
