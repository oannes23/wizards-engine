"""Alembic environment configuration for Wizards Engine.

This file is executed by Alembic when running ``alembic upgrade``,
``alembic downgrade``, or ``alembic revision --autogenerate``.

It imports ``Base`` from the models package so that autogenerate can
compare the current SQLAlchemy metadata against the live database schema.

The database URL is constructed from the ``WIZARDS_DB_PATH`` environment
variable (falling back to ``wizards_engine.db``) rather than hardcoded in
``alembic.ini``.
"""

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# ---------------------------------------------------------------------------
# Ensure the src/ package is importable when running alembic from the project
# root (i.e., before the package is installed in editable mode in every env).
# ---------------------------------------------------------------------------
_repo_root = Path(__file__).resolve().parent.parent
_src_path = str(_repo_root / "src")
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

# Import all models so that SQLAlchemy's mapper registry is fully populated
# before autogenerate inspects the metadata.  The package __init__.py imports
# every model module in dependency order, so a single package import is enough.
import wizards_engine.models  # noqa: F401 — registers all 18 models

from wizards_engine.models.base import Base  # noqa: E402

target_metadata = Base.metadata

# ---------------------------------------------------------------------------
# Alembic config and logging
# ---------------------------------------------------------------------------

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# Database URL
# ---------------------------------------------------------------------------

from wizards_engine.db import _DEFAULT_DB_PATH

_db_path = os.environ.get("WIZARDS_DB_PATH", _DEFAULT_DB_PATH)
_db_url = f"sqlite:///{_db_path}"

# Override whatever is in alembic.ini with the runtime-resolved URL.
config.set_main_option("sqlalchemy.url", _db_url)

# ---------------------------------------------------------------------------
# Migration runners
# ---------------------------------------------------------------------------


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (generates SQL without a live connection)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connects to the database directly)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
