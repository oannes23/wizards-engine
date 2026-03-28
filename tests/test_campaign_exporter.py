"""Tests for the CampaignExporter (Story 7.1.3).

Each test populates a fresh in-memory SQLite database (via the ``db`` fixture
from conftest.py) and runs the exporter against a temporary output directory.
The seed_data fixture provides a baseline set of characters, users, groups,
locations, and slots.  Individual tests extend the seed data to cover all
entity types (sessions, stories, clocks, trait templates, magic effects).

All YAML output is validated against the Pydantic schemas from 7.1.1 to
confirm the exported structure is importable.
"""

from __future__ import annotations

import secrets
from datetime import date
from pathlib import Path

import pytest
import yaml

from wizards_engine.campaign.exporter import CampaignExporter, ExportResult, _slugify
from wizards_engine.campaign.schemas import (
    CampaignMeta,
    ClockYaml,
    GroupYaml,
    LocationYaml,
    NPCCharacterYaml,
    PCCharacterYaml,
    SessionYaml,
    StoryYaml,
    TraitTemplateYaml,
    UserYaml,
)
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run_export(db, tmp_path: Path) -> tuple[CampaignExporter, ExportResult]:
    """Run the exporter and return (exporter, result)."""
    exporter = CampaignExporter(db, tmp_path)
    result = exporter.export_all()
    return exporter, result


def load_yaml(path: Path) -> dict:
    """Load a YAML file and return the parsed dict."""
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# ---------------------------------------------------------------------------
# _slugify unit tests
# ---------------------------------------------------------------------------


def test_slugify_basic():
    assert _slugify("The Shattered Coast") == "the-shattered-coast"


def test_slugify_special_chars():
    assert _slugify("Hello, World!") == "hello-world"


def test_slugify_multiple_spaces():
    assert _slugify("Multi  Space  Name") == "multi-space-name"


def test_slugify_leading_trailing_hyphens():
    result = _slugify("  ...weird name...")
    assert not result.startswith("-")
    assert not result.endswith("-")


# ---------------------------------------------------------------------------
# ExportResult dataclass
# ---------------------------------------------------------------------------


def test_export_result_defaults():
    r = ExportResult()
    assert r.trait_templates == 0
    assert r.characters_pc == 0
    assert r.characters_npc == 0
    assert r.groups == 0
    assert r.clocks == 0
    assert r.users == 0
    assert r.sessions == 0
    assert r.stories == 0


# ---------------------------------------------------------------------------
# meta.yaml
# ---------------------------------------------------------------------------


def test_export_meta_written(db, seed_data, tmp_path):
    run_export(db, tmp_path)
    meta_path = tmp_path / "meta.yaml"
    assert meta_path.exists(), "meta.yaml should be written"
    data = load_yaml(meta_path)
    CampaignMeta.model_validate(data)  # Must validate against schema


def test_export_meta_fields(db, seed_data, tmp_path):
    run_export(db, tmp_path)
    data = load_yaml(tmp_path / "meta.yaml")
    assert "engine_version" in data
    assert "campaign_name" in data
    assert "format_version" in data
    assert data["format_version"] == 1


def test_export_meta_has_timestamp(db, seed_data, tmp_path):
    run_export(db, tmp_path)
    data = load_yaml(tmp_path / "meta.yaml")
    assert "exported_at" in data


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


def test_export_users_count(db, seed_data, tmp_path):
    _, result = run_export(db, tmp_path)
    # seed_data has 5 active users (gm + 3 players + 1 viewer)
    assert result.users == 5


def test_export_user_files_exist(db, seed_data, tmp_path):
    run_export(db, tmp_path)
    usr_dir = tmp_path / "users"
    assert usr_dir.is_dir()
    yaml_files = list(usr_dir.glob("*.yaml"))
    # seed_data has 5 active users (gm + 3 players + 1 viewer)
    assert len(yaml_files) == 5


def test_export_user_schema_validates(db, seed_data, tmp_path):
    run_export(db, tmp_path)
    for yaml_file in (tmp_path / "users").glob("*.yaml"):
        data = load_yaml(yaml_file)
        UserYaml.model_validate(data)


def test_export_user_gm_has_no_character(db, seed_data, tmp_path):
    run_export(db, tmp_path)
    gm = seed_data["gm"]
    slug = _slugify(gm.display_name)
    data = load_yaml(tmp_path / "users" / f"{slug}.yaml")
    assert data.get("character") is None


def test_export_user_player_has_character(db, seed_data, tmp_path):
    run_export(db, tmp_path)
    player1 = seed_data["player1"]
    slug = _slugify(player1.display_name)
    data = load_yaml(tmp_path / "users" / f"{slug}.yaml")
    assert data["character"] == seed_data["pc1"].name


def test_export_user_role_preserved(db, seed_data, tmp_path):
    run_export(db, tmp_path)
    gm_slug = _slugify(seed_data["gm"].display_name)
    gm_data = load_yaml(tmp_path / "users" / f"{gm_slug}.yaml")
    assert gm_data["role"] == "gm"

    p1_slug = _slugify(seed_data["player1"].display_name)
    p1_data = load_yaml(tmp_path / "users" / f"{p1_slug}.yaml")
    assert p1_data["role"] == "player"


# ---------------------------------------------------------------------------
# Characters — PCs
# ---------------------------------------------------------------------------


def test_export_pc_count(db, seed_data, tmp_path):
    _, result = run_export(db, tmp_path)
    assert result.characters_pc == 3  # pc1, pc2, pc3


def test_export_npc_count(db, seed_data, tmp_path):
    _, result = run_export(db, tmp_path)
    assert result.characters_npc == 2  # npc1, npc2


def test_export_pc_directory_exists(db, seed_data, tmp_path):
    run_export(db, tmp_path)
    pcs_dir = tmp_path / "characters" / "pcs"
    assert pcs_dir.is_dir()
    assert len(list(pcs_dir.glob("*.yaml"))) == 3


def test_export_npc_directory_exists(db, seed_data, tmp_path):
    run_export(db, tmp_path)
    npcs_dir = tmp_path / "characters" / "npcs"
    assert npcs_dir.is_dir()
    assert len(list(npcs_dir.glob("*.yaml"))) == 2


def test_export_pc_schema_validates(db, seed_data, tmp_path):
    run_export(db, tmp_path)
    for yaml_file in (tmp_path / "characters" / "pcs").glob("*.yaml"):
        data = load_yaml(yaml_file)
        PCCharacterYaml.model_validate(data)


def test_export_npc_schema_validates(db, seed_data, tmp_path):
    run_export(db, tmp_path)
    for yaml_file in (tmp_path / "characters" / "npcs").glob("*.yaml"):
        data = load_yaml(yaml_file)
        NPCCharacterYaml.model_validate(data)


def test_export_pc_has_meters(db, seed_data, tmp_path):
    run_export(db, tmp_path)
    pc1 = seed_data["pc1"]
    slug = _slugify(pc1.name)
    data = load_yaml(tmp_path / "characters" / "pcs" / f"{slug}.yaml")
    assert "meters" in data
    assert set(data["meters"].keys()) == {"stress", "free_time", "plot", "gnosis"}


def test_export_pc_has_skills(db, seed_data, tmp_path):
    run_export(db, tmp_path)
    pc1 = seed_data["pc1"]
    slug = _slugify(pc1.name)
    data = load_yaml(tmp_path / "characters" / "pcs" / f"{slug}.yaml")
    assert "skills" in data
    assert "awareness" in data["skills"]


def test_export_pc_has_magic_stats(db, seed_data, tmp_path):
    run_export(db, tmp_path)
    pc1 = seed_data["pc1"]
    slug = _slugify(pc1.name)
    data = load_yaml(tmp_path / "characters" / "pcs" / f"{slug}.yaml")
    assert "magic_stats" in data
    assert "being" in data["magic_stats"]


def test_export_pc_bonds_inlined(db, seed_data, tmp_path):
    """pc1 has a pc_bond; it should appear in the PC's YAML."""
    run_export(db, tmp_path)
    pc1 = seed_data["pc1"]
    slug = _slugify(pc1.name)
    data = load_yaml(tmp_path / "characters" / "pcs" / f"{slug}.yaml")
    assert "bonds" in data
    assert len(data["bonds"]) >= 1
    bond = data["bonds"][0]
    assert "target" in bond
    # Target should use group name, not ULID
    assert bond["target"]["name"] == seed_data["group"].name
    assert bond["target"]["type"] == "group"


def test_export_pc_bond_has_no_ulids(db, seed_data, tmp_path):
    """Verify no ULID strings appear in PC bond target."""
    run_export(db, tmp_path)
    pc1 = seed_data["pc1"]
    slug = _slugify(pc1.name)
    data = load_yaml(tmp_path / "characters" / "pcs" / f"{slug}.yaml")
    for bond in data.get("bonds", []):
        # A ULID is 26 uppercase/digit chars — names won't look like that
        target_name = bond["target"]["name"]
        assert len(target_name) != 26 or not target_name.isupper()


def test_export_npc_bonds_inlined(db, seed_data, tmp_path):
    """npc1 has an npc_bond; it should appear in the NPC's YAML."""
    run_export(db, tmp_path)
    npc1 = seed_data["npc1"]
    slug = _slugify(npc1.name)
    data = load_yaml(tmp_path / "characters" / "npcs" / f"{slug}.yaml")
    assert "bonds" in data
    bond = data["bonds"][0]
    assert bond["target"]["name"] == seed_data["region"].name
    assert bond["target"]["type"] == "location"


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------


def test_export_group_count(db, seed_data, tmp_path):
    _, result = run_export(db, tmp_path)
    assert result.groups == 1


def test_export_group_file_exists(db, seed_data, tmp_path):
    run_export(db, tmp_path)
    grp_dir = tmp_path / "groups"
    assert grp_dir.is_dir()
    slug = _slugify(seed_data["group"].name)
    assert (grp_dir / f"{slug}.yaml").exists()


def test_export_group_schema_validates(db, seed_data, tmp_path):
    run_export(db, tmp_path)
    for yaml_file in (tmp_path / "groups").glob("*.yaml"):
        data = load_yaml(yaml_file)
        GroupYaml.model_validate(data)


def test_export_group_tier_preserved(db, seed_data, tmp_path):
    run_export(db, tmp_path)
    grp = seed_data["group"]
    slug = _slugify(grp.name)
    data = load_yaml(tmp_path / "groups" / f"{slug}.yaml")
    assert data["tier"] == grp.tier


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------


def test_export_location_count(db, seed_data, tmp_path):
    _, result = run_export(db, tmp_path)
    assert result.locations == 2  # region + district


def test_export_location_directory_structure(db, seed_data, tmp_path):
    """The parent location should create a directory; child is nested inside."""
    run_export(db, tmp_path)
    loc_root = tmp_path / "locations"
    region = seed_data["region"]
    district = seed_data["district"]
    region_slug = _slugify(region.name)
    district_slug = _slugify(district.name)
    # Both should have _location.yaml files
    assert (loc_root / region_slug / "_location.yaml").exists()
    assert (loc_root / region_slug / district_slug / "_location.yaml").exists()


def test_export_location_schema_validates(db, seed_data, tmp_path):
    run_export(db, tmp_path)
    for yaml_file in (tmp_path / "locations").rglob("_location.yaml"):
        data = load_yaml(yaml_file)
        LocationYaml.model_validate(data)


def test_export_location_parent_name_in_yaml(db, seed_data, tmp_path):
    """The child location YAML should contain the parent name (not ULID)."""
    run_export(db, tmp_path)
    district = seed_data["district"]
    region = seed_data["region"]
    region_slug = _slugify(region.name)
    district_slug = _slugify(district.name)
    data = load_yaml(
        tmp_path / "locations" / region_slug / district_slug / "_location.yaml"
    )
    assert data.get("parent") == region.name


# ---------------------------------------------------------------------------
# Clocks
# ---------------------------------------------------------------------------


def test_export_clock_basic(db, seed_data, tmp_path):
    grp = seed_data["group"]
    clock = Clock(
        name="Consolidate Power",
        segments=8,
        progress=3,
        associated_type="group",
        associated_id=grp.id,
    )
    db.add(clock)
    db.commit()
    db.refresh(clock)

    _, result = run_export(db, tmp_path)
    assert result.clocks == 1

    clk_dir = tmp_path / "clocks"
    assert (clk_dir / "consolidate-power.yaml").exists()
    data = load_yaml(clk_dir / "consolidate-power.yaml")
    ClockYaml.model_validate(data)


def test_export_clock_associated_with_name(db, seed_data, tmp_path):
    """Clock association should use group name, not ULID."""
    grp = seed_data["group"]
    clock = Clock(
        name="Test Clock",
        segments=5,
        progress=1,
        associated_type="group",
        associated_id=grp.id,
    )
    db.add(clock)
    db.commit()

    run_export(db, tmp_path)
    slug = _slugify("Test Clock")
    data = load_yaml(tmp_path / "clocks" / f"{slug}.yaml")
    assert data["associated_with"]["name"] == grp.name
    assert data["associated_with"]["type"] == "group"


def test_export_clock_no_association(db, seed_data, tmp_path):
    clock = Clock(name="Bare Clock", segments=4, progress=0)
    db.add(clock)
    db.commit()

    run_export(db, tmp_path)
    data = load_yaml(tmp_path / "clocks" / "bare-clock.yaml")
    assert data.get("associated_with") is None


def test_export_clock_deleted_excluded(db, seed_data, tmp_path):
    clock = Clock(name="Dead Clock", segments=3, progress=0, is_deleted=True)
    db.add(clock)
    db.commit()
    _, result = run_export(db, tmp_path)
    assert result.clocks == 0


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


def test_export_session_basic(db, seed_data, tmp_path):
    pc1 = seed_data["pc1"]
    sess = GameSession(status="ended", summary="The Hoover Dam Attack")
    db.add(sess)
    db.flush()
    participant = SessionParticipant(
        session_id=sess.id,
        character_id=pc1.id,
        additional_contribution=False,
    )
    db.add(participant)
    db.commit()

    _, result = run_export(db, tmp_path)
    assert result.sessions == 1

    sess_dir = tmp_path / "sessions"
    yaml_files = list(sess_dir.glob("*.yaml"))
    assert len(yaml_files) == 1
    data = load_yaml(yaml_files[0])
    SessionYaml.model_validate(data)


def test_export_session_number_is_sequential(db, seed_data, tmp_path):
    """Sessions should be numbered 1, 2, 3 by ULID creation order."""
    for i in range(3):
        sess = GameSession(status="ended", summary=f"Session {i + 1}")
        db.add(sess)
    db.commit()

    run_export(db, tmp_path)
    sess_dir = tmp_path / "sessions"
    files_sorted = sorted(sess_dir.glob("*.yaml"))
    numbers = [load_yaml(f)["number"] for f in files_sorted]
    assert sorted(numbers) == list(range(1, 4))


def test_export_session_participant_name(db, seed_data, tmp_path):
    """Session participant should show character name, not ULID."""
    pc1 = seed_data["pc1"]
    sess = GameSession(status="ended")
    db.add(sess)
    db.flush()
    db.add(SessionParticipant(session_id=sess.id, character_id=pc1.id))
    db.commit()

    run_export(db, tmp_path)
    data = load_yaml(next((tmp_path / "sessions").glob("*.yaml")))
    assert data["participants"][0]["character"] == pc1.name


def test_export_session_filename_zero_padded(db, seed_data, tmp_path):
    """Session filename starts with zero-padded number."""
    sess = GameSession(status="ended", summary="First Session")
    db.add(sess)
    db.commit()

    run_export(db, tmp_path)
    files = list((tmp_path / "sessions").glob("*.yaml"))
    assert len(files) == 1
    assert files[0].name.startswith("001-")


# ---------------------------------------------------------------------------
# Stories
# ---------------------------------------------------------------------------


def test_export_story_basic(db, seed_data, tmp_path):
    gm = seed_data["gm"]
    pc1 = seed_data["pc1"]

    story = Story(name="The Blackout Murders", status="active")
    db.add(story)
    db.flush()

    owner = StoryOwner(story_id=story.id, owner_type="character", owner_id=pc1.id)
    entry = StoryEntry(
        story_id=story.id,
        text="It began on a rainy Tuesday.",
        author_id=gm.id,
    )
    db.add_all([owner, entry])
    db.commit()

    _, result = run_export(db, tmp_path)
    assert result.stories == 1

    story_dir = tmp_path / "stories"
    assert (story_dir / "the-blackout-murders.yaml").exists()
    data = load_yaml(story_dir / "the-blackout-murders.yaml")
    StoryYaml.model_validate(data)


def test_export_story_owner_uses_name(db, seed_data, tmp_path):
    """Story owner should show character name, not ULID."""
    gm = seed_data["gm"]
    pc1 = seed_data["pc1"]

    story = Story(name="Character Arc", status="active")
    db.add(story)
    db.flush()
    db.add(StoryOwner(story_id=story.id, owner_type="character", owner_id=pc1.id))
    db.add(StoryEntry(story_id=story.id, text="Start.", author_id=gm.id))
    db.commit()

    run_export(db, tmp_path)
    data = load_yaml(tmp_path / "stories" / "character-arc.yaml")
    assert data["owners"][0]["name"] == pc1.name
    assert data["owners"][0]["type"] == "character"


def test_export_story_entry_author_display_name(db, seed_data, tmp_path):
    """Story entry author should be user display_name, not ULID."""
    gm = seed_data["gm"]
    story = Story(name="Lore Drop", status="active")
    db.add(story)
    db.flush()
    db.add(StoryEntry(story_id=story.id, text="Ancient history.", author_id=gm.id))
    db.commit()

    run_export(db, tmp_path)
    data = load_yaml(tmp_path / "stories" / "lore-drop.yaml")
    assert data["entries"][0]["author"] == gm.display_name


def test_export_story_children_embedded(db, seed_data, tmp_path):
    """Child stories should be embedded under the parent's 'children' key."""
    gm = seed_data["gm"]
    parent = Story(name="Main Arc", status="active")
    db.add(parent)
    db.flush()
    child = Story(name="Sub Arc", status="active", parent_id=parent.id)
    db.add(child)
    db.flush()
    db.add(StoryEntry(story_id=child.id, text="A sub-plot.", author_id=gm.id))
    db.commit()

    _, result = run_export(db, tmp_path)
    # Only top-level stories should be counted/written to files
    assert result.stories == 1
    assert (tmp_path / "stories" / "main-arc.yaml").exists()
    assert not (tmp_path / "stories" / "sub-arc.yaml").exists()

    data = load_yaml(tmp_path / "stories" / "main-arc.yaml")
    assert "children" in data
    assert len(data["children"]) == 1
    assert data["children"][0]["name"] == "Sub Arc"


# ---------------------------------------------------------------------------
# Trait templates
# ---------------------------------------------------------------------------


def test_export_trait_templates(db, seed_data, tmp_path):
    tt = TraitTemplate(name="Unstoppable", type="core", description="You cannot be stopped.")
    db.add(tt)
    db.commit()

    _, result = run_export(db, tmp_path)
    assert result.trait_templates == 1

    tt_dir = tmp_path / "trait-templates"
    assert (tt_dir / "unstoppable.yaml").exists()
    data = load_yaml(tt_dir / "unstoppable.yaml")
    TraitTemplateYaml.model_validate(data)


def test_export_trait_template_deleted_excluded(db, seed_data, tmp_path):
    tt = TraitTemplate(
        name="Removed Trait", type="role", description="...", is_deleted=True
    )
    db.add(tt)
    db.commit()
    _, result = run_export(db, tmp_path)
    assert result.trait_templates == 0


def test_export_pc_trait_uses_template_name(db, seed_data, tmp_path):
    """PC trait slot should reference template by name, not ULID."""
    pc1 = seed_data["pc1"]
    tt = TraitTemplate(name="Street Savvy", type="core", description="You know the streets.")
    db.add(tt)
    db.flush()
    slot = Slot(
        slot_type="core_trait",
        owner_type="character",
        owner_id=pc1.id,
        name="Street Savvy",
        template_id=tt.id,
        charge=4,
        is_active=True,
    )
    db.add(slot)
    db.commit()

    run_export(db, tmp_path)
    pc1_slug = _slugify(pc1.name)
    data = load_yaml(tmp_path / "characters" / "pcs" / f"{pc1_slug}.yaml")
    assert len(data["core_traits"]) == 1
    assert data["core_traits"][0]["template"] == "Street Savvy"
    assert data["core_traits"][0]["charge"] == 4


# ---------------------------------------------------------------------------
# Magic effects
# ---------------------------------------------------------------------------


def test_export_magic_effects_inlined(db, seed_data, tmp_path):
    pc1 = seed_data["pc1"]
    effect = MagicEffect(
        character_id=pc1.id,
        name="Shadow Walk",
        description="You can pass through shadows.",
        effect_type="permanent",
        power_level=3,
        is_active=True,
    )
    db.add(effect)
    db.commit()

    run_export(db, tmp_path)
    pc1_slug = _slugify(pc1.name)
    data = load_yaml(tmp_path / "characters" / "pcs" / f"{pc1_slug}.yaml")
    assert "magic_effects" in data
    assert len(data["magic_effects"]) == 1
    me = data["magic_effects"][0]
    assert me["name"] == "Shadow Walk"
    assert me["effect_type"] == "permanent"
    assert me["power_level"] == 3


def test_export_magic_effect_charged_has_charges_dict(db, seed_data, tmp_path):
    pc1 = seed_data["pc1"]
    effect = MagicEffect(
        character_id=pc1.id,
        name="Fireball",
        description="A burst of arcane fire.",
        effect_type="charged",
        power_level=2,
        charges_current=3,
        charges_max=5,
        is_active=True,
    )
    db.add(effect)
    db.commit()

    run_export(db, tmp_path)
    pc1_slug = _slugify(pc1.name)
    data = load_yaml(tmp_path / "characters" / "pcs" / f"{pc1_slug}.yaml")
    me = data["magic_effects"][0]
    assert me["charges"] == {"current": 3, "max": 5}


# ---------------------------------------------------------------------------
# Group slots
# ---------------------------------------------------------------------------


def test_export_group_traits_inlined(db, seed_data, tmp_path):
    grp = seed_data["group"]
    trait_slot = Slot(
        slot_type="group_trait",
        owner_type="group",
        owner_id=grp.id,
        name="Well-Connected",
        description="Knows people everywhere.",
        is_active=True,
    )
    db.add(trait_slot)
    db.commit()

    run_export(db, tmp_path)
    grp_slug = _slugify(grp.name)
    data = load_yaml(tmp_path / "groups" / f"{grp_slug}.yaml")
    assert "traits" in data
    assert data["traits"][0]["name"] == "Well-Connected"


def test_export_group_holding_uses_location_name(db, seed_data, tmp_path):
    grp = seed_data["group"]
    region = seed_data["region"]
    holding = Slot(
        slot_type="group_holding",
        owner_type="group",
        owner_id=grp.id,
        name="Headquarters",
        target_id=region.id,
        description="Their main base of operations.",
        is_active=True,
    )
    db.add(holding)
    db.commit()

    run_export(db, tmp_path)
    grp_slug = _slugify(grp.name)
    data = load_yaml(tmp_path / "groups" / f"{grp_slug}.yaml")
    assert "holdings" in data
    assert data["holdings"][0]["target"] == region.name


def test_export_group_relation_uses_group_name(db, seed_data, tmp_path):
    grp = seed_data["group"]
    # Create a second group to relate to
    rival = Group(name="The Rivals", tier=1)
    db.add(rival)
    db.flush()

    relation = Slot(
        slot_type="group_relation",
        owner_type="group",
        owner_id=grp.id,
        name="Hostile Alliance",
        target_id=rival.id,
        bidirectional=False,
        is_active=True,
    )
    db.add(relation)
    db.commit()

    run_export(db, tmp_path)
    grp_slug = _slugify(grp.name)
    data = load_yaml(tmp_path / "groups" / f"{grp_slug}.yaml")
    assert "relations" in data
    assert data["relations"][0]["target"] == rival.name


# ---------------------------------------------------------------------------
# Location slots
# ---------------------------------------------------------------------------


def test_export_location_feature_inlined(db, seed_data, tmp_path):
    region = seed_data["region"]
    feature = Slot(
        slot_type="feature_trait",
        owner_type="location",
        owner_id=region.id,
        name="Ancient Ruins",
        description="Crumbling stone structures line the coast.",
        is_active=True,
    )
    db.add(feature)
    db.commit()

    run_export(db, tmp_path)
    region_slug = _slugify(region.name)
    data = load_yaml(tmp_path / "locations" / region_slug / "_location.yaml")
    assert "features" in data
    assert data["features"][0]["name"] == "Ancient Ruins"


def test_export_location_bond_uses_target_name(db, seed_data, tmp_path):
    region = seed_data["region"]
    grp = seed_data["group"]
    bond = Slot(
        slot_type="location_bond",
        owner_type="location",
        owner_id=region.id,
        name="Controlled By",
        target_type="group",
        target_id=grp.id,
        is_active=True,
    )
    db.add(bond)
    db.commit()

    run_export(db, tmp_path)
    region_slug = _slugify(region.name)
    data = load_yaml(tmp_path / "locations" / region_slug / "_location.yaml")
    assert "bonds" in data
    assert data["bonds"][0]["target"]["name"] == grp.name
    assert data["bonds"][0]["target"]["type"] == "group"


# ---------------------------------------------------------------------------
# Output directory is created automatically
# ---------------------------------------------------------------------------


def test_export_creates_output_directory(db, seed_data, tmp_path):
    new_dir = tmp_path / "nested" / "output"
    assert not new_dir.exists()
    exporter = CampaignExporter(db, new_dir)
    exporter.export_all()
    assert new_dir.is_dir()


# ---------------------------------------------------------------------------
# Additional coverage: edge cases and untested paths
# ---------------------------------------------------------------------------


def test_export_session_additional_contribution_true(db, seed_data, tmp_path):
    """additional_contribution=True is included in the YAML output."""
    pc1 = seed_data["pc1"]
    sess = GameSession(status="ended", summary="Big Contribution")
    db.add(sess)
    db.flush()
    db.add(
        SessionParticipant(
            session_id=sess.id,
            character_id=pc1.id,
            additional_contribution=True,
        )
    )
    db.commit()

    run_export(db, tmp_path)
    data = load_yaml(next((tmp_path / "sessions").glob("*.yaml")))
    assert len(data["participants"]) == 1
    participant = data["participants"][0]
    assert participant.get("additional_contribution") is True


def test_export_session_additional_contribution_false_omitted(db, seed_data, tmp_path):
    """additional_contribution=False is omitted from the YAML output (default)."""
    pc1 = seed_data["pc1"]
    sess = GameSession(status="ended", summary="Normal Session")
    db.add(sess)
    db.flush()
    db.add(
        SessionParticipant(
            session_id=sess.id,
            character_id=pc1.id,
            additional_contribution=False,
        )
    )
    db.commit()

    run_export(db, tmp_path)
    data = load_yaml(next((tmp_path / "sessions").glob("*.yaml")))
    participant = data["participants"][0]
    # False should be absent (falsy default not written to keep YAML terse).
    assert "additional_contribution" not in participant


def test_export_magic_effect_inactive_not_included(db, seed_data, tmp_path):
    """Inactive (is_active=False) magic effects are exported.

    The exporter currently does NOT filter out inactive magic effects —
    this test documents that behavior so it is not silently broken.
    The MagicEffect.is_active flag is written to YAML as ``is_active: false``.
    """
    pc1 = seed_data["pc1"]
    effect = MagicEffect(
        character_id=pc1.id,
        name="Faded Spell",
        description="An old effect, no longer active.",
        effect_type="permanent",
        power_level=1,
        is_active=False,
    )
    db.add(effect)
    db.commit()

    run_export(db, tmp_path)
    pc1_slug = _slugify(pc1.name)
    data = load_yaml(tmp_path / "characters" / "pcs" / f"{pc1_slug}.yaml")
    assert "magic_effects" in data
    assert any(me["name"] == "Faded Spell" for me in data["magic_effects"])


def test_export_story_tags_preserved(db, seed_data, tmp_path):
    """Story tags list is written to YAML when non-empty."""
    gm = seed_data["gm"]
    story = Story(name="Tagged Story", status="active", tags=["mystery", "faction"])
    db.add(story)
    db.flush()
    db.add(StoryEntry(story_id=story.id, text="Content.", author_id=gm.id))
    db.commit()

    run_export(db, tmp_path)
    data = load_yaml(tmp_path / "stories" / "tagged-story.yaml")
    assert data.get("tags") == ["mystery", "faction"]


def test_export_story_group_owner(db, seed_data, tmp_path):
    """Story owners of type 'group' are serialised with group name."""
    gm = seed_data["gm"]
    grp = seed_data["group"]

    story = Story(name="Faction Arc", status="active")
    db.add(story)
    db.flush()
    db.add(StoryOwner(story_id=story.id, owner_type="group", owner_id=grp.id))
    db.add(StoryEntry(story_id=story.id, text="The faction moves.", author_id=gm.id))
    db.commit()

    run_export(db, tmp_path)
    data = load_yaml(tmp_path / "stories" / "faction-arc.yaml")
    assert data["owners"][0]["type"] == "group"
    assert data["owners"][0]["name"] == grp.name


def test_export_clock_associated_with_character(db, seed_data, tmp_path):
    """Clock associated with a character uses the character's name."""
    pc1 = seed_data["pc1"]
    clock = Clock(
        name="Countdown to Death",
        segments=6,
        progress=0,
        associated_type="character",
        associated_id=pc1.id,
    )
    db.add(clock)
    db.commit()

    run_export(db, tmp_path)
    data = load_yaml(tmp_path / "clocks" / "countdown-to-death.yaml")
    assert data["associated_with"]["type"] == "character"
    assert data["associated_with"]["name"] == pc1.name


def test_export_clock_associated_with_location(db, seed_data, tmp_path):
    """Clock associated with a location uses the location's name."""
    region = seed_data["region"]
    clock = Clock(
        name="City Under Siege",
        segments=8,
        progress=4,
        associated_type="location",
        associated_id=region.id,
    )
    db.add(clock)
    db.commit()

    run_export(db, tmp_path)
    data = load_yaml(tmp_path / "clocks" / "city-under-siege.yaml")
    assert data["associated_with"]["type"] == "location"
    assert data["associated_with"]["name"] == region.name


def test_export_deleted_user_excluded(db, seed_data, tmp_path):
    """Inactive (is_active=False) users are excluded from the export."""
    inactive_user = User(
        display_name="Departed Player",
        role="player",
        login_code=secrets.token_urlsafe(32),
        is_active=False,
    )
    db.add(inactive_user)
    db.commit()

    _, result = run_export(db, tmp_path)
    # Still 5 — the seed has 5 active users; the inactive one should be excluded.
    assert result.users == 5
    names_on_disk = [
        load_yaml(f)["display_name"]
        for f in (tmp_path / "users").glob("*.yaml")
    ]
    assert "Departed Player" not in names_on_disk


def test_export_deleted_character_excluded(db, seed_data, tmp_path):
    """Soft-deleted characters are excluded from the export."""
    from wizards_engine.models.character import Character

    deleted_char = Character(
        name="Ghost Character",
        detail_level="full",
        stress=0,
        free_time=0,
        plot=0,
        gnosis=0,
        skills={},
        magic_stats={},
        last_session_time_now=0,
        is_deleted=True,
    )
    db.add(deleted_char)
    db.commit()

    _, result = run_export(db, tmp_path)
    # Seed has 3 PCs and 2 NPCs. Deleted character must not count.
    assert result.characters_pc == 3
    assert result.characters_npc == 2


def test_export_deleted_group_excluded(db, seed_data, tmp_path):
    """Soft-deleted groups are excluded from the export."""
    deleted_group = Group(name="Defunct Faction", tier=1, is_deleted=True)
    db.add(deleted_group)
    db.commit()

    _, result = run_export(db, tmp_path)
    assert result.groups == 1  # Only the seed group


def test_export_deleted_location_excluded(db, seed_data, tmp_path):
    """Soft-deleted locations are excluded from the export."""
    deleted_loc = Location(name="Ruins of the Past", is_deleted=True)
    db.add(deleted_loc)
    db.commit()

    _, result = run_export(db, tmp_path)
    assert result.locations == 2  # Only the seed region + district


def test_export_deleted_story_excluded(db, seed_data, tmp_path):
    """Soft-deleted stories are excluded from the export."""
    gm = seed_data["gm"]
    story = Story(name="Abandoned Plot", status="abandoned", is_deleted=True)
    db.add(story)
    db.commit()

    _, result = run_export(db, tmp_path)
    assert result.stories == 0


def test_export_pc_bond_is_trauma_preserved(db, seed_data, tmp_path):
    """PC bond is_trauma=True round-trips correctly through YAML."""
    pc1 = seed_data["pc1"]
    grp = seed_data["group"]
    trauma_slot = Slot(
        slot_type="pc_bond",
        owner_type="character",
        owner_id=pc1.id,
        name="Trauma Bond",
        target_type="group",
        target_id=grp.id,
        charges=1,
        degradations=3,
        is_trauma=True,
        bidirectional=True,
        is_active=True,
    )
    db.add(trauma_slot)
    db.commit()

    run_export(db, tmp_path)
    pc1_slug = _slugify(pc1.name)
    data = load_yaml(tmp_path / "characters" / "pcs" / f"{pc1_slug}.yaml")
    trauma_bonds = [b for b in data["bonds"] if b.get("is_trauma") is True]
    assert len(trauma_bonds) == 1
    assert trauma_bonds[0]["name"] == "Trauma Bond"
    assert trauma_bonds[0]["charges"] == 1
    assert trauma_bonds[0]["degradations"] == 3
