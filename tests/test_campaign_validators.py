"""Tests for two-pass campaign validation (Story 7.1.2).

Creates minimal YAML campaign directories in tmp_path and exercises:
- Pass 1: schema validation (valid files pass, invalid files produce errors)
- Pass 2: reference validation (all cross-reference checks)
- Happy path: a complete self-consistent campaign directory
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from wizards_engine.campaign.validators import ValidationFinding, validate_campaign


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def write_yaml(path: Path, data: object) -> None:
    """Write a Python object as YAML to ``path``, creating parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        yaml.dump(data, fh, allow_unicode=True, default_flow_style=False)


def make_minimal_campaign(base: Path) -> None:
    """Scaffold a valid minimal campaign in ``base``.

    Entities:
    - 1 trait template (core): "Iron Will"
    - 1 location: "Las Vegas"
    - 1 PC character: "Alexander" with 1 core trait + 1 bond → Las Vegas
    - 1 NPC character: "The Owner"
    - 1 group: "Moloch Society" with 1 relation + 1 holding
    - 1 clock with association → character "Alexander"
    - 1 user (GM, no character)
    - 1 user (player) → "Alexander"
    - 1 session with participant "Alexander"
    - 1 story with owner "Alexander", 1 entry by "GM"
    """
    write_yaml(base / "meta.yaml", {
        "engine_version": "1.0.0",
        "campaign_name": "Test Campaign",
        "format_version": 1,
    })

    write_yaml(base / "trait-templates" / "iron-will.yaml", {
        "name": "Iron Will",
        "type": "core",
        "description": "Unbreakable resolve.",
    })

    write_yaml(base / "locations" / "las-vegas" / "_location.yaml", {
        "name": "Las Vegas",
        "description": "The city.",
    })

    write_yaml(base / "characters" / "pcs" / "alexander.yaml", {
        "name": "Alexander",
        "detail_level": "full",
        "core_traits": [{"template": "Iron Will", "charge": 5}],
        "bonds": [{"name": "Tied to the City", "target": {"type": "location", "name": "Las Vegas"}}],
    })

    write_yaml(base / "characters" / "npcs" / "the-owner.yaml", {
        "name": "The Owner",
        "detail_level": "simplified",
    })

    write_yaml(base / "groups" / "moloch-society.yaml", {
        "name": "Moloch Society",
        "tier": 3,
        "relations": [{"name": "Enemy", "target": "Moloch Society"}],
        "holdings": [{"name": "HQ", "target": "Las Vegas"}],
    })

    write_yaml(base / "clocks" / "consolidate-power.yaml", {
        "name": "Consolidate Power",
        "segments": 8,
        "progress": 3,
        "associated_with": {"type": "character", "name": "Alexander"},
    })

    write_yaml(base / "users" / "gm.yaml", {
        "display_name": "GM",
        "role": "gm",
    })

    write_yaml(base / "users" / "player-alice.yaml", {
        "display_name": "Alice",
        "role": "player",
        "character": "Alexander",
    })

    write_yaml(base / "sessions" / "001-first-session.yaml", {
        "number": 1,
        "status": "ended",
        "participants": [{"character": "Alexander"}],
    })

    write_yaml(base / "stories" / "blackout-murders.yaml", {
        "name": "Blackout Murders",
        "status": "active",
        "owners": [{"type": "character", "name": "Alexander"}],
        "entries": [{
            "text": "It began with a murder.",
            "author": "GM",
            "character": "Alexander",
            "session": 1,
        }],
    })


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_valid_campaign_returns_no_errors(self, tmp_path):
        make_minimal_campaign(tmp_path)
        errors = validate_campaign(tmp_path)
        assert errors == [], [str(e) for e in errors]

    def test_empty_directory_returns_no_errors(self, tmp_path):
        """An empty campaign dir is technically valid (nothing to import)."""
        errors = validate_campaign(tmp_path)
        assert errors == []

    def test_returns_list(self, tmp_path):
        errors = validate_campaign(tmp_path)
        assert isinstance(errors, list)


# ---------------------------------------------------------------------------
# Pass 1 — schema validation
# ---------------------------------------------------------------------------


class TestSchemaValidation:
    def test_invalid_meta_yaml_field(self, tmp_path):
        write_yaml(tmp_path / "meta.yaml", {
            "engine_version": "1.0.0",
            # missing campaign_name
        })
        errors = validate_campaign(tmp_path)
        assert len(errors) > 0
        assert any(e.file_path == "meta.yaml" for e in errors)

    def test_invalid_trait_template_type(self, tmp_path):
        write_yaml(tmp_path / "trait-templates" / "bad.yaml", {
            "name": "Bad Trait",
            "type": "legendary",  # invalid
            "description": "Oops.",
        })
        errors = validate_campaign(tmp_path)
        assert len(errors) > 0
        assert any("trait-templates" in e.file_path for e in errors)

    def test_invalid_pc_character_detail_level(self, tmp_path):
        write_yaml(tmp_path / "characters" / "pcs" / "bad.yaml", {
            "name": "Bad PC",
            "detail_level": "simplified",  # wrong for PCs
        })
        errors = validate_campaign(tmp_path)
        assert len(errors) > 0

    def test_invalid_npc_character_detail_level(self, tmp_path):
        write_yaml(tmp_path / "characters" / "npcs" / "bad.yaml", {
            "name": "Bad NPC",
            "detail_level": "full",  # wrong for NPCs
        })
        errors = validate_campaign(tmp_path)
        assert len(errors) > 0

    def test_invalid_session_status(self, tmp_path):
        write_yaml(tmp_path / "sessions" / "001-bad.yaml", {
            "number": 1,
            "status": "ongoing",  # invalid
        })
        errors = validate_campaign(tmp_path)
        assert len(errors) > 0

    def test_invalid_story_status(self, tmp_path):
        write_yaml(tmp_path / "stories" / "bad.yaml", {
            "name": "Bad Story",
            "status": "forgotten",  # invalid
        })
        errors = validate_campaign(tmp_path)
        assert len(errors) > 0

    def test_invalid_user_role(self, tmp_path):
        write_yaml(tmp_path / "users" / "bad.yaml", {
            "display_name": "Baddie",
            "role": "observer",  # invalid
        })
        errors = validate_campaign(tmp_path)
        assert len(errors) > 0

    def test_invalid_clock_segments_zero(self, tmp_path):
        write_yaml(tmp_path / "clocks" / "bad.yaml", {
            "name": "Dead Clock",
            "segments": 0,  # must be >= 1
            "progress": 0,
        })
        errors = validate_campaign(tmp_path)
        assert len(errors) > 0

    def test_multiple_schema_errors_collected(self, tmp_path):
        """Pass 1 collects all errors, not just the first one."""
        write_yaml(tmp_path / "sessions" / "001-bad.yaml", {
            "number": 1,
            "status": "ongoing",
        })
        write_yaml(tmp_path / "users" / "bad.yaml", {
            "display_name": "X",
            "role": "observer",
        })
        errors = validate_campaign(tmp_path)
        assert len(errors) >= 2

    def test_yaml_parse_error_reported(self, tmp_path):
        bad = tmp_path / "groups" / "corrupt.yaml"
        bad.parent.mkdir(parents=True, exist_ok=True)
        bad.write_text("name: [unclosed bracket\n", encoding="utf-8")
        errors = validate_campaign(tmp_path)
        assert len(errors) > 0
        assert any("YAML parse error" in e.error_message for e in errors)

    def test_error_has_file_path(self, tmp_path):
        write_yaml(tmp_path / "users" / "bad.yaml", {
            "display_name": "X",
            "role": "observer",
        })
        errors = validate_campaign(tmp_path)
        assert all(e.file_path for e in errors)

    def test_schema_error_has_field(self, tmp_path):
        # Missing required field 'campaign_name' produces a field-level error
        # with a non-empty field path from Pydantic.
        write_yaml(tmp_path / "meta.yaml", {
            "engine_version": "1.0.0",
            # campaign_name deliberately omitted
        })
        errors = validate_campaign(tmp_path)
        assert any(e.field for e in errors)


# ---------------------------------------------------------------------------
# Pass 2 — reference validation
# ---------------------------------------------------------------------------


class TestReferenceValidation:
    def test_bond_target_missing_character(self, tmp_path):
        write_yaml(tmp_path / "characters" / "pcs" / "alice.yaml", {
            "name": "Alice",
            "detail_level": "full",
            "bonds": [{"name": "Friend", "target": {"type": "character", "name": "Ghost"}}],
        })
        errors = validate_campaign(tmp_path)
        assert len(errors) > 0
        assert any("Ghost" in e.error_message for e in errors)

    def test_bond_target_missing_group(self, tmp_path):
        write_yaml(tmp_path / "characters" / "pcs" / "alice.yaml", {
            "name": "Alice",
            "detail_level": "full",
            "bonds": [{"name": "Member", "target": {"type": "group", "name": "Phantom Org"}}],
        })
        errors = validate_campaign(tmp_path)
        assert any("Phantom Org" in e.error_message for e in errors)

    def test_bond_target_missing_location(self, tmp_path):
        write_yaml(tmp_path / "characters" / "pcs" / "alice.yaml", {
            "name": "Alice",
            "detail_level": "full",
            "bonds": [{"name": "Home", "target": {"type": "location", "name": "Nowhere"}}],
        })
        errors = validate_campaign(tmp_path)
        assert any("Nowhere" in e.error_message for e in errors)

    def test_trait_template_ref_missing(self, tmp_path):
        write_yaml(tmp_path / "characters" / "pcs" / "alice.yaml", {
            "name": "Alice",
            "detail_level": "full",
            "core_traits": [{"template": "Ghost Template"}],
        })
        errors = validate_campaign(tmp_path)
        assert any("Ghost Template" in e.error_message for e in errors)

    def test_user_character_ref_missing(self, tmp_path):
        write_yaml(tmp_path / "users" / "player.yaml", {
            "display_name": "Bob",
            "role": "player",
            "character": "NonExistent",
        })
        errors = validate_campaign(tmp_path)
        assert any("NonExistent" in e.error_message for e in errors)

    def test_session_participant_missing(self, tmp_path):
        write_yaml(tmp_path / "sessions" / "001-session.yaml", {
            "number": 1,
            "status": "ended",
            "participants": [{"character": "Ghost"}],
        })
        errors = validate_campaign(tmp_path)
        assert any("Ghost" in e.error_message for e in errors)

    def test_story_owner_missing(self, tmp_path):
        write_yaml(tmp_path / "users" / "gm.yaml", {
            "display_name": "GM",
            "role": "gm",
        })
        write_yaml(tmp_path / "stories" / "arc.yaml", {
            "name": "Arc",
            "status": "active",
            "owners": [{"type": "character", "name": "Nobody"}],
            "entries": [],
        })
        errors = validate_campaign(tmp_path)
        assert any("Nobody" in e.error_message for e in errors)

    def test_story_entry_author_missing(self, tmp_path):
        write_yaml(tmp_path / "stories" / "arc.yaml", {
            "name": "Arc",
            "status": "active",
            "owners": [],
            "entries": [{
                "text": "Entry text.",
                "author": "UnknownAuthor",
            }],
        })
        errors = validate_campaign(tmp_path)
        assert any("UnknownAuthor" in e.error_message for e in errors)

    def test_story_entry_character_missing(self, tmp_path):
        write_yaml(tmp_path / "users" / "gm.yaml", {
            "display_name": "GM",
            "role": "gm",
        })
        write_yaml(tmp_path / "stories" / "arc.yaml", {
            "name": "Arc",
            "status": "active",
            "owners": [],
            "entries": [{
                "text": "Entry text.",
                "author": "GM",
                "character": "NoChar",
            }],
        })
        errors = validate_campaign(tmp_path)
        assert any("NoChar" in e.error_message for e in errors)

    def test_story_entry_session_missing(self, tmp_path):
        write_yaml(tmp_path / "users" / "gm.yaml", {
            "display_name": "GM",
            "role": "gm",
        })
        write_yaml(tmp_path / "stories" / "arc.yaml", {
            "name": "Arc",
            "status": "active",
            "owners": [],
            "entries": [{
                "text": "Entry text.",
                "author": "GM",
                "session": 99,
            }],
        })
        errors = validate_campaign(tmp_path)
        assert any("99" in e.error_message for e in errors)

    def test_clock_association_missing(self, tmp_path):
        write_yaml(tmp_path / "clocks" / "rising-tide.yaml", {
            "name": "Rising Tide",
            "segments": 4,
            "progress": 1,
            "associated_with": {"type": "group", "name": "No Group"},
        })
        errors = validate_campaign(tmp_path)
        assert any("No Group" in e.error_message for e in errors)

    def test_location_parent_missing(self, tmp_path):
        write_yaml(tmp_path / "locations" / "child" / "_location.yaml", {
            "name": "Child Location",
            "parent": "Nonexistent Parent",
        })
        errors = validate_campaign(tmp_path)
        assert any("Nonexistent Parent" in e.error_message for e in errors)

    def test_group_relation_target_missing(self, tmp_path):
        write_yaml(tmp_path / "groups" / "alpha.yaml", {
            "name": "Alpha",
            "tier": 1,
            "relations": [{"name": "Rivalry", "target": "Beta"}],
        })
        errors = validate_campaign(tmp_path)
        assert any("Beta" in e.error_message for e in errors)

    def test_group_holding_target_missing(self, tmp_path):
        write_yaml(tmp_path / "groups" / "alpha.yaml", {
            "name": "Alpha",
            "tier": 1,
            "holdings": [{"name": "Base", "target": "Phantom HQ"}],
        })
        errors = validate_campaign(tmp_path)
        assert any("Phantom HQ" in e.error_message for e in errors)

    def test_npc_bond_target_missing(self, tmp_path):
        write_yaml(tmp_path / "characters" / "npcs" / "npc.yaml", {
            "name": "The NPC",
            "detail_level": "simplified",
            "bonds": [{"name": "Ally", "target": {"type": "character", "name": "Nobody"}}],
        })
        errors = validate_campaign(tmp_path)
        assert any("Nobody" in e.error_message for e in errors)

    def test_duplicate_character_names(self, tmp_path):
        write_yaml(tmp_path / "characters" / "pcs" / "alice.yaml", {
            "name": "Alice",
            "detail_level": "full",
        })
        write_yaml(tmp_path / "characters" / "npcs" / "alice-npc.yaml", {
            "name": "Alice",  # duplicate across subdirs
            "detail_level": "simplified",
        })
        errors = validate_campaign(tmp_path)
        assert any("Alice" in e.error_message for e in errors)

    def test_duplicate_location_names(self, tmp_path):
        write_yaml(tmp_path / "locations" / "loc-a" / "_location.yaml", {
            "name": "Downtown",
        })
        write_yaml(tmp_path / "locations" / "loc-b" / "_location.yaml", {
            "name": "Downtown",  # duplicate
        })
        errors = validate_campaign(tmp_path)
        assert any("Downtown" in e.error_message for e in errors)

    def test_duplicate_group_names(self, tmp_path):
        write_yaml(tmp_path / "groups" / "alpha-1.yaml", {
            "name": "Alpha",
            "tier": 1,
        })
        write_yaml(tmp_path / "groups" / "alpha-2.yaml", {
            "name": "Alpha",
            "tier": 2,
        })
        errors = validate_campaign(tmp_path)
        assert any("Alpha" in e.error_message for e in errors)

    def test_story_child_entry_author_missing(self, tmp_path):
        """Reference validation recurses into story children."""
        write_yaml(tmp_path / "stories" / "arc.yaml", {
            "name": "Arc",
            "status": "active",
            "owners": [],
            "entries": [],
            "children": [{
                "name": "Sub Arc",
                "status": "active",
                "owners": [],
                "entries": [{
                    "text": "Child entry.",
                    "author": "ChildAuthor",
                }],
            }],
        })
        errors = validate_campaign(tmp_path)
        assert any("ChildAuthor" in e.error_message for e in errors)

    def test_pass2_skipped_when_pass1_has_errors(self, tmp_path):
        """If schema errors exist, reference errors are NOT reported."""
        # Schema error: bad user role
        write_yaml(tmp_path / "users" / "bad.yaml", {
            "display_name": "X",
            "role": "observer",
        })
        # Reference error: bond to non-existent character
        write_yaml(tmp_path / "characters" / "pcs" / "alice.yaml", {
            "name": "Alice",
            "detail_level": "full",
            "bonds": [{"name": "Link", "target": {"type": "character", "name": "Ghost"}}],
        })
        errors = validate_campaign(tmp_path)
        # We must have errors (from pass 1) but none should mention "Ghost"
        assert len(errors) > 0
        assert not any("Ghost" in e.error_message for e in errors)

    def test_error_dataclass_fields(self, tmp_path):
        write_yaml(tmp_path / "users" / "bad.yaml", {
            "display_name": "X",
            "role": "observer",
        })
        errors = validate_campaign(tmp_path)
        err = errors[0]
        assert isinstance(err, ValidationFinding)
        assert hasattr(err, "file_path")
        assert hasattr(err, "field")
        assert hasattr(err, "error_message")

    def test_role_trait_template_ref_missing(self, tmp_path):
        """Pass 2 catches missing trait template for a role_trait slot."""
        write_yaml(tmp_path / "characters" / "pcs" / "alice.yaml", {
            "name": "Alice",
            "detail_level": "full",
            "role_traits": [{"template": "Phantom Role Trait"}],
        })
        errors = validate_campaign(tmp_path)
        assert any("Phantom Role Trait" in e.error_message for e in errors)

    def test_location_bond_target_missing(self, tmp_path):
        """Pass 2 catches a location bond whose target does not exist."""
        write_yaml(tmp_path / "locations" / "downtown" / "_location.yaml", {
            "name": "Downtown",
            "bonds": [{"name": "Linked", "target": {"type": "character", "name": "Ghost"}}],
        })
        errors = validate_campaign(tmp_path)
        assert any("Ghost" in e.error_message for e in errors)

    def test_duplicate_trait_template_names(self, tmp_path):
        """Pass 2 catches duplicate trait template names across files."""
        write_yaml(tmp_path / "trait-templates" / "iron-will-a.yaml", {
            "name": "Iron Will",
            "type": "core",
            "description": "First copy.",
        })
        write_yaml(tmp_path / "trait-templates" / "iron-will-b.yaml", {
            "name": "Iron Will",
            "type": "core",
            "description": "Second copy.",
        })
        errors = validate_campaign(tmp_path)
        assert any("Iron Will" in e.error_message for e in errors)

    def test_duplicate_story_names(self, tmp_path):
        """Pass 2 catches duplicate story names across files."""
        write_yaml(tmp_path / "stories" / "arc-a.yaml", {
            "name": "The Heist",
            "status": "active",
            "owners": [],
            "entries": [],
        })
        write_yaml(tmp_path / "stories" / "arc-b.yaml", {
            "name": "The Heist",
            "status": "active",
            "owners": [],
            "entries": [],
        })
        errors = validate_campaign(tmp_path)
        assert any("The Heist" in e.error_message for e in errors)

    def test_circular_location_parents(self, tmp_path):
        """Pass 2 detects a circular parent chain in locations."""
        # A → parent B, B → parent A (cycle)
        write_yaml(tmp_path / "locations" / "loc-a" / "_location.yaml", {
            "name": "Location A",
            "parent": "Location B",
        })
        write_yaml(tmp_path / "locations" / "loc-b" / "_location.yaml", {
            "name": "Location B",
            "parent": "Location A",
        })
        errors = validate_campaign(tmp_path)
        assert len(errors) > 0
        assert any("Cycle" in e.error_message or "cycle" in e.error_message for e in errors)
