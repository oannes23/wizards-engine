"""Example test demonstrating the shared fixture system (Story 1.2.5).

Shows the canonical pattern for integration tests:

1. Declare ``client``, ``db``, and ``seed_data`` as fixtures.
2. Use ``auth_as(client, user)`` to authenticate as any seeded user.
3. Make HTTP requests via the TestClient and assert on the JSON response.

This file serves as a living reference — future tests should follow the
same pattern.
"""

from tests.conftest import auth_as


# ---------------------------------------------------------------------------
# GET /api/v1/me — authenticated as GM
# ---------------------------------------------------------------------------


def test_get_me_returns_gm_identity(client, seed_data):
    """Authenticated GET /me as the GM returns expected identity fields."""
    gm = seed_data["gm"]
    auth_as(client, gm)

    response = client.get("/api/v1/me")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == gm.id
    assert body["display_name"] == "Test GM"
    assert body["role"] == "gm"
    assert body["character_id"] is None


# ---------------------------------------------------------------------------
# GET /api/v1/me — authenticated as a player
# ---------------------------------------------------------------------------


def test_get_me_returns_player_identity_with_character_id(client, seed_data):
    """Authenticated GET /me as Player 1 returns their linked character_id."""
    player1 = seed_data["player1"]
    pc1 = seed_data["pc1"]
    auth_as(client, player1)

    response = client.get("/api/v1/me")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == player1.id
    assert body["display_name"] == "Player 1"
    assert body["role"] == "player"
    assert body["character_id"] == pc1.id


# ---------------------------------------------------------------------------
# GET /api/v1/me — unauthenticated
# ---------------------------------------------------------------------------


def test_get_me_returns_401_when_not_authenticated(client, seed_data):
    """GET /me without a cookie returns 401 cookie_missing."""
    response = client.get("/api/v1/me")

    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "cookie_missing"


# ---------------------------------------------------------------------------
# Seed data structure — verify canonical entities were created
# ---------------------------------------------------------------------------


def test_seed_data_contains_expected_entities(db, seed_data):
    """seed_data() creates all expected users, characters, world objects, and slots."""
    # Users
    assert seed_data["gm"].role == "gm"
    assert seed_data["player1"].display_name == "Player 1"
    assert seed_data["player2"].display_name == "Player 2"
    assert seed_data["player3"].display_name == "Player 3"

    # Full characters linked to players
    assert seed_data["pc1"].detail_level == "full"
    assert seed_data["pc2"].detail_level == "full"
    assert seed_data["pc3"].detail_level == "full"

    # Simplified NPCs
    assert seed_data["npc1"].detail_level == "simplified"
    assert seed_data["npc2"].detail_level == "simplified"
    assert seed_data["npc1"].stress is None
    assert seed_data["npc2"].skills is None

    # Group
    assert seed_data["group"].tier == 2

    # Locations — nested hierarchy
    district = seed_data["district"]
    region = seed_data["region"]
    assert district.parent_id == region.id

    # Slots
    assert seed_data["pc1_bond"].slot_type == "pc_bond"
    assert seed_data["pc1_bond"].target_id == seed_data["group"].id
    assert seed_data["pc2_bond"].slot_type == "pc_bond"
    assert seed_data["npc1_bond"].slot_type == "npc_bond"
    assert seed_data["npc1_bond"].target_id == region.id
    assert seed_data["npc2_bond"].slot_type == "npc_bond"
    assert seed_data["npc2_bond"].target_id == district.id
