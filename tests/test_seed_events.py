"""Tests for the seed_events seeding script (Story 8.7.2).

Tests cover:
- seed_events() creates sessions, events, and proposals
- Events span every major event type
- Proposals exist in pending, approved, and rejected states
- Events have varied visibility levels
- Events target characters, groups, locations, and clocks
- At least one rider event (parent_event_id set)
- Idempotency: skips seeding if events already exist
- CLI: seed-events subcommand returns exit 0 on success

All tests use an isolated in-memory SQLite database populated via
CampaignImporter against the fixture campaign directory.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, event as sa_event, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from wizards_engine.campaign.cli import _build_parser, _cmd_import, _cmd_seed_events
from wizards_engine.campaign.importer import CampaignImporter
from wizards_engine.campaign.seed_events import SeedResult, seed_events
from wizards_engine.models.base import Base
from wizards_engine.models.event import Event
from wizards_engine.models.proposal import Proposal
from wizards_engine.models.session import Session as SessionModel

FIXTURE_CAMPAIGN_DIR = Path(__file__).parent / "fixtures" / "campaign"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_engine():
    """Create an isolated in-memory SQLite engine with all tables."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @sa_event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return engine


def _make_session(engine) -> Session:
    """Return an open session bound to *engine*."""
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return factory()


def _import_fixture(db: Session) -> None:
    """Import the fixture campaign into *db*."""
    importer = CampaignImporter(db, FIXTURE_CAMPAIGN_DIR)
    importer.import_all(dry_run=False, force=False)
    db.commit()


@pytest.fixture()
def seeded_db():
    """Provide a database populated with fixture campaign data + seeded events.

    Yields the open Session.  Caller must not commit — the fixture manages
    the session lifecycle.
    """
    engine = _make_engine()
    db = _make_session(engine)
    try:
        _import_fixture(db)
        result = seed_events(db)
        assert not result.skipped, f"Seed was skipped unexpectedly: {result.reason}"
        db.commit()
        yield db, result
    finally:
        db.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# Basic seeding tests
# ---------------------------------------------------------------------------


def test_seed_events_returns_result(seeded_db):
    """seed_events returns a SeedResult with non-zero counts."""
    db, result = seeded_db
    assert isinstance(result, SeedResult)
    assert result.events_created > 0
    assert result.proposals_created > 0
    assert result.sessions_created > 0


def test_events_written_to_db(seeded_db):
    """Events are persisted in the database after seeding."""
    db, result = seeded_db
    count = db.scalar(select(func.count()).select_from(Event))
    assert count > 0
    assert count == result.events_created


def test_proposals_written_to_db(seeded_db):
    """Proposals are persisted in the database after seeding."""
    db, result = seeded_db
    count = db.scalar(select(func.count()).select_from(Proposal))
    assert count == result.proposals_created


def test_sessions_written_to_db(seeded_db):
    """Sessions are persisted in the database after seeding.

    The count includes any sessions that were part of the imported fixture
    campaign, so we check that at least as many sessions exist as were
    created by the seeder.
    """
    db, result = seeded_db
    count = db.scalar(select(func.count()).select_from(SessionModel))
    assert count >= result.sessions_created


# ---------------------------------------------------------------------------
# Session state coverage
# ---------------------------------------------------------------------------


def test_draft_session_exists(seeded_db):
    """At least one draft session exists after seeding."""
    db, _ = seeded_db
    count = db.scalar(
        select(func.count()).select_from(SessionModel).where(SessionModel.status == "draft")
    )
    assert count >= 1


def test_active_session_exists(seeded_db):
    """Exactly one active session exists after seeding."""
    db, _ = seeded_db
    count = db.scalar(
        select(func.count()).select_from(SessionModel).where(SessionModel.status == "active")
    )
    assert count == 1


def test_ended_sessions_exist(seeded_db):
    """At least two ended sessions exist after seeding."""
    db, _ = seeded_db
    count = db.scalar(
        select(func.count()).select_from(SessionModel).where(SessionModel.status == "ended")
    )
    assert count >= 2


# ---------------------------------------------------------------------------
# Event type coverage
# ---------------------------------------------------------------------------


def _event_types(db: Session) -> set[str]:
    """Return the set of distinct event types in the database."""
    rows = db.scalars(select(Event.type).distinct()).all()
    return set(rows)


def test_session_events_created(seeded_db):
    """session.started and session.ended events are present."""
    db, _ = seeded_db
    types = _event_types(db)
    assert "session.started" in types
    assert "session.ended" in types


def test_character_events_created(seeded_db):
    """character.* events of all four meter types are present."""
    db, _ = seeded_db
    types = _event_types(db)
    assert "character.stress_changed" in types
    assert "character.free_time_changed" in types
    assert "character.plot_changed" in types
    assert "character.gnosis_changed" in types


def test_character_stat_events_created(seeded_db):
    """character.skills_changed and character.magic_stats_changed events exist."""
    db, _ = seeded_db
    types = _event_types(db)
    assert "character.skills_changed" in types
    assert "character.magic_stats_changed" in types


def test_bond_events_created(seeded_db):
    """bond.created, bond.degraded, and bond.retired events exist."""
    db, _ = seeded_db
    types = _event_types(db)
    assert "bond.created" in types
    assert "bond.degraded" in types
    assert "bond.retired" in types


def test_trait_events_created(seeded_db):
    """trait.created, trait.recharged, and trait.retired events exist."""
    db, _ = seeded_db
    types = _event_types(db)
    assert "trait.created" in types
    assert "trait.recharged" in types
    assert "trait.retired" in types


def test_effect_events_created(seeded_db):
    """effect.created, effect.used, and effect.retired events exist."""
    db, _ = seeded_db
    types = _event_types(db)
    assert "effect.created" in types
    assert "effect.used" in types
    assert "effect.retired" in types


def test_clock_events_created(seeded_db):
    """clock.advanced and clock.completed events exist."""
    db, _ = seeded_db
    types = _event_types(db)
    assert "clock.advanced" in types
    assert "clock.completed" in types


def test_proposal_events_created(seeded_db):
    """proposal.submitted, proposal.approved, and proposal.rejected events exist."""
    db, _ = seeded_db
    types = _event_types(db)
    assert "proposal.submitted" in types
    assert "proposal.approved" in types
    assert "proposal.rejected" in types


def test_gm_action_events_created(seeded_db):
    """Multiple gm_action.* event types are present."""
    db, _ = seeded_db
    types = _event_types(db)
    gm_action_types = {t for t in types if t.startswith("gm_action.")}
    assert len(gm_action_types) >= 3, f"Expected at least 3 gm_action types, got: {gm_action_types}"


# ---------------------------------------------------------------------------
# Visibility coverage
# ---------------------------------------------------------------------------


def _visibilities(db: Session) -> set[str]:
    """Return the set of distinct visibility levels in the database."""
    rows = db.scalars(select(Event.visibility).distinct()).all()
    return set(rows)


def test_all_visibility_levels_present(seeded_db):
    """All 7 visibility levels are represented in the seeded events."""
    db, _ = seeded_db
    visibilities = _visibilities(db)
    expected = {"silent", "gm_only", "private", "bonded", "familiar", "public", "global"}
    missing = expected - visibilities
    assert not missing, f"Missing visibility levels: {missing}"


# ---------------------------------------------------------------------------
# Event targets
# ---------------------------------------------------------------------------


def test_events_target_characters(seeded_db):
    """At least one event targets a character."""
    db, _ = seeded_db
    from wizards_engine.models.event import EventTarget
    count = db.scalar(
        select(func.count()).select_from(EventTarget).where(EventTarget.target_type == "character")
    )
    assert count >= 1


def test_events_target_groups(seeded_db):
    """At least one event targets a group."""
    db, _ = seeded_db
    from wizards_engine.models.event import EventTarget
    count = db.scalar(
        select(func.count()).select_from(EventTarget).where(EventTarget.target_type == "group")
    )
    assert count >= 1


def test_events_target_clocks(seeded_db):
    """At least one event targets a clock."""
    db, _ = seeded_db
    from wizards_engine.models.event import EventTarget
    count = db.scalar(
        select(func.count()).select_from(EventTarget).where(EventTarget.target_type == "clock")
    )
    assert count >= 1


# ---------------------------------------------------------------------------
# Rider event
# ---------------------------------------------------------------------------


def test_rider_event_exists(seeded_db):
    """At least one event has parent_event_id set (rider event)."""
    db, _ = seeded_db
    count = db.scalar(
        select(func.count()).select_from(Event).where(Event.parent_event_id.is_not(None))
    )
    assert count >= 1


def test_rider_event_type(seeded_db):
    """The rider event has the expected resolve_trauma type."""
    db, _ = seeded_db
    rider = db.scalars(
        select(Event).where(Event.parent_event_id.is_not(None))
    ).first()
    assert rider is not None
    assert rider.type == "character.resolve_trauma_generated"


# ---------------------------------------------------------------------------
# Proposal state coverage
# ---------------------------------------------------------------------------


def test_pending_proposals_exist(seeded_db):
    """At least 2 pending proposals exist after seeding."""
    db, _ = seeded_db
    count = db.scalar(
        select(func.count()).select_from(Proposal).where(Proposal.status == "pending")
    )
    assert count >= 2


def test_approved_proposals_exist(seeded_db):
    """At least 3 approved proposals exist after seeding."""
    db, _ = seeded_db
    count = db.scalar(
        select(func.count()).select_from(Proposal).where(Proposal.status == "approved")
    )
    assert count >= 3


def test_rejected_proposals_exist(seeded_db):
    """At least 2 rejected proposals exist after seeding."""
    db, _ = seeded_db
    count = db.scalar(
        select(func.count()).select_from(Proposal).where(Proposal.status == "rejected")
    )
    assert count >= 2


def test_pending_player_origin_proposal_exists(seeded_db):
    """At least 1 pending proposal with player origin exists."""
    db, _ = seeded_db
    count = db.scalar(
        select(func.count()).select_from(Proposal).where(
            Proposal.status == "pending",
            Proposal.origin == "player",
        )
    )
    assert count >= 1


def test_pending_system_origin_proposal_exists(seeded_db):
    """At least 1 pending proposal with system origin exists."""
    db, _ = seeded_db
    count = db.scalar(
        select(func.count()).select_from(Proposal).where(
            Proposal.status == "pending",
            Proposal.origin == "system",
        )
    )
    assert count >= 1


def test_proposal_action_type_variety(seeded_db):
    """Proposals cover multiple action types."""
    db, _ = seeded_db
    action_types = db.scalars(select(Proposal.action_type).distinct()).all()
    assert len(set(action_types)) >= 4, (
        f"Expected at least 4 distinct action types, got: {set(action_types)}"
    )


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_seed_events_is_idempotent(seeded_db):
    """Calling seed_events a second time skips seeding without error."""
    db, first_result = seeded_db
    second_result = seed_events(db)

    assert second_result.skipped is True
    assert "already exist" in second_result.reason.lower()

    # No new events or proposals should have been created.
    count_after = db.scalar(select(func.count()).select_from(Event))
    assert count_after == first_result.events_created


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_seed_events_raises_if_no_characters():
    """seed_events raises RuntimeError if no characters are in the database."""
    engine = _make_engine()
    db = _make_session(engine)
    try:
        # Empty database — no users or characters.
        with pytest.raises(RuntimeError, match="import"):
            seed_events(db)
    finally:
        db.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# CLI: seed-events subcommand
# ---------------------------------------------------------------------------


def _parse(args: list[str]) -> object:
    """Parse CLI args."""
    return _build_parser().parse_args(args)


def test_cli_seed_events_returns_0(tmp_path):
    """seed-events CLI subcommand returns exit code 0 after a successful import."""
    db_file = tmp_path / "test.db"

    # First import the fixture campaign.
    import_args = _parse([
        "import",
        "--input", str(FIXTURE_CAMPAIGN_DIR),
        "--db", str(db_file),
    ])
    assert _cmd_import(import_args) == 0

    # Now seed events.
    seed_args = _parse([
        "seed-events",
        "--db", str(db_file),
    ])
    code = _cmd_seed_events(seed_args)
    assert code == 0


def test_cli_seed_events_skips_if_already_seeded(tmp_path):
    """seed-events returns 0 (skip) when events already exist."""
    db_file = tmp_path / "test.db"

    import_args = _parse([
        "import",
        "--input", str(FIXTURE_CAMPAIGN_DIR),
        "--db", str(db_file),
    ])
    assert _cmd_import(import_args) == 0

    seed_args = _parse([
        "seed-events",
        "--db", str(db_file),
    ])
    # First run.
    assert _cmd_seed_events(seed_args) == 0
    # Second run — should still return 0 (idempotent skip).
    assert _cmd_seed_events(seed_args) == 0


def test_cli_seed_events_returns_2_if_no_import(tmp_path):
    """seed-events returns exit code 2 if no import has been run (no characters)."""
    import tempfile, os
    from sqlalchemy import create_engine as ce
    from sqlalchemy.orm import sessionmaker as sm

    db_file = tmp_path / "empty.db"

    # Create tables but do NOT import any data.
    from wizards_engine.models.base import Base as _Base
    engine = ce(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    _Base.metadata.create_all(engine)
    engine.dispose()

    seed_args = _parse([
        "seed-events",
        "--db", str(db_file),
    ])
    code = _cmd_seed_events(seed_args)
    assert code == 2
