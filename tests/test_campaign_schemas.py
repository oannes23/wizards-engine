"""Tests for campaign YAML schema validation (Story 7.1.1).

Covers valid and invalid inputs for all Pydantic models in
``wizards_engine.campaign.schemas``.  Each test round-trips through
``model_validate`` (simulating what the importer does after
``yaml.safe_load``).

Also covers ``wizards_engine.campaign.ordering`` — import-phase constants
and the location topological sort.
"""

import pytest
from pydantic import ValidationError

from wizards_engine.campaign.ordering import (
    IMPORT_PHASES,
    PHASE_1,
    PHASE_2,
    PHASE_3,
    PHASE_4,
    PHASE_5,
    PHASE_6,
    topological_sort_locations,
)
from wizards_engine.campaign.schemas import (
    CampaignMeta,
    ClockYaml,
    GroupHoldingYaml,
    GroupRelationYaml,
    GroupTraitYaml,
    GroupYaml,
    LocationBondYaml,
    LocationFeatureYaml,
    LocationYaml,
    MagicEffectYaml,
    NPCBondYaml,
    NPCCharacterYaml,
    PCBondYaml,
    PCCharacterYaml,
    PCTraitYaml,
    SessionParticipantYaml,
    SessionYaml,
    StoryEntryYaml,
    StoryOwnerYaml,
    StoryYaml,
    TargetRef,
    TraitTemplateYaml,
    UserYaml,
)


# ---------------------------------------------------------------------------
# TargetRef
# ---------------------------------------------------------------------------


class TestTargetRef:
    def test_valid_character_ref(self):
        ref = TargetRef.model_validate({"type": "character", "name": "Alexander"})
        assert ref.type == "character"
        assert ref.name == "Alexander"

    def test_valid_group_ref(self):
        ref = TargetRef.model_validate({"type": "group", "name": "The Syndicate"})
        assert ref.type == "group"

    def test_valid_location_ref(self):
        ref = TargetRef.model_validate({"type": "location", "name": "Las Vegas"})
        assert ref.type == "location"

    def test_invalid_type_rejected(self):
        with pytest.raises(ValidationError, match="type must be one of"):
            TargetRef.model_validate({"type": "faction", "name": "Bad"})

    def test_missing_name_rejected(self):
        with pytest.raises(ValidationError):
            TargetRef.model_validate({"type": "character"})


# ---------------------------------------------------------------------------
# CampaignMeta
# ---------------------------------------------------------------------------


class TestCampaignMeta:
    def test_valid_meta(self):
        meta = CampaignMeta.model_validate(
            {"engine_version": "0.1.0", "campaign_name": "Dark City", "format_version": 1}
        )
        assert meta.campaign_name == "Dark City"
        assert meta.format_version == 1

    def test_default_format_version(self):
        meta = CampaignMeta.model_validate(
            {"engine_version": "0.1.0", "campaign_name": "Test Campaign"}
        )
        assert meta.format_version == 1

    def test_missing_required_field_rejected(self):
        with pytest.raises(ValidationError):
            CampaignMeta.model_validate({"engine_version": "0.1.0"})


# ---------------------------------------------------------------------------
# UserYaml
# ---------------------------------------------------------------------------


class TestUserYaml:
    def test_valid_gm_user(self):
        user = UserYaml.model_validate({"display_name": "Test GM", "role": "gm"})
        assert user.role == "gm"
        assert user.character is None

    def test_valid_player_user(self):
        user = UserYaml.model_validate(
            {"display_name": "Alice", "role": "player", "character": "Alexander"}
        )
        assert user.character == "Alexander"

    def test_invalid_role_rejected(self):
        with pytest.raises(ValidationError, match="role must be"):
            UserYaml.model_validate({"display_name": "Alice", "role": "admin"})


# ---------------------------------------------------------------------------
# TraitTemplateYaml
# ---------------------------------------------------------------------------


class TestTraitTemplateYaml:
    def test_valid_core_template(self):
        tmpl = TraitTemplateYaml.model_validate(
            {"name": "Unstoppable", "type": "core", "description": "You push through."}
        )
        assert tmpl.type == "core"

    def test_valid_role_template(self):
        tmpl = TraitTemplateYaml.model_validate(
            {"name": "Street Savvy", "type": "role", "description": "You know the streets."}
        )
        assert tmpl.type == "role"

    def test_invalid_type_rejected(self):
        with pytest.raises(ValidationError, match="type must be 'core' or 'role'"):
            TraitTemplateYaml.model_validate(
                {"name": "Bad", "type": "other", "description": "nope"}
            )


# ---------------------------------------------------------------------------
# PCTraitYaml
# ---------------------------------------------------------------------------


class TestPCTraitYaml:
    def test_valid_trait(self):
        trait = PCTraitYaml.model_validate({"template": "Unstoppable", "charge": 3})
        assert trait.charge == 3
        assert trait.is_active is True

    def test_defaults(self):
        trait = PCTraitYaml.model_validate({"template": "Street Savvy"})
        assert trait.charge == 5
        assert trait.is_active is True


# ---------------------------------------------------------------------------
# PCBondYaml / NPCBondYaml
# ---------------------------------------------------------------------------


class TestPCBondYaml:
    def test_valid_bond(self):
        bond = PCBondYaml.model_validate(
            {
                "name": "Allies in shadow",
                "target": {"type": "group", "name": "The Syndicate"},
                "charges": 4,
                "degradations": 1,
                "is_trauma": False,
            }
        )
        assert bond.charges == 4
        assert bond.is_trauma is False

    def test_defaults(self):
        bond = PCBondYaml.model_validate(
            {"name": "Bond", "target": {"type": "character", "name": "NPC1"}}
        )
        assert bond.charges == 5
        assert bond.degradations == 0
        assert bond.is_trauma is False
        assert bond.is_active is True

    def test_invalid_target_type_rejected(self):
        with pytest.raises(ValidationError, match="type must be one of"):
            PCBondYaml.model_validate(
                {"name": "Bond", "target": {"type": "bad", "name": "X"}}
            )


class TestNPCBondYaml:
    def test_valid_bond(self):
        bond = NPCBondYaml.model_validate(
            {
                "name": "Works for",
                "target": {"type": "group", "name": "The Syndicate"},
                "bidirectional": True,
            }
        )
        assert bond.bidirectional is True

    def test_no_charges_field(self):
        """NPC bonds have no charges — validate model has no such field."""
        bond = NPCBondYaml.model_validate(
            {"name": "Bond", "target": {"type": "character", "name": "Alex"}}
        )
        assert not hasattr(bond, "charges")


# ---------------------------------------------------------------------------
# MagicEffectYaml
# ---------------------------------------------------------------------------


class TestMagicEffectYaml:
    def test_valid_instant(self):
        effect = MagicEffectYaml.model_validate(
            {
                "name": "Flash Ward",
                "description": "Single-use shield.",
                "effect_type": "instant",
                "power_level": 2,
            }
        )
        assert effect.effect_type == "instant"
        assert effect.charges is None

    def test_valid_charged(self):
        effect = MagicEffectYaml.model_validate(
            {
                "name": "Flame Hex",
                "description": "Burns targets.",
                "effect_type": "charged",
                "power_level": 3,
                "charges": {"current": 3, "max": 5},
            }
        )
        assert effect.charges == {"current": 3, "max": 5}

    def test_invalid_effect_type_rejected(self):
        with pytest.raises(ValidationError, match="effect_type must be"):
            MagicEffectYaml.model_validate(
                {"name": "X", "description": "X", "effect_type": "passive", "power_level": 1}
            )

    def test_charged_effect_missing_keys_rejected(self):
        with pytest.raises(ValidationError, match="'current' and 'max' keys"):
            MagicEffectYaml.model_validate(
                {
                    "name": "Bad",
                    "description": "Missing keys.",
                    "effect_type": "charged",
                    "power_level": 1,
                    "charges": {"amount": 3},
                }
            )


# ---------------------------------------------------------------------------
# PCCharacterYaml
# ---------------------------------------------------------------------------


class TestPCCharacterYaml:
    def test_valid_minimal_pc(self):
        char = PCCharacterYaml.model_validate({"name": "Alexander"})
        assert char.detail_level == "full"
        assert char.meters["stress"] == 0
        assert char.bonds == []

    def test_valid_full_pc(self):
        data = {
            "name": "Miriam",
            "detail_level": "full",
            "description": "A wandering mage.",
            "meters": {"stress": 2, "free_time": 5, "plot": 1, "gnosis": 10},
            "skills": {
                "awareness": 2,
                "composure": 1,
                "influence": 0,
                "finesse": 3,
                "speed": 1,
                "power": 0,
                "knowledge": 2,
                "technology": 0,
            },
            "magic_stats": {
                "being": {"level": 2, "xp": 3},
                "wyrding": {"level": 0, "xp": 0},
                "summoning": {"level": 1, "xp": 0},
                "enchanting": {"level": 0, "xp": 0},
                "dreaming": {"level": 0, "xp": 0},
            },
            "core_traits": [{"template": "Unstoppable", "charge": 5}],
            "bonds": [
                {
                    "name": "Old ally",
                    "target": {"type": "character", "name": "NPC1"},
                    "charges": 3,
                }
            ],
        }
        char = PCCharacterYaml.model_validate(data)
        assert char.meters["stress"] == 2
        assert len(char.core_traits) == 1
        assert len(char.bonds) == 1

    def test_wrong_detail_level_rejected(self):
        with pytest.raises(ValidationError, match="detail_level='full'"):
            PCCharacterYaml.model_validate({"name": "X", "detail_level": "simplified"})

    def test_secrets_field_accepted(self):
        char = PCCharacterYaml.model_validate(
            {"name": "Alice", "secrets": "Has a secret identity."}
        )
        assert char.secrets == "Has a secret identity."


# ---------------------------------------------------------------------------
# NPCCharacterYaml
# ---------------------------------------------------------------------------


class TestNPCCharacterYaml:
    def test_valid_minimal_npc(self):
        char = NPCCharacterYaml.model_validate({"name": "The Owner"})
        assert char.detail_level == "simplified"
        assert char.bonds == []

    def test_wrong_detail_level_rejected(self):
        with pytest.raises(ValidationError, match="detail_level='simplified'"):
            NPCCharacterYaml.model_validate({"name": "X", "detail_level": "full"})

    def test_with_bonds(self):
        data = {
            "name": "Shovel",
            "bonds": [
                {
                    "name": "Bound to",
                    "target": {"type": "character", "name": "Alexander"},
                }
            ],
        }
        char = NPCCharacterYaml.model_validate(data)
        assert len(char.bonds) == 1


# ---------------------------------------------------------------------------
# GroupYaml
# ---------------------------------------------------------------------------


class TestGroupYaml:
    def test_valid_minimal_group(self):
        group = GroupYaml.model_validate({"name": "Moloch Society", "tier": 3})
        assert group.tier == 3
        assert group.traits == []
        assert group.relations == []
        assert group.holdings == []

    def test_with_inline_slots(self):
        data = {
            "name": "The Syndicate",
            "tier": 2,
            "traits": [{"name": "Well Connected", "description": "They know people."}],
            "relations": [
                {"name": "Rivals with", "target": "Moloch Society", "bidirectional": True}
            ],
            "holdings": [{"name": "HQ", "target": "Old Quarter"}],
        }
        group = GroupYaml.model_validate(data)
        assert len(group.traits) == 1
        assert len(group.relations) == 1
        assert group.relations[0].bidirectional is True
        assert len(group.holdings) == 1


# ---------------------------------------------------------------------------
# LocationYaml
# ---------------------------------------------------------------------------


class TestLocationYaml:
    def test_valid_minimal_location(self):
        loc = LocationYaml.model_validate({"name": "Las Vegas"})
        assert loc.parent is None
        assert loc.features == []
        assert loc.bonds == []

    def test_with_parent_and_slots(self):
        data = {
            "name": "Lane 23",
            "parent": "Las Vegas",
            "features": [{"name": "Neon Signs", "description": "Bright lights."}],
            "bonds": [
                {
                    "name": "Controlled by",
                    "target": {"type": "group", "name": "The Syndicate"},
                }
            ],
        }
        loc = LocationYaml.model_validate(data)
        assert loc.parent == "Las Vegas"
        assert len(loc.features) == 1
        assert len(loc.bonds) == 1


# ---------------------------------------------------------------------------
# ClockYaml
# ---------------------------------------------------------------------------


class TestClockYaml:
    def test_valid_clock(self):
        clock = ClockYaml.model_validate(
            {"name": "Consolidate Power", "segments": 8, "progress": 3}
        )
        assert clock.segments == 8
        assert clock.progress == 3

    def test_with_association(self):
        data = {
            "name": "Revenge Plan",
            "segments": 6,
            "progress": 0,
            "associated_with": {"type": "group", "name": "Moloch Society"},
        }
        clock = ClockYaml.model_validate(data)
        assert clock.associated_with is not None
        assert clock.associated_with.type == "group"

    def test_zero_segments_rejected(self):
        with pytest.raises(ValidationError, match="segments must be at least 1"):
            ClockYaml.model_validate({"name": "Bad", "segments": 0})

    def test_negative_progress_rejected(self):
        with pytest.raises(ValidationError, match="progress must be non-negative"):
            ClockYaml.model_validate({"name": "Bad", "segments": 5, "progress": -1})


# ---------------------------------------------------------------------------
# SessionYaml
# ---------------------------------------------------------------------------


class TestSessionYaml:
    def test_valid_session(self):
        session = SessionYaml.model_validate(
            {
                "number": 1,
                "status": "ended",
                "date": "2026-01-15",
                "summary": "The team raided the dam.",
            }
        )
        assert session.number == 1
        assert session.status == "ended"

    def test_with_participants(self):
        data = {
            "number": 2,
            "status": "ended",
            "participants": [
                {"character": "Alexander", "additional_contribution": True},
                {"character": "Miriam"},
            ],
        }
        session = SessionYaml.model_validate(data)
        assert len(session.participants) == 2
        assert session.participants[0].additional_contribution is True
        assert session.participants[1].additional_contribution is False

    def test_invalid_status_rejected(self):
        with pytest.raises(ValidationError, match="status must be"):
            SessionYaml.model_validate({"number": 1, "status": "cancelled"})


# ---------------------------------------------------------------------------
# StoryYaml
# ---------------------------------------------------------------------------


class TestStoryYaml:
    def test_valid_minimal_story(self):
        story = StoryYaml.model_validate({"name": "The Blackout Murders", "status": "active"})
        assert story.status == "active"
        assert story.entries == []
        assert story.children == []

    def test_with_entries_and_owners(self):
        data = {
            "name": "Arc One",
            "status": "completed",
            "tags": ["mystery", "noir"],
            "owners": [{"type": "character", "name": "Alexander"}],
            "entries": [
                {"text": "It began on a dark night.", "author": "Test GM"}
            ],
        }
        story = StoryYaml.model_validate(data)
        assert len(story.entries) == 1
        assert story.entries[0].author == "Test GM"
        assert len(story.owners) == 1

    def test_nested_children(self):
        data = {
            "name": "Parent Arc",
            "status": "active",
            "children": [
                {"name": "Child Arc", "status": "active"}
            ],
        }
        story = StoryYaml.model_validate(data)
        assert len(story.children) == 1
        assert story.children[0].name == "Child Arc"

    def test_invalid_status_rejected(self):
        with pytest.raises(ValidationError, match="status must be"):
            StoryYaml.model_validate({"name": "Bad", "status": "draft"})

    def test_invalid_owner_type_rejected(self):
        with pytest.raises(ValidationError, match="type must be one of"):
            StoryYaml.model_validate(
                {
                    "name": "Story",
                    "status": "active",
                    "owners": [{"type": "event", "name": "X"}],
                }
            )


# ---------------------------------------------------------------------------
# StoryEntryYaml
# ---------------------------------------------------------------------------


class TestStoryEntryYaml:
    def test_valid_entry(self):
        entry = StoryEntryYaml.model_validate(
            {"text": "The fog rolled in.", "author": "Test GM"}
        )
        assert entry.text == "The fog rolled in."
        assert entry.character is None
        assert entry.session is None

    def test_entry_with_links(self):
        entry = StoryEntryYaml.model_validate(
            {
                "text": "She arrived at the scene.",
                "author": "Alice",
                "character": "Miriam",
                "session": 5,
            }
        )
        assert entry.session == 5
        assert entry.character == "Miriam"


# ---------------------------------------------------------------------------
# Direct construction of sub-models (GroupTraitYaml, GroupRelationYaml,
# GroupHoldingYaml, LocationFeatureYaml, LocationBondYaml,
# SessionParticipantYaml, StoryOwnerYaml)
# ---------------------------------------------------------------------------


class TestGroupTraitYaml:
    def test_valid_trait(self):
        trait = GroupTraitYaml.model_validate(
            {"name": "Well Connected", "description": "They know people."}
        )
        assert trait.name == "Well Connected"
        assert trait.is_active is True

    def test_optional_description(self):
        trait = GroupTraitYaml.model_validate({"name": "Secretive"})
        assert trait.description is None

    def test_inactive_trait(self):
        trait = GroupTraitYaml.model_validate(
            {"name": "Old Allies", "is_active": False}
        )
        assert trait.is_active is False


class TestGroupRelationYaml:
    def test_valid_relation(self):
        rel = GroupRelationYaml.model_validate(
            {"name": "Rivals with", "target": "Moloch Society"}
        )
        assert rel.bidirectional is False
        assert rel.labels is None

    def test_bidirectional_with_labels(self):
        rel = GroupRelationYaml.model_validate(
            {
                "name": "Allied with",
                "target": "The Syndicate",
                "bidirectional": True,
                "labels": {"source": "Partner", "target": "Partner"},
            }
        )
        assert rel.bidirectional is True
        assert rel.labels == {"source": "Partner", "target": "Partner"}

    def test_missing_target_rejected(self):
        with pytest.raises(ValidationError):
            GroupRelationYaml.model_validate({"name": "Rivals"})


class TestGroupHoldingYaml:
    def test_valid_holding(self):
        holding = GroupHoldingYaml.model_validate(
            {"name": "HQ", "target": "Old Quarter"}
        )
        assert holding.name == "HQ"
        assert holding.description is None
        assert holding.is_active is True

    def test_with_description(self):
        holding = GroupHoldingYaml.model_validate(
            {"name": "Casino", "target": "Las Vegas Strip", "description": "Their main asset."}
        )
        assert holding.description == "Their main asset."

    def test_missing_target_rejected(self):
        with pytest.raises(ValidationError):
            GroupHoldingYaml.model_validate({"name": "HQ"})


class TestLocationFeatureYaml:
    def test_valid_feature(self):
        feature = LocationFeatureYaml.model_validate(
            {"name": "Neon Signs", "description": "Bright lights."}
        )
        assert feature.name == "Neon Signs"
        assert feature.is_active is True

    def test_optional_description(self):
        feature = LocationFeatureYaml.model_validate({"name": "Underground Tunnels"})
        assert feature.description is None


class TestLocationBondYaml:
    def test_valid_bond(self):
        bond = LocationBondYaml.model_validate(
            {
                "name": "Controlled by",
                "target": {"type": "group", "name": "The Syndicate"},
            }
        )
        assert bond.name == "Controlled by"
        assert bond.is_active is True
        assert bond.labels is None

    def test_invalid_target_type_rejected(self):
        with pytest.raises(ValidationError, match="type must be one of"):
            LocationBondYaml.model_validate(
                {"name": "Bond", "target": {"type": "faction", "name": "X"}}
            )

    def test_missing_target_rejected(self):
        with pytest.raises(ValidationError):
            LocationBondYaml.model_validate({"name": "Controlled by"})


class TestSessionParticipantYaml:
    def test_valid_participant(self):
        p = SessionParticipantYaml.model_validate({"character": "Alexander"})
        assert p.character == "Alexander"
        assert p.additional_contribution is False

    def test_additional_contribution_true(self):
        p = SessionParticipantYaml.model_validate(
            {"character": "Miriam", "additional_contribution": True}
        )
        assert p.additional_contribution is True

    def test_missing_character_rejected(self):
        with pytest.raises(ValidationError):
            SessionParticipantYaml.model_validate({"additional_contribution": False})


class TestStoryOwnerYaml:
    def test_valid_character_owner(self):
        owner = StoryOwnerYaml.model_validate({"type": "character", "name": "Alexander"})
        assert owner.type == "character"

    def test_valid_group_owner(self):
        owner = StoryOwnerYaml.model_validate({"type": "group", "name": "The Syndicate"})
        assert owner.type == "group"

    def test_valid_location_owner(self):
        owner = StoryOwnerYaml.model_validate({"type": "location", "name": "Las Vegas"})
        assert owner.type == "location"

    def test_invalid_type_rejected(self):
        with pytest.raises(ValidationError, match="type must be one of"):
            StoryOwnerYaml.model_validate({"type": "npc", "name": "Shovel"})


# ---------------------------------------------------------------------------
# Additional edge-case coverage for previously tested models
# ---------------------------------------------------------------------------


class TestMagicEffectYamlAdditional:
    """Cover the 'permanent' effect_type branch and boundary values."""

    def test_valid_permanent_effect(self):
        effect = MagicEffectYaml.model_validate(
            {
                "name": "Eternal Sight",
                "description": "Permanent magical vision.",
                "effect_type": "permanent",
                "power_level": 4,
            }
        )
        assert effect.effect_type == "permanent"
        assert effect.charges is None

    def test_inactive_effect(self):
        effect = MagicEffectYaml.model_validate(
            {
                "name": "Expired Ward",
                "description": "No longer active.",
                "effect_type": "instant",
                "power_level": 1,
                "is_active": False,
            }
        )
        assert effect.is_active is False


class TestPCTraitYamlEdgeCases:
    """Boundary charge values and is_active=False."""

    def test_charge_zero(self):
        trait = PCTraitYaml.model_validate({"template": "Depleted", "charge": 0})
        assert trait.charge == 0

    def test_charge_five(self):
        trait = PCTraitYaml.model_validate({"template": "Full", "charge": 5})
        assert trait.charge == 5

    def test_inactive_trait(self):
        trait = PCTraitYaml.model_validate({"template": "Retired", "is_active": False})
        assert trait.is_active is False


class TestPCBondYamlEdgeCases:
    """Boundary charges/degradations and is_trauma=True."""

    def test_charges_zero(self):
        bond = PCBondYaml.model_validate(
            {"name": "Severed", "target": {"type": "character", "name": "X"}, "charges": 0}
        )
        assert bond.charges == 0

    def test_charges_five(self):
        bond = PCBondYaml.model_validate(
            {"name": "Strong", "target": {"type": "character", "name": "X"}, "charges": 5}
        )
        assert bond.charges == 5

    def test_trauma_bond(self):
        bond = PCBondYaml.model_validate(
            {
                "name": "Trauma",
                "target": {"type": "character", "name": "X"},
                "is_trauma": True,
            }
        )
        assert bond.is_trauma is True

    def test_inactive_bond(self):
        bond = PCBondYaml.model_validate(
            {
                "name": "Old Bond",
                "target": {"type": "location", "name": "Las Vegas"},
                "is_active": False,
            }
        )
        assert bond.is_active is False


class TestClockYamlEdgeCases:
    """Confirm that progress > segments is not blocked by the model (importer validates this)."""

    def test_segments_one(self):
        clock = ClockYaml.model_validate({"name": "Minimal", "segments": 1, "progress": 0})
        assert clock.segments == 1

    def test_progress_equal_segments(self):
        clock = ClockYaml.model_validate(
            {"name": "Complete", "segments": 6, "progress": 6}
        )
        assert clock.progress == 6

    def test_default_segments(self):
        clock = ClockYaml.model_validate({"name": "Default Clock"})
        assert clock.segments == 5
        assert clock.progress == 0


# ---------------------------------------------------------------------------
# ordering.py — phase constants
# ---------------------------------------------------------------------------


class TestImportPhaseConstants:
    """Verify the 6-phase import order constants are correctly defined."""

    def test_phase_1_contains_expected_types(self):
        assert "trait_templates" in PHASE_1
        assert "locations" in PHASE_1

    def test_phase_2_contains_expected_types(self):
        assert "groups" in PHASE_2
        assert "characters" in PHASE_2

    def test_phase_3_contains_expected_types(self):
        assert "slots" in PHASE_3
        assert "magic_effects" in PHASE_3

    def test_phase_4_contains_clocks(self):
        assert "clocks" in PHASE_4

    def test_phase_5_contains_users(self):
        assert "users" in PHASE_5

    def test_phase_6_contains_sessions_and_stories(self):
        assert "sessions" in PHASE_6
        assert "stories" in PHASE_6

    def test_import_phases_has_six_entries(self):
        assert len(IMPORT_PHASES) == 6

    def test_import_phases_order(self):
        assert IMPORT_PHASES[0] is PHASE_1
        assert IMPORT_PHASES[1] is PHASE_2
        assert IMPORT_PHASES[2] is PHASE_3
        assert IMPORT_PHASES[3] is PHASE_4
        assert IMPORT_PHASES[4] is PHASE_5
        assert IMPORT_PHASES[5] is PHASE_6

    def test_all_entity_types_appear_exactly_once(self):
        all_types: list[str] = []
        for phase in IMPORT_PHASES:
            all_types.extend(phase)
        # No entity type should appear in more than one phase.
        assert len(all_types) == len(set(all_types))


# ---------------------------------------------------------------------------
# ordering.py — topological_sort_locations
# ---------------------------------------------------------------------------


class TestTopologicalSortLocations:
    def test_empty_input_returns_empty(self):
        assert topological_sort_locations([]) == []

    def test_single_root(self):
        locs = [{"name": "Las Vegas"}]
        result = topological_sort_locations(locs)
        assert result == locs

    def test_parent_before_child(self):
        locs = [
            {"name": "Lane 23", "parent": "Las Vegas"},
            {"name": "Las Vegas"},
        ]
        result = topological_sort_locations(locs)
        names = [r["name"] for r in result]
        assert names.index("Las Vegas") < names.index("Lane 23")

    def test_deep_chain_ordering(self):
        # A -> B -> C -> D  (each is a child of the previous)
        locs = [
            {"name": "D", "parent": "C"},
            {"name": "B", "parent": "A"},
            {"name": "C", "parent": "B"},
            {"name": "A"},
        ]
        result = topological_sort_locations(locs)
        names = [r["name"] for r in result]
        assert names.index("A") < names.index("B")
        assert names.index("B") < names.index("C")
        assert names.index("C") < names.index("D")

    def test_multiple_roots_sorted_alphabetically(self):
        locs = [
            {"name": "Planes"},
            {"name": "Las Vegas"},
        ]
        result = topological_sort_locations(locs)
        assert result[0]["name"] == "Las Vegas"
        assert result[1]["name"] == "Planes"

    def test_multiple_children_of_same_parent(self):
        locs = [
            {"name": "Child B", "parent": "Root"},
            {"name": "Child A", "parent": "Root"},
            {"name": "Root"},
        ]
        result = topological_sort_locations(locs)
        names = [r["name"] for r in result]
        assert names[0] == "Root"
        # Both children must come after root
        assert names.index("Root") < names.index("Child A")
        assert names.index("Root") < names.index("Child B")

    def test_cycle_raises_value_error(self):
        locs = [
            {"name": "A", "parent": "B"},
            {"name": "B", "parent": "A"},
        ]
        with pytest.raises(ValueError, match="Cycle detected"):
            topological_sort_locations(locs)

    def test_self_reference_cycle_raises_value_error(self):
        locs = [{"name": "A", "parent": "A"}]
        with pytest.raises(ValueError, match="Cycle detected"):
            topological_sort_locations(locs)

    def test_unknown_parent_raises_value_error(self):
        locs = [{"name": "Lane 23", "parent": "Nonexistent City"}]
        with pytest.raises(ValueError, match="unknown parent"):
            topological_sort_locations(locs)

    def test_duplicate_name_raises_value_error(self):
        locs = [
            {"name": "Las Vegas"},
            {"name": "Las Vegas", "parent": None},
        ]
        with pytest.raises(ValueError, match="Duplicate location name"):
            topological_sort_locations(locs)

    def test_none_parent_treated_as_root(self):
        locs = [
            {"name": "Child", "parent": None},
            {"name": "Root"},
        ]
        # "Child" has parent=None so it's a root — no ordering constraint
        result = topological_sort_locations(locs)
        assert len(result) == 2
