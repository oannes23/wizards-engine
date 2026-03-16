# Wizards Engine — Project Conventions

This document defines conventions for any Claude instance (or human) working on this project.

---

## Project Overview

A backend state tracker for a single narrative-heavy, low-crunch tabletop RPG campaign. Tracks character sheets, game world state, and provides a proposal workflow for player actions. API-first REST backend for a small fixed group (4–6 players + 1 GM).

**Core principle**: Mutable state + append-only event log. No DSL — all game logic is hardcoded in Python. API-first REST.

**Current phase**: Specification complete. Ready for implementation.

---

## Repository Structure

```
wizards-engine/
├── spec/                    # Agent-centric specifications (structured for LLM consumption)
│   ├── MASTER.md            # Central index and status tracker
│   ├── glossary.md          # Canonical term definitions
│   ├── walkthrough.md       # End-to-end UX walkthrough (player + GM journeys)
│   ├── architecture/        # System-level design docs
│   ├── domains/             # Feature area specifications (11 specs, all complete)
│   └── implementation/      # Epic and Story specs (13 epics, 46 stories, Phases 1-5)
├── docs/
│   └── archive/             # Historical design notes (engine-original-notes.md)
├── .claude/
│   ├── CLAUDE.md            # This file
│   └── commands/            # Custom slash commands
└── src/                     # Source code (future)
```

---

## Specification Conventions

### Document Format

Spec documents use structured decision blocks:

```markdown
### [Decision Area]

- **Decision**: [What was decided]
- **Rationale**: [Why this choice was made]
- **Implications**: [What this affects downstream]
- **Alternatives considered**: [Optional — what else was evaluated]
```

### Status Tracking

MASTER.md tracks spec status:
- 🔴 Not started
- 🟡 In progress
- 🟢 Complete
- 🔄 Needs revision

### Cross-References

Use relative markdown links for cross-document references:
```markdown
See [example.md](domains/example.md) for details.
```

### Glossary Usage

- All domain terms should have canonical definitions in glossary.md
- When introducing a new term, add it to the glossary
- Use consistent terminology across all documents

---

## Available Commands

### Spec Development

| Command | Purpose |
|---------|---------|
| `/interrogate <spec-path>` | Deepen a spec through structured Q&A |
| `/ingest <notes-file>` | Extract spec content from unstructured notes |
| `/new-domain <name>` | Scaffold a new domain spec from template |

### Spec Maintenance

| Command | Purpose |
|---------|---------|
| `/status` | Dashboard view of all spec statuses |
| `/verify <spec-path>` | Check spec against code, update "Last verified" |
| `/sync-spec <spec-path>` | Deep audit and reconciliation of spec vs code |

### Documentation

| Command | Purpose |
|---------|---------|
| `/human-docs <spec-path>` | Generate human-readable docs from specs |

---

## Interrogation Workflow

The `/interrogate` command drives spec development:

1. Invoke with target: `/interrogate spec/domains/<area>`
2. Agent reads context (MASTER.md, target doc, glossary, related docs)
3. Agent asks 3-5 multiple choice questions per round
4. User answers
5. Agent updates target doc, glossary, and MASTER.md
6. Repeat until no open questions remain

### Question Format

Questions should be:
- Multiple choice with 2-4 options
- Include "Other" when appropriate
- Have short headers (≤12 chars)
- Use `multiSelect=true` when multiple answers apply

---

## Verification Workflow

Specs can become stale as implementation evolves. Use these commands to keep them in sync:

1. **Regular checks**: Run `/status` to see which specs need attention
2. **After implementation**: Run `/verify <spec>` to confirm spec matches code
3. **Major drift**: Run `/sync-spec <spec>` for deep reconciliation

### Last Verified Field

All specs include a "Last verified" metadata field:
- `—` means never verified against implementation
- Date means last confirmed accurate
- Specs not verified in 30+ days are flagged as possibly stale

---

## Implementation Hierarchy

When we reach implementation:

```
Phase (major milestone)
└── Epic (~5 stories, one orchestration session)
    └── Story (atomic unit, one agent session)
```

**Sizing heuristics:**
- **Story**: Completable in one focused session. Clear acceptance criteria. Produces testable artifact.
- **Epic**: Related stories. Completion = demonstrable capability.
- **Phase**: Business milestone.

---

## Implementation Progress Tracking

After completing a Story, update progress tracking in this order:

1. **Epic file** (`spec/implementation/phase*-*.md`): In the story status table, set the story's status to `🟢 Complete` and the Completed column to today's date (YYYY-MM-DD).
2. **README** (`spec/implementation/README.md`): Increment the Progress column for the epic (e.g., `0/4` → `1/4`). Update the epic's Status using the derivation rules below.

### Status Values

- `🔴 Not started` — no stories started
- `🟡 In progress` — at least one story is `🟡 In progress` or `🟢 Complete`, but not all `🟢 Complete`
- `🟢 Complete` — all stories `🟢 Complete`

### Epic Status Derivation

- All stories `🔴` → Epic is `🔴 Not started`
- Any story `🟡` or `🟢` but not all `🟢` → Epic is `🟡 In progress`
- All stories `🟢` → Epic is `🟢 Complete`

### When Starting a Story

Set the story's status to `🟡 In progress` in the epic file's status table. If the epic was `🔴`, update it to `🟡 In progress` in README.md.

---

## Technical Conventions

### Stack
- **Language**: Python 3.11+
- **Framework**: FastAPI
- **Database**: SQLite
- **ORM**: SQLAlchemy
- **Migrations**: Alembic
- **Validation**: Pydantic
- **IDs**: ULIDs (python-ulid)
- **Package management**: uv + pip (`pip install -e .`)
- **Dev server**: `uvicorn --reload`

### Code Style
- Type hints where applicable
- Docstrings for public functions
- Tests alongside code (pytest + httpx test client)
- Integration tests against fixture DB (canonical seed data per test)

### Key Implementation Decisions
- **Bond-graph traversal**: App-layer BFS in Python (load active bonds into memory, traverse with standard BFS). Not SQL recursive CTEs. See `spec/architecture/overview.md`.
- **System proposals**: Two auto-generated proposal types — `resolve_clock` (on clock completion) and `resolve_trauma` (on Stress hitting max). Both follow the same pattern: system detects boundary → generates pending proposal → GM fills in details and approves.
- **Bond charges**: Bonds use "charges" (0–5) conceptually identical to trait charges. Physical DB columns are named `stress`/`stress_degradations` for historical reasons. See `spec/domains/bonds.md`.
- **12 action types**: 3 session actions + 7 downtime actions + 2 system proposals. See `spec/domains/actions.md`.
- **Magic Stat XP**: Resets to 0 on level-up. No overflow carry.

---

## Files to Read First

When starting work:
1. `spec/MASTER.md` — overall status and structure
2. `spec/glossary.md` — term definitions
3. `spec/architecture/overview.md` — system context
4. Target domain spec — the area you're working on

---

## Communication Style

- Be precise about domain terminology
- Reference glossary definitions
- Flag ambiguities explicitly
- Distinguish between "decided" and "tentative"
- Update MASTER.md status after changes

---

_This document is the ground truth for project conventions._
