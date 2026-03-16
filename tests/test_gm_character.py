"""Tests for Story 3.1.3 — POST /api/v1/me/character (GM character creation).

Covers:
- GM can create a character via POST /me/character → 201 + CharacterResponse
- Name validation: stripped, 1–200 chars, non-empty
- Character is created as a full character (detail_level='full', all meters=0,
  skills and magic_stats initialised to zero)
- GM's character_id is updated to the new character's id
- If GM already has a character, the old character stays in DB as ownerless
  (no owner FK) and the new character is linked
- Player role is rejected with 403
- Unauthenticated request returns 401
"""

from tests.conftest import auth_as
from wizards_engine.models.character import Character
from wizards_engine.models.user import User

_URL = "/api/v1/me/character"


# ---------------------------------------------------------------------------
# Happy path — basic 201 response
# ---------------------------------------------------------------------------


def test_gm_create_character_returns_201(client, seed_data):
    """GM POST /me/character returns HTTP 201."""
    gm = seed_data["gm"]
    auth_as(client, gm)
    response = client.post(_URL, json={"name": "Seraphel"})
    assert response.status_code == 201


def test_gm_create_character_response_shape(client, seed_data):
    """Response contains id, name, detail_level, and other CharacterResponse fields."""
    gm = seed_data["gm"]
    auth_as(client, gm)
    response = client.post(_URL, json={"name": "Seraphel"})
    body = response.json()
    assert body["name"] == "Seraphel"
    assert body["detail_level"] == "full"
    assert "id" in body
    assert "is_deleted" in body
    assert "created_at" in body
    assert "updated_at" in body


def test_gm_create_character_links_to_gm(client, db, seed_data):
    """After creation, the GM user's character_id points to the new character."""
    gm = seed_data["gm"]
    auth_as(client, gm)
    response = client.post(_URL, json={"name": "Seraphel"})
    new_char_id = response.json()["id"]

    db.expire(gm)
    gm_refreshed = db.get(User, gm.id)
    assert gm_refreshed.character_id == new_char_id


def test_gm_create_character_full_detail_level(client, db, seed_data):
    """New GM character has detail_level='full'."""
    gm = seed_data["gm"]
    auth_as(client, gm)
    response = client.post(_URL, json={"name": "Seraphel"})
    char = db.get(Character, response.json()["id"])
    assert char.detail_level == "full"


def test_gm_create_character_meters_default_to_zero(client, db, seed_data):
    """New GM character has stress, free_time, plot, gnosis, and last_session_time_now all at 0."""
    gm = seed_data["gm"]
    auth_as(client, gm)
    response = client.post(_URL, json={"name": "Seraphel"})
    char = db.get(Character, response.json()["id"])
    assert char.stress == 0
    assert char.free_time == 0
    assert char.plot == 0
    assert char.gnosis == 0
    assert char.last_session_time_now == 0


def test_gm_create_character_skills_all_zero(client, db, seed_data):
    """New GM character has all 8 skills at level 0."""
    expected_skills = {
        "awareness", "composure", "influence", "finesse",
        "speed", "power", "knowledge", "technology",
    }
    gm = seed_data["gm"]
    auth_as(client, gm)
    response = client.post(_URL, json={"name": "Seraphel"})
    char = db.get(Character, response.json()["id"])
    assert char.skills is not None
    assert set(char.skills.keys()) == expected_skills
    for skill, level in char.skills.items():
        assert level == 0, f"skills[{skill}] should be 0"


def test_gm_create_character_magic_stats_all_zero(client, db, seed_data):
    """New GM character has all 5 magic stats at level=0 and xp=0."""
    expected_schools = {"being", "wyrding", "summoning", "enchanting", "dreaming"}
    gm = seed_data["gm"]
    auth_as(client, gm)
    response = client.post(_URL, json={"name": "Seraphel"})
    char = db.get(Character, response.json()["id"])
    assert char.magic_stats is not None
    assert set(char.magic_stats.keys()) == expected_schools
    for school, stat in char.magic_stats.items():
        assert stat["level"] == 0, f"magic_stats[{school}].level should be 0"
        assert stat["xp"] == 0, f"magic_stats[{school}].xp should be 0"


# ---------------------------------------------------------------------------
# Old character stays ownerless when GM already has one
# ---------------------------------------------------------------------------


def test_gm_replace_character_old_char_stays_in_db(client, db, seed_data):
    """When GM already has a character, the old one is NOT deleted after replacement."""
    gm = seed_data["gm"]
    auth_as(client, gm)

    # Give the GM a first character.
    r1 = client.post(_URL, json={"name": "First Character"})
    first_char_id = r1.json()["id"]

    # Create a second character.
    r2 = client.post(_URL, json={"name": "Second Character"})
    assert r2.status_code == 201

    # The first character record must still exist in the DB.
    old_char = db.get(Character, first_char_id)
    assert old_char is not None, "Old character should not have been deleted"


def test_gm_replace_character_old_char_has_no_owner(client, db, seed_data):
    """After replacement, no user's character_id points to the old character."""
    gm = seed_data["gm"]
    auth_as(client, gm)

    r1 = client.post(_URL, json={"name": "First Character"})
    first_char_id = r1.json()["id"]

    client.post(_URL, json={"name": "Second Character"})

    # No user should reference the old character.
    owner = db.query(User).filter(User.character_id == first_char_id).first()
    assert owner is None, "Old character should be ownerless after GM creates a new one"


def test_gm_replace_character_new_char_is_linked(client, db, seed_data):
    """After two creations, GM's character_id points to the second (latest) character."""
    gm = seed_data["gm"]
    auth_as(client, gm)

    client.post(_URL, json={"name": "First Character"})
    r2 = client.post(_URL, json={"name": "Second Character"})
    second_char_id = r2.json()["id"]

    db.expire(gm)
    gm_refreshed = db.get(User, gm.id)
    assert gm_refreshed.character_id == second_char_id


# ---------------------------------------------------------------------------
# Authorization errors
# ---------------------------------------------------------------------------


def test_player_cannot_create_character_via_gm_endpoint(client, seed_data):
    """A player calling POST /me/character receives 403."""
    player = seed_data["player1"]
    auth_as(client, player)
    response = client.post(_URL, json={"name": "ShouldFail"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "insufficient_role"


def test_unauthenticated_create_character_returns_401(client, seed_data):
    """An unauthenticated POST /me/character returns 401."""
    client.cookies.clear()
    response = client.post(_URL, json={"name": "ShouldFail"})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Name validation
# ---------------------------------------------------------------------------


def test_gm_create_character_empty_name_returns_422(client, seed_data):
    """An empty name after stripping returns 422."""
    gm = seed_data["gm"]
    auth_as(client, gm)
    response = client.post(_URL, json={"name": "   "})
    assert response.status_code == 422


def test_gm_create_character_name_too_long_returns_422(client, seed_data):
    """A name exceeding 200 characters returns 422."""
    gm = seed_data["gm"]
    auth_as(client, gm)
    response = client.post(_URL, json={"name": "X" * 201})
    assert response.status_code == 422


def test_gm_create_character_name_stripped(client, db, seed_data):
    """Name is stored stripped of surrounding whitespace."""
    gm = seed_data["gm"]
    auth_as(client, gm)
    response = client.post(_URL, json={"name": "  Seraphel  "})
    assert response.status_code == 201
    char = db.get(Character, response.json()["id"])
    assert char.name == "Seraphel"
