"""Tests for Story 1.1.3 — All Table Migrations.

Covers:
- alembic upgrade head creates all 18 tables
- all composite primary keys are present
- all required indexes exist (users.login_code, slots composite indexes)
- alembic downgrade base drops all 18 tables cleanly
- re-applying upgrade head after downgrade succeeds
"""

import os
import tempfile

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The 18 application tables expected after upgrade head.
_EXPECTED_TABLES = {
    "users",
    "invites",
    "characters",
    "groups",
    "locations",
    "trait_templates",
    "slots",
    "magic_effects",
    "clocks",
    "sessions",
    "session_participants",
    "stories",
    "story_owners",
    "story_entries",
    "events",
    "event_targets",
    "proposals",
    "starred_objects",
}


def _make_alembic_config(db_path: str) -> Config:
    """Return an Alembic Config pointing at a temporary SQLite database."""
    cfg = Config(os.path.join(_REPO_ROOT, "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    # Ensure env.py uses the same URL by setting the env var that env.py reads.
    os.environ["WIZARDS_DB_PATH"] = db_path
    return cfg


def _get_table_names(db_path: str) -> set[str]:
    """Return the set of user-created table names in the SQLite file."""
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name != 'alembic_version'")
        ).fetchall()
    engine.dispose()
    return {row[0] for row in rows}


def _get_indexes(db_path: str, table: str) -> list[dict]:
    """Return index info for a table via SQLAlchemy inspect."""
    engine = create_engine(f"sqlite:///{db_path}")
    insp = inspect(engine)
    indexes = insp.get_indexes(table)
    engine.dispose()
    return indexes


def _get_pk_columns(db_path: str, table: str) -> list[str]:
    """Return the primary-key column names for a table."""
    engine = create_engine(f"sqlite:///{db_path}")
    insp = inspect(engine)
    pk = insp.get_pk_constraint(table)
    engine.dispose()
    return pk["constrained_columns"]


# ---------------------------------------------------------------------------
# Fixture: isolated temporary database for each test
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_db(tmp_path):
    """Provide a path to a temporary SQLite database file."""
    return str(tmp_path / "test_migration.db")


# ---------------------------------------------------------------------------
# upgrade head
# ---------------------------------------------------------------------------


def test_upgrade_head_creates_all_18_tables(tmp_db):
    """alembic upgrade head must create all 18 application tables."""
    cfg = _make_alembic_config(tmp_db)
    command.upgrade(cfg, "head")

    tables = _get_table_names(tmp_db)
    assert tables == _EXPECTED_TABLES, (
        f"Missing: {_EXPECTED_TABLES - tables}, Extra: {tables - _EXPECTED_TABLES}"
    )


def test_upgrade_head_creates_no_extra_tables(tmp_db):
    """upgrade head must not create unexpected tables beyond the 18 defined."""
    cfg = _make_alembic_config(tmp_db)
    command.upgrade(cfg, "head")

    tables = _get_table_names(tmp_db)
    extra = tables - _EXPECTED_TABLES
    assert extra == set(), f"Unexpected tables created: {extra}"


# ---------------------------------------------------------------------------
# downgrade base
# ---------------------------------------------------------------------------


def test_downgrade_base_drops_all_tables(tmp_db):
    """alembic downgrade base must drop all 18 application tables."""
    cfg = _make_alembic_config(tmp_db)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    tables = _get_table_names(tmp_db)
    assert tables == set(), f"Tables still present after downgrade: {tables}"


def test_upgrade_after_downgrade_recreates_all_tables(tmp_db):
    """Re-running upgrade head after a downgrade must recreate all tables."""
    cfg = _make_alembic_config(tmp_db)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

    tables = _get_table_names(tmp_db)
    assert tables == _EXPECTED_TABLES


# ---------------------------------------------------------------------------
# Composite primary keys
# ---------------------------------------------------------------------------


def test_session_participants_composite_pk(tmp_db):
    """session_participants must have a composite PK of (session_id, character_id)."""
    cfg = _make_alembic_config(tmp_db)
    command.upgrade(cfg, "head")

    pk_cols = _get_pk_columns(tmp_db, "session_participants")
    assert set(pk_cols) == {"session_id", "character_id"}


def test_story_owners_composite_pk(tmp_db):
    """story_owners must have a composite PK of (story_id, owner_type, owner_id)."""
    cfg = _make_alembic_config(tmp_db)
    command.upgrade(cfg, "head")

    pk_cols = _get_pk_columns(tmp_db, "story_owners")
    assert set(pk_cols) == {"story_id", "owner_type", "owner_id"}


def test_event_targets_composite_pk(tmp_db):
    """event_targets must have a composite PK of (event_id, target_type, target_id)."""
    cfg = _make_alembic_config(tmp_db)
    command.upgrade(cfg, "head")

    pk_cols = _get_pk_columns(tmp_db, "event_targets")
    assert set(pk_cols) == {"event_id", "target_type", "target_id"}


def test_starred_objects_composite_pk(tmp_db):
    """starred_objects must have a composite PK of (user_id, object_type, object_id)."""
    cfg = _make_alembic_config(tmp_db)
    command.upgrade(cfg, "head")

    pk_cols = _get_pk_columns(tmp_db, "starred_objects")
    assert set(pk_cols) == {"user_id", "object_type", "object_id"}


# ---------------------------------------------------------------------------
# Required indexes
# ---------------------------------------------------------------------------


def test_users_login_code_index_exists(tmp_db):
    """users.login_code must have an index."""
    cfg = _make_alembic_config(tmp_db)
    command.upgrade(cfg, "head")

    indexes = _get_indexes(tmp_db, "users")
    indexed_cols = [tuple(idx["column_names"]) for idx in indexes]
    assert ("login_code",) in indexed_cols, (
        f"No index on users.login_code; found indexes: {indexed_cols}"
    )


def test_slots_owner_composite_index_exists(tmp_db):
    """slots must have a composite index on (owner_type, owner_id, slot_type)."""
    cfg = _make_alembic_config(tmp_db)
    command.upgrade(cfg, "head")

    indexes = _get_indexes(tmp_db, "slots")
    indexed_col_sets = [tuple(idx["column_names"]) for idx in indexes]
    assert ("owner_type", "owner_id", "slot_type") in indexed_col_sets, (
        f"No composite index on slots(owner_type, owner_id, slot_type); found: {indexed_col_sets}"
    )


def test_slots_target_composite_index_exists(tmp_db):
    """slots must have a composite index on (target_type, target_id)."""
    cfg = _make_alembic_config(tmp_db)
    command.upgrade(cfg, "head")

    indexes = _get_indexes(tmp_db, "slots")
    indexed_col_sets = [tuple(idx["column_names"]) for idx in indexes]
    assert ("target_type", "target_id") in indexed_col_sets, (
        f"No composite index on slots(target_type, target_id); found: {indexed_col_sets}"
    )


# ---------------------------------------------------------------------------
# Column spot-checks — key columns from the spec
# ---------------------------------------------------------------------------


def _get_column_names(db_path: str, table: str) -> set[str]:
    engine = create_engine(f"sqlite:///{db_path}")
    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns(table)}
    engine.dispose()
    return cols


def test_users_columns(tmp_db):
    """users table must have all spec-required columns."""
    cfg = _make_alembic_config(tmp_db)
    command.upgrade(cfg, "head")

    cols = _get_column_names(tmp_db, "users")
    required = {"id", "display_name", "role", "login_code", "character_id", "is_active", "created_at", "updated_at"}
    assert required.issubset(cols), f"Missing columns: {required - cols}"


def test_slots_columns(tmp_db):
    """slots table must have all spec-required columns including bond and trait mechanics."""
    cfg = _make_alembic_config(tmp_db)
    command.upgrade(cfg, "head")

    cols = _get_column_names(tmp_db, "slots")
    required = {
        "id", "slot_type", "owner_type", "owner_id", "name", "description",
        "is_active", "target_type", "target_id", "source_label", "target_label",
        "bidirectional", "template_id", "charge", "stress", "stress_degradations",
        "is_trauma", "created_at", "updated_at",
    }
    assert required.issubset(cols), f"Missing columns: {required - cols}"


def test_events_has_only_created_at_no_updated_at(tmp_db):
    """events table must have created_at but not updated_at (append-only log)."""
    cfg = _make_alembic_config(tmp_db)
    command.upgrade(cfg, "head")

    cols = _get_column_names(tmp_db, "events")
    assert "created_at" in cols
    assert "updated_at" not in cols


def test_invites_has_only_created_at_no_updated_at(tmp_db):
    """invites table must have created_at but not updated_at."""
    cfg = _make_alembic_config(tmp_db)
    command.upgrade(cfg, "head")

    cols = _get_column_names(tmp_db, "invites")
    assert "created_at" in cols
    assert "updated_at" not in cols


def test_proposals_columns(tmp_db):
    """proposals table must have all spec-required columns including rider_event_id."""
    cfg = _make_alembic_config(tmp_db)
    command.upgrade(cfg, "head")

    cols = _get_column_names(tmp_db, "proposals")
    required = {
        "id", "character_id", "action_type", "origin", "narrative", "selections",
        "calculated_effect", "status", "gm_notes", "gm_overrides", "event_id",
        "clock_id", "rider_event_id", "created_at", "updated_at",
    }
    assert required.issubset(cols), f"Missing columns: {required - cols}"


def test_events_metadata_column(tmp_db):
    """events table must have a 'metadata' column (mapped from metadata_ attribute)."""
    cfg = _make_alembic_config(tmp_db)
    command.upgrade(cfg, "head")

    cols = _get_column_names(tmp_db, "events")
    assert "metadata" in cols
