"""Tests for CampaignImporter (Story 7.1.4).

Tests cover:
- All 6 import phases (trait templates, locations, groups, characters,
  slots, magic effects, clocks, users, sessions, stories)
- Happy-path import into an empty database
- Cross-reference resolution (bond targets, trait templates, etc.)
- Rollback on validation failure
- dry_run=True — no DB changes
- force=True — import into non-empty DB
- force=False (default) — refuses non-empty DB
- secrets field appended to notes
- All entity types created with correct fields
- Nested stories (children)
- Session participants
- Story owners + entries
- Clocks with optional associated_with
- PC and NPC characters with correct detail_level
- Magic effects with charged/instant/permanent types

All tests use an isolated in-memory SQLite database via the ``db`` fixture
from conftest.py.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

from sqlalchemy import func, select

from wizards_engine.campaign.importer import CampaignImporter, ImportResult
from wizards_engine.models.character import Character
from wizards_engine.models.clock import Clock
from wizards_engine.models.group import Group
from wizards_engine.models.location import Location
from wizards_engine.models.magic_effect import MagicEffect
from wizards_engine.models.session import Session as SessionModel
from wizards_engine.models.session import SessionParticipant
from wizards_engine.models.slot import Slot, TraitTemplate
from wizards_engine.models.story import Story, StoryEntry, StoryOwner
from wizards_engine.models.user import User


# ---------------------------------------------------------------------------
# Helpers — YAML campaign builder
# ---------------------------------------------------------------------------


def _write(path: Path, content: str) -> None:
    """Write *content* to *path*, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content), encoding="utf-8")


def _make_minimal_campaign(base: Path) -> None:
    """Write a minimal valid campaign with one of each basic entity type."""
    _write(base / "meta.yaml", """\
        engine_version: "0.1.0"
        campaign_name: Test Campaign
        format_version: 1
    """)
    _write(base / "trait-templates" / "resilient.yaml", """\
        name: Resilient
        type: core
        description: You bounce back from adversity.
    """)
    _write(base / "trait-templates" / "street-wise.yaml", """\
        name: Street Wise
        type: role
        description: You know how the streets work.
    """)
    _write(base / "locations" / "the-city" / "_location.yaml", """\
        name: The City
        description: A vast urban sprawl.
    """)
    _write(base / "groups" / "syndicate.yaml", """\
        name: The Syndicate
        tier: 3
        description: A powerful criminal organisation.
    """)
    _write(base / "characters" / "pcs" / "alex.yaml", """\
        name: Alex
        detail_level: full
        description: A resourceful fixer.
        meters:
          stress: 1
          free_time: 2
          plot: 3
          gnosis: 4
        skills:
          awareness: 1
          composure: 0
          influence: 2
          finesse: 1
          speed: 0
          power: 0
          knowledge: 1
          technology: 0
        magic_stats:
          being: {level: 1, xp: 3}
          wyrding: {level: 0, xp: 0}
          summoning: {level: 0, xp: 0}
          enchanting: {level: 0, xp: 0}
          dreaming: {level: 0, xp: 0}
        core_traits:
          - template: Resilient
            charge: 4
        role_traits:
          - template: Street Wise
            charge: 3
        bonds:
          - name: Old Debt
            target: {type: group, name: The Syndicate}
            charges: 5
            degradations: 0
            is_trauma: false
    """)
    _write(base / "characters" / "npcs" / "boss.yaml", """\
        name: The Boss
        detail_level: simplified
        description: Head of the Syndicate.
        bonds:
          - name: Controls The City
            target: {type: location, name: The City}
    """)
    _write(base / "users" / "gm.yaml", """\
        display_name: GM
        role: gm
    """)
    _write(base / "users" / "player-alex.yaml", """\
        display_name: Alice
        role: player
        character: Alex
    """)
    _write(base / "sessions" / "001-first-session.yaml", """\
        number: 1
        status: ended
        time_now: 10
        date: "2026-01-15"
        summary: The story begins.
        participants:
          - character: Alex
            additional_contribution: false
    """)
    _write(base / "stories" / "main-arc.yaml", """\
        name: The Main Arc
        status: active
        summary: The central conflict.
        owners:
          - type: character
            name: Alex
        entries:
          - text: It all started here.
            author: GM
            character: Alex
            session: 1
        children:
          - name: The Sub-Arc
            status: active
    """)
    _write(base / "clocks" / "consolidate-power.yaml", """\
        name: Consolidate Power
        segments: 6
        progress: 2
        associated_with:
          type: group
          name: The Syndicate
    """)


# ---------------------------------------------------------------------------
# Tests — happy path
# ---------------------------------------------------------------------------


def test_import_happy_path_returns_result(db, tmp_path):
    """A complete import returns an ImportResult with non-zero counts."""
    _make_minimal_campaign(tmp_path)
    importer = CampaignImporter(db, tmp_path)
    result = importer.import_all()

    assert isinstance(result, ImportResult)
    assert result.dry_run is False
    assert result.total_entities() > 0


def test_import_trait_templates_created(db, tmp_path):
    """Trait templates are created with correct name, type, description."""
    _make_minimal_campaign(tmp_path)
    CampaignImporter(db, tmp_path).import_all()

    templates = db.execute(select(TraitTemplate)).scalars().all()
    names = {t.name for t in templates}
    assert "Resilient" in names
    assert "Street Wise" in names

    resilient = next(t for t in templates if t.name == "Resilient")
    assert resilient.type == "core"
    assert "adversity" in resilient.description


def test_import_locations_created(db, tmp_path):
    """Locations are created with correct name."""
    _make_minimal_campaign(tmp_path)
    CampaignImporter(db, tmp_path).import_all()

    locs = db.execute(select(Location)).scalars().all()
    names = {l.name for l in locs}
    assert "The City" in names


def test_import_group_created(db, tmp_path):
    """Groups are created with correct fields."""
    _make_minimal_campaign(tmp_path)
    CampaignImporter(db, tmp_path).import_all()

    groups = db.execute(select(Group)).scalars().all()
    assert len(groups) == 1
    g = groups[0]
    assert g.name == "The Syndicate"
    assert g.tier == 3
    assert g.description == "A powerful criminal organisation."


def test_import_pc_character_created_with_full_detail(db, tmp_path):
    """PC characters get detail_level='full' and all mechanical columns set."""
    _make_minimal_campaign(tmp_path)
    CampaignImporter(db, tmp_path).import_all()

    chars = db.execute(
        select(Character).where(Character.name == "Alex")
    ).scalars().all()
    assert len(chars) == 1
    c = chars[0]
    assert c.detail_level == "full"
    assert c.stress == 1
    assert c.free_time == 2
    assert c.plot == 3
    assert c.gnosis == 4
    assert c.skills["awareness"] == 1
    assert c.skills["influence"] == 2
    assert c.magic_stats["being"]["level"] == 1
    assert c.magic_stats["being"]["xp"] == 3


def test_import_npc_character_created_with_simplified_detail(db, tmp_path):
    """NPC characters get detail_level='simplified' and null mechanical columns."""
    _make_minimal_campaign(tmp_path)
    CampaignImporter(db, tmp_path).import_all()

    npc = db.execute(
        select(Character).where(Character.name == "The Boss")
    ).scalar_one()
    assert npc.detail_level == "simplified"
    assert npc.stress is None
    assert npc.free_time is None
    assert npc.skills is None
    assert npc.magic_stats is None


def test_import_pc_core_trait_slot_created(db, tmp_path):
    """A PC core_trait slot is created with correct fields."""
    _make_minimal_campaign(tmp_path)
    CampaignImporter(db, tmp_path).import_all()

    slot = db.execute(
        select(Slot).where(
            Slot.slot_type == "core_trait",
            Slot.owner_type == "character",
        )
    ).scalar_one()
    assert slot.name == "Resilient"
    assert slot.charge == 4
    assert slot.template_id is not None


def test_import_pc_role_trait_slot_created(db, tmp_path):
    """A PC role_trait slot is created with correct fields."""
    _make_minimal_campaign(tmp_path)
    CampaignImporter(db, tmp_path).import_all()

    slot = db.execute(
        select(Slot).where(
            Slot.slot_type == "role_trait",
            Slot.owner_type == "character",
        )
    ).scalar_one()
    assert slot.name == "Street Wise"
    assert slot.charge == 3


def test_import_pc_bond_slot_created(db, tmp_path):
    """A PC bond slot is created with correct mechanical fields."""
    _make_minimal_campaign(tmp_path)
    CampaignImporter(db, tmp_path).import_all()

    slot = db.execute(
        select(Slot).where(
            Slot.slot_type == "pc_bond",
        )
    ).scalar_one()
    assert slot.name == "Old Debt"
    assert slot.target_type == "group"
    assert slot.charges == 5
    assert slot.degradations == 0
    assert slot.is_trauma is False


def test_import_npc_bond_slot_created(db, tmp_path):
    """An NPC bond slot is created with correct fields."""
    _make_minimal_campaign(tmp_path)
    CampaignImporter(db, tmp_path).import_all()

    slot = db.execute(
        select(Slot).where(
            Slot.slot_type == "npc_bond",
        )
    ).scalar_one()
    assert slot.name == "Controls The City"
    assert slot.target_type == "location"


def test_import_clock_created(db, tmp_path):
    """Clocks are created with correct fields and associated game object."""
    _make_minimal_campaign(tmp_path)
    CampaignImporter(db, tmp_path).import_all()

    clock = db.execute(select(Clock)).scalar_one()
    assert clock.name == "Consolidate Power"
    assert clock.segments == 6
    assert clock.progress == 2
    assert clock.associated_type == "group"
    assert clock.associated_id is not None


def test_import_users_created_with_login_codes(db, tmp_path):
    """Users are created with generated login codes (not empty strings)."""
    _make_minimal_campaign(tmp_path)
    CampaignImporter(db, tmp_path).import_all()

    users = db.execute(select(User)).scalars().all()
    assert len(users) == 2
    for user in users:
        assert user.login_code
        assert len(user.login_code) > 20


def test_import_player_user_linked_to_character(db, tmp_path):
    """Player users have character_id pointing to the correct character."""
    _make_minimal_campaign(tmp_path)
    CampaignImporter(db, tmp_path).import_all()

    user = db.execute(
        select(User).where(User.display_name == "Alice")
    ).scalar_one()
    assert user.character_id is not None

    char = db.execute(
        select(Character).where(Character.id == user.character_id)
    ).scalar_one()
    assert char.name == "Alex"


def test_import_gm_user_has_no_character(db, tmp_path):
    """GM users have character_id=None."""
    _make_minimal_campaign(tmp_path)
    CampaignImporter(db, tmp_path).import_all()

    gm = db.execute(
        select(User).where(User.display_name == "GM")
    ).scalar_one()
    assert gm.role == "gm"
    assert gm.character_id is None


def test_import_viewer_user_has_no_character(db, tmp_path):
    """Viewer users are imported with role='viewer' and character_id=None."""
    _make_minimal_campaign(tmp_path)
    _write(tmp_path / "users" / "viewer-iris.yaml", """\
        display_name: Viewer Iris
        role: viewer
        character: null
    """)
    CampaignImporter(db, tmp_path).import_all()

    viewer = db.execute(
        select(User).where(User.display_name == "Viewer Iris")
    ).scalar_one()
    assert viewer.role == "viewer"
    assert viewer.character_id is None


def test_import_session_created(db, tmp_path):
    """Sessions are created with correct status, date, and time_now."""
    _make_minimal_campaign(tmp_path)
    CampaignImporter(db, tmp_path).import_all()

    sessions = db.execute(select(SessionModel)).scalars().all()
    assert len(sessions) == 1
    s = sessions[0]
    assert s.status == "ended"
    assert s.time_now == 10
    assert str(s.date) == "2026-01-15"
    assert "begins" in s.summary


def test_import_session_participant_created(db, tmp_path):
    """Session participants are created linking session to character."""
    _make_minimal_campaign(tmp_path)
    CampaignImporter(db, tmp_path).import_all()

    participants = db.execute(select(SessionParticipant)).scalars().all()
    assert len(participants) == 1
    p = participants[0]
    assert p.additional_contribution is False


def test_import_story_created(db, tmp_path):
    """Stories are created with correct fields."""
    _make_minimal_campaign(tmp_path)
    CampaignImporter(db, tmp_path).import_all()

    stories = db.execute(select(Story)).scalars().all()
    names = {s.name for s in stories}
    assert "The Main Arc" in names
    assert "The Sub-Arc" in names


def test_import_nested_story_has_parent_id(db, tmp_path):
    """Nested (child) stories have parent_id pointing to the parent story."""
    _make_minimal_campaign(tmp_path)
    CampaignImporter(db, tmp_path).import_all()

    parent = db.execute(
        select(Story).where(Story.name == "The Main Arc")
    ).scalar_one()
    child = db.execute(
        select(Story).where(Story.name == "The Sub-Arc")
    ).scalar_one()
    assert child.parent_id == parent.id


def test_import_story_owner_created(db, tmp_path):
    """Story owners are created linking story to the correct game object."""
    _make_minimal_campaign(tmp_path)
    CampaignImporter(db, tmp_path).import_all()

    owners = db.execute(select(StoryOwner)).scalars().all()
    assert len(owners) == 1
    o = owners[0]
    assert o.owner_type == "character"


def test_import_story_entry_created(db, tmp_path):
    """Story entries are created with correct text, author, character, session links."""
    _make_minimal_campaign(tmp_path)
    CampaignImporter(db, tmp_path).import_all()

    entries = db.execute(select(StoryEntry)).scalars().all()
    assert len(entries) == 1
    e = entries[0]
    assert "started" in e.text
    assert e.author_id is not None
    assert e.character_id is not None
    assert e.session_id is not None


def test_import_result_counts(db, tmp_path):
    """ImportResult counts match the actual entities in the database."""
    _make_minimal_campaign(tmp_path)
    importer = CampaignImporter(db, tmp_path)
    result = importer.import_all()

    assert result.trait_templates == 2
    assert result.locations == 1
    assert result.groups == 1
    assert result.characters == 2
    assert result.users == 2
    assert result.sessions == 1
    assert result.session_participants == 1
    # 1 core_trait + 1 role_trait + 1 pc_bond + 1 npc_bond = 4
    assert result.slots == 4
    assert result.clocks == 1
    # 1 parent story + 1 child story
    assert result.stories == 2
    assert result.story_owners == 1
    assert result.story_entries == 1


# ---------------------------------------------------------------------------
# Tests — dry_run
# ---------------------------------------------------------------------------


def test_dry_run_does_not_commit(db, tmp_path):
    """dry_run=True runs all logic but does not persist any data."""
    _make_minimal_campaign(tmp_path)
    result = CampaignImporter(db, tmp_path).import_all(dry_run=True)

    assert result.dry_run is True
    # No data should be in the DB after a dry run.
    count = db.execute(select(func.count()).select_from(Character)).scalar_one()
    assert count == 0


def test_dry_run_returns_correct_counts(db, tmp_path):
    """dry_run=True still returns accurate entity counts."""
    _make_minimal_campaign(tmp_path)
    result = CampaignImporter(db, tmp_path).import_all(dry_run=True)
    assert result.characters == 2
    assert result.trait_templates == 2


# ---------------------------------------------------------------------------
# Tests — force flag and non-empty DB
# ---------------------------------------------------------------------------


def test_refuses_non_empty_db_without_force(db, tmp_path):
    """Import into a non-empty DB raises RuntimeError unless force=True."""
    from tests.fixtures import seed_data
    seed_data(db)  # populate DB

    _make_minimal_campaign(tmp_path)
    with pytest.raises(RuntimeError, match="not empty"):
        CampaignImporter(db, tmp_path).import_all(force=False)


def test_force_allows_import_into_non_empty_db(db, tmp_path):
    """force=True allows importing into a non-empty database."""
    from tests.fixtures import seed_data
    seed_data(db)  # populate DB with existing data

    _make_minimal_campaign(tmp_path)
    result = CampaignImporter(db, tmp_path).import_all(force=True)

    # New entities should have been created on top of the existing ones.
    assert result.characters == 2
    total = db.execute(select(func.count()).select_from(Character)).scalar_one()
    assert total > 2  # existing seed + new imports


# ---------------------------------------------------------------------------
# Tests — validation failure (no DB changes)
# ---------------------------------------------------------------------------


def test_validation_failure_raises_value_error(db, tmp_path):
    """A campaign with a broken reference raises ValueError before any DB writes."""
    _make_minimal_campaign(tmp_path)
    # Overwrite a bond target with a non-existent character name.
    _write(tmp_path / "characters" / "pcs" / "alex.yaml", """\
        name: Alex
        detail_level: full
        meters: {stress: 0, free_time: 0, plot: 0, gnosis: 0}
        skills:
          awareness: 0
          composure: 0
          influence: 0
          finesse: 0
          speed: 0
          power: 0
          knowledge: 0
          technology: 0
        magic_stats:
          being: {level: 0, xp: 0}
          wyrding: {level: 0, xp: 0}
          summoning: {level: 0, xp: 0}
          enchanting: {level: 0, xp: 0}
          dreaming: {level: 0, xp: 0}
        bonds:
          - name: Bad Bond
            target: {type: character, name: DOES_NOT_EXIST}
    """)

    with pytest.raises(ValueError, match="validation failed"):
        CampaignImporter(db, tmp_path).import_all()

    # No characters should have been created.
    count = db.execute(select(func.count()).select_from(Character)).scalar_one()
    assert count == 0


def test_validation_failure_leaves_db_empty(db, tmp_path):
    """After a validation failure, the database remains completely clean."""
    _make_minimal_campaign(tmp_path)
    # Add invalid schema (wrong effect_type) to trigger schema validation failure.
    _write(tmp_path / "clocks" / "broken-clock.yaml", """\
        name: Broken Clock
        segments: -1
        progress: 0
    """)

    with pytest.raises(ValueError):
        CampaignImporter(db, tmp_path).import_all()

    count = db.execute(select(func.count()).select_from(Clock)).scalar_one()
    assert count == 0


# ---------------------------------------------------------------------------
# Tests — rollback on mid-import error
# ---------------------------------------------------------------------------


def test_rollback_on_mid_import_error(db, tmp_path):
    """If an error occurs after partial inserts, the transaction rolls back."""
    _make_minimal_campaign(tmp_path)
    importer = CampaignImporter(db, tmp_path)

    # Monkeypatch _phase4_clocks to raise after Phase 1 has run.
    def _broken_phase4(result):
        raise RuntimeError("Simulated mid-import failure")

    importer._phase4_clocks = _broken_phase4

    with pytest.raises(RuntimeError, match="Simulated"):
        importer.import_all()

    # Everything should have been rolled back.
    count = db.execute(select(func.count()).select_from(TraitTemplate)).scalar_one()
    assert count == 0


# ---------------------------------------------------------------------------
# Tests — secrets field
# ---------------------------------------------------------------------------


def test_pc_secrets_appended_to_notes(db, tmp_path):
    """PC character secrets are appended to the notes column with separator."""
    _write(tmp_path / "meta.yaml", """\
        engine_version: "0.1.0"
        campaign_name: Test
        format_version: 1
    """)
    _write(tmp_path / "characters" / "pcs" / "spy.yaml", """\
        name: The Spy
        detail_level: full
        notes: Regular notes here.
        secrets: This is a secret.
        meters: {stress: 0, free_time: 0, plot: 0, gnosis: 0}
        skills:
          awareness: 0
          composure: 0
          influence: 0
          finesse: 0
          speed: 0
          power: 0
          knowledge: 0
          technology: 0
        magic_stats:
          being: {level: 0, xp: 0}
          wyrding: {level: 0, xp: 0}
          summoning: {level: 0, xp: 0}
          enchanting: {level: 0, xp: 0}
          dreaming: {level: 0, xp: 0}
    """)
    _write(tmp_path / "users" / "gm.yaml", """\
        display_name: GM
        role: gm
    """)

    CampaignImporter(db, tmp_path).import_all()

    char = db.execute(
        select(Character).where(Character.name == "The Spy")
    ).scalar_one()
    assert char.notes is not None
    assert "Regular notes here." in char.notes
    assert "SECRETS:" in char.notes
    assert "This is a secret." in char.notes


def test_npc_secrets_appended_to_notes(db, tmp_path):
    """NPC character secrets are appended to the notes column with separator."""
    _write(tmp_path / "meta.yaml", """\
        engine_version: "0.1.0"
        campaign_name: Test
        format_version: 1
    """)
    _write(tmp_path / "characters" / "npcs" / "informant.yaml", """\
        name: The Informant
        detail_level: simplified
        secrets: Hidden agenda.
    """)
    _write(tmp_path / "users" / "gm.yaml", """\
        display_name: GM
        role: gm
    """)

    CampaignImporter(db, tmp_path).import_all()

    char = db.execute(
        select(Character).where(Character.name == "The Informant")
    ).scalar_one()
    assert char.notes is not None
    assert "SECRETS:" in char.notes
    assert "Hidden agenda." in char.notes


def test_secrets_only_no_existing_notes(db, tmp_path):
    """secrets without existing notes creates notes from secrets alone."""
    _write(tmp_path / "meta.yaml", """\
        engine_version: "0.1.0"
        campaign_name: Test
        format_version: 1
    """)
    _write(tmp_path / "characters" / "npcs" / "ghost.yaml", """\
        name: Ghost
        detail_level: simplified
        secrets: Nobody knows this.
    """)
    _write(tmp_path / "users" / "gm.yaml", """\
        display_name: GM
        role: gm
    """)

    CampaignImporter(db, tmp_path).import_all()

    char = db.execute(
        select(Character).where(Character.name == "Ghost")
    ).scalar_one()
    assert char.notes is not None
    assert "SECRETS:" in char.notes
    assert "Nobody knows this." in char.notes


# ---------------------------------------------------------------------------
# Tests — location hierarchy
# ---------------------------------------------------------------------------


def test_location_parent_child_hierarchy(db, tmp_path):
    """Child locations have parent_id pointing to the correct parent Location."""
    _write(tmp_path / "meta.yaml", """\
        engine_version: "0.1.0"
        campaign_name: Test
        format_version: 1
    """)
    _write(tmp_path / "locations" / "country" / "_location.yaml", """\
        name: The Country
        description: A vast land.
    """)
    _write(tmp_path / "locations" / "country" / "city" / "_location.yaml", """\
        name: The City
        description: A bustling city.
    """)
    _write(tmp_path / "users" / "gm.yaml", """\
        display_name: GM
        role: gm
    """)

    CampaignImporter(db, tmp_path).import_all()

    parent = db.execute(
        select(Location).where(Location.name == "The Country")
    ).scalar_one()
    child = db.execute(
        select(Location).where(Location.name == "The City")
    ).scalar_one()

    assert child.parent_id == parent.id
    assert parent.parent_id is None


def test_location_explicit_parent_override(db, tmp_path):
    """Explicit parent field in YAML overrides directory-inferred parent."""
    _write(tmp_path / "meta.yaml", """\
        engine_version: "0.1.0"
        campaign_name: Test
        format_version: 1
    """)
    _write(tmp_path / "locations" / "region-a" / "_location.yaml", """\
        name: Region A
    """)
    _write(tmp_path / "locations" / "region-b" / "_location.yaml", """\
        name: Region B
    """)
    # region-b/district/_location.yaml would normally have Region B as parent,
    # but the explicit parent field overrides to Region A.
    _write(tmp_path / "locations" / "region-b" / "district" / "_location.yaml", """\
        name: The District
        parent: Region A
    """)
    _write(tmp_path / "users" / "gm.yaml", """\
        display_name: GM
        role: gm
    """)

    CampaignImporter(db, tmp_path).import_all()

    region_a = db.execute(
        select(Location).where(Location.name == "Region A")
    ).scalar_one()
    district = db.execute(
        select(Location).where(Location.name == "The District")
    ).scalar_one()
    assert district.parent_id == region_a.id


# ---------------------------------------------------------------------------
# Tests — group slots
# ---------------------------------------------------------------------------


def test_group_trait_slot_created(db, tmp_path):
    """Group traits are created as group_trait slots."""
    _write(tmp_path / "meta.yaml", """\
        engine_version: "0.1.0"
        campaign_name: Test
        format_version: 1
    """)
    _write(tmp_path / "groups" / "guild.yaml", """\
        name: The Guild
        tier: 2
        traits:
          - name: Ancient Knowledge
            description: Centuries of gathered lore.
    """)
    _write(tmp_path / "users" / "gm.yaml", """\
        display_name: GM
        role: gm
    """)

    CampaignImporter(db, tmp_path).import_all()

    slot = db.execute(
        select(Slot).where(Slot.slot_type == "group_trait")
    ).scalar_one()
    assert slot.name == "Ancient Knowledge"
    assert slot.owner_type == "group"


def test_group_relation_slot_created(db, tmp_path):
    """Group relations are created as group_relation slots linking two groups."""
    _write(tmp_path / "meta.yaml", """\
        engine_version: "0.1.0"
        campaign_name: Test
        format_version: 1
    """)
    _write(tmp_path / "groups" / "alpha.yaml", """\
        name: Alpha
        tier: 1
        relations:
          - name: Rivals
            target: Beta
            bidirectional: true
    """)
    _write(tmp_path / "groups" / "beta.yaml", """\
        name: Beta
        tier: 1
    """)
    _write(tmp_path / "users" / "gm.yaml", """\
        display_name: GM
        role: gm
    """)

    CampaignImporter(db, tmp_path).import_all()

    slot = db.execute(
        select(Slot).where(Slot.slot_type == "group_relation")
    ).scalar_one()
    assert slot.name == "Rivals"
    assert slot.target_type == "group"
    assert slot.bidirectional is True


def test_group_holding_slot_created(db, tmp_path):
    """Group holdings are created as group_holding slots linking group to location."""
    _write(tmp_path / "meta.yaml", """\
        engine_version: "0.1.0"
        campaign_name: Test
        format_version: 1
    """)
    _write(tmp_path / "locations" / "warehouse" / "_location.yaml", """\
        name: The Warehouse
    """)
    _write(tmp_path / "groups" / "owners.yaml", """\
        name: The Owners
        tier: 2
        holdings:
          - name: Storage Facility
            target: The Warehouse
            description: Where they keep the goods.
    """)
    _write(tmp_path / "users" / "gm.yaml", """\
        display_name: GM
        role: gm
    """)

    CampaignImporter(db, tmp_path).import_all()

    slot = db.execute(
        select(Slot).where(Slot.slot_type == "group_holding")
    ).scalar_one()
    assert slot.name == "Storage Facility"
    assert slot.target_type == "location"


# ---------------------------------------------------------------------------
# Tests — location slots
# ---------------------------------------------------------------------------


def test_location_feature_slot_created(db, tmp_path):
    """Location features are created as feature_trait slots."""
    _write(tmp_path / "meta.yaml", """\
        engine_version: "0.1.0"
        campaign_name: Test
        format_version: 1
    """)
    _write(tmp_path / "locations" / "the-park" / "_location.yaml", """\
        name: The Park
        features:
          - name: Hidden Grotto
            description: Few know of this secret place.
    """)
    _write(tmp_path / "users" / "gm.yaml", """\
        display_name: GM
        role: gm
    """)

    CampaignImporter(db, tmp_path).import_all()

    slot = db.execute(
        select(Slot).where(Slot.slot_type == "feature_trait")
    ).scalar_one()
    assert slot.name == "Hidden Grotto"
    assert slot.owner_type == "location"


def test_location_bond_slot_created(db, tmp_path):
    """Location bonds are created as location_bond slots."""
    _write(tmp_path / "meta.yaml", """\
        engine_version: "0.1.0"
        campaign_name: Test
        format_version: 1
    """)
    _write(tmp_path / "groups" / "local-guild.yaml", """\
        name: Local Guild
        tier: 1
    """)
    _write(tmp_path / "locations" / "market" / "_location.yaml", """\
        name: The Market
        bonds:
          - name: Guild Presence
            target: {type: group, name: Local Guild}
    """)
    _write(tmp_path / "users" / "gm.yaml", """\
        display_name: GM
        role: gm
    """)

    CampaignImporter(db, tmp_path).import_all()

    slot = db.execute(
        select(Slot).where(Slot.slot_type == "location_bond")
    ).scalar_one()
    assert slot.name == "Guild Presence"
    assert slot.target_type == "group"


# ---------------------------------------------------------------------------
# Tests — magic effects
# ---------------------------------------------------------------------------


def test_magic_effect_charged_created(db, tmp_path):
    """Charged magic effects are created with charges_current and charges_max."""
    _write(tmp_path / "meta.yaml", """\
        engine_version: "0.1.0"
        campaign_name: Test
        format_version: 1
    """)
    _write(tmp_path / "characters" / "pcs" / "mage.yaml", """\
        name: The Mage
        detail_level: full
        meters: {stress: 0, free_time: 0, plot: 0, gnosis: 0}
        skills:
          awareness: 0
          composure: 0
          influence: 0
          finesse: 0
          speed: 0
          power: 0
          knowledge: 0
          technology: 0
        magic_stats:
          being: {level: 0, xp: 0}
          wyrding: {level: 0, xp: 0}
          summoning: {level: 0, xp: 0}
          enchanting: {level: 0, xp: 0}
          dreaming: {level: 0, xp: 0}
        magic_effects:
          - name: Fireball
            description: A ball of fire.
            effect_type: charged
            power_level: 3
            charges: {current: 2, max: 5}
    """)
    _write(tmp_path / "users" / "gm.yaml", """\
        display_name: GM
        role: gm
    """)

    CampaignImporter(db, tmp_path).import_all()

    effect = db.execute(select(MagicEffect)).scalar_one()
    assert effect.name == "Fireball"
    assert effect.effect_type == "charged"
    assert effect.power_level == 3
    assert effect.charges_current == 2
    assert effect.charges_max == 5


def test_magic_effect_permanent_has_null_charges(db, tmp_path):
    """Permanent magic effects have null charges_current and charges_max."""
    _write(tmp_path / "meta.yaml", """\
        engine_version: "0.1.0"
        campaign_name: Test
        format_version: 1
    """)
    _write(tmp_path / "characters" / "pcs" / "mage.yaml", """\
        name: The Mage
        detail_level: full
        meters: {stress: 0, free_time: 0, plot: 0, gnosis: 0}
        skills:
          awareness: 0
          composure: 0
          influence: 0
          finesse: 0
          speed: 0
          power: 0
          knowledge: 0
          technology: 0
        magic_stats:
          being: {level: 0, xp: 0}
          wyrding: {level: 0, xp: 0}
          summoning: {level: 0, xp: 0}
          enchanting: {level: 0, xp: 0}
          dreaming: {level: 0, xp: 0}
        magic_effects:
          - name: Eternal Shield
            description: An everlasting ward.
            effect_type: permanent
            power_level: 5
    """)
    _write(tmp_path / "users" / "gm.yaml", """\
        display_name: GM
        role: gm
    """)

    CampaignImporter(db, tmp_path).import_all()

    effect = db.execute(select(MagicEffect)).scalar_one()
    assert effect.effect_type == "permanent"
    assert effect.charges_current is None
    assert effect.charges_max is None


# ---------------------------------------------------------------------------
# Tests — clocks without associated_with
# ---------------------------------------------------------------------------


def test_clock_without_association(db, tmp_path):
    """Clocks with no associated_with are created with null associated fields."""
    _write(tmp_path / "meta.yaml", """\
        engine_version: "0.1.0"
        campaign_name: Test
        format_version: 1
    """)
    _write(tmp_path / "clocks" / "countdown.yaml", """\
        name: Countdown
        segments: 4
        progress: 1
    """)
    _write(tmp_path / "users" / "gm.yaml", """\
        display_name: GM
        role: gm
    """)

    CampaignImporter(db, tmp_path).import_all()

    clock = db.execute(select(Clock)).scalar_one()
    assert clock.name == "Countdown"
    assert clock.associated_type is None
    assert clock.associated_id is None


# ---------------------------------------------------------------------------
# Tests — trait template cross-reference
# ---------------------------------------------------------------------------


def test_trait_slot_template_id_resolves_correctly(db, tmp_path):
    """Trait slot template_id foreign key points to the correct TraitTemplate row."""
    _make_minimal_campaign(tmp_path)
    CampaignImporter(db, tmp_path).import_all()

    # Get the core_trait slot and its template.
    slot = db.execute(
        select(Slot).where(Slot.slot_type == "core_trait")
    ).scalar_one()
    template = db.execute(
        select(TraitTemplate).where(TraitTemplate.id == slot.template_id)
    ).scalar_one()
    assert template.name == "Resilient"


# ---------------------------------------------------------------------------
# Tests — bond target cross-reference
# ---------------------------------------------------------------------------


def test_pc_bond_target_id_resolves_to_group(db, tmp_path):
    """PC bond target_id is the ULID of the referenced Group."""
    _make_minimal_campaign(tmp_path)
    CampaignImporter(db, tmp_path).import_all()

    bond_slot = db.execute(
        select(Slot).where(Slot.slot_type == "pc_bond")
    ).scalar_one()
    group = db.execute(
        select(Group).where(Group.id == bond_slot.target_id)
    ).scalar_one()
    assert group.name == "The Syndicate"


# ---------------------------------------------------------------------------
# Tests — empty campaign (no subdirectories)
# ---------------------------------------------------------------------------


def test_import_empty_campaign_directory(db, tmp_path):
    """Importing a campaign directory with only meta.yaml produces zero counts."""
    _write(tmp_path / "meta.yaml", """\
        engine_version: "0.1.0"
        campaign_name: Empty Campaign
        format_version: 1
    """)

    result = CampaignImporter(db, tmp_path).import_all()
    assert result.total_entities() == 0
    assert result.dry_run is False


# ---------------------------------------------------------------------------
# Tests — bond labels
# ---------------------------------------------------------------------------


def test_pc_bond_labels_stored(db, tmp_path):
    """Bond source/target labels are stored in the slot's label columns."""
    _write(tmp_path / "meta.yaml", """\
        engine_version: "0.1.0"
        campaign_name: Test
        format_version: 1
    """)
    _write(tmp_path / "groups" / "faction.yaml", """\
        name: The Faction
        tier: 1
    """)
    _write(tmp_path / "characters" / "pcs" / "hero.yaml", """\
        name: The Hero
        detail_level: full
        meters: {stress: 0, free_time: 0, plot: 0, gnosis: 0}
        skills:
          awareness: 0
          composure: 0
          influence: 0
          finesse: 0
          speed: 0
          power: 0
          knowledge: 0
          technology: 0
        magic_stats:
          being: {level: 0, xp: 0}
          wyrding: {level: 0, xp: 0}
          summoning: {level: 0, xp: 0}
          enchanting: {level: 0, xp: 0}
          dreaming: {level: 0, xp: 0}
        bonds:
          - name: Allegiance
            target: {type: group, name: The Faction}
            labels:
              source: loyal member
              target: useful asset
            charges: 4
            degradations: 1
            is_trauma: false
    """)
    _write(tmp_path / "users" / "gm.yaml", """\
        display_name: GM
        role: gm
    """)

    CampaignImporter(db, tmp_path).import_all()

    slot = db.execute(
        select(Slot).where(Slot.slot_type == "pc_bond")
    ).scalar_one()
    assert slot.source_label == "loyal member"
    assert slot.target_label == "useful asset"
    assert slot.charges == 4
    assert slot.degradations == 1


# ---------------------------------------------------------------------------
# Tests — fresh ULIDs
# ---------------------------------------------------------------------------


def test_all_entities_have_fresh_ulids(db, tmp_path):
    """All created entities have unique, non-empty ULID primary keys."""
    _make_minimal_campaign(tmp_path)
    CampaignImporter(db, tmp_path).import_all()

    all_ids: list[str] = []
    for model in (Character, Group, Location, TraitTemplate, User, SessionModel, Clock, Story):
        rows = db.execute(select(model)).scalars().all()
        for row in rows:
            all_ids.append(row.id)

    # All IDs must be unique.
    assert len(all_ids) == len(set(all_ids))
    # All IDs must be non-empty 26-character strings (ULID format).
    for ulid in all_ids:
        assert len(ulid) == 26


# ---------------------------------------------------------------------------
# Additional coverage: untested paths and edge cases
# ---------------------------------------------------------------------------


def test_magic_effect_instant_created(db, tmp_path):
    """Instant magic effects are created with null charges fields."""
    _write(tmp_path / "meta.yaml", """\
        engine_version: "0.1.0"
        campaign_name: Test
        format_version: 1
    """)
    _write(tmp_path / "characters" / "pcs" / "mage.yaml", """\
        name: The Mage
        detail_level: full
        meters: {stress: 0, free_time: 0, plot: 0, gnosis: 0}
        skills:
          awareness: 0
          composure: 0
          influence: 0
          finesse: 0
          speed: 0
          power: 0
          knowledge: 0
          technology: 0
        magic_stats:
          being: {level: 0, xp: 0}
          wyrding: {level: 0, xp: 0}
          summoning: {level: 0, xp: 0}
          enchanting: {level: 0, xp: 0}
          dreaming: {level: 0, xp: 0}
        magic_effects:
          - name: Lightning Bolt
            description: A single shocking strike.
            effect_type: instant
            power_level: 2
    """)
    _write(tmp_path / "users" / "gm.yaml", """\
        display_name: GM
        role: gm
    """)

    CampaignImporter(db, tmp_path).import_all()

    effect = db.execute(select(MagicEffect)).scalar_one()
    assert effect.name == "Lightning Bolt"
    assert effect.effect_type == "instant"
    assert effect.power_level == 2
    assert effect.charges_current is None
    assert effect.charges_max is None


def test_import_result_magic_effects_count(db, tmp_path):
    """ImportResult.magic_effects is incremented correctly."""
    _write(tmp_path / "meta.yaml", """\
        engine_version: "0.1.0"
        campaign_name: Test
        format_version: 1
    """)
    _write(tmp_path / "characters" / "pcs" / "mage.yaml", """\
        name: Mage
        detail_level: full
        meters: {stress: 0, free_time: 0, plot: 0, gnosis: 0}
        skills:
          awareness: 0
          composure: 0
          influence: 0
          finesse: 0
          speed: 0
          power: 0
          knowledge: 0
          technology: 0
        magic_stats:
          being: {level: 0, xp: 0}
          wyrding: {level: 0, xp: 0}
          summoning: {level: 0, xp: 0}
          enchanting: {level: 0, xp: 0}
          dreaming: {level: 0, xp: 0}
        magic_effects:
          - name: Flame
            description: Fire.
            effect_type: instant
            power_level: 1
          - name: Shield
            description: Ward.
            effect_type: permanent
            power_level: 2
    """)
    _write(tmp_path / "users" / "gm.yaml", """\
        display_name: GM
        role: gm
    """)

    result = CampaignImporter(db, tmp_path).import_all()
    assert result.magic_effects == 2


def test_import_entities_subdirectory(db, tmp_path):
    """Characters in characters/entities/ are imported as simplified NPCs."""
    _write(tmp_path / "meta.yaml", """\
        engine_version: "0.1.0"
        campaign_name: Test
        format_version: 1
    """)
    _write(tmp_path / "characters" / "entities" / "beast.yaml", """\
        name: The Beast
        detail_level: simplified
        description: A fearsome creature.
    """)
    _write(tmp_path / "users" / "gm.yaml", """\
        display_name: GM
        role: gm
    """)

    CampaignImporter(db, tmp_path).import_all()

    char = db.execute(
        select(Character).where(Character.name == "The Beast")
    ).scalar_one()
    assert char.detail_level == "simplified"
    assert char.description == "A fearsome creature."


def test_import_npc_bond_to_character(db, tmp_path):
    """NPC bond targeting another character resolves target_id correctly."""
    _write(tmp_path / "meta.yaml", """\
        engine_version: "0.1.0"
        campaign_name: Test
        format_version: 1
    """)
    _write(tmp_path / "characters" / "pcs" / "hero.yaml", """\
        name: Hero
        detail_level: full
        meters: {stress: 0, free_time: 0, plot: 0, gnosis: 0}
        skills:
          awareness: 0
          composure: 0
          influence: 0
          finesse: 0
          speed: 0
          power: 0
          knowledge: 0
          technology: 0
        magic_stats:
          being: {level: 0, xp: 0}
          wyrding: {level: 0, xp: 0}
          summoning: {level: 0, xp: 0}
          enchanting: {level: 0, xp: 0}
          dreaming: {level: 0, xp: 0}
    """)
    _write(tmp_path / "characters" / "npcs" / "villain.yaml", """\
        name: Villain
        detail_level: simplified
        bonds:
          - name: Nemesis
            target: {type: character, name: Hero}
    """)
    _write(tmp_path / "users" / "gm.yaml", """\
        display_name: GM
        role: gm
    """)

    CampaignImporter(db, tmp_path).import_all()

    bond = db.execute(
        select(Slot).where(Slot.slot_type == "npc_bond")
    ).scalar_one()
    assert bond.target_type == "character"
    assert bond.target_id is not None

    hero = db.execute(
        select(Character).where(Character.id == bond.target_id)
    ).scalar_one()
    assert hero.name == "Hero"


def test_import_session_notes_preserved(db, tmp_path):
    """Session notes are stored in the notes column."""
    _write(tmp_path / "meta.yaml", """\
        engine_version: "0.1.0"
        campaign_name: Test
        format_version: 1
    """)
    _write(tmp_path / "sessions" / "001-session.yaml", """\
        number: 1
        status: ended
        summary: The first session.
        notes: Remember the ritual timing.
    """)
    _write(tmp_path / "users" / "gm.yaml", """\
        display_name: GM
        role: gm
    """)

    CampaignImporter(db, tmp_path).import_all()

    session = db.execute(select(SessionModel)).scalar_one()
    assert session.notes == "Remember the ritual timing."


def test_import_story_completed_status(db, tmp_path):
    """Stories with status='completed' are imported correctly."""
    _write(tmp_path / "meta.yaml", """\
        engine_version: "0.1.0"
        campaign_name: Test
        format_version: 1
    """)
    _write(tmp_path / "stories" / "done.yaml", """\
        name: Done Arc
        status: completed
    """)
    _write(tmp_path / "users" / "gm.yaml", """\
        display_name: GM
        role: gm
    """)

    CampaignImporter(db, tmp_path).import_all()

    story = db.execute(
        select(Story).where(Story.name == "Done Arc")
    ).scalar_one()
    assert story.status == "completed"


def test_import_story_tags_preserved(db, tmp_path):
    """Story tags list is stored in the tags column."""
    _write(tmp_path / "meta.yaml", """\
        engine_version: "0.1.0"
        campaign_name: Test
        format_version: 1
    """)
    _write(tmp_path / "stories" / "tagged.yaml", """\
        name: Tagged Story
        status: active
        tags: [mystery, faction, urgent]
    """)
    _write(tmp_path / "users" / "gm.yaml", """\
        display_name: GM
        role: gm
    """)

    CampaignImporter(db, tmp_path).import_all()

    story = db.execute(
        select(Story).where(Story.name == "Tagged Story")
    ).scalar_one()
    assert story.tags == ["mystery", "faction", "urgent"]


def test_import_group_owner_story(db, tmp_path):
    """Story owned by a group resolves owner_id to the correct Group."""
    _write(tmp_path / "meta.yaml", """\
        engine_version: "0.1.0"
        campaign_name: Test
        format_version: 1
    """)
    _write(tmp_path / "groups" / "council.yaml", """\
        name: The Council
        tier: 2
    """)
    _write(tmp_path / "stories" / "council-arc.yaml", """\
        name: Council Arc
        status: active
        owners:
          - type: group
            name: The Council
    """)
    _write(tmp_path / "users" / "gm.yaml", """\
        display_name: GM
        role: gm
    """)

    CampaignImporter(db, tmp_path).import_all()

    owner = db.execute(select(StoryOwner)).scalar_one()
    assert owner.owner_type == "group"

    group = db.execute(
        select(Group).where(Group.id == owner.owner_id)
    ).scalar_one()
    assert group.name == "The Council"


def test_import_location_bond_to_character(db, tmp_path):
    """Location bond targeting a character resolves target_id correctly."""
    _write(tmp_path / "meta.yaml", """\
        engine_version: "0.1.0"
        campaign_name: Test
        format_version: 1
    """)
    _write(tmp_path / "characters" / "pcs" / "warden.yaml", """\
        name: The Warden
        detail_level: full
        meters: {stress: 0, free_time: 0, plot: 0, gnosis: 0}
        skills:
          awareness: 0
          composure: 0
          influence: 0
          finesse: 0
          speed: 0
          power: 0
          knowledge: 0
          technology: 0
        magic_stats:
          being: {level: 0, xp: 0}
          wyrding: {level: 0, xp: 0}
          summoning: {level: 0, xp: 0}
          enchanting: {level: 0, xp: 0}
          dreaming: {level: 0, xp: 0}
    """)
    _write(tmp_path / "locations" / "keep" / "_location.yaml", """\
        name: The Keep
        bonds:
          - name: Warden's Domain
            target: {type: character, name: The Warden}
    """)
    _write(tmp_path / "users" / "gm.yaml", """\
        display_name: GM
        role: gm
    """)

    CampaignImporter(db, tmp_path).import_all()

    bond = db.execute(
        select(Slot).where(Slot.slot_type == "location_bond")
    ).scalar_one()
    assert bond.target_type == "character"

    warden = db.execute(
        select(Character).where(Character.id == bond.target_id)
    ).scalar_one()
    assert warden.name == "The Warden"


def test_import_deeply_nested_locations(db, tmp_path):
    """Three-level location nesting preserves the full parent chain."""
    _write(tmp_path / "meta.yaml", """\
        engine_version: "0.1.0"
        campaign_name: Test
        format_version: 1
    """)
    _write(tmp_path / "locations" / "continent" / "_location.yaml", """\
        name: The Continent
    """)
    _write(tmp_path / "locations" / "continent" / "country" / "_location.yaml", """\
        name: The Country
    """)
    _write(
        tmp_path / "locations" / "continent" / "country" / "city" / "_location.yaml",
        """\
        name: The Capital City
    """,
    )
    _write(tmp_path / "users" / "gm.yaml", """\
        display_name: GM
        role: gm
    """)

    CampaignImporter(db, tmp_path).import_all()

    continent = db.execute(
        select(Location).where(Location.name == "The Continent")
    ).scalar_one()
    country = db.execute(
        select(Location).where(Location.name == "The Country")
    ).scalar_one()
    city = db.execute(
        select(Location).where(Location.name == "The Capital City")
    ).scalar_one()

    assert continent.parent_id is None
    assert country.parent_id == continent.id
    assert city.parent_id == country.id


def test_import_clock_notes_preserved(db, tmp_path):
    """Clock notes field is stored in the notes column."""
    _write(tmp_path / "meta.yaml", """\
        engine_version: "0.1.0"
        campaign_name: Test
        format_version: 1
    """)
    _write(tmp_path / "clocks" / "ticking-bomb.yaml", """\
        name: Ticking Bomb
        segments: 4
        progress: 1
        notes: Defuse before the third act.
    """)
    _write(tmp_path / "users" / "gm.yaml", """\
        display_name: GM
        role: gm
    """)

    CampaignImporter(db, tmp_path).import_all()

    clock = db.execute(select(Clock)).scalar_one()
    assert clock.notes == "Defuse before the third act."
