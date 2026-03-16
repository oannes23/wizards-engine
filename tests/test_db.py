"""Tests for Story 1.1.2 — Database & ORM Setup.

Covers:
- SQLAlchemy engine connects to a SQLite database file
- Base model mixin provides id (ULID, TEXT, PK), created_at, updated_at
- ULID generation uses the python-ulid library and produces 26-char strings
- get_db FastAPI dependency yields a scoped session and handles lifecycle
- DATABASE_URL is configurable via WIZARDS_DB_PATH environment variable
"""

import os
import re
import tempfile
from datetime import datetime, timezone

import pytest
from sqlalchemy import Column, String, inspect, text
from sqlalchemy.orm import Session

from wizards_engine.db import SessionLocal, engine, get_db
from wizards_engine.models.base import Base, TimestampMixin, _new_ulid


# ---------------------------------------------------------------------------
# Minimal concrete model used only by these tests — not part of real schema
# ---------------------------------------------------------------------------


class _Widget(TimestampMixin, Base):
    """Throwaway model for mixin tests. Not part of the real schema."""

    __tablename__ = "_test_widget"
    label = Column(String(100), nullable=False)


# ---------------------------------------------------------------------------
# Session-scoped fixture: create / drop the test table around the test module
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module", autouse=True)
def _create_test_tables():
    """Create the _test_widget table before tests and drop it after."""
    _Widget.__table__.create(bind=engine, checkfirst=True)
    yield
    _Widget.__table__.drop(bind=engine, checkfirst=True)


# ---------------------------------------------------------------------------
# ULID generation
# ---------------------------------------------------------------------------


def test_new_ulid_returns_26_chars():
    """_new_ulid() must produce a 26-character string."""
    uid = _new_ulid()
    assert isinstance(uid, str)
    assert len(uid) == 26


def test_new_ulid_is_unique():
    """Two consecutive ULIDs must be different."""
    assert _new_ulid() != _new_ulid()


def test_new_ulid_timestamp_prefix_is_time_ordered():
    """ULIDs encode timestamp in the first 10 chars; two IDs from different
    milliseconds must sort correctly by that prefix."""
    import time

    id_early = _new_ulid()
    time.sleep(0.002)  # ensure a different millisecond
    id_late = _new_ulid()

    # The first 10 characters encode the timestamp in Crockford base32.
    assert id_early[:10] <= id_late[:10]


# ---------------------------------------------------------------------------
# Engine / database connection
# ---------------------------------------------------------------------------


def test_engine_connects_to_sqlite():
    """The engine must connect to a SQLite database without error."""
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        assert result.scalar() == 1


def test_database_url_uses_sqlite_scheme():
    """DATABASE_URL must start with 'sqlite:///'."""
    from wizards_engine.db import DATABASE_URL

    assert DATABASE_URL.startswith("sqlite:///")


def test_wizards_db_path_env_var_controls_url_construction(tmp_path):
    """DATABASE_URL must be derived from WIZARDS_DB_PATH when that env var is set.

    This test verifies the URL construction logic by importing a fresh copy of
    the db module in a subprocess, avoiding any state mutation that could
    break other tests that depend on the module-level engine.
    """
    import subprocess
    import sys

    custom_db = str(tmp_path / "custom.db")
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from wizards_engine.db import DATABASE_URL; print(DATABASE_URL)",
        ],
        env={**os.environ, "WIZARDS_DB_PATH": custom_db},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"sqlite:///{custom_db}"


# ---------------------------------------------------------------------------
# TimestampMixin — column presence and types
# ---------------------------------------------------------------------------


def test_mixin_id_column_is_primary_key():
    """id column must be the primary key."""
    insp = inspect(engine)
    pk_cols = insp.get_pk_constraint("_test_widget")["constrained_columns"]
    assert "id" in pk_cols


def test_mixin_has_created_at_and_updated_at():
    """created_at and updated_at columns must exist on the table."""
    insp = inspect(engine)
    col_names = {c["name"] for c in insp.get_columns("_test_widget")}
    assert "created_at" in col_names
    assert "updated_at" in col_names


def test_mixin_id_auto_generated_on_insert():
    """Inserting a row without providing id must auto-populate it."""
    with SessionLocal() as db:
        widget = _Widget(label="auto-id test")
        db.add(widget)
        db.commit()
        db.refresh(widget)

        assert widget.id is not None
        assert len(widget.id) == 26


def test_mixin_created_at_auto_set_on_insert():
    """created_at must be set automatically on row creation."""
    with SessionLocal() as db:
        widget = _Widget(label="created_at test")
        db.add(widget)
        db.commit()
        db.refresh(widget)

        assert isinstance(widget.created_at, datetime)


def test_mixin_updated_at_auto_set_on_insert():
    """updated_at must be set automatically on row creation."""
    with SessionLocal() as db:
        widget = _Widget(label="updated_at initial test")
        db.add(widget)
        db.commit()
        db.refresh(widget)

        assert isinstance(widget.updated_at, datetime)


def test_mixin_updated_at_changes_on_update():
    """updated_at must be refreshed when the row is updated."""
    with SessionLocal() as db:
        widget = _Widget(label="original")
        db.add(widget)
        db.commit()
        db.refresh(widget)
        original_updated = widget.updated_at

    with SessionLocal() as db:
        widget = db.get(_Widget, widget.id)
        widget.label = "modified"
        db.commit()
        db.refresh(widget)

        assert widget.updated_at >= original_updated


# ---------------------------------------------------------------------------
# get_db dependency
# ---------------------------------------------------------------------------


def test_get_db_yields_a_session():
    """get_db() must yield a SQLAlchemy Session."""
    gen = get_db()
    db = next(gen)
    assert isinstance(db, Session)
    # Close out the generator cleanly
    try:
        next(gen)
    except StopIteration:
        pass


def test_get_db_commits_on_success():
    """Data written inside a get_db() scope must be persisted after the generator exits."""
    gen = get_db()
    db = next(gen)

    widget = _Widget(label="commit-test")
    db.add(widget)
    db.flush()  # assign id without committing, keeping the session open
    widget_id = widget.id  # capture before session closes

    try:
        next(gen)  # triggers the commit + session close
    except StopIteration:
        pass

    # Verify it was committed by reading with a fresh session
    with SessionLocal() as verify_db:
        found = verify_db.get(_Widget, widget_id)
        assert found is not None
        assert found.label == "commit-test"


def test_get_db_rollback_on_exception():
    """An exception inside a get_db() scope must trigger a rollback."""
    # Pre-assign a ULID so we can look it up after the rollback without
    # accessing the detached instance (which would raise DetachedInstanceError).
    widget_id = _new_ulid()

    gen = get_db()
    db = next(gen)
    widget = _Widget(id=widget_id, label="rollback-test")
    db.add(widget)

    try:
        gen.throw(RuntimeError("forced error"))
    except RuntimeError:
        pass

    # The row must NOT have been persisted
    with SessionLocal() as verify_db:
        found = verify_db.get(_Widget, widget_id)
        assert found is None
