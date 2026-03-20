"""Tests for NameResolver (Story 7.1.2).

Covers registration, duplicate detection, resolution, and polymorphic
TargetRef resolution.
"""

from __future__ import annotations

import pytest

from wizards_engine.campaign.exceptions import (
    CampaignValidationError,
    DuplicateNameError,
    UnresolvedReferenceError,
)
from wizards_engine.campaign.resolver import NameResolver
from wizards_engine.campaign.schemas import TargetRef


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class TestExceptionHierarchy:
    def test_duplicate_name_error_is_campaign_validation_error(self):
        exc = DuplicateNameError("character", "Alexander")
        assert isinstance(exc, CampaignValidationError)

    def test_unresolved_reference_error_is_campaign_validation_error(self):
        exc = UnresolvedReferenceError("character", "Unknown")
        assert isinstance(exc, CampaignValidationError)

    def test_duplicate_name_error_message(self):
        exc = DuplicateNameError("group", "Moloch Society")
        assert "Moloch Society" in str(exc)
        assert "group" in str(exc)

    def test_unresolved_reference_error_message(self):
        exc = UnresolvedReferenceError("location", "Las Vegas")
        assert "Las Vegas" in str(exc)
        assert "location" in str(exc)

    def test_duplicate_name_error_attributes(self):
        exc = DuplicateNameError("character", "Alice")
        assert exc.entity_type == "character"
        assert exc.name == "Alice"

    def test_unresolved_reference_error_attributes(self):
        exc = UnresolvedReferenceError("group", "Shadow Council")
        assert exc.entity_type == "group"
        assert exc.name == "Shadow Council"


# ---------------------------------------------------------------------------
# NameResolver.register
# ---------------------------------------------------------------------------


class TestRegister:
    def test_register_single_entity(self):
        resolver = NameResolver()
        resolver.register("character", "Alexander", "01ABCDEF")
        assert resolver.is_registered("character", "Alexander")

    def test_register_multiple_types(self):
        resolver = NameResolver()
        resolver.register("character", "Alexander", "ID_CHAR")
        resolver.register("group", "Moloch Society", "ID_GROUP")
        resolver.register("location", "Las Vegas", "ID_LOC")
        assert resolver.is_registered("character", "Alexander")
        assert resolver.is_registered("group", "Moloch Society")
        assert resolver.is_registered("location", "Las Vegas")

    def test_register_same_name_different_types(self):
        """Same name is allowed in different entity type namespaces."""
        resolver = NameResolver()
        resolver.register("character", "Alpha", "ID_1")
        resolver.register("group", "Alpha", "ID_2")
        # No exception — different type namespaces
        assert resolver.is_registered("character", "Alpha")
        assert resolver.is_registered("group", "Alpha")

    def test_register_duplicate_raises(self):
        resolver = NameResolver()
        resolver.register("character", "Alexander", "ID_1")
        with pytest.raises(DuplicateNameError) as exc_info:
            resolver.register("character", "Alexander", "ID_2")
        assert exc_info.value.entity_type == "character"
        assert exc_info.value.name == "Alexander"

    def test_register_strips_whitespace_from_name(self):
        resolver = NameResolver()
        resolver.register("character", "  Alexander  ", "ID_1")
        assert resolver.is_registered("character", "Alexander")

    def test_register_strips_whitespace_detects_duplicate(self):
        resolver = NameResolver()
        resolver.register("character", "Alexander", "ID_1")
        with pytest.raises(DuplicateNameError):
            resolver.register("character", "  Alexander  ", "ID_2")

    def test_register_strips_whitespace_from_entity_type(self):
        resolver = NameResolver()
        resolver.register("  character  ", "Alexander", "ID_1")
        assert resolver.is_registered("character", "Alexander")


# ---------------------------------------------------------------------------
# NameResolver.resolve
# ---------------------------------------------------------------------------


class TestResolve:
    def test_resolve_returns_ulid(self):
        resolver = NameResolver()
        resolver.register("character", "Alexander", "01ABCDEF")
        assert resolver.resolve("character", "Alexander") == "01ABCDEF"

    def test_resolve_unknown_type_raises(self):
        resolver = NameResolver()
        with pytest.raises(UnresolvedReferenceError) as exc_info:
            resolver.resolve("character", "Alexander")
        assert exc_info.value.entity_type == "character"
        assert exc_info.value.name == "Alexander"

    def test_resolve_unknown_name_raises(self):
        resolver = NameResolver()
        resolver.register("character", "Alexander", "ID_1")
        with pytest.raises(UnresolvedReferenceError) as exc_info:
            resolver.resolve("character", "Unknown")
        assert exc_info.value.name == "Unknown"

    def test_resolve_strips_whitespace(self):
        resolver = NameResolver()
        resolver.register("character", "Alexander", "ID_1")
        assert resolver.resolve("character", "  Alexander  ") == "ID_1"

    def test_resolve_does_not_cross_type_namespaces(self):
        """Resolving 'character'/'Alpha' must not find a 'group'/'Alpha'."""
        resolver = NameResolver()
        resolver.register("group", "Alpha", "GROUP_ID")
        with pytest.raises(UnresolvedReferenceError):
            resolver.resolve("character", "Alpha")

    def test_resolve_multiple_entities(self):
        resolver = NameResolver()
        resolver.register("character", "Alice", "ID_A")
        resolver.register("character", "Bob", "ID_B")
        assert resolver.resolve("character", "Alice") == "ID_A"
        assert resolver.resolve("character", "Bob") == "ID_B"


# ---------------------------------------------------------------------------
# NameResolver.resolve_target_ref
# ---------------------------------------------------------------------------


class TestResolveTargetRef:
    def test_resolve_character_ref(self):
        resolver = NameResolver()
        resolver.register("character", "Alexander", "CHAR_ID")
        ref = TargetRef(type="character", name="Alexander")
        target_type, target_id = resolver.resolve_target_ref(ref)
        assert target_type == "character"
        assert target_id == "CHAR_ID"

    def test_resolve_group_ref(self):
        resolver = NameResolver()
        resolver.register("group", "Moloch Society", "GROUP_ID")
        ref = TargetRef(type="group", name="Moloch Society")
        target_type, target_id = resolver.resolve_target_ref(ref)
        assert target_type == "group"
        assert target_id == "GROUP_ID"

    def test_resolve_location_ref(self):
        resolver = NameResolver()
        resolver.register("location", "Las Vegas", "LOC_ID")
        ref = TargetRef(type="location", name="Las Vegas")
        target_type, target_id = resolver.resolve_target_ref(ref)
        assert target_type == "location"
        assert target_id == "LOC_ID"

    def test_resolve_target_ref_returns_tuple(self):
        resolver = NameResolver()
        resolver.register("character", "Alice", "ID_A")
        ref = TargetRef(type="character", name="Alice")
        result = resolver.resolve_target_ref(ref)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_resolve_target_ref_unresolved_raises(self):
        resolver = NameResolver()
        ref = TargetRef(type="character", name="Nobody")
        with pytest.raises(UnresolvedReferenceError):
            resolver.resolve_target_ref(ref)


# ---------------------------------------------------------------------------
# NameResolver.registered_names
# ---------------------------------------------------------------------------


class TestRegisteredNames:
    def test_registered_names_empty(self):
        resolver = NameResolver()
        assert resolver.registered_names("character") == []

    def test_registered_names_sorted(self):
        resolver = NameResolver()
        resolver.register("character", "Zara", "ID_Z")
        resolver.register("character", "Alice", "ID_A")
        resolver.register("character", "Bob", "ID_B")
        assert resolver.registered_names("character") == ["Alice", "Bob", "Zara"]

    def test_registered_names_does_not_cross_type(self):
        resolver = NameResolver()
        resolver.register("character", "Alice", "ID_A")
        resolver.register("group", "Moloch", "ID_M")
        assert resolver.registered_names("group") == ["Moloch"]
        assert resolver.registered_names("character") == ["Alice"]


# ---------------------------------------------------------------------------
# is_registered
# ---------------------------------------------------------------------------


class TestIsRegistered:
    def test_is_registered_true(self):
        resolver = NameResolver()
        resolver.register("character", "Alice", "ID_A")
        assert resolver.is_registered("character", "Alice") is True

    def test_is_registered_false_unknown_name(self):
        resolver = NameResolver()
        assert resolver.is_registered("character", "Alice") is False

    def test_is_registered_false_wrong_type(self):
        resolver = NameResolver()
        resolver.register("character", "Alice", "ID_A")
        assert resolver.is_registered("group", "Alice") is False
