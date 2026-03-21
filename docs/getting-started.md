# Getting Started

Set up Wizards Engine on your local machine, create the GM account, and invite your players.

## Prerequisites

- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** -- Python package manager
- **Git**

## Install

```bash
git clone <repo-url>
cd wizards-engine
uv pip install -e ".[dev]"
```

## Initialize the Database

```bash
uv run alembic upgrade head
```

This creates a SQLite database file. By default it's `wizards_engine.db` in the current directory. Set `WIZARDS_DB_PATH` to use a different location:

```bash
WIZARDS_DB_PATH=/path/to/game.db uv run alembic upgrade head
```

## Start the Server

```bash
uv run uvicorn wizards_engine.app:app --reload
```

The server starts at `http://localhost:8000`. For local HTTP (no HTTPS), disable the secure cookie flag:

```bash
WIZARDS_COOKIE_SECURE=false uv run uvicorn wizards_engine.app:app --reload
```

## GM Setup

1. Open `http://localhost:8000/setup` in your browser.
2. Enter your display name (you'll appear as "GM [name]").
3. Save the magic link the system gives you -- it's your permanent login URL. Bookmark it.

The setup endpoint locks permanently after first use.

## Invite Players

1. Navigate to the Invites screen from your GM dashboard.
2. Create an invite -- you'll get a magic link URL.
3. Share that link with your player (text, email, etc.).
4. When they open it, they'll see a join form where they enter their display name and character name.
5. After joining, the same link becomes their permanent login.

Repeat for each player. You can manage all invites and player links from the Player Roster screen.

## Import Campaign Data (Optional)

If you have existing campaign data in YAML format, use the `wizards-campaign` CLI to import it.

Validate first:

```bash
uv run wizards-campaign validate --input campaign-data/
```

Then import:

```bash
uv run wizards-campaign import --input campaign-data/
```

See [campaign-format.md](campaign-format.md) for the full YAML reference.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `WIZARDS_DB_PATH` | `wizards_engine.db` | SQLite database file path |
| `WIZARDS_COOKIE_SECURE` | `true` | Set to `false` for local HTTP development (no HTTPS) |
| `CORS_ORIGINS` | *(empty)* | Comma-separated allowed origins for CORS; not needed when frontend is served from the same origin |

## Next Steps

- [Deployment](deployment.md) -- put it on a server for your group
- [GM Guide](gm-guide.md) -- learn the session workflow and GM tools
- [Player Guide](player-guide.md) -- share with your players
