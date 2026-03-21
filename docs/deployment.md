# Deployment

Run Wizards Engine on a Linux VPS with systemd and Caddy (automatic HTTPS). The stack is a single Python process serving both the API and the frontend, backed by a SQLite file.

## Server Requirements

- Linux VPS (any provider -- DigitalOcean, Hetzner, Linode, etc.)
- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- A domain name pointed at the server (e.g. `wizards.example.com`)

## Install on Server

```bash
git clone <repo-url> /opt/wizards-engine
cd /opt/wizards-engine
uv pip install -e .
```

## Run Migrations

```bash
WIZARDS_DB_PATH=/opt/wizards-engine/data/game.db \
  uv run alembic upgrade head
```

Create the data directory first if needed: `mkdir -p /opt/wizards-engine/data`

## systemd Service

Create `/etc/systemd/system/wizards-engine.service`:

```ini
[Unit]
Description=Wizards Engine
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/wizards-engine
Environment=WIZARDS_DB_PATH=/opt/wizards-engine/data/game.db
ExecStart=/usr/bin/env uv run uvicorn wizards_engine.app:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now wizards-engine
```

Check status: `sudo systemctl status wizards-engine`

View logs: `sudo journalctl -u wizards-engine -f`

## Caddy Reverse Proxy

[Caddy](https://caddyserver.com/) handles HTTPS automatically via Let's Encrypt.

Install Caddy, then add to `/etc/caddy/Caddyfile`:

```
wizards.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

Reload: `sudo systemctl reload caddy`

That's it -- Caddy obtains and renews TLS certificates automatically. Your game is live at `https://wizards.example.com`.

## Backups

The entire game state lives in one SQLite file. Back it up by copying it:

```bash
# Safe copy (works even if the server is running with WAL mode)
sqlite3 /opt/wizards-engine/data/game.db ".backup /backups/game-$(date +%F).db"
```

You can also export to YAML for a human-readable backup:

```bash
WIZARDS_DB_PATH=/opt/wizards-engine/data/game.db \
  uv run wizards-campaign export --output /backups/campaign-$(date +%F)/
```

Automate with a cron job:

```bash
# Daily backup at 4 AM
0 4 * * * sqlite3 /opt/wizards-engine/data/game.db ".backup /backups/game-$(date +\%F).db"
```

## Updating

```bash
cd /opt/wizards-engine
git pull
uv pip install -e .
WIZARDS_DB_PATH=/opt/wizards-engine/data/game.db uv run alembic upgrade head
sudo systemctl restart wizards-engine
```

## Nginx Alternative

If you prefer Nginx over Caddy, use this server block (you'll need to manage TLS certificates separately via certbot):

```nginx
server {
    listen 443 ssl;
    server_name wizards.example.com;

    ssl_certificate /etc/letsencrypt/live/wizards.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/wizards.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Troubleshooting

**409 on `/setup`**: The GM account already exists. If this is a fresh install and you're seeing this, check that you're pointing at the right database file.

**Cookie issues / can't stay logged in**: Make sure you're accessing the site over HTTPS. The auth cookie has `Secure=true` by default, which means browsers won't send it over plain HTTP. If you're testing without HTTPS, set `WIZARDS_COOKIE_SECURE=false` in the systemd environment.

**"database is locked" errors**: SQLite handles concurrent reads well but serializes writes. This is fine for 4-6 players. If you see lock errors, ensure only one server process is running against the database file. Check for stale `-wal` or `-shm` files if the server crashed.

**Players can't connect**: Verify the domain resolves to your server (`dig wizards.example.com`), Caddy is running (`systemctl status caddy`), and the app is running (`systemctl status wizards-engine`).
