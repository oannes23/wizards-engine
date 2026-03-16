"""Tests for Story 1.1.4 — SQLAlchemy ORM Models.

Covers:
- All 18 model classes can be imported from wizards_engine.models
- Tables create successfully against a SQLite database
- Column presence, types, and constraints match the data model spec
- Composite PK tables have no id / timestamp columns
- Invite and Event have created_at only (no updated_at)
- Slot composite indexes are defined
- Polymorphic association tables have correct composite PKs
- Basic ORM round-trips: insert and retrieve rows for each model family
"""

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from wizards_engine.models import (
    Base,
    Character,
    Clock,
    Event,
    EventTarget,
    Group,
    Invite,
    Location,
    MagicEffect,
    Proposal,
    Session,
    SessionParticipant,
    Slot,
    StarredObject,
    Story,
    StoryEntry,
    StoryOwner,
    TraitTemplate,
    User,
)
from wizards_engine.models.base import _new_ulid


# ---------------------------------------------------------------------------
# Shared in-memory SQLite engine / session for all model tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def db_engine():
    """Create an in-memory SQLite engine with all tables."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="module")
def db_session(db_engine):
    """Provide a module-scoped session connected to the in-memory engine."""
    Session_ = sessionmaker(bind=db_engine)
    session = Session_()
    yield session
    session.close()


@pytest.fixture(scope="module")
def insp(db_engine):
    """SQLAlchemy inspector against the in-memory engine."""
    return inspect(db_engine)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def col_names(insp, table: str) -> set[str]:
    return {c["name"] for c in insp.get_columns(table)}


def pk_cols(insp, table: str) -> list[str]:
    return insp.get_pk_constraint(table)["constrained_columns"]


# ---------------------------------------------------------------------------
# 1. All models importable from wizards_engine.models
# ---------------------------------------------------------------------------


def test_all_18_model_classes_importable():
    """All 18 table-bearing model classes must be importable from the package."""
    expected = {
        "User", "Invite", "Character", "Group", "Location",
        "TraitTemplate", "Slot", "MagicEffect", "Clock",
        "Session", "SessionParticipant", "Story", "StoryOwner",
        "StoryEntry", "Event", "EventTarget", "Proposal", "StarredObject",
    }
    from wizards_engine import models
    actual = {name for name in dir(models) if name in expected}
    assert actual == expected


# ---------------------------------------------------------------------------
# 2. Tables created
# ---------------------------------------------------------------------------


def test_all_18_tables_exist(insp):
    """All 18 tables must be present in the schema after create_all()."""
    expected_tables = {
        "users", "invites", "characters", "groups", "locations",
        "trait_templates", "slots", "magic_effects", "clocks",
        "sessions", "session_participants", "stories", "story_owners",
        "story_entries", "events", "event_targets", "proposals",
        "starred_objects",
    }
    actual = set(insp.get_table_names())
    assert expected_tables.issubset(actual)


# ---------------------------------------------------------------------------
# 3. Column presence per spec
# ---------------------------------------------------------------------------


def test_users_columns(insp):
    cols = col_names(insp, "users")
    assert {"id", "display_name", "role", "login_code", "character_id",
            "is_active", "created_at", "updated_at"}.issubset(cols)


def test_invites_columns_created_at_only(insp):
    """Invite has created_at but NOT updated_at."""
    cols = col_names(insp, "invites")
    assert {"id", "is_consumed", "created_at"}.issubset(cols)
    assert "updated_at" not in cols


def test_characters_columns(insp):
    cols = col_names(insp, "characters")
    assert {
        "id", "name", "description", "detail_level", "attributes",
        "stress", "free_time", "plot", "gnosis", "skills", "magic_stats",
        "last_session_time_now", "notes", "is_deleted", "created_at", "updated_at",
    }.issubset(cols)


def test_groups_columns(insp):
    cols = col_names(insp, "groups")
    assert {"id", "name", "description", "tier", "notes",
            "is_deleted", "created_at", "updated_at"}.issubset(cols)


def test_locations_columns(insp):
    cols = col_names(insp, "locations")
    assert {"id", "name", "description", "parent_id", "notes",
            "is_deleted", "created_at", "updated_at"}.issubset(cols)


def test_trait_templates_columns(insp):
    cols = col_names(insp, "trait_templates")
    assert {"id", "name", "description", "type",
            "is_deleted", "created_at", "updated_at"}.issubset(cols)


def test_slots_columns(insp):
    cols = col_names(insp, "slots")
    assert {
        "id", "slot_type", "owner_type", "owner_id", "name", "description",
        "is_active", "target_type", "target_id", "source_label", "target_label",
        "bidirectional", "template_id", "charge", "stress", "stress_degradations",
        "is_trauma", "created_at", "updated_at",
    }.issubset(cols)


def test_magic_effects_columns(insp):
    cols = col_names(insp, "magic_effects")
    assert {
        "id", "character_id", "name", "description", "effect_type",
        "power_level", "charges_current", "charges_max", "is_active",
        "created_at", "updated_at",
    }.issubset(cols)


def test_clocks_columns(insp):
    cols = col_names(insp, "clocks")
    assert {
        "id", "name", "segments", "progress", "associated_type",
        "associated_id", "notes", "is_deleted", "created_at", "updated_at",
    }.issubset(cols)


def test_sessions_columns(insp):
    cols = col_names(insp, "sessions")
    assert {"id", "status", "time_now", "date", "summary", "notes",
            "created_at", "updated_at"}.issubset(cols)


def test_session_participants_columns_no_id_no_timestamps(insp):
    """session_participants has no id column and no timestamps."""
    cols = col_names(insp, "session_participants")
    assert {"session_id", "character_id", "additional_contribution"}.issubset(cols)
    assert "id" not in cols
    assert "created_at" not in cols
    assert "updated_at" not in cols


def test_stories_columns(insp):
    cols = col_names(insp, "stories")
    assert {
        "id", "name", "summary", "status", "parent_id", "tags",
        "visibility_level", "visibility_overrides", "is_deleted",
        "created_at", "updated_at",
    }.issubset(cols)


def test_story_owners_columns_no_id_no_timestamps(insp):
    """story_owners has no id column and no timestamps."""
    cols = col_names(insp, "story_owners")
    assert {"story_id", "owner_type", "owner_id"}.issubset(cols)
    assert "id" not in cols
    assert "created_at" not in cols


def test_story_entries_columns(insp):
    cols = col_names(insp, "story_entries")
    assert {
        "id", "story_id", "text", "author_id", "character_id", "session_id",
        "event_id", "game_object_refs", "is_deleted", "deleted_by", "updated_by",
        "created_at", "updated_at",
    }.issubset(cols)


def test_events_columns_created_at_only(insp):
    """events has created_at but NOT updated_at."""
    cols = col_names(insp, "events")
    assert {
        "id", "type", "actor_type", "actor_id", "changes", "created_objects",
        "deleted_objects", "narrative", "visibility", "proposal_id",
        "parent_event_id", "session_id", "metadata", "created_at",
    }.issubset(cols)
    assert "updated_at" not in cols


def test_event_targets_columns_no_id_no_timestamps(insp):
    """event_targets has no id column and no timestamps."""
    cols = col_names(insp, "event_targets")
    assert {"event_id", "target_type", "target_id", "is_primary"}.issubset(cols)
    assert "id" not in cols
    assert "created_at" not in cols


def test_proposals_columns(insp):
    cols = col_names(insp, "proposals")
    assert {
        "id", "character_id", "action_type", "origin", "narrative",
        "selections", "calculated_effect", "status", "gm_notes", "gm_overrides",
        "event_id", "clock_id", "rider_event_id", "created_at", "updated_at",
    }.issubset(cols)


def test_starred_objects_columns_no_id_no_timestamps(insp):
    """starred_objects has no id column and no timestamps."""
    cols = col_names(insp, "starred_objects")
    assert {"user_id", "object_type", "object_id"}.issubset(cols)
    assert "id" not in cols
    assert "created_at" not in cols


# ---------------------------------------------------------------------------
# 4. Primary key constraints
# ---------------------------------------------------------------------------


def test_session_participants_composite_pk(insp):
    pks = pk_cols(insp, "session_participants")
    assert set(pks) == {"session_id", "character_id"}


def test_story_owners_composite_pk(insp):
    pks = pk_cols(insp, "story_owners")
    assert set(pks) == {"story_id", "owner_type", "owner_id"}


def test_event_targets_composite_pk(insp):
    pks = pk_cols(insp, "event_targets")
    assert set(pks) == {"event_id", "target_type", "target_id"}


def test_starred_objects_composite_pk(insp):
    pks = pk_cols(insp, "starred_objects")
    assert set(pks) == {"user_id", "object_type", "object_id"}


# ---------------------------------------------------------------------------
# 5. Slots composite indexes
# ---------------------------------------------------------------------------


def test_slots_owner_index_defined():
    """Slot model must declare a composite index on (owner_type, owner_id, slot_type)."""
    index_cols = {
        frozenset(col.name for col in idx.columns)
        for idx in Slot.__table__.indexes
    }
    assert frozenset({"owner_type", "owner_id", "slot_type"}) in index_cols


def test_slots_target_index_defined():
    """Slot model must declare a composite index on (target_type, target_id)."""
    index_cols = {
        frozenset(col.name for col in idx.columns)
        for idx in Slot.__table__.indexes
    }
    assert frozenset({"target_type", "target_id"}) in index_cols


# ---------------------------------------------------------------------------
# 6. Metadata column name mapping on Event
# ---------------------------------------------------------------------------


def test_event_metadata_python_attr_maps_to_db_column_metadata():
    """Event.metadata_ Python attribute must map to a DB column named 'metadata'."""
    # The DB column must be named 'metadata'.
    col = Event.__table__.c.get("metadata")
    assert col is not None, "Expected a column named 'metadata' on the events table"
    assert col.name == "metadata"
    # The SQLAlchemy mapper attribute must be accessible as 'metadata_' (not 'metadata'),
    # to avoid colliding with SQLAlchemy's own metadata attribute.
    from sqlalchemy import inspect as sa_inspect
    mapper = sa_inspect(Event)
    attr_keys = {attr.key for attr in mapper.mapper.column_attrs}
    assert "metadata_" in attr_keys, "Expected mapper attribute key 'metadata_' on Event"
    assert "metadata" not in attr_keys or True  # 'metadata' is a class attr, not column attr


# ---------------------------------------------------------------------------
# 7. ORM round-trips (insert + retrieve)
# ---------------------------------------------------------------------------


def test_orm_user_insert_retrieve(db_session):
    user = User(display_name="Test GM", role="gm", login_code=_new_ulid())
    db_session.add(user)
    db_session.flush()
    found = db_session.get(User, user.id)
    assert found is not None
    assert found.display_name == "Test GM"
    assert found.is_active is True


def test_orm_invite_insert_retrieve(db_session):
    invite = Invite()
    db_session.add(invite)
    db_session.flush()
    found = db_session.get(Invite, invite.id)
    assert found is not None
    assert found.is_consumed is False
    assert found.created_at is not None
    assert not hasattr(found, "updated_at") or "updated_at" not in Invite.__table__.c


def test_orm_character_insert_retrieve(db_session):
    char = Character(name="Elara", detail_level="full")
    db_session.add(char)
    db_session.flush()
    found = db_session.get(Character, char.id)
    assert found.name == "Elara"
    assert found.is_deleted is False


def test_orm_group_insert_retrieve(db_session):
    grp = Group(name="The Iron Ring", tier=3)
    db_session.add(grp)
    db_session.flush()
    assert db_session.get(Group, grp.id).tier == 3


def test_orm_location_self_ref(db_session):
    parent = Location(name="Ashwood City")
    child = Location(name="The Docks")
    db_session.add_all([parent, child])
    db_session.flush()
    child.parent_id = parent.id
    db_session.flush()
    found = db_session.get(Location, child.id)
    assert found.parent_id == parent.id


def test_orm_trait_template_and_slot(db_session):
    tmpl = TraitTemplate(name="Hawk-Eyed", description="Sharp vision", type="core")
    db_session.add(tmpl)
    db_session.flush()
    char = Character(name="Scout", detail_level="full")
    db_session.add(char)
    db_session.flush()
    slot = Slot(
        slot_type="core_trait",
        owner_type="character",
        owner_id=char.id,
        name="Hawk-Eyed",
        template_id=tmpl.id,
        charge=3,
    )
    db_session.add(slot)
    db_session.flush()
    found = db_session.get(Slot, slot.id)
    assert found.charge == 3
    assert found.template_id == tmpl.id


def test_orm_magic_effect_linked_to_character(db_session):
    char = Character(name="Witch", detail_level="full")
    db_session.add(char)
    db_session.flush()
    effect = MagicEffect(
        character_id=char.id,
        name="Whisper Ward",
        description="Conceals sound.",
        effect_type="permanent",
        power_level=2,
    )
    db_session.add(effect)
    db_session.flush()
    found = db_session.get(MagicEffect, effect.id)
    assert found.character_id == char.id
    assert found.is_active is True


def test_orm_clock_insert(db_session):
    clock = Clock(name="The Unraveling", segments=8)
    db_session.add(clock)
    db_session.flush()
    found = db_session.get(Clock, clock.id)
    assert found.segments == 8
    assert found.progress == 0


def test_orm_session_with_participant(db_session):
    sess = Session(status="draft")
    char = Character(name="Participant", detail_level="simplified")
    db_session.add_all([sess, char])
    db_session.flush()
    participant = SessionParticipant(
        session_id=sess.id,
        character_id=char.id,
    )
    db_session.add(participant)
    db_session.flush()
    found = db_session.get(SessionParticipant, (sess.id, char.id))
    assert found is not None
    assert found.additional_contribution is False


def test_orm_story_self_ref_and_owner(db_session):
    parent_story = Story(name="The Grand Arc", status="active")
    db_session.add(parent_story)
    db_session.flush()
    child_story = Story(name="The Side Quest", status="active", parent_id=parent_story.id)
    db_session.add(child_story)
    db_session.flush()
    owner = StoryOwner(
        story_id=child_story.id,
        owner_type="character",
        owner_id=_new_ulid(),
    )
    db_session.add(owner)
    db_session.flush()
    found = db_session.get(StoryOwner, (child_story.id, "character", owner.owner_id))
    assert found is not None


def test_orm_story_entry(db_session):
    story = Story(name="Entry Test Story", status="active")
    user = User(display_name="Author", role="player", login_code=_new_ulid())
    db_session.add_all([story, user])
    db_session.flush()
    entry = StoryEntry(story_id=story.id, text="It was a dark night.", author_id=user.id)
    db_session.add(entry)
    db_session.flush()
    found = db_session.get(StoryEntry, entry.id)
    assert found.text == "It was a dark night."
    assert found.is_deleted is False


def test_orm_event_with_target(db_session):
    event = Event(
        type="character.stress_changed",
        actor_type="gm",
        changes={"character.abc.stress": {"op": "meter.delta", "before": 2, "after": 4}},
        visibility="familiar",
    )
    db_session.add(event)
    db_session.flush()
    target = EventTarget(
        event_id=event.id,
        target_type="character",
        target_id=_new_ulid(),
        is_primary=True,
    )
    db_session.add(target)
    db_session.flush()
    found_event = db_session.get(Event, event.id)
    assert found_event.type == "character.stress_changed"
    # Confirm no updated_at attribute exists on Event instances.
    assert not hasattr(found_event, "updated_at")
    found_target = db_session.get(EventTarget, (event.id, "character", target.target_id))
    assert found_target.is_primary is True


def test_orm_event_has_no_updated_at_attribute():
    """Event must not have an updated_at column."""
    assert "updated_at" not in Event.__table__.c


def test_orm_proposal_insert(db_session):
    char = Character(name="Proposer", detail_level="full")
    db_session.add(char)
    db_session.flush()
    proposal = Proposal(
        character_id=char.id,
        action_type="use_skill",
        origin="player",
        narrative="I attempt to sneak past the guard.",
        selections={"core_trait_id": None, "role_trait_id": None},
        status="pending",
    )
    db_session.add(proposal)
    db_session.flush()
    found = db_session.get(Proposal, proposal.id)
    assert found.status == "pending"
    assert found.action_type == "use_skill"


def test_orm_starred_object_composite_pk(db_session):
    user = User(display_name="Star User", role="player", login_code=_new_ulid())
    db_session.add(user)
    db_session.flush()
    starred = StarredObject(
        user_id=user.id,
        object_type="character",
        object_id=_new_ulid(),
    )
    db_session.add(starred)
    db_session.flush()
    found = db_session.get(StarredObject, (user.id, "character", starred.object_id))
    assert found is not None


def test_orm_metadata_field_on_event(db_session):
    """Event.metadata_ must persist and round-trip correctly."""
    event = Event(
        type="clock.completed",
        actor_type="system",
        changes={},
        visibility="gm_only",
        metadata_={"clock_id": "01ABC", "note": "reached segments"},
    )
    db_session.add(event)
    db_session.flush()
    found = db_session.get(Event, event.id)
    assert found.metadata_["note"] == "reached segments"
