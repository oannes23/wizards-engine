"""Gap-filling tests for Epic 1.1 acceptance criteria not covered by existing tests.

Covers:
- Story 1.1.1: directory layout, Python version requirement, single migration file
- Story 1.1.2: Alembic env.py uses Base.metadata as target_metadata
- Story 1.1.3: column types (TEXT/ULIDs, INTEGER, BOOLEAN, JSON, DATETIME, DATE), FK constraints
- Story 1.1.4: ORM relationship traversal (User↔Character, Character→MagicEffects,
  Story parent/children, Location parent/children, Event parent_event/rider_events,
  Event→EventTargets, Session→SessionParticipants, Story→StoryEntries/StoryOwners);
  JSON columns use SQLAlchemy JSON type
"""

import os

import pytest
from sqlalchemy import create_engine, inspect, JSON as SA_JSON
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

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# Shared in-memory engine fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def db_engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="module")
def db_session(db_engine):
    Session_ = sessionmaker(bind=db_engine)
    session = Session_()
    yield session
    session.close()


@pytest.fixture(scope="module")
def insp(db_engine):
    return inspect(db_engine)


# ---------------------------------------------------------------------------
# Story 1.1.1 — Project structure
# ---------------------------------------------------------------------------


def test_directory_layout_api_package():
    """src/wizards_engine/api/ must exist as a Python package."""
    api_init = os.path.join(_REPO_ROOT, "src", "wizards_engine", "api", "__init__.py")
    assert os.path.isfile(api_init), f"Missing: {api_init}"


def test_directory_layout_models_package():
    """src/wizards_engine/models/ must exist as a Python package."""
    models_init = os.path.join(_REPO_ROOT, "src", "wizards_engine", "models", "__init__.py")
    assert os.path.isfile(models_init), f"Missing: {models_init}"


def test_directory_layout_services_package():
    """src/wizards_engine/services/ must exist as a Python package."""
    services_init = os.path.join(_REPO_ROOT, "src", "wizards_engine", "services", "__init__.py")
    assert os.path.isfile(services_init), f"Missing: {services_init}"


def test_directory_layout_schemas_package():
    """src/wizards_engine/schemas/ must exist as a Python package."""
    schemas_init = os.path.join(_REPO_ROOT, "src", "wizards_engine", "schemas", "__init__.py")
    assert os.path.isfile(schemas_init), f"Missing: {schemas_init}"


def test_pyproject_requires_python_311():
    """pyproject.toml must declare requires-python >= 3.11."""
    pyproject = os.path.join(_REPO_ROOT, "pyproject.toml")
    with open(pyproject) as f:
        content = f.read()
    assert 'requires-python = ">=3.11"' in content, (
        "pyproject.toml must have requires-python = \">=3.11\""
    )


def test_single_migration_file():
    """There must be exactly one migration file in alembic/versions/."""
    versions_dir = os.path.join(_REPO_ROOT, "alembic", "versions")
    migration_files = [
        f for f in os.listdir(versions_dir)
        if f.endswith(".py") and not f.startswith("__")
    ]
    assert len(migration_files) == 1, (
        f"Expected 1 migration file, found {len(migration_files)}: {migration_files}"
    )


# ---------------------------------------------------------------------------
# Story 1.1.2 — Alembic configured to read Base.metadata
# ---------------------------------------------------------------------------


def test_alembic_env_imports_base_metadata():
    """alembic/env.py must assign Base.metadata to target_metadata."""
    env_py = os.path.join(_REPO_ROOT, "alembic", "env.py")
    with open(env_py) as f:
        content = f.read()
    assert "target_metadata = Base.metadata" in content, (
        "alembic/env.py must set target_metadata = Base.metadata"
    )


def test_alembic_env_imports_all_models():
    """alembic/env.py must import wizards_engine.models to populate the mapper registry."""
    env_py = os.path.join(_REPO_ROOT, "alembic", "env.py")
    with open(env_py) as f:
        content = f.read()
    assert "wizards_engine.models" in content, (
        "alembic/env.py must import wizards_engine.models so all 18 models are registered"
    )


# ---------------------------------------------------------------------------
# Story 1.1.3 — Column types in the migrated schema
# ---------------------------------------------------------------------------


def _col_types(db_path: str, table: str) -> dict[str, str]:
    """Return {column_name: type_string} for a table."""
    from sqlalchemy import create_engine, inspect as sa_inspect
    engine = create_engine(f"sqlite:///{db_path}")
    insp = sa_inspect(engine)
    result = {c["name"]: str(c["type"]) for c in insp.get_columns(table)}
    engine.dispose()
    return result


@pytest.fixture(scope="module")
def migrated_db(tmp_path_factory):
    """A temporary SQLite database with the full migration applied."""
    import os
    from alembic import command
    from alembic.config import Config

    db_path = str(tmp_path_factory.mktemp("migration") / "schema_types.db")
    cfg = Config(os.path.join(_REPO_ROOT, "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    os.environ["WIZARDS_DB_PATH"] = db_path
    command.upgrade(cfg, "head")
    return db_path


def test_users_ulid_pk_is_text(migrated_db):
    """users.id must be TEXT (ULID stored as TEXT)."""
    types = _col_types(migrated_db, "users")
    assert types["id"].upper().startswith("VARCHAR") or types["id"].upper() == "TEXT", (
        f"users.id expected TEXT/VARCHAR, got {types['id']}"
    )


def test_characters_stress_is_integer(migrated_db):
    """characters.stress must be INTEGER."""
    types = _col_types(migrated_db, "characters")
    assert "INTEGER" in types["stress"].upper(), (
        f"characters.stress expected INTEGER, got {types['stress']}"
    )


def test_characters_skills_is_json(migrated_db):
    """characters.skills must be JSON type."""
    types = _col_types(migrated_db, "characters")
    assert "JSON" in types["skills"].upper(), (
        f"characters.skills expected JSON, got {types['skills']}"
    )


def test_characters_attributes_is_json(migrated_db):
    """characters.attributes must be JSON type."""
    types = _col_types(migrated_db, "characters")
    assert "JSON" in types["attributes"].upper(), (
        f"characters.attributes expected JSON, got {types['attributes']}"
    )


def test_characters_is_deleted_is_boolean(migrated_db):
    """characters.is_deleted must be BOOLEAN."""
    types = _col_types(migrated_db, "characters")
    assert "BOOLEAN" in types["is_deleted"].upper(), (
        f"characters.is_deleted expected BOOLEAN, got {types['is_deleted']}"
    )


def test_sessions_date_is_date(migrated_db):
    """sessions.date must be DATE type."""
    types = _col_types(migrated_db, "sessions")
    assert "DATE" in types["date"].upper(), (
        f"sessions.date expected DATE, got {types['date']}"
    )


def test_events_created_at_is_datetime(migrated_db):
    """events.created_at must be DATETIME."""
    types = _col_types(migrated_db, "events")
    assert "DATETIME" in types["created_at"].upper() or "TIMESTAMP" in types["created_at"].upper(), (
        f"events.created_at expected DATETIME, got {types['created_at']}"
    )


def test_proposals_selections_is_json(migrated_db):
    """proposals.selections must be JSON."""
    types = _col_types(migrated_db, "proposals")
    assert "JSON" in types["selections"].upper(), (
        f"proposals.selections expected JSON, got {types['selections']}"
    )


def test_fk_magic_effects_character_id(migrated_db):
    """magic_effects.character_id must have a FK constraint to characters.id."""
    from sqlalchemy import create_engine, inspect as sa_inspect
    engine = create_engine(f"sqlite:///{migrated_db}")
    insp = sa_inspect(engine)
    fks = insp.get_foreign_keys("magic_effects")
    engine.dispose()
    fk_targets = [(fk["constrained_columns"], fk["referred_table"]) for fk in fks]
    assert (["character_id"], "characters") in fk_targets, (
        f"Expected FK magic_effects.character_id -> characters, found: {fk_targets}"
    )


def test_fk_slots_template_id(migrated_db):
    """slots.template_id must have a FK constraint to trait_templates.id."""
    from sqlalchemy import create_engine, inspect as sa_inspect
    engine = create_engine(f"sqlite:///{migrated_db}")
    insp = sa_inspect(engine)
    fks = insp.get_foreign_keys("slots")
    engine.dispose()
    fk_targets = [(fk["constrained_columns"], fk["referred_table"]) for fk in fks]
    assert (["template_id"], "trait_templates") in fk_targets, (
        f"Expected FK slots.template_id -> trait_templates, found: {fk_targets}"
    )


def test_fk_story_entries_author_id(migrated_db):
    """story_entries.author_id must have a FK constraint to users.id."""
    from sqlalchemy import create_engine, inspect as sa_inspect
    engine = create_engine(f"sqlite:///{migrated_db}")
    insp = sa_inspect(engine)
    fks = insp.get_foreign_keys("story_entries")
    engine.dispose()
    fk_targets = [(fk["constrained_columns"], fk["referred_table"]) for fk in fks]
    assert (["author_id"], "users") in fk_targets, (
        f"Expected FK story_entries.author_id -> users, found: {fk_targets}"
    )


def test_fk_users_character_id(migrated_db):
    """users.character_id must have a FK constraint to characters.id."""
    from sqlalchemy import create_engine, inspect as sa_inspect
    engine = create_engine(f"sqlite:///{migrated_db}")
    insp = sa_inspect(engine)
    fks = insp.get_foreign_keys("users")
    engine.dispose()
    fk_targets = [(fk["constrained_columns"], fk["referred_table"]) for fk in fks]
    assert (["character_id"], "characters") in fk_targets, (
        f"Expected FK users.character_id -> characters, found: {fk_targets}"
    )


def test_fk_proposals_clock_id(migrated_db):
    """proposals.clock_id must have a FK constraint to clocks.id."""
    from sqlalchemy import create_engine, inspect as sa_inspect
    engine = create_engine(f"sqlite:///{migrated_db}")
    insp = sa_inspect(engine)
    fks = insp.get_foreign_keys("proposals")
    engine.dispose()
    fk_targets = [(fk["constrained_columns"], fk["referred_table"]) for fk in fks]
    assert (["clock_id"], "clocks") in fk_targets, (
        f"Expected FK proposals.clock_id -> clocks, found: {fk_targets}"
    )


def test_fk_events_parent_event_id(migrated_db):
    """events.parent_event_id must have a self-referential FK to events.id."""
    from sqlalchemy import create_engine, inspect as sa_inspect
    engine = create_engine(f"sqlite:///{migrated_db}")
    insp = sa_inspect(engine)
    fks = insp.get_foreign_keys("events")
    engine.dispose()
    fk_targets = [(fk["constrained_columns"], fk["referred_table"]) for fk in fks]
    assert (["parent_event_id"], "events") in fk_targets, (
        f"Expected self-ref FK events.parent_event_id -> events, found: {fk_targets}"
    )


# ---------------------------------------------------------------------------
# Story 1.1.4 — ORM relationship traversal
# ---------------------------------------------------------------------------


def test_orm_user_character_relationship(db_session):
    """User.character relationship navigates to the linked Character."""
    char = Character(name="Linked Char", detail_level="full")
    db_session.add(char)
    db_session.flush()

    user = User(display_name="Player", role="player", login_code=_new_ulid(), character_id=char.id)
    db_session.add(user)
    db_session.flush()

    found_user = db_session.get(User, user.id)
    assert found_user.character is not None
    assert found_user.character.name == "Linked Char"


def test_orm_character_user_back_ref(db_session):
    """Character.user back-ref navigates to the owning User."""
    char = Character(name="Char With User", detail_level="full")
    db_session.add(char)
    db_session.flush()

    user = User(display_name="Back-ref Player", role="player", login_code=_new_ulid(), character_id=char.id)
    db_session.add(user)
    db_session.flush()

    found_char = db_session.get(Character, char.id)
    assert found_char.user is not None
    assert found_char.user.display_name == "Back-ref Player"


def test_orm_character_magic_effects_relationship(db_session):
    """Character.magic_effects navigates to all linked MagicEffects."""
    char = Character(name="Magic User", detail_level="full")
    db_session.add(char)
    db_session.flush()

    e1 = MagicEffect(character_id=char.id, name="Glow", description="Faint glow.", effect_type="permanent", power_level=1)
    e2 = MagicEffect(character_id=char.id, name="Haste", description="Move faster.", effect_type="charged", power_level=3)
    db_session.add_all([e1, e2])
    db_session.flush()

    found = db_session.get(Character, char.id)
    effect_names = {e.name for e in found.magic_effects}
    assert "Glow" in effect_names
    assert "Haste" in effect_names


def test_orm_story_parent_children_relationship(db_session):
    """Story.parent and Story.children self-referential relationships work."""
    parent = Story(name="Main Arc", status="active")
    db_session.add(parent)
    db_session.flush()

    child1 = Story(name="Sub Arc 1", status="active", parent_id=parent.id)
    child2 = Story(name="Sub Arc 2", status="active", parent_id=parent.id)
    db_session.add_all([child1, child2])
    db_session.flush()

    # Expire to force reload from DB.
    db_session.expire_all()

    found_parent = db_session.get(Story, parent.id)
    child_names = {c.name for c in found_parent.children}
    assert "Sub Arc 1" in child_names
    assert "Sub Arc 2" in child_names

    found_child = db_session.get(Story, child1.id)
    assert found_child.parent is not None
    assert found_child.parent.name == "Main Arc"


def test_orm_story_entries_relationship(db_session):
    """Story.entries navigates to all linked StoryEntries."""
    story = Story(name="Entry Relationship Story", status="active")
    author = User(display_name="Writer", role="player", login_code=_new_ulid())
    db_session.add_all([story, author])
    db_session.flush()

    entry = StoryEntry(story_id=story.id, text="Once upon a time.", author_id=author.id)
    db_session.add(entry)
    db_session.flush()
    db_session.expire_all()

    found_story = db_session.get(Story, story.id)
    assert len(found_story.entries) == 1
    assert found_story.entries[0].text == "Once upon a time."


def test_orm_story_owners_relationship(db_session):
    """Story.owners navigates to all linked StoryOwners."""
    story = Story(name="Owned Story", status="active")
    db_session.add(story)
    db_session.flush()

    owner = StoryOwner(story_id=story.id, owner_type="character", owner_id=_new_ulid())
    db_session.add(owner)
    db_session.flush()
    db_session.expire_all()

    found_story = db_session.get(Story, story.id)
    assert len(found_story.owners) == 1
    assert found_story.owners[0].owner_type == "character"


def test_orm_location_parent_children_relationship(db_session):
    """Location.parent and Location.children self-referential relationships work."""
    city = Location(name="Vellum City")
    db_session.add(city)
    db_session.flush()

    district = Location(name="Old Quarter", parent_id=city.id)
    db_session.add(district)
    db_session.flush()
    db_session.expire_all()

    found_city = db_session.get(Location, city.id)
    assert len(found_city.children) == 1
    assert found_city.children[0].name == "Old Quarter"

    found_district = db_session.get(Location, district.id)
    assert found_district.parent is not None
    assert found_district.parent.name == "Vellum City"


def test_orm_event_parent_event_relationship(db_session):
    """Event.parent_event and Event.rider_events self-referential relationships work."""
    parent_event = Event(
        type="proposal.approved",
        actor_type="gm",
        changes={},
        visibility="familiar",
    )
    db_session.add(parent_event)
    db_session.flush()

    rider = Event(
        type="character.stress_changed",
        actor_type="system",
        changes={},
        visibility="familiar",
        parent_event_id=parent_event.id,
    )
    db_session.add(rider)
    db_session.flush()
    db_session.expire_all()

    found_parent = db_session.get(Event, parent_event.id)
    assert len(found_parent.rider_events) == 1
    assert found_parent.rider_events[0].type == "character.stress_changed"

    found_rider = db_session.get(Event, rider.id)
    assert found_rider.parent_event is not None
    assert found_rider.parent_event.type == "proposal.approved"


def test_orm_event_targets_relationship(db_session):
    """Event.targets navigates to all linked EventTargets."""
    event = Event(
        type="character.plot_changed",
        actor_type="gm",
        changes={},
        visibility="public",
    )
    db_session.add(event)
    db_session.flush()

    t1 = EventTarget(event_id=event.id, target_type="character", target_id=_new_ulid(), is_primary=True)
    t2 = EventTarget(event_id=event.id, target_type="group", target_id=_new_ulid(), is_primary=False)
    db_session.add_all([t1, t2])
    db_session.flush()
    db_session.expire_all()

    found_event = db_session.get(Event, event.id)
    assert len(found_event.targets) == 2
    primary_targets = [t for t in found_event.targets if t.is_primary]
    assert len(primary_targets) == 1


def test_orm_session_participants_relationship(db_session):
    """Session.participants navigates to all linked SessionParticipants."""
    sess = Session(status="draft")
    char = Character(name="Session Member", detail_level="simplified")
    db_session.add_all([sess, char])
    db_session.flush()

    p = SessionParticipant(session_id=sess.id, character_id=char.id)
    db_session.add(p)
    db_session.flush()
    db_session.expire_all()

    found_session = db_session.get(Session, sess.id)
    assert len(found_session.participants) == 1
    assert found_session.participants[0].character_id == char.id


# ---------------------------------------------------------------------------
# Story 1.1.4 — JSON column types on ORM models
# ---------------------------------------------------------------------------


def test_json_column_type_characters_skills(insp):
    """characters.skills must use SQLAlchemy JSON type."""
    col = Character.__table__.c["skills"]
    assert isinstance(col.type, SA_JSON), (
        f"characters.skills should be JSON, got {type(col.type)}"
    )


def test_json_column_type_characters_magic_stats(insp):
    """characters.magic_stats must use SQLAlchemy JSON type."""
    col = Character.__table__.c["magic_stats"]
    assert isinstance(col.type, SA_JSON), (
        f"characters.magic_stats should be JSON, got {type(col.type)}"
    )


def test_json_column_type_characters_attributes(insp):
    """characters.attributes must use SQLAlchemy JSON type."""
    col = Character.__table__.c["attributes"]
    assert isinstance(col.type, SA_JSON), (
        f"characters.attributes should be JSON, got {type(col.type)}"
    )


def test_json_column_type_proposals_selections(insp):
    """proposals.selections must use SQLAlchemy JSON type."""
    col = Proposal.__table__.c["selections"]
    assert isinstance(col.type, SA_JSON), (
        f"proposals.selections should be JSON, got {type(col.type)}"
    )


def test_json_column_type_events_changes(insp):
    """events.changes must use SQLAlchemy JSON type."""
    col = Event.__table__.c["changes"]
    assert isinstance(col.type, SA_JSON), (
        f"events.changes should be JSON, got {type(col.type)}"
    )


def test_json_column_type_stories_tags(insp):
    """stories.tags must use SQLAlchemy JSON type."""
    col = Story.__table__.c["tags"]
    assert isinstance(col.type, SA_JSON), (
        f"stories.tags should be JSON, got {type(col.type)}"
    )
