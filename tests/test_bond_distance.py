"""Tests for CR-013 — bond_distance field in entity detail responses.

Verifies that GET /api/v1/characters/{id}, GET /api/v1/groups/{id}, and
GET /api/v1/locations/{id} return a correct ``bond_distance`` value based on
the requesting user's position in the bond graph.

| Value | Meaning                                                        |
|-------|----------------------------------------------------------------|
| null  | Caller is GM, Viewer, or has no character — full detail always |
| 0     | Entity is the caller's own character                           |
| 1     | 1-hop (bonded)                                                 |
| 2     | 2-hop (familiar)                                               |
| 3     | 3-hop (public)                                                 |
| 4     | Beyond 3 hops (unreachable in bond graph)                      |

Seed data recap (from tests/fixtures.py):
  - pc1 → group (bidirectional bond)
  - pc2 → group (bidirectional bond)
  - npc1 → region (one-way bond)
  - npc2 → district (one-way bond)
  - pc3 has NO bonds
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as DBSession

from tests.conftest import auth_as
from wizards_engine.models.character import Character
from wizards_engine.models.slot import Slot


# ---------------------------------------------------------------------------
# Bond helper (mirrors the one in test_visibility.py)
# ---------------------------------------------------------------------------


def _bond(
    db: DBSession,
    owner_type: str,
    owner_id: str,
    target_type: str,
    target_id: str,
    *,
    bidirectional: bool = True,
    is_active: bool = True,
    slot_type: str | None = None,
) -> Slot:
    """Insert a bond slot directly into the test database."""
    if slot_type is None:
        if owner_type == "character":
            obj = db.get(Character, owner_id)
            slot_type = "pc_bond" if (obj and obj.detail_level == "full") else "npc_bond"
        elif owner_type == "group":
            slot_type = "group_holding" if target_type == "location" else "group_relation"
        else:
            slot_type = "location_bond"

    slot = Slot(
        slot_type=slot_type,
        owner_type=owner_type,
        owner_id=owner_id,
        target_type=target_type,
        target_id=target_id,
        name="test bond",
        bidirectional=bidirectional,
        is_active=is_active,
    )
    if slot_type == "pc_bond":
        slot.charges = 0
        slot.degradations = 0
        slot.is_trauma = False
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return slot


# ===========================================================================
# Character detail — bond_distance
# ===========================================================================


def test_gm_gets_null_bond_distance_on_character(client: TestClient, seed_data: dict) -> None:
    """GM viewing any character should receive bond_distance: null."""
    gm = seed_data["gm"]
    npc1 = seed_data["npc1"]

    auth_as(client, gm)
    resp = client.get(f"/api/v1/characters/{npc1.id}")

    assert resp.status_code == 200
    assert resp.json()["bond_distance"] is None


def test_viewer_gets_null_bond_distance_on_character(client: TestClient, seed_data: dict) -> None:
    """Viewer (has_full_visibility) viewing a character should receive bond_distance: null."""
    viewer = seed_data["viewer"]
    npc1 = seed_data["npc1"]

    auth_as(client, viewer)
    resp = client.get(f"/api/v1/characters/{npc1.id}")

    assert resp.status_code == 200
    assert resp.json()["bond_distance"] is None


def test_own_character_gets_zero_bond_distance(client: TestClient, seed_data: dict) -> None:
    """Player viewing their own character should receive bond_distance: 0."""
    player1 = seed_data["player1"]
    pc1 = seed_data["pc1"]

    auth_as(client, player1)
    resp = client.get(f"/api/v1/characters/{pc1.id}")

    assert resp.status_code == 200
    assert resp.json()["bond_distance"] == 0


def test_directly_bonded_character_gets_one(
    client: TestClient, db: DBSession, seed_data: dict
) -> None:
    """Player viewing a character with a direct bond gets bond_distance: 1."""
    player1 = seed_data["player1"]
    pc1 = seed_data["pc1"]
    npc1 = seed_data["npc1"]

    # Add a direct bond from pc1 → npc1
    _bond(db, "character", pc1.id, "character", npc1.id, slot_type="npc_bond")

    auth_as(client, player1)
    resp = client.get(f"/api/v1/characters/{npc1.id}")

    assert resp.status_code == 200
    assert resp.json()["bond_distance"] == 1


def test_unreachable_character_gets_four(client: TestClient, seed_data: dict) -> None:
    """Player with no bonds viewing any character gets bond_distance: 4."""
    player3 = seed_data["player3"]
    npc1 = seed_data["npc1"]

    auth_as(client, player3)
    resp = client.get(f"/api/v1/characters/{npc1.id}")

    assert resp.status_code == 200
    assert resp.json()["bond_distance"] == 4


# ===========================================================================
# Group detail — bond_distance
# ===========================================================================


def test_gm_gets_null_on_group(client: TestClient, seed_data: dict) -> None:
    """GM viewing a group should receive bond_distance: null."""
    gm = seed_data["gm"]
    group = seed_data["group"]

    auth_as(client, gm)
    resp = client.get(f"/api/v1/groups/{group.id}")

    assert resp.status_code == 200
    assert resp.json()["bond_distance"] is None


def test_bonded_group_gets_one(client: TestClient, seed_data: dict) -> None:
    """Player with a direct bond to the group gets bond_distance: 1.

    Seed data: pc1 has a bidirectional bond to group, so group is 1-hop from pc1.
    """
    player1 = seed_data["player1"]
    group = seed_data["group"]

    auth_as(client, player1)
    resp = client.get(f"/api/v1/groups/{group.id}")

    assert resp.status_code == 200
    assert resp.json()["bond_distance"] == 1


def test_unreachable_group_gets_four(client: TestClient, seed_data: dict) -> None:
    """Player with no bonds viewing the group gets bond_distance: 4."""
    player3 = seed_data["player3"]
    group = seed_data["group"]

    auth_as(client, player3)
    resp = client.get(f"/api/v1/groups/{group.id}")

    assert resp.status_code == 200
    assert resp.json()["bond_distance"] == 4


# ===========================================================================
# Location detail — bond_distance
# ===========================================================================


def test_gm_gets_null_on_location(client: TestClient, seed_data: dict) -> None:
    """GM viewing a location should receive bond_distance: null."""
    gm = seed_data["gm"]
    region = seed_data["region"]

    auth_as(client, gm)
    resp = client.get(f"/api/v1/locations/{region.id}")

    assert resp.status_code == 200
    assert resp.json()["bond_distance"] is None


def test_unreachable_location_gets_four(client: TestClient, seed_data: dict) -> None:
    """Player with no bonds viewing a location gets bond_distance: 4."""
    player3 = seed_data["player3"]
    region = seed_data["region"]

    auth_as(client, player3)
    resp = client.get(f"/api/v1/locations/{region.id}")

    assert resp.status_code == 200
    assert resp.json()["bond_distance"] == 4
