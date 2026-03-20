"""Tests for the wizards-campaign CLI (Story 7.1.5).

Each test invokes cli.main() directly with a controlled argument list and
checks return behaviour via sys.exit (captured with pytest.raises) or via
the return value of the internal handler functions.

The tests use:
- tmp_path: an isolated temp directory for export/import output
- db fixture: an isolated in-memory SQLite database
- seed_data fixture: pre-populated entities for export tests
- FIXTURE_CAMPAIGN_DIR: the small valid YAML campaign in tests/fixtures/campaign/
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from wizards_engine.campaign.cli import (
    _build_parser,
    _cmd_export,
    _cmd_import,
    _cmd_validate,
    _make_engine,
    _open_session,
)
from wizards_engine.models.base import Base

# Path to the small fixture campaign committed to the repo.
FIXTURE_CAMPAIGN_DIR = Path(__file__).parent / "fixtures" / "campaign"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fresh_db_engine():
    """Create an isolated in-memory SQLite engine with all tables."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return engine


def _fresh_session(engine) -> Session:
    """Return an open session bound to *engine*."""
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return factory()


def _parse(args: list[str]) -> object:
    """Return a parsed Namespace for *args* using the real parser."""
    return _build_parser().parse_args(args)


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------


def test_parser_export_requires_output():
    """export without --output should exit with an argparse error (code 2)."""
    with pytest.raises(SystemExit) as exc_info:
        _build_parser().parse_args(["export"])
    assert exc_info.value.code == 2


def test_parser_import_requires_input():
    """import without --input should exit with an argparse error (code 2)."""
    with pytest.raises(SystemExit) as exc_info:
        _build_parser().parse_args(["import"])
    assert exc_info.value.code == 2


def test_parser_validate_requires_input():
    """validate without --input should exit with an argparse error (code 2)."""
    with pytest.raises(SystemExit) as exc_info:
        _build_parser().parse_args(["validate"])
    assert exc_info.value.code == 2


def test_parser_export_sets_output_path(tmp_path):
    """export --output sets args.output as a Path."""
    args = _parse(["export", "--output", str(tmp_path)])
    assert args.output == tmp_path
    assert args.db is None


def test_parser_import_sets_flags(tmp_path):
    """import --dry-run --force sets the correct boolean flags."""
    args = _parse(["import", "--input", str(tmp_path), "--dry-run", "--force"])
    assert args.input == tmp_path
    assert args.dry_run is True
    assert args.force is True


def test_parser_import_defaults(tmp_path):
    """import without flags defaults dry_run=False, force=False."""
    args = _parse(["import", "--input", str(tmp_path)])
    assert args.dry_run is False
    assert args.force is False


def test_parser_db_override(tmp_path):
    """--db flag overrides the database path on export."""
    db_file = tmp_path / "custom.db"
    args = _parse(["export", "--output", str(tmp_path), "--db", str(db_file)])
    assert args.db == db_file


def test_parser_no_subcommand_exits():
    """Running with no sub-command should exit (argparse required=True)."""
    with pytest.raises(SystemExit) as exc_info:
        _build_parser().parse_args([])
    assert exc_info.value.code != 0


# ---------------------------------------------------------------------------
# validate command
# ---------------------------------------------------------------------------


def test_validate_returns_0_for_valid_campaign():
    """validate returns 0 for the committed fixture campaign."""
    args = _parse(["validate", "--input", str(FIXTURE_CAMPAIGN_DIR)])
    code = _cmd_validate(args)
    assert code == 0


def test_validate_returns_1_for_invalid_campaign(tmp_path):
    """validate returns 1 when the campaign has schema errors."""
    # Write a trait-template with a missing required 'type' field.
    bad_dir = tmp_path / "bad"
    (bad_dir / "meta.yaml").parent.mkdir(parents=True, exist_ok=True)
    (bad_dir / "meta.yaml").write_text(
        "engine_version: '0.1.0'\ncampaign_name: Bad\nformat_version: 1\n"
    )
    (bad_dir / "trait-templates").mkdir()
    (bad_dir / "trait-templates" / "broken.yaml").write_text(
        "name: Broken\ndescription: Missing type field.\n"
    )
    args = _parse(["validate", "--input", str(bad_dir)])
    code = _cmd_validate(args)
    assert code == 1


def test_validate_returns_2_for_missing_directory(tmp_path):
    """validate returns 2 when the input directory does not exist."""
    nonexistent = tmp_path / "does-not-exist"
    args = _parse(["validate", "--input", str(nonexistent)])
    code = _cmd_validate(args)
    assert code == 2


# ---------------------------------------------------------------------------
# import command
# ---------------------------------------------------------------------------


def test_import_returns_0_for_valid_campaign(tmp_path):
    """import returns 0 and commits data for the fixture campaign."""
    db_file = tmp_path / "test.db"
    args = _parse([
        "import",
        "--input", str(FIXTURE_CAMPAIGN_DIR),
        "--db", str(db_file),
    ])
    code = _cmd_import(args)
    assert code == 0
    # DB file should now exist.
    assert db_file.exists()


def test_import_dry_run_returns_0_and_writes_nothing(tmp_path):
    """import --dry-run returns 0 but does not commit data."""
    from sqlalchemy import select
    from wizards_engine.models.character import Character

    db_file = tmp_path / "dry.db"
    args = _parse([
        "import",
        "--input", str(FIXTURE_CAMPAIGN_DIR),
        "--db", str(db_file),
        "--dry-run",
    ])
    code = _cmd_import(args)
    assert code == 0

    # The DB file is created (tables exist) but should have no characters.
    engine = _make_engine(db_file)
    with Session(engine) as session:
        chars = session.execute(select(Character)).scalars().all()
    assert chars == []


def test_import_returns_2_for_missing_directory(tmp_path):
    """import returns 2 when the input directory does not exist."""
    args = _parse([
        "import",
        "--input", str(tmp_path / "missing"),
        "--db", str(tmp_path / "test.db"),
    ])
    code = _cmd_import(args)
    assert code == 2


def test_import_returns_1_for_invalid_campaign(tmp_path):
    """import returns 1 when the campaign fails validation."""
    bad_dir = tmp_path / "bad"
    (bad_dir / "meta.yaml").parent.mkdir(parents=True, exist_ok=True)
    (bad_dir / "meta.yaml").write_text(
        "engine_version: '0.1.0'\ncampaign_name: Bad\nformat_version: 1\n"
    )
    (bad_dir / "trait-templates").mkdir()
    # A trait template with an invalid type field.
    (bad_dir / "trait-templates" / "broken.yaml").write_text(
        "name: Broken\ntype: invalid\ndescription: Bad type.\n"
    )
    db_file = tmp_path / "test.db"
    args = _parse([
        "import",
        "--input", str(bad_dir),
        "--db", str(db_file),
    ])
    code = _cmd_import(args)
    assert code == 1


# ---------------------------------------------------------------------------
# export command
# ---------------------------------------------------------------------------


def test_export_returns_0_with_seed_data(db, seed_data, tmp_path):
    """export returns 0 and writes YAML files for the seeded database."""
    # Wire up a real file-backed engine sharing the seed data.
    # We must save the seed data to a temp file-backed DB because
    # CampaignExporter needs a real session, not the in-memory one
    # (which cannot be opened by path).  Instead, we test _cmd_export
    # indirectly by calling _cmd_export with a --db pointing to a temp DB
    # that we populate via a fresh import from the fixture campaign.
    db_file = tmp_path / "source.db"
    import_dir = FIXTURE_CAMPAIGN_DIR
    import_args = _parse([
        "import",
        "--input", str(import_dir),
        "--db", str(db_file),
    ])
    assert _cmd_import(import_args) == 0

    output_dir = tmp_path / "exported"
    export_args = _parse([
        "export",
        "--output", str(output_dir),
        "--db", str(db_file),
    ])
    code = _cmd_export(export_args)
    assert code == 0
    assert (output_dir / "meta.yaml").exists()


def test_export_returns_2_for_runtime_error(tmp_path):
    """export returns 2 when the database cannot be opened."""
    # Point to a non-existent directory path to trigger a SQLite error
    # when attempting to create tables.
    bad_db_path = tmp_path / "nonexistent_dir" / "db.sqlite"
    args = _parse([
        "export",
        "--output", str(tmp_path / "out"),
        "--db", str(bad_db_path),
    ])
    code = _cmd_export(args)
    assert code == 2
