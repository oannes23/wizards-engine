"""Round-trip tests for Campaign Import/Export (Story 7.1.5).

Tests the full cycle:
  seed DB → CampaignExporter → YAML files → CampaignImporter → fresh DB

Verifies that:
- Entity counts match between export and re-import
- Location hierarchy (parent_id) is preserved
- Slot assignments (owner_type, owner_id) are correct
- Mechanical values (stress, skills, magic_stats, bond charges) are preserved
- Cross-references (bond targets, user→character links, etc.) are intact

All tests use the ``db`` and ``seed_data`` fixtures from conftest.py for the
source database, and spin up a fresh in-memory SQLite engine as the import
target.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from wizards_engine.campaign.exporter import CampaignExporter, ExportResult
from wizards_engine.campaign.importer import CampaignImporter, ImportResult
from wizards_engine.campaign.validators import validate_campaign
from wizards_engine.models.base import Base
from wizards_engine.models.character import Character
from wizards_engine.models.clock import Clock
from wizards_engine.models.group import Group
from wizards_engine.models.location import Location
from wizards_engine.models.magic_effect import MagicEffect
from wizards_engine.models.session import Session as GameSession
from wizards_engine.models.session import SessionParticipant
from wizards_engine.models.slot import Slot, TraitTemplate
from wizards_engine.models.story import Story, StoryEntry, StoryOwner
from wizards_engine.models.user import User

# Path to the committed fixture campaign.
FIXTURE_CAMPAIGN_DIR = Path(__file__).parent / "fixtures" / "campaign"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fresh_engine():
    """Create an isolated in-memory SQLite engine with all tables created."""
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


def _make_session(engine) -> Session:
    """Return a new open Session bound to *engine*."""
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return factory()


def _count(session: Session, model) -> int:
    """Return the row count for *model* in *session*."""
    return session.execute(select(func.count()).select_from(model)).scalar_one()


def _do_export(source_db: Session, export_dir: Path) -> ExportResult:
    """Export *source_db* to *export_dir* and return the ExportResult."""
    exporter = CampaignExporter(source_db, export_dir)
    return exporter.export_all()


def _do_import(target_db: Session, import_dir: Path, force: bool = False) -> ImportResult:
    """Import *import_dir* into *target_db* and return the ImportResult."""
    importer = CampaignImporter(target_db, import_dir)
    return importer.import_all(force=force)


# ---------------------------------------------------------------------------
# Fixture campaign round-trip (no seed data needed)
# ---------------------------------------------------------------------------


def test_fixture_campaign_validates(tmp_path):
    """The committed fixture campaign passes two-pass validation."""
    errors = validate_campaign(FIXTURE_CAMPAIGN_DIR)
    assert errors == [], [
        f"{e.file_path}:{e.field}: {e.error_message}" for e in errors
    ]


def test_fixture_campaign_imports_cleanly(tmp_path):
    """The fixture campaign imports into a fresh DB without errors."""
    engine = _make_fresh_engine()
    session = _make_session(engine)
    try:
        result = _do_import(session, FIXTURE_CAMPAIGN_DIR)
        assert result.characters > 0
        assert result.users > 0
        assert result.locations > 0
    finally:
        session.close()
        engine.dispose()


def test_fixture_campaign_export_then_reimport(tmp_path):
    """Import fixture → export → re-import: counts match."""
    # Step 1: import fixture into DB A
    engine_a = _make_fresh_engine()
    session_a = _make_session(engine_a)
    try:
        result_a = _do_import(session_a, FIXTURE_CAMPAIGN_DIR)
    finally:
        session_a.close()

    # Step 2: export DB A to YAML
    export_dir = tmp_path / "exported"
    session_a2 = _make_session(engine_a)
    try:
        export_result = _do_export(session_a2, export_dir)
    finally:
        session_a2.close()
        engine_a.dispose()

    # Step 3: validate the export
    errors = validate_campaign(export_dir)
    assert errors == [], [
        f"{e.file_path}:{e.field}: {e.error_message}" for e in errors
    ]

    # Step 4: import into fresh DB B
    engine_b = _make_fresh_engine()
    session_b = _make_session(engine_b)
    try:
        result_b = _do_import(session_b, export_dir)
        # Entity counts must match
        assert _count(session_b, Character) == result_a.characters
        assert _count(session_b, Location) == result_a.locations
        assert _count(session_b, Group) == result_a.groups
        assert _count(session_b, User) == result_a.users
        assert _count(session_b, Clock) == result_a.clocks
        assert _count(session_b, Slot) == result_a.slots
    finally:
        session_b.close()
        engine_b.dispose()


# ---------------------------------------------------------------------------
# Seed-data round-trip tests
# ---------------------------------------------------------------------------


def test_roundtrip_entity_counts(db, seed_data, tmp_path):
    """Export seed DB and re-import into a fresh DB; entity counts match.

    The seed_data fixture provides: 5 characters, 1 group, 2 locations,
    4 users, 4 slots (bonds).  No sessions, clocks, or stories — but the
    exporter should handle empty entity types gracefully.
    """
    # Count source
    source_chars = _count(db, Character)
    source_locs = _count(db, Location)
    source_groups = _count(db, Group)
    source_users = _count(db, User)
    source_slots = _count(db, Slot)

    # Export
    export_dir = tmp_path / "exported"
    export_result = _do_export(db, export_dir)

    # Validate exported YAML
    errors = validate_campaign(export_dir)
    assert errors == [], [
        f"{e.file_path}:{e.field}: {e.error_message}" for e in errors
    ]

    # Import into fresh DB
    fresh_engine = _make_fresh_engine()
    fresh_session = _make_session(fresh_engine)
    try:
        import_result = _do_import(fresh_session, export_dir)

        assert _count(fresh_session, Character) == source_chars
        assert _count(fresh_session, Location) == source_locs
        assert _count(fresh_session, Group) == source_groups
        assert _count(fresh_session, User) == source_users
        assert _count(fresh_session, Slot) == source_slots
    finally:
        fresh_session.close()
        fresh_engine.dispose()


def test_roundtrip_location_hierarchy(db, seed_data, tmp_path):
    """Location parent-child hierarchy is preserved through export/import."""
    # The seed_data has region (parent) and district (child of region).
    region = seed_data["region"]
    district = seed_data["district"]

    export_dir = tmp_path / "exported"
    _do_export(db, export_dir)

    fresh_engine = _make_fresh_engine()
    fresh_session = _make_session(fresh_engine)
    try:
        _do_import(fresh_session, export_dir)

        locs = fresh_session.execute(select(Location)).scalars().all()
        by_name = {loc.name: loc for loc in locs}

        # Both locations must exist in the re-imported DB.
        assert region.name in by_name
        assert district.name in by_name

        imported_district = by_name[district.name]
        imported_region = by_name[region.name]

        # The district's parent_id must point to the re-imported region.
        assert imported_district.parent_id == imported_region.id
    finally:
        fresh_session.close()
        fresh_engine.dispose()


def test_roundtrip_slot_assignments(db, seed_data, tmp_path):
    """Bond slots are re-created with correct owner and target linkage."""
    pc1 = seed_data["pc1"]
    pc1_bond = seed_data["pc1_bond"]

    export_dir = tmp_path / "exported"
    _do_export(db, export_dir)

    fresh_engine = _make_fresh_engine()
    fresh_session = _make_session(fresh_engine)
    try:
        _do_import(fresh_session, export_dir)

        # Find the re-imported bond by name.
        bonds = fresh_session.execute(
            select(Slot).where(Slot.name == pc1_bond.name)
        ).scalars().all()
        assert len(bonds) == 1
        bond = bonds[0]

        # Verify owner is a character with the same name as pc1.
        assert bond.owner_type == "character"
        owner = fresh_session.get(Character, bond.owner_id)
        assert owner is not None
        assert owner.name == pc1.name

        # Verify target is a group with the same name as the seed group.
        group = seed_data["group"]
        assert bond.target_type == "group"
        target = fresh_session.get(Group, bond.target_id)
        assert target is not None
        assert target.name == group.name
    finally:
        fresh_session.close()
        fresh_engine.dispose()


def test_roundtrip_mechanical_values(db, seed_data, tmp_path):
    """PC character mechanical values (skills, magic_stats) survive the cycle."""
    pc1 = seed_data["pc1"]

    export_dir = tmp_path / "exported"
    _do_export(db, export_dir)

    fresh_engine = _make_fresh_engine()
    fresh_session = _make_session(fresh_engine)
    try:
        _do_import(fresh_session, export_dir)

        imported = fresh_session.execute(
            select(Character).where(Character.name == pc1.name)
        ).scalar_one()

        assert imported.detail_level == "full"
        assert imported.stress == pc1.stress
        assert imported.free_time == pc1.free_time
        assert imported.plot == pc1.plot
        assert imported.gnosis == pc1.gnosis
        # Skills dict must match.
        assert imported.skills == pc1.skills
        # Magic stats structure must match.
        for discipline in ("being", "wyrding", "summoning", "enchanting", "dreaming"):
            assert imported.magic_stats[discipline]["level"] == pc1.magic_stats[discipline]["level"]
            assert imported.magic_stats[discipline]["xp"] == pc1.magic_stats[discipline]["xp"]
    finally:
        fresh_session.close()
        fresh_engine.dispose()


def test_roundtrip_bond_charges(db, seed_data, tmp_path):
    """Bond mechanical values (charges, degradations, is_trauma) are preserved."""
    pc1_bond = seed_data["pc1_bond"]

    export_dir = tmp_path / "exported"
    _do_export(db, export_dir)

    fresh_engine = _make_fresh_engine()
    fresh_session = _make_session(fresh_engine)
    try:
        _do_import(fresh_session, export_dir)

        bond = fresh_session.execute(
            select(Slot).where(Slot.name == pc1_bond.name)
        ).scalar_one()

        assert bond.charges == pc1_bond.charges
        assert bond.degradations == pc1_bond.degradations
        assert bond.is_trauma == pc1_bond.is_trauma
    finally:
        fresh_session.close()
        fresh_engine.dispose()


def test_roundtrip_user_character_link(db, seed_data, tmp_path):
    """User→character foreign key links are preserved through export/import."""
    player1 = seed_data["player1"]
    pc1 = seed_data["pc1"]

    export_dir = tmp_path / "exported"
    _do_export(db, export_dir)

    fresh_engine = _make_fresh_engine()
    fresh_session = _make_session(fresh_engine)
    try:
        _do_import(fresh_session, export_dir)

        # Find the re-imported user with the same display_name.
        imported_user = fresh_session.execute(
            select(User).where(User.display_name == player1.display_name)
        ).scalar_one()

        assert imported_user.character_id is not None
        linked_char = fresh_session.get(Character, imported_user.character_id)
        assert linked_char is not None
        assert linked_char.name == pc1.name
    finally:
        fresh_session.close()
        fresh_engine.dispose()


def test_roundtrip_exported_yaml_validates(db, seed_data, tmp_path):
    """The exported YAML passes validate_campaign with zero errors."""
    export_dir = tmp_path / "exported"
    _do_export(db, export_dir)

    errors = validate_campaign(export_dir)
    assert errors == [], [
        f"{e.file_path}:{e.field}: {e.error_message}" for e in errors
    ]


def test_roundtrip_slot_type_and_bidirectional(db, seed_data, tmp_path):
    """slot_type discriminator and bidirectional flag are preserved for all bond types.

    The seed data provides:
      - pc1_bond: slot_type=pc_bond, bidirectional=True
      - npc1_bond: slot_type=npc_bond, bidirectional=False (target: location)
    """
    pc1_bond = seed_data["pc1_bond"]
    npc1_bond = seed_data["npc1_bond"]

    export_dir = tmp_path / "exported"
    _do_export(db, export_dir)

    fresh_engine = _make_fresh_engine()
    fresh_session = _make_session(fresh_engine)
    try:
        _do_import(fresh_session, export_dir)

        imported_pc_bond = fresh_session.execute(
            select(Slot).where(Slot.name == pc1_bond.name)
        ).scalar_one()
        assert imported_pc_bond.slot_type == "pc_bond"
        assert imported_pc_bond.bidirectional is True

        imported_npc_bond = fresh_session.execute(
            select(Slot).where(Slot.name == npc1_bond.name)
        ).scalar_one()
        assert imported_npc_bond.slot_type == "npc_bond"
        assert imported_npc_bond.bidirectional is False
    finally:
        fresh_session.close()
        fresh_engine.dispose()


def test_roundtrip_npc_bond_location_target(db, seed_data, tmp_path):
    """NPC bond with target_type=location cross-reference is preserved."""
    npc1 = seed_data["npc1"]
    npc1_bond = seed_data["npc1_bond"]
    region = seed_data["region"]

    export_dir = tmp_path / "exported"
    _do_export(db, export_dir)

    fresh_engine = _make_fresh_engine()
    fresh_session = _make_session(fresh_engine)
    try:
        _do_import(fresh_session, export_dir)

        bond = fresh_session.execute(
            select(Slot).where(Slot.name == npc1_bond.name)
        ).scalar_one()

        assert bond.target_type == "location"
        target = fresh_session.get(Location, bond.target_id)
        assert target is not None
        assert target.name == region.name

        owner = fresh_session.get(Character, bond.owner_id)
        assert owner is not None
        assert owner.name == npc1.name
    finally:
        fresh_session.close()
        fresh_engine.dispose()


def test_roundtrip_user_without_character_link(db, seed_data, tmp_path):
    """A user with no character link (e.g. the GM) keeps character_id=None after round-trip."""
    gm = seed_data["gm"]
    assert gm.character_id is None, "precondition: gm has no character link"

    export_dir = tmp_path / "exported"
    _do_export(db, export_dir)

    fresh_engine = _make_fresh_engine()
    fresh_session = _make_session(fresh_engine)
    try:
        _do_import(fresh_session, export_dir)

        imported_gm = fresh_session.execute(
            select(User).where(User.display_name == gm.display_name)
        ).scalar_one()
        assert imported_gm.character_id is None
        assert imported_gm.role == "gm"
    finally:
        fresh_session.close()
        fresh_engine.dispose()


def test_fixture_roundtrip_sessions_and_stories(tmp_path):
    """Sessions, stories, story entries, and session participants survive the fixture round-trip."""
    # Import fixture into DB A.
    engine_a = _make_fresh_engine()
    session_a = _make_session(engine_a)
    try:
        result_a = _do_import(session_a, FIXTURE_CAMPAIGN_DIR)
    finally:
        session_a.close()

    # Export DB A.
    export_dir = tmp_path / "exported"
    session_a2 = _make_session(engine_a)
    try:
        _do_export(session_a2, export_dir)
    finally:
        session_a2.close()
        engine_a.dispose()

    # Import into fresh DB B.
    engine_b = _make_fresh_engine()
    session_b = _make_session(engine_b)
    try:
        _do_import(session_b, export_dir)

        assert _count(session_b, GameSession) == result_a.sessions
        assert _count(session_b, SessionParticipant) == result_a.session_participants
        assert _count(session_b, Story) == result_a.stories
        assert _count(session_b, StoryOwner) == result_a.story_owners
        assert _count(session_b, StoryEntry) == result_a.story_entries
    finally:
        session_b.close()
        engine_b.dispose()


def test_fixture_roundtrip_core_trait_charge(tmp_path):
    """Core trait slots (slot_type=core_trait) with their charge value survive the round-trip.

    The fixture campaign has Evelyn with a core trait 'Iron Will' at charge=4.
    """
    # Import fixture into DB A.
    engine_a = _make_fresh_engine()
    session_a = _make_session(engine_a)
    try:
        _do_import(session_a, FIXTURE_CAMPAIGN_DIR)
    finally:
        session_a.close()

    # Export DB A.
    export_dir = tmp_path / "exported"
    session_a2 = _make_session(engine_a)
    try:
        _do_export(session_a2, export_dir)
    finally:
        session_a2.close()
        engine_a.dispose()

    # Import into fresh DB B and verify the trait.
    engine_b = _make_fresh_engine()
    session_b = _make_session(engine_b)
    try:
        _do_import(session_b, export_dir)

        # Find Evelyn's core trait slot.
        evelyn = session_b.execute(
            select(Character).where(Character.name == "Evelyn")
        ).scalar_one()
        core_traits = session_b.execute(
            select(Slot).where(
                Slot.owner_type == "character",
                Slot.owner_id == evelyn.id,
                Slot.slot_type == "core_trait",
            )
        ).scalars().all()

        assert len(core_traits) == 1
        trait = core_traits[0]
        assert trait.name == "Iron Will"
        assert trait.charge == 4

        # The template should also exist and be linked.
        template = session_b.get(TraitTemplate, trait.template_id)
        assert template is not None
        assert template.name == "Iron Will"
        assert template.type == "core"
    finally:
        session_b.close()
        engine_b.dispose()
