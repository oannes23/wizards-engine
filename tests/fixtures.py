"""Canonical seed data factory for integration tests.

Call ``seed_data(db)`` to populate a test database with a representative,
self-consistent set of entities.  The returned dict is keyed by role/name so
tests can reference specific objects without knowing their generated IDs.

Seed contents
-------------
Users:
  ``gm``        — 1 GM user (display_name: "Test GM", role: "gm")
  ``player1``   — Player 1 user linked to character ``pc1``
  ``player2``   — Player 2 user linked to character ``pc2``
  ``player3``   — Player 3 user linked to character ``pc3``

Characters:
  ``pc1``       — Full character (Player 1's PC)
  ``pc2``       — Full character (Player 2's PC)
  ``pc3``       — Full character (Player 3's PC)
  ``npc1``      — Simplified character (NPC)
  ``npc2``      — Simplified character (NPC)

World objects:
  ``group``     — 1 Group (tier=2, "The Syndicate")
  ``region``    — Parent location ("The Shattered Coast")
  ``district``  — Child location nested under ``region`` ("Old Quarter")

Slots:
  ``pc1_bond``  — pc_bond: pc1 → group
  ``pc2_bond``  — pc_bond: pc2 → group
  ``npc1_bond`` — npc_bond: npc1 → region
  ``npc2_bond`` — npc_bond: npc2 → district
"""

import secrets

from sqlalchemy.orm import Session

from wizards_engine.models.character import Character
from wizards_engine.models.group import Group
from wizards_engine.models.location import Location
from wizards_engine.models.slot import Slot
from wizards_engine.models.user import User

# ---------------------------------------------------------------------------
# Full-character stat block defaults
# ---------------------------------------------------------------------------

_FULL_SKILLS = {
    "awareness": 0,
    "composure": 0,
    "influence": 0,
    "finesse": 0,
    "speed": 0,
    "power": 0,
    "knowledge": 0,
    "technology": 0,
}

_FULL_MAGIC_STATS = {
    "being": {"level": 0, "xp": 0},
    "wyrding": {"level": 0, "xp": 0},
    "summoning": {"level": 0, "xp": 0},
    "enchanting": {"level": 0, "xp": 0},
    "dreaming": {"level": 0, "xp": 0},
}


def _full_character(name: str) -> Character:
    """Return a new full (PC-level) Character with all meter/skill columns set."""
    return Character(
        name=name,
        detail_level="full",
        stress=0,
        free_time=0,
        plot=0,
        gnosis=0,
        skills=dict(_FULL_SKILLS),
        magic_stats={k: dict(v) for k, v in _FULL_MAGIC_STATS.items()},
        last_session_time_now=0,
    )


def _simplified_character(name: str) -> Character:
    """Return a new simplified (NPC-level) Character with meter/skill columns as None."""
    return Character(
        name=name,
        detail_level="simplified",
        # All meter/skill/magic columns remain None (simplified NPC)
    )


def seed_data(db: Session) -> dict:
    """Populate *db* with canonical seed data and return a reference dict.

    All objects are committed before this function returns.  The caller
    receives a dict whose keys map to the created ORM instances so tests can
    look up IDs and attributes without hard-coding values.

    Args:
        db: An open SQLAlchemy Session bound to the test database.

    Returns:
        A dict with keys: ``gm``, ``player1``, ``player2``, ``player3``,
        ``pc1``, ``pc2``, ``pc3``, ``npc1``, ``npc2``, ``group``,
        ``region``, ``district``, ``pc1_bond``, ``pc2_bond``,
        ``npc1_bond``, ``npc2_bond``.
    """
    # ------------------------------------------------------------------
    # Characters — create before users (FK: users.character_id → characters.id)
    # ------------------------------------------------------------------
    pc1 = _full_character("Player One's Character")
    pc2 = _full_character("Player Two's Character")
    pc3 = _full_character("Player Three's Character")
    npc1 = _simplified_character("The Archivist")
    npc2 = _simplified_character("The Harbour Master")

    db.add_all([pc1, pc2, pc3, npc1, npc2])
    db.flush()  # populate IDs before FK references below

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------
    gm = User(
        display_name="Test GM",
        role="gm",
        login_code=secrets.token_urlsafe(32),
        is_active=True,
    )
    player1 = User(
        display_name="Player 1",
        role="player",
        login_code=secrets.token_urlsafe(32),
        is_active=True,
        character_id=pc1.id,
    )
    player2 = User(
        display_name="Player 2",
        role="player",
        login_code=secrets.token_urlsafe(32),
        is_active=True,
        character_id=pc2.id,
    )
    player3 = User(
        display_name="Player 3",
        role="player",
        login_code=secrets.token_urlsafe(32),
        is_active=True,
        character_id=pc3.id,
    )

    db.add_all([gm, player1, player2, player3])
    db.flush()

    # ------------------------------------------------------------------
    # World objects — Group and Locations
    # ------------------------------------------------------------------
    group = Group(
        name="The Syndicate",
        tier=2,
    )
    region = Location(
        name="The Shattered Coast",
    )

    db.add_all([group, region])
    db.flush()  # region.id must exist before district references it

    district = Location(
        name="Old Quarter",
        parent_id=region.id,
    )

    db.add(district)
    db.flush()

    # ------------------------------------------------------------------
    # Slots — bonds linking characters/NPCs to world objects
    # ------------------------------------------------------------------
    pc1_bond = Slot(
        slot_type="pc_bond",
        owner_type="character",
        owner_id=pc1.id,
        target_type="group",
        target_id=group.id,
        name="Syndicate Contact",
        description="A reliable back-channel to the inner circle.",
        stress=0,
        stress_degradations=0,
        is_trauma=False,
        bidirectional=False,
    )
    pc2_bond = Slot(
        slot_type="pc_bond",
        owner_type="character",
        owner_id=pc2.id,
        target_type="group",
        target_id=group.id,
        name="Old Debt",
        description="They once pulled me out of a very deep hole.",
        stress=0,
        stress_degradations=0,
        is_trauma=False,
        bidirectional=False,
    )
    npc1_bond = Slot(
        slot_type="npc_bond",
        owner_type="character",
        owner_id=npc1.id,
        target_type="location",
        target_id=region.id,
        name="Guardian of the Coast",
        description="Watches over the old archives along the shoreline.",
        bidirectional=False,
    )
    npc2_bond = Slot(
        slot_type="npc_bond",
        owner_type="character",
        owner_id=npc2.id,
        target_type="location",
        target_id=district.id,
        name="Quartermaster's Domain",
        description="Controls the flow of goods through the Old Quarter.",
        bidirectional=False,
    )

    db.add_all([pc1_bond, pc2_bond, npc1_bond, npc2_bond])
    db.commit()

    # Refresh all objects so callers can access .id and other DB-generated attrs.
    for obj in [
        gm, player1, player2, player3,
        pc1, pc2, pc3, npc1, npc2,
        group, region, district,
        pc1_bond, pc2_bond, npc1_bond, npc2_bond,
    ]:
        db.refresh(obj)

    return {
        "gm": gm,
        "player1": player1,
        "player2": player2,
        "player3": player3,
        "pc1": pc1,
        "pc2": pc2,
        "pc3": pc3,
        "npc1": npc1,
        "npc2": npc2,
        "group": group,
        "region": region,
        "district": district,
        "pc1_bond": pc1_bond,
        "pc2_bond": pc2_bond,
        "npc1_bond": npc1_bond,
        "npc2_bond": npc2_bond,
    }
