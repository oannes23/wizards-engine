"""Tests that verify fixture system isolation properties (Story 1.2.5).

These tests confirm:
- Each test gets a completely fresh in-memory engine (no cross-test data leakage).
- The ``db`` fixture exposes a live, committing session that the TestClient can read.
- The ``seed_data`` fixture populates all expected entities with correct types/IDs.
- The ``auth_as`` helper correctly switches identity between calls.
- An unauthenticated client gets the right 401 error shape.
- The seed database contains exactly the expected row counts.

Isolation is proven indirectly: two tests that each write unique data cannot
see each other's data.  Because each ``db_engine`` fixture call creates a
distinct ``sqlite:///:memory:`` engine with ``StaticPool``, the in-memory
databases are completely separate processes of the same SQLite library and
share no storage.  Any data leak would show up as unexpected rows when
querying counts after seed.
"""

from sqlalchemy import text

from tests.conftest import auth_as
from wizards_engine.models.user import User
from wizards_engine.models.character import Character
from wizards_engine.models.group import Group
from wizards_engine.models.location import Location
from wizards_engine.models.slot import Slot


# ---------------------------------------------------------------------------
# Isolation: consecutive tests do not share state
# ---------------------------------------------------------------------------

# We use a module-level list to capture the engine id from each test.  If two
# tests shared an engine the same id would appear twice.
_seen_engine_ids: list[int] = []


def test_isolation_first_write(db_engine, db):
    """Write a sentinel row; record the engine identity."""
    _seen_engine_ids.append(id(db_engine))

    extra_user = User(
        display_name="Sentinel A",
        role="player",
        login_code="sentinel-code-aaa",
        is_active=True,
    )
    db.add(extra_user)
    db.commit()

    count = db.query(User).filter_by(display_name="Sentinel A").count()
    assert count == 1


def test_isolation_second_write(db_engine, db):
    """Write a different sentinel row; confirm the first test's row is absent."""
    _seen_engine_ids.append(id(db_engine))

    # The first test's sentinel must NOT be visible in this isolated DB.
    count_a = db.query(User).filter_by(display_name="Sentinel A").count()
    assert count_a == 0, (
        "Found Sentinel A row — engine isolation broken between tests"
    )

    extra_user = User(
        display_name="Sentinel B",
        role="player",
        login_code="sentinel-code-bbb",
        is_active=True,
    )
    db.add(extra_user)
    db.commit()

    count_b = db.query(User).filter_by(display_name="Sentinel B").count()
    assert count_b == 1


def test_isolation_engines_are_distinct():
    """Verify the two prior tests received different engine objects."""
    assert len(_seen_engine_ids) == 2, (
        "Expected exactly 2 engine ids recorded by the sentinel tests"
    )
    assert _seen_engine_ids[0] != _seen_engine_ids[1], (
        "Both sentinel tests received the same engine — isolation broken"
    )


# ---------------------------------------------------------------------------
# Seed data row counts
# ---------------------------------------------------------------------------


def test_seed_data_user_count(db, seed_data):
    """seed_data creates exactly 4 users: 1 GM + 3 players."""
    total = db.query(User).count()
    assert total == 4


def test_seed_data_character_count(db, seed_data):
    """seed_data creates exactly 5 characters: 3 full + 2 simplified."""
    total = db.query(Character).count()
    assert total == 5

    full_count = db.query(Character).filter_by(detail_level="full").count()
    simplified_count = db.query(Character).filter_by(detail_level="simplified").count()
    assert full_count == 3
    assert simplified_count == 2


def test_seed_data_group_count(db, seed_data):
    """seed_data creates exactly 1 Group."""
    total = db.query(Group).count()
    assert total == 1


def test_seed_data_location_count(db, seed_data):
    """seed_data creates exactly 2 Locations (region + district)."""
    total = db.query(Location).count()
    assert total == 2


def test_seed_data_slot_count(db, seed_data):
    """seed_data creates exactly 4 Slots (2 pc_bond + 2 npc_bond)."""
    total = db.query(Slot).count()
    assert total == 4

    pc_bonds = db.query(Slot).filter_by(slot_type="pc_bond").count()
    npc_bonds = db.query(Slot).filter_by(slot_type="npc_bond").count()
    assert pc_bonds == 2
    assert npc_bonds == 2


# ---------------------------------------------------------------------------
# Seed data — entity attributes
# ---------------------------------------------------------------------------


def test_seed_data_gm_has_no_character(db, seed_data):
    """The GM user has role='gm' and no linked character_id."""
    gm = seed_data["gm"]
    assert gm.role == "gm"
    assert gm.character_id is None


def test_seed_data_players_have_unique_characters(seed_data):
    """Each player is linked to a distinct full character."""
    character_ids = {
        seed_data["player1"].character_id,
        seed_data["player2"].character_id,
        seed_data["player3"].character_id,
    }
    # All three must be non-null and distinct.
    assert None not in character_ids
    assert len(character_ids) == 3


def test_seed_data_player1_character_id_matches_pc1(seed_data):
    """player1.character_id == pc1.id (FK integrity)."""
    assert seed_data["player1"].character_id == seed_data["pc1"].id


def test_seed_data_full_character_meters(seed_data):
    """Full characters (pc1–pc3) have all meter columns set to 0."""
    for key in ("pc1", "pc2", "pc3"):
        char = seed_data[key]
        assert char.stress == 0, f"{key}.stress should be 0"
        assert char.free_time == 0, f"{key}.free_time should be 0"
        assert char.plot == 0, f"{key}.plot should be 0"
        assert char.gnosis == 0, f"{key}.gnosis should be 0"


def test_seed_data_full_character_skills(seed_data):
    """Full characters have a skills dict with all 8 expected keys."""
    expected_skills = {
        "awareness", "composure", "influence", "finesse",
        "speed", "power", "knowledge", "technology",
    }
    for key in ("pc1", "pc2", "pc3"):
        char = seed_data[key]
        assert char.skills is not None, f"{key}.skills should not be None"
        assert set(char.skills.keys()) == expected_skills, (
            f"{key}.skills keys mismatch: {set(char.skills.keys())}"
        )


def test_seed_data_full_character_magic_stats(seed_data):
    """Full characters have a magic_stats dict with all 5 schools."""
    expected_schools = {"being", "wyrding", "summoning", "enchanting", "dreaming"}
    for key in ("pc1", "pc2", "pc3"):
        char = seed_data[key]
        assert char.magic_stats is not None, f"{key}.magic_stats should not be None"
        assert set(char.magic_stats.keys()) == expected_schools, (
            f"{key}.magic_stats keys mismatch: {set(char.magic_stats.keys())}"
        )
        for school, stat in char.magic_stats.items():
            assert stat["level"] == 0, f"{key}.magic_stats[{school}].level should be 0"
            assert stat["xp"] == 0, f"{key}.magic_stats[{school}].xp should be 0"


def test_seed_data_simplified_characters_have_null_meters(seed_data):
    """Simplified NPCs have null meter, skill, and magic_stats columns."""
    for key in ("npc1", "npc2"):
        char = seed_data[key]
        assert char.stress is None, f"{key}.stress should be None"
        assert char.free_time is None, f"{key}.free_time should be None"
        assert char.plot is None, f"{key}.plot should be None"
        assert char.gnosis is None, f"{key}.gnosis should be None"
        assert char.skills is None, f"{key}.skills should be None"
        assert char.magic_stats is None, f"{key}.magic_stats should be None"


def test_seed_data_group_attributes(seed_data):
    """The seeded group has name='The Syndicate' and tier=2."""
    group = seed_data["group"]
    assert group.name == "The Syndicate"
    assert group.tier == 2


def test_seed_data_location_hierarchy(seed_data):
    """The district is nested under the region via parent_id."""
    region = seed_data["region"]
    district = seed_data["district"]
    assert region.parent_id is None
    assert district.parent_id == region.id


def test_seed_data_pc_bonds_point_to_group(seed_data):
    """pc1_bond and pc2_bond target the seeded group."""
    group_id = seed_data["group"].id
    assert seed_data["pc1_bond"].target_type == "group"
    assert seed_data["pc1_bond"].target_id == group_id
    assert seed_data["pc2_bond"].target_type == "group"
    assert seed_data["pc2_bond"].target_id == group_id


def test_seed_data_npc_bonds_point_to_locations(seed_data):
    """npc1_bond targets region; npc2_bond targets district."""
    assert seed_data["npc1_bond"].target_type == "location"
    assert seed_data["npc1_bond"].target_id == seed_data["region"].id
    assert seed_data["npc2_bond"].target_type == "location"
    assert seed_data["npc2_bond"].target_id == seed_data["district"].id


def test_seed_data_pc_bond_fields(seed_data):
    """pc_bond slots have stress=5 (full charges), stress_degradations=0, is_trauma=False."""
    for key in ("pc1_bond", "pc2_bond"):
        bond = seed_data[key]
        assert bond.stress == 5, f"{key}.stress should be 5 (full charges)"
        assert bond.stress_degradations == 0, f"{key}.stress_degradations should be 0"
        assert bond.is_trauma is False, f"{key}.is_trauma should be False"


def test_seed_data_all_entities_have_ids(seed_data):
    """Every seeded entity has a non-empty ULID id."""
    keys = [
        "gm", "player1", "player2", "player3",
        "pc1", "pc2", "pc3", "npc1", "npc2",
        "group", "region", "district",
        "pc1_bond", "pc2_bond", "npc1_bond", "npc2_bond",
    ]
    for key in keys:
        obj = seed_data[key]
        assert obj.id, f"seed_data['{key}'].id is falsy"
        assert len(obj.id) == 26, (
            f"seed_data['{key}'].id length {len(obj.id)} != 26 (expected ULID)"
        )


# ---------------------------------------------------------------------------
# auth_as helper — cookie switching
# ---------------------------------------------------------------------------


def test_auth_as_sets_gm_cookie(client, seed_data):
    """auth_as(client, gm) results in GET /me returning the GM's identity."""
    gm = seed_data["gm"]
    auth_as(client, gm)
    response = client.get("/api/v1/me")
    assert response.status_code == 200
    assert response.json()["id"] == gm.id
    assert response.json()["role"] == "gm"


def test_auth_as_can_switch_identity(client, seed_data):
    """Calling auth_as twice in one test replaces the prior cookie."""
    player1 = seed_data["player1"]
    player2 = seed_data["player2"]

    auth_as(client, player1)
    r1 = client.get("/api/v1/me")
    assert r1.status_code == 200
    assert r1.json()["id"] == player1.id

    auth_as(client, player2)
    r2 = client.get("/api/v1/me")
    assert r2.status_code == 200
    assert r2.json()["id"] == player2.id


def test_unauthenticated_request_returns_401_cookie_missing(client, seed_data):
    """A request with no cookie returns 401 with code=cookie_missing."""
    # Ensure no lingering cookie from a previous call.
    client.cookies.clear()
    response = client.get("/api/v1/me")
    assert response.status_code == 401
    body = response.json()
    assert "error" in body
    assert body["error"]["code"] == "cookie_missing"


# ---------------------------------------------------------------------------
# client fixture uses the same in-memory DB as db fixture
# ---------------------------------------------------------------------------


def test_client_sees_db_fixture_writes(client, db, seed_data):
    """Data written directly via the db session is visible to the TestClient."""
    # The seed_data GM exists in the db session — the client must be able to
    # authenticate as that user, proving the two share the same engine.
    gm = seed_data["gm"]
    auth_as(client, gm)
    response = client.get("/api/v1/me")
    assert response.status_code == 200
    assert response.json()["display_name"] == "Test GM"


def test_empty_db_has_no_users(db):
    """Without seed_data, a fresh db fixture contains zero users."""
    count = db.query(User).count()
    assert count == 0
