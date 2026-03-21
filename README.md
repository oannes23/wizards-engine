# Wizards Engine

A backend state tracker for a single narrative-heavy, low-crunch tabletop RPG campaign. Tracks character sheets, game world state, and provides a proposal workflow for player actions. API-first REST backend for a small fixed group (4-6 players + 1 GM).

**Not** a dice roller or virtual tabletop -- all rolling happens at the physical table. The system tracks the mechanical consequences.

## What It Tracks

- **Characters** (PCs and NPCs) -- meters (Stress, Free Time, Plot, Gnosis), 8 skills, 5 magic stats, traits, bonds, magic effects
- **Game Objects** -- Characters, Groups (orgs/factions), Locations (nestable hierarchy)
- **Proposals** -- 12 action types: 3 session actions, 7 downtime actions, 2 system-generated
- **Events** -- append-only log with 7-level bond-distance visibility filtering
- **Sessions** -- lifecycle (Draft -> Active -> Ended), resource distribution, clock tracking

## Quick Start

```bash
git clone <repo-url> && cd wizards-engine
uv pip install -e ".[dev]"
uv run alembic upgrade head
uv run uvicorn wizards_engine.app:app --reload
```

Visit `/setup` to create the GM account. See [docs/getting-started.md](docs/getting-started.md) for the full walkthrough.

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11+ |
| Framework | FastAPI |
| Database | SQLite |
| ORM | SQLAlchemy |
| Migrations | Alembic |
| Validation | Pydantic |
| Frontend | Pico CSS + Alpine.js |
| Testing | pytest |

## Documentation

| Guide | Audience | Description |
|-------|----------|-------------|
| [Getting Started](docs/getting-started.md) | GM | Install, run, set up your game |
| [Deployment](docs/deployment.md) | GM | Production server with systemd + Caddy |
| [GM Guide](docs/gm-guide.md) | GM | Running sessions, reviewing proposals, world management |
| [Player Guide](docs/player-guide.md) | Players | Character sheet, proposals, feed |
| [Campaign Format](docs/campaign-format.md) | GM | YAML import/export reference |
| API Reference | All | Interactive docs at `/docs` when the server is running |

## Project Status

Fully implemented -- 7 phases, 21 epics, 91 stories, ~2,750 passing tests. See [`spec/implementation/README.md`](spec/implementation/README.md) for the full breakdown.

## License

Private project -- not open source.
