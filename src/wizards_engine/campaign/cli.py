"""Command-line interface for campaign import/export.

Provides three sub-commands:

``export``
    Dump the entire database to a YAML directory tree.

``import``
    Populate the database from a YAML directory.

``validate``
    Run two-pass validation against a YAML directory without touching the DB.

Exit codes
----------
0
    Success.
1
    Validation failure (schema or reference errors in the campaign YAML).
2
    Runtime error (database error, I/O error, unexpected exception).

Usage examples::

    uv run wizards-campaign export --output ./campaign-data/
    uv run wizards-campaign import --input ./campaign-data/ --dry-run
    uv run wizards-campaign import --input ./campaign-data/ --force
    uv run wizards-campaign validate --input ./campaign-data/

Database path
-------------
The ``--db`` flag overrides the SQLite file path for ``export`` and ``import``
commands.  When omitted the path is read from the ``WIZARDS_DB_PATH``
environment variable, falling back to ``wizards_engine.db`` in the current
working directory.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from wizards_engine.campaign.exporter import CampaignExporter, ExportResult
from wizards_engine.campaign.importer import CampaignImporter, ImportResult
from wizards_engine.campaign.validators import ValidationFinding, validate_campaign
from wizards_engine.models.base import Base

_DEFAULT_DB_PATH = "wizards_engine.db"


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def _make_engine(db_path: Path | None):
    """Create a SQLAlchemy engine pointing to *db_path*.

    If *db_path* is ``None``, the path is read from ``WIZARDS_DB_PATH``
    environment variable, defaulting to ``wizards_engine.db`` in the current
    working directory.

    Parameters
    ----------
    db_path:
        Override path for the SQLite database file, or ``None`` to use the
        environment variable / default.

    Returns
    -------
    sqlalchemy.engine.Engine
        A configured synchronous SQLite engine.
    """
    if db_path is None:
        path_str = os.environ.get("WIZARDS_DB_PATH", _DEFAULT_DB_PATH)
    else:
        path_str = str(db_path)

    url = f"sqlite:///{path_str}"
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False},
        echo=False,
    )

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_conn, connection_record):  # noqa: ANN001
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.close()

    return engine


def _open_session(db_path: Path | None, create_tables: bool = False) -> Session:
    """Open a SQLAlchemy session for the given *db_path*.

    Parameters
    ----------
    db_path:
        Path override for the SQLite file, or ``None`` for env/default.
    create_tables:
        If ``True``, run ``Base.metadata.create_all`` before returning the
        session.  Used by ``import`` so it can populate a brand-new database
        file.

    Returns
    -------
    sqlalchemy.orm.Session
        An open session.  The caller is responsible for closing it.
    """
    engine = _make_engine(db_path)
    if create_tables:
        Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return SessionLocal()


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _print_export_summary(result: ExportResult) -> None:
    """Print a human-readable export summary to stdout.

    Parameters
    ----------
    result:
        The :class:`ExportResult` returned by :class:`CampaignExporter`.
    """
    print("Export complete.")
    print(f"  Trait templates : {result.trait_templates}")
    print(f"  Locations       : {result.locations}")
    print(f"  Characters (PC) : {result.characters_pc}")
    print(f"  Characters (NPC): {result.characters_npc}")
    print(f"  Groups          : {result.groups}")
    print(f"  Clocks          : {result.clocks}")
    print(f"  Users           : {result.users}")
    print(f"  Sessions        : {result.sessions}")
    print(f"  Stories         : {result.stories}")


def _print_import_summary(result: ImportResult) -> None:
    """Print a human-readable import summary to stdout.

    Parameters
    ----------
    result:
        The :class:`ImportResult` returned by :class:`CampaignImporter`.
    """
    label = "Dry-run complete (no data written)." if result.dry_run else "Import complete."
    print(label)
    print(f"  Trait templates     : {result.trait_templates}")
    print(f"  Locations           : {result.locations}")
    print(f"  Characters          : {result.characters}")
    print(f"  Groups              : {result.groups}")
    print(f"  Slots               : {result.slots}")
    print(f"  Magic effects       : {result.magic_effects}")
    print(f"  Clocks              : {result.clocks}")
    print(f"  Users               : {result.users}")
    print(f"  Sessions            : {result.sessions}")
    print(f"  Session participants: {result.session_participants}")
    print(f"  Stories             : {result.stories}")
    print(f"  Story owners        : {result.story_owners}")
    print(f"  Story entries       : {result.story_entries}")
    if result.warnings:
        print(f"\nWarnings ({len(result.warnings)}):")
        for w in result.warnings:
            print(f"  [warn] {w}")


def _print_validation_errors(errors: list[ValidationFinding]) -> None:
    """Print structured validation errors to stderr.

    Each error is printed on its own line in the format::

        <file_path>:<field>: <error_message>

    Parameters
    ----------
    errors:
        List of :class:`ValidationFinding` instances from
        :func:`validate_campaign`.
    """
    print(f"Validation failed with {len(errors)} error(s):", file=sys.stderr)
    for err in errors:
        field_part = f":{err.field}" if err.field else ""
        print(f"  {err.file_path}{field_part}: {err.error_message}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Sub-command handlers
# ---------------------------------------------------------------------------


def _cmd_export(args: argparse.Namespace) -> int:
    """Handle the ``export`` sub-command.

    Connects to the database, runs the exporter, writes YAML files to the
    output directory, and prints a summary.

    Parameters
    ----------
    args:
        Parsed command-line arguments (``args.output``, ``args.db``).

    Returns
    -------
    int
        Exit code: 0 on success, 2 on runtime error.
    """
    output_dir: Path = args.output
    db_path: Path | None = args.db

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        db = _open_session(db_path, create_tables=False)
        try:
            exporter = CampaignExporter(db, output_dir)
            result = exporter.export_all()
        finally:
            db.close()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    _print_export_summary(result)
    return 0


def _cmd_import(args: argparse.Namespace) -> int:
    """Handle the ``import`` sub-command.

    Validates the input directory, then imports all entities into the database
    (or reports what would be created if ``--dry-run`` is set).

    Parameters
    ----------
    args:
        Parsed command-line arguments (``args.input``, ``args.dry_run``,
        ``args.force``, ``args.db``).

    Returns
    -------
    int
        Exit code: 0 on success, 1 on validation failure, 2 on runtime error.
    """
    input_dir: Path = args.input
    dry_run: bool = args.dry_run
    force: bool = args.force
    db_path: Path | None = args.db

    if not input_dir.is_dir():
        print(f"Error: input directory does not exist: {input_dir}", file=sys.stderr)
        return 2

    try:
        db = _open_session(db_path, create_tables=True)
        try:
            importer = CampaignImporter(db, input_dir)
            result = importer.import_all(dry_run=dry_run, force=force)
        finally:
            db.close()
    except ValueError as exc:
        # Validation errors from the importer are reported as ValueError.
        # Extract structured errors by re-running validate_campaign for display.
        from wizards_engine.campaign.validators import validate_campaign as _validate

        errors = _validate(input_dir)
        if errors:
            _print_validation_errors(errors)
        else:
            # Fallback: not schema/ref errors (e.g. non-empty DB)
            print(f"Error: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    _print_import_summary(result)
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    """Handle the ``validate`` sub-command.

    Runs two-pass validation against the input directory without touching
    the database.

    Parameters
    ----------
    args:
        Parsed command-line arguments (``args.input``).

    Returns
    -------
    int
        Exit code: 0 on success, 1 on validation failure, 2 on runtime error.
    """
    input_dir: Path = args.input

    if not input_dir.is_dir():
        print(f"Error: input directory does not exist: {input_dir}", file=sys.stderr)
        return 2

    try:
        errors = validate_campaign(input_dir)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    if errors:
        _print_validation_errors(errors)
        return 1

    print("Campaign is valid. No errors found.")
    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    """Build and return the top-level argument parser.

    Returns
    -------
    argparse.ArgumentParser
        The fully configured parser with all three sub-commands.
    """
    parser = argparse.ArgumentParser(
        prog="wizards-campaign",
        description="Wizards Engine campaign data tool — export, import, and validate YAML.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- export ---
    export_parser = subparsers.add_parser(
        "export",
        help="Export the database to a YAML directory.",
    )
    export_parser.add_argument(
        "--output",
        "-o",
        type=Path,
        required=True,
        metavar="DIR",
        help="Output directory for the exported YAML files.",
    )
    export_parser.add_argument(
        "--db",
        type=Path,
        default=None,
        metavar="FILE",
        help="SQLite database file path (overrides WIZARDS_DB_PATH env var).",
    )

    # --- import ---
    import_parser = subparsers.add_parser(
        "import",
        help="Import a YAML directory into the database.",
    )
    import_parser.add_argument(
        "--input",
        "-i",
        type=Path,
        required=True,
        metavar="DIR",
        help="Input directory containing the campaign YAML files.",
    )
    import_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Validate and count entities without writing to the database.",
    )
    import_parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Allow importing into a non-empty database.",
    )
    import_parser.add_argument(
        "--db",
        type=Path,
        default=None,
        metavar="FILE",
        help="SQLite database file path (overrides WIZARDS_DB_PATH env var).",
    )

    # --- validate ---
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate a campaign YAML directory (no database required).",
    )
    validate_parser.add_argument(
        "--input",
        "-i",
        type=Path,
        required=True,
        metavar="DIR",
        help="Input directory containing the campaign YAML files.",
    )

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    """Parse arguments and dispatch to the appropriate sub-command handler.

    This function is the ``[project.scripts]`` entry point.  It calls
    ``sys.exit`` with the return code from the sub-command handler.

    Parameters
    ----------
    argv:
        Argument list to parse.  Defaults to ``sys.argv[1:]`` when ``None``.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    dispatch = {
        "export": _cmd_export,
        "import": _cmd_import,
        "validate": _cmd_validate,
    }

    handler = dispatch[args.command]
    exit_code = handler(args)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
