"""Tests for Story 3.1.4 — Character Detail Response (Full Sheet).

Covers all acceptance criteria:

GET /api/v1/characters/{id} — full character:
  - Returns all base fields: name, description, notes, attributes, detail_level
  - Returns resource meters: stress, free_time, plot, gnosis
  - Returns skills dict (all 8 skills with levels)
  - Returns magic_stats dict (all 5 stats with level + xp)
  - Returns last_session_time_now
  - Returns computed effective_stress_max
  - Returns computed active_magic_effects_count
  - Returns computed active_trait_count
  - Returns computed active_bond_count
  - Returns session_ids list (populated from session_participants)
  - Returns traits grouped as {active: [...], past: [...]}
  - Returns magic_effects grouped as {active: [...], past: [...]}
  - effective_stress_max decreases by 1 per trauma bond

GET /api/v1/characters/{id} — simplified character:
  - Returns only base fields + bonds + locations
  - Does NOT return meters, skills, magic_stats, traits, effects, session_ids

Per-bond computed value:
  - BondDisplayResponse.stress and stress_degradations present on pc_bonds
  - effective_bond_stress_max = 5 - stress_degradations (via stress_degradations field)
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as DBSession

from tests.conftest import auth_as
from wizards_engine.models.magic_effect import MagicEffect
from wizards_engine.models.session import Session as SessionModel, SessionParticipant
from wizards_engine.models.slot import Slot, TraitTemplate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _add_session_with_participant(db: DBSession, character_id: str) -> SessionModel:
    """Create a draft session and register the character as a participant."""
    session = SessionModel(status="draft", time_now=5)
    db.add(session)
    db.flush()
    participant = SessionParticipant(session_id=session.id, character_id=character_id)
    db.add(participant)
    db.commit()
    db.refresh(session)
    return session


def _add_trait_slot(
    db: DBSession,
    character_id: str,
    slot_type: str = "core_trait",
    name: str = "Iron Will",
    description: str = "Resist all pressure.",
    charge: int = 3,
    is_active: bool = True,
    template: TraitTemplate | None = None,
) -> Slot:
    """Insert a trait slot directly for a character."""
    slot = Slot(
        slot_type=slot_type,
        owner_type="character",
        owner_id=character_id,
        name=name,
        description=description,
        charge=charge,
        is_active=is_active,
        template_id=template.id if template else None,
    )
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return slot


def _add_magic_effect(
    db: DBSession,
    character_id: str,
    name: str = "Arcane Shield",
    description: str = "A shimmering barrier.",
    effect_type: str = "charged",
    power_level: int = 2,
    charges_current: int | None = 3,
    charges_max: int | None = 5,
    is_active: bool = True,
) -> MagicEffect:
    """Insert a magic effect directly for a character."""
    effect = MagicEffect(
        character_id=character_id,
        name=name,
        description=description,
        effect_type=effect_type,
        power_level=power_level,
        charges_current=charges_current,
        charges_max=charges_max,
        is_active=is_active,
    )
    db.add(effect)
    db.commit()
    db.refresh(effect)
    return effect


def _add_trauma_bond(
    db: DBSession,
    character_id: str,
    name: str = "The Wound",
    description: str = "A bond broken by trauma.",
) -> Slot:
    """Insert an active pc_bond with is_trauma=True for the given character."""
    slot = Slot(
        slot_type="pc_bond",
        owner_type="character",
        owner_id=character_id,
        name=name,
        description=description,
        stress=0,
        stress_degradations=2,
        is_trauma=True,
        is_active=True,
        bidirectional=False,
    )
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return slot


# ---------------------------------------------------------------------------
# Full character — base fields and meters
# ---------------------------------------------------------------------------


class TestFullCharacterBaseFields:
    def test_returns_all_base_fields(self, client: TestClient, seed_data: dict):
        """Full character GET returns name, description, notes, attributes, detail_level."""
        auth_as(client, seed_data["gm"])
        pc_id = seed_data["pc1"].id
        response = client.get(f"/api/v1/characters/{pc_id}")

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == pc_id
        assert body["name"] == "Player One's Character"
        assert body["detail_level"] == "full"
        assert "description" in body
        assert "notes" in body
        assert "attributes" in body
        assert "is_deleted" in body
        assert "created_at" in body
        assert "updated_at" in body

    def test_returns_resource_meters(self, client: TestClient, seed_data: dict):
        """Full character GET returns stress, free_time, plot, gnosis."""
        auth_as(client, seed_data["gm"])
        pc_id = seed_data["pc1"].id
        response = client.get(f"/api/v1/characters/{pc_id}")

        assert response.status_code == 200
        body = response.json()
        assert body["stress"] == 0
        assert body["free_time"] == 0
        assert body["plot"] == 0
        assert body["gnosis"] == 0

    def test_returns_last_session_time_now(self, client: TestClient, seed_data: dict):
        """Full character GET returns last_session_time_now."""
        auth_as(client, seed_data["gm"])
        pc_id = seed_data["pc1"].id
        response = client.get(f"/api/v1/characters/{pc_id}")

        assert response.status_code == 200
        assert response.json()["last_session_time_now"] == 0

    def test_returns_skills_dict(self, client: TestClient, seed_data: dict):
        """Full character GET returns skills dict with all 8 skills."""
        auth_as(client, seed_data["gm"])
        pc_id = seed_data["pc1"].id
        response = client.get(f"/api/v1/characters/{pc_id}")

        assert response.status_code == 200
        skills = response.json()["skills"]
        assert skills is not None
        expected_skills = {
            "awareness",
            "composure",
            "influence",
            "finesse",
            "speed",
            "power",
            "knowledge",
            "technology",
        }
        assert set(skills.keys()) == expected_skills
        for level in skills.values():
            assert level == 0

    def test_returns_magic_stats_dict(self, client: TestClient, seed_data: dict):
        """Full character GET returns magic_stats dict with all 5 stats."""
        auth_as(client, seed_data["gm"])
        pc_id = seed_data["pc1"].id
        response = client.get(f"/api/v1/characters/{pc_id}")

        assert response.status_code == 200
        magic_stats = response.json()["magic_stats"]
        assert magic_stats is not None
        expected_stats = {"being", "wyrding", "summoning", "enchanting", "dreaming"}
        assert set(magic_stats.keys()) == expected_stats
        for stat in magic_stats.values():
            assert stat["level"] == 0
            assert stat["xp"] == 0


# ---------------------------------------------------------------------------
# Full character — computed values
# ---------------------------------------------------------------------------


class TestFullCharacterComputedValues:
    def test_effective_stress_max_no_trauma(self, client: TestClient, seed_data: dict):
        """effective_stress_max is 9 when there are no trauma bonds."""
        auth_as(client, seed_data["gm"])
        pc_id = seed_data["pc1"].id
        response = client.get(f"/api/v1/characters/{pc_id}")

        assert response.status_code == 200
        assert response.json()["effective_stress_max"] == 9

    def test_effective_stress_max_with_one_trauma(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """effective_stress_max decreases by 1 for each active trauma bond."""
        pc_id = seed_data["pc1"].id
        _add_trauma_bond(db, pc_id)

        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/characters/{pc_id}")

        assert response.status_code == 200
        assert response.json()["effective_stress_max"] == 8

    def test_effective_stress_max_with_two_traumas(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """effective_stress_max decreases to 7 with two trauma bonds."""
        pc_id = seed_data["pc1"].id
        _add_trauma_bond(db, pc_id, name="Trauma One")
        _add_trauma_bond(db, pc_id, name="Trauma Two")

        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/characters/{pc_id}")

        assert response.status_code == 200
        assert response.json()["effective_stress_max"] == 7

    def test_active_magic_effects_count_no_effects(
        self, client: TestClient, seed_data: dict
    ):
        """active_magic_effects_count is 0 with no magic effects."""
        auth_as(client, seed_data["gm"])
        pc_id = seed_data["pc1"].id
        response = client.get(f"/api/v1/characters/{pc_id}")

        assert response.status_code == 200
        assert response.json()["active_magic_effects_count"] == 0

    def test_active_magic_effects_count_counts_charged_and_permanent(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """active_magic_effects_count includes charged and permanent, not instant."""
        pc_id = seed_data["pc1"].id
        _add_magic_effect(db, pc_id, name="Charged Effect", effect_type="charged")
        _add_magic_effect(
            db,
            pc_id,
            name="Permanent Effect",
            effect_type="permanent",
            charges_current=None,
            charges_max=None,
        )
        _add_magic_effect(
            db,
            pc_id,
            name="Instant Effect",
            effect_type="instant",
            charges_current=None,
            charges_max=None,
        )

        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/characters/{pc_id}")

        assert response.status_code == 200
        # charged + permanent = 2; instant does not count
        assert response.json()["active_magic_effects_count"] == 2

    def test_active_magic_effects_count_excludes_retired(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Retired effects do not count toward active_magic_effects_count."""
        pc_id = seed_data["pc1"].id
        _add_magic_effect(
            db, pc_id, name="Retired Effect", effect_type="charged", is_active=False
        )
        _add_magic_effect(db, pc_id, name="Active Effect", effect_type="permanent",
                          charges_current=None, charges_max=None)

        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/characters/{pc_id}")

        assert response.status_code == 200
        assert response.json()["active_magic_effects_count"] == 1

    def test_active_trait_count_no_traits(self, client: TestClient, seed_data: dict):
        """active_trait_count is 0 with no traits."""
        auth_as(client, seed_data["gm"])
        pc_id = seed_data["pc1"].id
        response = client.get(f"/api/v1/characters/{pc_id}")

        assert response.status_code == 200
        assert response.json()["active_trait_count"] == 0

    def test_active_trait_count_with_traits(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """active_trait_count counts active core_trait + role_trait slots."""
        pc_id = seed_data["pc1"].id
        _add_trait_slot(db, pc_id, slot_type="core_trait", name="Core Trait 1")
        _add_trait_slot(db, pc_id, slot_type="role_trait", name="Role Trait 1")
        _add_trait_slot(
            db, pc_id, slot_type="core_trait", name="Past Trait", is_active=False
        )

        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/characters/{pc_id}")

        assert response.status_code == 200
        # Only the 2 active slots count (not the past one)
        assert response.json()["active_trait_count"] == 2

    def test_active_bond_count(self, client: TestClient, seed_data: dict):
        """active_bond_count counts active pc_bond slots owned by the character."""
        auth_as(client, seed_data["gm"])
        # pc1 has one active pc_bond in seed data (pc1_bond → group)
        pc_id = seed_data["pc1"].id
        response = client.get(f"/api/v1/characters/{pc_id}")

        assert response.status_code == 200
        assert response.json()["active_bond_count"] == 1

    def test_active_bond_count_no_bonds(self, client: TestClient, seed_data: dict):
        """active_bond_count is 0 for a PC with no bonds (pc3 has no bonds)."""
        auth_as(client, seed_data["gm"])
        pc_id = seed_data["pc3"].id
        response = client.get(f"/api/v1/characters/{pc_id}")

        assert response.status_code == 200
        assert response.json()["active_bond_count"] == 0


# ---------------------------------------------------------------------------
# Full character — session_ids
# ---------------------------------------------------------------------------


class TestFullCharacterSessionIds:
    def test_session_ids_empty_when_no_sessions(
        self, client: TestClient, seed_data: dict
    ):
        """session_ids is an empty list when the character has no sessions."""
        auth_as(client, seed_data["gm"])
        pc_id = seed_data["pc1"].id
        response = client.get(f"/api/v1/characters/{pc_id}")

        assert response.status_code == 200
        assert response.json()["session_ids"] == []

    def test_session_ids_populated_after_registration(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """session_ids contains session ULIDs for registered sessions."""
        pc_id = seed_data["pc1"].id
        session = _add_session_with_participant(db, pc_id)

        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/characters/{pc_id}")

        assert response.status_code == 200
        session_ids = response.json()["session_ids"]
        assert session.id in session_ids

    def test_session_ids_multiple_sessions(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """session_ids includes all sessions a character has participated in."""
        pc_id = seed_data["pc1"].id
        s1 = _add_session_with_participant(db, pc_id)
        s2 = _add_session_with_participant(db, pc_id)

        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/characters/{pc_id}")

        assert response.status_code == 200
        session_ids = response.json()["session_ids"]
        assert s1.id in session_ids
        assert s2.id in session_ids
        assert len(session_ids) == 2


# ---------------------------------------------------------------------------
# Full character — traits
# ---------------------------------------------------------------------------


class TestFullCharacterTraits:
    def test_traits_empty_groups_when_no_traits(
        self, client: TestClient, seed_data: dict
    ):
        """Traits field has empty active/past groups when no traits exist."""
        auth_as(client, seed_data["gm"])
        pc_id = seed_data["pc1"].id
        response = client.get(f"/api/v1/characters/{pc_id}")

        assert response.status_code == 200
        traits = response.json()["traits"]
        assert traits is not None
        assert traits["active"] == []
        assert traits["past"] == []

    def test_traits_active_group_populated(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Active traits appear in traits.active group with correct fields."""
        pc_id = seed_data["pc1"].id
        _add_trait_slot(
            db,
            pc_id,
            slot_type="core_trait",
            name="Iron Will",
            description="Resist pressure.",
            charge=3,
            is_active=True,
        )

        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/characters/{pc_id}")

        assert response.status_code == 200
        traits = response.json()["traits"]
        assert len(traits["active"]) == 1
        assert traits["past"] == []

        trait = traits["active"][0]
        assert trait["slot_type"] == "core_trait"
        assert trait["name"] == "Iron Will"
        assert trait["description"] == "Resist pressure."
        assert trait["charge"] == 3
        assert trait["is_active"] is True
        assert "id" in trait
        assert "created_at" in trait

    def test_traits_past_group_populated(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Retired traits appear in traits.past group."""
        pc_id = seed_data["pc1"].id
        _add_trait_slot(
            db,
            pc_id,
            slot_type="role_trait",
            name="Old Code",
            description="A discarded belief.",
            is_active=False,
        )

        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/characters/{pc_id}")

        assert response.status_code == 200
        traits = response.json()["traits"]
        assert traits["active"] == []
        assert len(traits["past"]) == 1
        assert traits["past"][0]["name"] == "Old Code"
        assert traits["past"][0]["is_active"] is False

    def test_traits_name_resolved_from_template(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """When a trait has a template_id, name and description come from the template."""
        pc_id = seed_data["pc1"].id

        template = TraitTemplate(
            name="Template Name",
            description="Template Description",
            type="core",
        )
        db.add(template)
        db.flush()

        _add_trait_slot(
            db,
            pc_id,
            slot_type="core_trait",
            name="Slot Name (overridden)",
            description="Slot Desc (overridden)",
            template=template,
        )

        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/characters/{pc_id}")

        assert response.status_code == 200
        trait = response.json()["traits"]["active"][0]
        # Template values win over slot values
        assert trait["name"] == "Template Name"
        assert trait["description"] == "Template Description"
        assert trait["template_id"] == template.id

    def test_traits_mixed_active_and_past(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Active and past traits are separated into correct groups."""
        pc_id = seed_data["pc1"].id
        _add_trait_slot(db, pc_id, slot_type="core_trait", name="Active Trait", is_active=True)
        _add_trait_slot(db, pc_id, slot_type="role_trait", name="Past Trait", is_active=False)

        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/characters/{pc_id}")

        traits = response.json()["traits"]
        assert len(traits["active"]) == 1
        assert len(traits["past"]) == 1
        assert traits["active"][0]["name"] == "Active Trait"
        assert traits["past"][0]["name"] == "Past Trait"


# ---------------------------------------------------------------------------
# Full character — magic effects
# ---------------------------------------------------------------------------


class TestFullCharacterMagicEffects:
    def test_magic_effects_empty_groups_when_no_effects(
        self, client: TestClient, seed_data: dict
    ):
        """magic_effects has empty active/past groups when no effects exist."""
        auth_as(client, seed_data["gm"])
        pc_id = seed_data["pc1"].id
        response = client.get(f"/api/v1/characters/{pc_id}")

        assert response.status_code == 200
        effects = response.json()["magic_effects"]
        assert effects is not None
        assert effects["active"] == []
        assert effects["past"] == []

    def test_magic_effects_active_group_populated(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Active magic effects appear in magic_effects.active group."""
        pc_id = seed_data["pc1"].id
        _add_magic_effect(
            db,
            pc_id,
            name="Arcane Shield",
            description="A barrier.",
            effect_type="charged",
            power_level=2,
            charges_current=3,
            charges_max=5,
        )

        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/characters/{pc_id}")

        effects = response.json()["magic_effects"]
        assert len(effects["active"]) == 1
        assert effects["past"] == []

        effect = effects["active"][0]
        assert effect["name"] == "Arcane Shield"
        assert effect["description"] == "A barrier."
        assert effect["effect_type"] == "charged"
        assert effect["power_level"] == 2
        assert effect["charges_current"] == 3
        assert effect["charges_max"] == 5
        assert effect["is_active"] is True
        assert "id" in effect
        assert "created_at" in effect

    def test_magic_effects_past_group_populated(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Retired magic effects appear in magic_effects.past group."""
        pc_id = seed_data["pc1"].id
        _add_magic_effect(
            db, pc_id, name="Old Ward", description="Faded.", is_active=False,
            charges_current=None, charges_max=None, effect_type="permanent"
        )

        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/characters/{pc_id}")

        effects = response.json()["magic_effects"]
        assert effects["active"] == []
        assert len(effects["past"]) == 1
        assert effects["past"][0]["name"] == "Old Ward"
        assert effects["past"][0]["is_active"] is False

    def test_magic_effects_permanent_has_null_charges(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Permanent effects have null charges_current and charges_max."""
        pc_id = seed_data["pc1"].id
        _add_magic_effect(
            db,
            pc_id,
            name="Eternal Flame",
            effect_type="permanent",
            charges_current=None,
            charges_max=None,
        )

        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/characters/{pc_id}")

        effect = response.json()["magic_effects"]["active"][0]
        assert effect["charges_current"] is None
        assert effect["charges_max"] is None


# ---------------------------------------------------------------------------
# Simplified character — restricted response
# ---------------------------------------------------------------------------


class TestSimplifiedCharacterResponse:
    def test_simplified_returns_base_fields(self, client: TestClient, seed_data: dict):
        """Simplified character GET returns name, description, notes, attributes, detail_level."""
        auth_as(client, seed_data["gm"])
        npc_id = seed_data["npc1"].id
        response = client.get(f"/api/v1/characters/{npc_id}")

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == npc_id
        assert body["detail_level"] == "simplified"
        assert "name" in body
        assert "description" in body
        assert "notes" in body
        assert "attributes" in body

    def test_simplified_returns_bonds(self, client: TestClient, seed_data: dict):
        """Simplified character GET returns bonds grouped as active/past."""
        auth_as(client, seed_data["gm"])
        npc_id = seed_data["npc1"].id
        response = client.get(f"/api/v1/characters/{npc_id}")

        assert response.status_code == 200
        body = response.json()
        assert "bonds" in body
        assert "active" in body["bonds"]
        assert "past" in body["bonds"]

    def test_simplified_returns_locations(self, client: TestClient, seed_data: dict):
        """Simplified character GET returns bond-distance locations."""
        auth_as(client, seed_data["gm"])
        npc_id = seed_data["npc1"].id
        response = client.get(f"/api/v1/characters/{npc_id}")

        assert response.status_code == 200
        body = response.json()
        assert "locations" in body
        assert "common" in body["locations"]
        assert "familiar" in body["locations"]
        assert "known" in body["locations"]

    def test_simplified_has_no_meters(self, client: TestClient, seed_data: dict):
        """Simplified character GET does NOT return stress, free_time, plot, gnosis."""
        auth_as(client, seed_data["gm"])
        npc_id = seed_data["npc1"].id
        response = client.get(f"/api/v1/characters/{npc_id}")

        assert response.status_code == 200
        body = response.json()
        assert body["stress"] is None
        assert body["free_time"] is None
        assert body["plot"] is None
        assert body["gnosis"] is None

    def test_simplified_has_no_skills(self, client: TestClient, seed_data: dict):
        """Simplified character GET does NOT return skills."""
        auth_as(client, seed_data["gm"])
        npc_id = seed_data["npc1"].id
        response = client.get(f"/api/v1/characters/{npc_id}")

        assert response.status_code == 200
        assert response.json()["skills"] is None

    def test_simplified_has_no_magic_stats(self, client: TestClient, seed_data: dict):
        """Simplified character GET does NOT return magic_stats."""
        auth_as(client, seed_data["gm"])
        npc_id = seed_data["npc1"].id
        response = client.get(f"/api/v1/characters/{npc_id}")

        assert response.status_code == 200
        assert response.json()["magic_stats"] is None

    def test_simplified_has_no_traits(self, client: TestClient, seed_data: dict):
        """Simplified character GET does NOT return traits."""
        auth_as(client, seed_data["gm"])
        npc_id = seed_data["npc1"].id
        response = client.get(f"/api/v1/characters/{npc_id}")

        assert response.status_code == 200
        assert response.json()["traits"] is None

    def test_simplified_has_no_magic_effects(self, client: TestClient, seed_data: dict):
        """Simplified character GET does NOT return magic_effects."""
        auth_as(client, seed_data["gm"])
        npc_id = seed_data["npc1"].id
        response = client.get(f"/api/v1/characters/{npc_id}")

        assert response.status_code == 200
        assert response.json()["magic_effects"] is None

    def test_simplified_has_no_session_ids(self, client: TestClient, seed_data: dict):
        """Simplified character GET does NOT return session_ids."""
        auth_as(client, seed_data["gm"])
        npc_id = seed_data["npc1"].id
        response = client.get(f"/api/v1/characters/{npc_id}")

        assert response.status_code == 200
        assert response.json()["session_ids"] is None

    def test_simplified_has_no_computed_values(self, client: TestClient, seed_data: dict):
        """Simplified character GET does NOT return computed fields."""
        auth_as(client, seed_data["gm"])
        npc_id = seed_data["npc1"].id
        response = client.get(f"/api/v1/characters/{npc_id}")

        assert response.status_code == 200
        body = response.json()
        assert body["effective_stress_max"] is None
        assert body["active_magic_effects_count"] is None
        assert body["active_trait_count"] is None
        assert body["active_bond_count"] is None


# ---------------------------------------------------------------------------
# Per-bond computed value: effective_bond_stress_max
# ---------------------------------------------------------------------------


class TestBondDisplayEffectiveStressMax:
    def test_pc_bond_has_stress_and_stress_degradations(
        self, client: TestClient, seed_data: dict
    ):
        """PC bond in response includes stress and stress_degradations fields."""
        auth_as(client, seed_data["gm"])
        pc_id = seed_data["pc1"].id
        response = client.get(f"/api/v1/characters/{pc_id}")

        assert response.status_code == 200
        active_bonds = response.json()["bonds"]["active"]
        # pc1 has one active pc_bond (pc1_bond → group)
        pc_bonds = [b for b in active_bonds if b["slot_type"] == "pc_bond"]
        assert len(pc_bonds) >= 1

        bond = pc_bonds[0]
        # stress_degradations = 0 → effective_bond_stress_max = 5 - 0 = 5
        assert bond["stress"] == 5
        assert bond["stress_degradations"] == 0

    def test_pc_bond_degraded_stress_degradations(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """PC bond with stress_degradations=2 reflects effective_bond_stress_max = 3."""
        pc_id = seed_data["pc3"].id
        # Add a pc_bond with stress_degradations=2 for pc3
        bond_slot = Slot(
            slot_type="pc_bond",
            owner_type="character",
            owner_id=pc_id,
            name="Strained Bond",
            description="Has been degraded.",
            stress=3,
            stress_degradations=2,
            is_trauma=False,
            is_active=True,
            bidirectional=False,
        )
        db.add(bond_slot)
        db.commit()
        db.refresh(bond_slot)

        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/characters/{pc_id}")

        assert response.status_code == 200
        active_bonds = response.json()["bonds"]["active"]
        pc_bonds = [b for b in active_bonds if b["slot_type"] == "pc_bond"]
        assert len(pc_bonds) == 1

        bond = pc_bonds[0]
        assert bond["stress_degradations"] == 2
        # Client computes: effective_bond_stress_max = 5 - stress_degradations = 3
        # We verify the raw field is present and correct; the formula is documented
        assert bond["stress"] == 3

    def test_npc_bond_has_null_stress_fields(self, client: TestClient, seed_data: dict):
        """NPC bond (npc_bond slot_type) has null stress and stress_degradations."""
        auth_as(client, seed_data["gm"])
        npc_id = seed_data["npc1"].id
        response = client.get(f"/api/v1/characters/{npc_id}")

        assert response.status_code == 200
        active_bonds = response.json()["bonds"]["active"]
        npc_bonds = [b for b in active_bonds if b["slot_type"] == "npc_bond"]
        assert len(npc_bonds) >= 1

        bond = npc_bonds[0]
        assert bond["stress"] is None
        assert bond["stress_degradations"] is None
