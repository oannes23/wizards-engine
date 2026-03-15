# MVP Scope

**Status**: 🟢 Complete
**Last interrogated**: 2026-03-04
**Last verified**: —

---

## MVP Philosophy

Single MVP — the full system. This is a backend for 4-6 people playing a tabletop game; the domain is well-defined and the implementation surface is manageable. No MVP 0/1 split. Instead, define a phased build order (which epics to implement first).

---

## Scope: Everything

### What's In

The MVP includes the complete system as specified across all domain specs:

- **Auth**: Setup endpoint, token middleware, GM account. Invite flow deferred to later phase — seed test users during development.
- **Game Objects**: All types — NPCs, Groups, Clocks, Locations, Sessions, Stories. Full CRUD with soft delete.
- **Characters**: Full sheet — Stress, FT, Plot, Gnosis, Skills (8), Magic Stats (5), Traits (Core ×2, Role ×3), Bonds (×7), Magic Effects (cap 9), Notes.
- **Proposals**: All 10 action types (3 session + 7 downtime) plus `resolve_clock` (system-generated). Full workflow: submit → calculate → GM approve/reject.
- **Magic**: Magic Actions, Charge Actions, Magic Effects, sacrifice system, Gnosis, Magic Stats.
- **Downtime**: Session lifecycle (Draft→Active→Ended), FT distribution, clock adjustments, all downtime actions.
- **Events**: Append-only log, bond-distance visibility (computed on read), convention-based types.
- **Web UI**: Basic web frontend — character sheets, proposal submission, GM approval dashboard.

### What's Explicitly Out

| Feature | Why | Revisit When |
|---------|-----|-------------|
| Real-time notifications (WebSockets/SSE) | Not essential — polling/manual refresh is fine | If players complain about stale data |
| Multi-campaign support | Single campaign by design | Probably never |
| Event visibility caching | Compute on read is fine for 4-6 players | If query performance is actually slow |
| Event undo/replay | GM corrects via direct actions | If undo is frequently needed in play |
| Spectator role | Two roles only (GM, player) | If someone wants to watch |

---

## Decisions

### Single MVP, Phased Build

- **Decision**: No MVP 0/1 split. The full system is the target. Implementation is organized as a phased build order (6 phases), not feature tiers.
- **Rationale**: The system isn't that big — it's a backend for a small TTRPG group. All the domains are interconnected. Shipping half the system isn't useful.
- **Implications**: Epic/Story specs should be organized by build phase, not by feature tier.

### Rider Events on Proposal Approval

- **Decision**: When approving a proposal, the GM can optionally attach a **rider event** — a bundled GM direct-action event that fires atomically with the approval. Same schema as any event: targets, changes, narrative.
- **Rationale**: The GM often needs to narrate side effects when approving an action. "Yes, your skill check succeeds AND the clock advances +2 AND this NPC reacts." Bundling avoids multiple manual steps.
- **Implications**: Proposal approval endpoint accepts an optional rider event payload. Rider event is created in the same transaction as the approval event. Updates proposals.md with this concept.

### System-Generated `resolve_clock` Proposal

- **Decision**: When a clock reaches completion (progress >= segments), the system auto-generates a proposal of type `resolve_clock`, pre-linked to the clock and its containing game objects (e.g., the Group that owns a project clock). The GM fills in narrative and optionally attaches a rider event to apply world state changes.
- **Rationale**: Clock completion is the GM's cue to narrate what happens. A proposal template gives the GM a structured place to write the outcome and mechanically apply consequences (e.g., reset another group's clock, create a story entry). This extends the Deferred Narrative Resolution principle — the clock tracked progress, the resolution is written when it completes.
- **Implications**: New proposal type `resolve_clock` (11th type, system-initiated). Proposals spec needs update. Clock completion detection logic needed. Rider event mechanism required.

### Typed Calculated Effect Per Action Type

- **Decision**: The `calculated_effect` field on proposals is a structured object with a known schema per action type. E.g., `use_skill: {dice_pool: 4, modifiers: [...]}`, `rest: {stress_healed: 5}`, `regain_gnosis: {gnosis_gained: 7}`. The GM can override any field.
- **Rationale**: Typed schemas are readable, validatable, and provide clear override points for the GM. The system pre-computes expected effects; the GM tweaks if needed. Most of the time the GM just hits approve.
- **Implications**: Each action type needs a defined effect schema. These schemas are part of the Pydantic model layer.

### Simplified Story Entry CRUD

- **Decision**: Story entries support simple CRUD with soft-delete. Fields: `text`, `created_at`, `created_by`, `updated_at`, `updated_by`, `is_deleted`. Players can create/edit/delete their own entries; GM can CRUD any entry. No full audit trail — just last-edit timestamp and editor.
- **Rationale**: Full audit trail (deleted_by, edit history) adds complexity for no practical gain in a 4-6 player game. A simple last-edit stamp is sufficient.
- **Implications**: Simplifies game-objects story entry model. Updates game-objects.md.

### Compute-On-Read Event Visibility

- **Decision**: Event visibility is computed per request based on the bond graph. No caching layer. The bond-distance calculation runs on every query.
- **Rationale**: SQLite can handle the bond graph traversal for 4-6 players. The cache + invalidation complexity isn't worth it at this scale. Add caching only if performance is measured as a problem.
- **Implications**: No cache invalidation logic needed. Events spec's "cached per character, invalidated on bond changes" is deferred. Simplifies implementation significantly.

### Player-Written Narratives

- **Decision**: Players write the narrative on proposal submission. When the GM agrees, they just hit approve — the player's narrative becomes the event narrative. GM can edit the narrative before approving or reject with a note for revision.
- **Rationale**: Reduces GM workload. Players describe their own actions. The GM is an arbiter, not a narrator-of-everything. Most proposals are straightforward.
- **Implications**: Proposal model has a `narrative` field filled by the player. Approval can optionally override it.

### Full Test Coverage with Fixture DB

- **Decision**: Comprehensive integration test suite from the start. Test through the FastAPI test client (pytest + httpx). Each test gets a fresh SQLite DB loaded with a canonical test fixture (full game state: GM, players, characters, game objects, proposals, events). Seed data is separate from production.
- **Rationale**: The cost of full test coverage is low for a project this size, and the reliability payoff is high. Testing validates the interconnected domain logic that spans multiple entities.
- **Implications**: Need a test fixture module that generates a complete, realistic game state. Tests are integration-heavy — fewer unit tests, more endpoint-level tests.

### Auth: Seed Early, Invite Flow Later

- **Decision**: Phase 1 builds the setup endpoint, token middleware, and GM account creation. Player accounts are seeded directly in the test DB during development. The invite generation and join flow are built in a later phase.
- **Rationale**: Gets to game logic faster. The invite flow is important for production but not for validating the core system. Test fixtures provide all the accounts needed.
- **Implications**: Auth phase is lighter. Invite endpoints are a separate epic in a later phase.

### Web UI as Phase 6

- **Decision**: The web UI is built after all API phases (1-5) are complete. During API development, OpenAPI/Swagger docs serve as the testing interface.
- **Rationale**: API-first approach. The API is the product; the UI is a consumer. Building the UI last means it's built against a stable, complete API. Swagger UI is sufficient for development testing.
- **Implications**: UI is a separate phase with its own epics. API design must be self-documenting (good OpenAPI schemas).

---

## Phased Build Order

### Phase 1: Foundation
- Project scaffolding (FastAPI, SQLAlchemy, Alembic, pytest)
- Database schema and migrations
- Auth middleware (token-based)
- Setup endpoint (create GM account)
- Test fixture system (canonical seed data)
- API skeleton (health check, OpenAPI docs)

### Phase 2: World
- Game object CRUD: NPCs, Groups, Locations, Stories, Clocks
- Soft delete across all types
- Lightweight bonds (NPC/Group bonds with directionality rules)
- Location hierarchy (nesting, curated affiliations, computed presence)
- Story entries (simple CRUD, soft-delete)
- Clock mechanics (segments, progress, completion detection)
- Group computed members, Story owners sub-resource

### Phase 3: Characters
- Character sheet (full model: meters, skills, magic stats)
- Trait Template catalog (GM-created)
- Trait Instances (Core ×2, Role ×3) with charges
- Bond Instances (×7) with stress/degradation
- Bond targets (polymorphic refs to game objects)
- Magic Effects on character sheet
- Computed values (effective stress max, trait/bond counts)
- Past/Retired section

### Phase 4: Actions
- Proposal workflow (submit → calculate → approve/reject)
- All 10 player action types + `resolve_clock`
- Typed calculated_effect per action type
- GM approval with overrides
- Rider events on approval
- Event log (append-only, convention-based types)
- Bond-distance visibility (computed on read)
- Magic Actions + Charge Actions + sacrifice system
- Resource deduction on approval (FT, charges, Gnosis, stress)

### Phase 5: Sessions
- Session lifecycle (Draft → Active → Ended)
- FT distribution (Time Now delta)
- Plot distribution (+1/+2 with Additional Contribution)
- Player registration + late joins
- Clock adjustments during Active sessions
- Session concurrency enforcement (one Active at a time)
- Invite generation and join flow
- GM token regen
- Find Time (direct player action, 3 Plot → 1 FT)

### Phase 6: Web UI
- Basic mobile-friendly web frontend
- Character sheet view (read + notes editing)
- Proposal submission forms
- GM approval dashboard
- Game object browsing/management
- Session management

---

## Success Criteria

The system is "done" when:

1. **All API endpoints functional** — every domain spec's API surface is implemented and tested
2. **Full test coverage** — integration tests for all endpoints using the fixture DB
3. **Basic web UI** — character sheets, proposal submission, GM approval dashboard, game object management
4. **Usable at the table** — non-developer players can interact with the system via the web UI during a real session
5. **Data integrity** — event log captures all state changes, soft delete works correctly, proposal workflow enforces validation

---

## Open Questions

All resolved.

---

_Last updated: 2026-03-04_
