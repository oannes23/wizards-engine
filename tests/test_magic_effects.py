"""Tests for Story 3.2.3 — Magic Effects on Characters.

Covers all acceptance criteria:

Service layer:
  - create_effect: instant effect (not counted toward cap)
  - create_effect: charged effect (counts toward cap, requires charges)
  - create_effect: permanent effect (counts toward cap, no charges)
  - create_effect: cap of 9 (charged + permanent; instants don't count)
  - create_effect: fails when cap would be exceeded
  - create_effect: rejects simplified character
  - create_effect: rejects invalid effect_type
  - create_effect: rejects out-of-range power_level
  - create_effect: rejects charged without charge fields
  - use_effect: decrements charges_current by 1
  - use_effect: raises when at 0 charges
  - use_effect: raises when effect is not charged
  - use_effect: raises when effect is not active
  - retire_effect: sets is_active=False
  - get_effects_for_character: returns all effects (active + retired)

API layer:
  - player can use own charged effect (200), charges decremented
  - player cannot use effect at 0 charges (409)
  - player cannot use non-charged effect (400)
  - player can retire own effect (200)
  - player cannot use another player's effects (403)
  - player cannot retire another player's effect (403)
  - GM can use any charged effect (200)
  - GM can retire any effect (200)
  - unauthenticated use → 401
  - unauthenticated retire → 401
  - use nonexistent effect → 404
  - retired effects visible in character detail under past effects
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import auth_as
from wizards_engine.models.magic_effect import MagicEffect
from wizards_engine.services import magic_effect as magic_effect_svc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _add_effect(
    db: Session,
    character_id: str,
    *,
    effect_type: str = "charged",
    name: str = "Test Effect",
    description: str = "A test effect.",
    power_level: int = 3,
    charges_current: int | None = 5,
    charges_max: int | None = 5,
) -> MagicEffect:
    """Create an effect directly via the service, bypassing route validation."""
    return magic_effect_svc.create_effect(
        db,
        character_id=character_id,
        name=name,
        description=description,
        effect_type=effect_type,
        power_level=power_level,
        charges_current=charges_current if effect_type == "charged" else None,
        charges_max=charges_max if effect_type == "charged" else None,
    )


# ---------------------------------------------------------------------------
# Service layer — create_effect
# ---------------------------------------------------------------------------


class TestCreateEffect:
    def test_create_instant_effect(self, db: Session, seed_data: dict):
        """Instant effects are created and not counted toward the cap."""
        pc = seed_data["pc1"]
        effect = magic_effect_svc.create_effect(
            db,
            character_id=pc.id,
            name="Flash of Insight",
            description="A blinding moment of clarity.",
            effect_type="instant",
            power_level=2,
        )
        assert effect.id is not None
        assert effect.effect_type == "instant"
        assert effect.is_active is True
        assert effect.charges_current is None
        assert effect.charges_max is None

    def test_create_charged_effect(self, db: Session, seed_data: dict):
        """Charged effects are created with charge fields set."""
        pc = seed_data["pc1"]
        effect = magic_effect_svc.create_effect(
            db,
            character_id=pc.id,
            name="Shadow Step",
            description="Step through shadows.",
            effect_type="charged",
            power_level=4,
            charges_current=3,
            charges_max=5,
        )
        assert effect.effect_type == "charged"
        assert effect.charges_current == 3
        assert effect.charges_max == 5
        assert effect.is_active is True

    def test_create_permanent_effect(self, db: Session, seed_data: dict):
        """Permanent effects are created without charge fields."""
        pc = seed_data["pc1"]
        effect = magic_effect_svc.create_effect(
            db,
            character_id=pc.id,
            name="Flame Ward",
            description="Perpetual fire resistance.",
            effect_type="permanent",
            power_level=1,
        )
        assert effect.effect_type == "permanent"
        assert effect.charges_current is None
        assert effect.charges_max is None
        assert effect.is_active is True

    def test_instant_effects_dont_count_toward_cap(self, db: Session, seed_data: dict):
        """9 instants can coexist with 9 charged/permanent without hitting the cap."""
        pc = seed_data["pc1"]
        # Fill the cap with permanent effects.
        for i in range(magic_effect_svc.EFFECT_CAP):
            magic_effect_svc.create_effect(
                db,
                character_id=pc.id,
                name=f"Permanent {i}",
                description="Permanent.",
                effect_type="permanent",
                power_level=1,
            )
        # Adding an instant should still succeed.
        instant = magic_effect_svc.create_effect(
            db,
            character_id=pc.id,
            name="Instant Burst",
            description="One-time boom.",
            effect_type="instant",
            power_level=1,
        )
        assert instant.is_active is True

    def test_cap_is_enforced_for_charged(self, db: Session, seed_data: dict):
        """Creating a charged effect beyond the cap raises ValueError."""
        pc = seed_data["pc1"]
        for i in range(magic_effect_svc.EFFECT_CAP):
            magic_effect_svc.create_effect(
                db,
                character_id=pc.id,
                name=f"Charged {i}",
                description="Charged.",
                effect_type="charged",
                power_level=1,
                charges_current=3,
                charges_max=3,
            )
        with pytest.raises(ValueError, match="cap"):
            magic_effect_svc.create_effect(
                db,
                character_id=pc.id,
                name="Over the Cap",
                description="Should fail.",
                effect_type="charged",
                power_level=1,
                charges_current=1,
                charges_max=1,
            )

    def test_cap_is_enforced_for_permanent(self, db: Session, seed_data: dict):
        """Creating a permanent effect beyond the cap raises ValueError."""
        pc = seed_data["pc1"]
        for i in range(magic_effect_svc.EFFECT_CAP):
            magic_effect_svc.create_effect(
                db,
                character_id=pc.id,
                name=f"Permanent {i}",
                description="Permanent.",
                effect_type="permanent",
                power_level=1,
            )
        with pytest.raises(ValueError, match="cap"):
            magic_effect_svc.create_effect(
                db,
                character_id=pc.id,
                name="Over the Cap",
                description="Should fail.",
                effect_type="permanent",
                power_level=1,
            )

    def test_retiring_frees_cap_space(self, db: Session, seed_data: dict):
        """Retiring an effect frees one slot so a new one can be created."""
        pc = seed_data["pc1"]
        effects = []
        for i in range(magic_effect_svc.EFFECT_CAP):
            e = magic_effect_svc.create_effect(
                db,
                character_id=pc.id,
                name=f"Permanent {i}",
                description="Permanent.",
                effect_type="permanent",
                power_level=1,
            )
            effects.append(e)
        # Retire one.
        magic_effect_svc.retire_effect(db, effects[0].id)
        # Now creation should succeed.
        new_effect = magic_effect_svc.create_effect(
            db,
            character_id=pc.id,
            name="New Permanent",
            description="Replacement.",
            effect_type="permanent",
            power_level=2,
        )
        assert new_effect.is_active is True

    def test_create_effect_simplified_character_raises(
        self, db: Session, seed_data: dict
    ):
        """Creating an effect on a simplified (NPC) character raises ValueError."""
        npc = seed_data["npc1"]
        with pytest.raises(ValueError, match="full"):
            magic_effect_svc.create_effect(
                db,
                character_id=npc.id,
                name="NPC Effect",
                description="Should fail.",
                effect_type="permanent",
                power_level=1,
            )

    def test_create_effect_invalid_type_raises(self, db: Session, seed_data: dict):
        """Unknown effect_type raises ValueError."""
        pc = seed_data["pc1"]
        with pytest.raises(ValueError, match="effect_type"):
            magic_effect_svc.create_effect(
                db,
                character_id=pc.id,
                name="Bad Type",
                description="Should fail.",
                effect_type="legendary",
                power_level=1,
            )

    def test_create_effect_power_level_out_of_range_raises(
        self, db: Session, seed_data: dict
    ):
        """power_level outside 1–5 raises ValueError."""
        pc = seed_data["pc1"]
        with pytest.raises(ValueError, match="power_level"):
            magic_effect_svc.create_effect(
                db,
                character_id=pc.id,
                name="Bad Power",
                description="Should fail.",
                effect_type="permanent",
                power_level=6,
            )

    def test_create_charged_without_charges_raises(self, db: Session, seed_data: dict):
        """Charged effect without charges_current/charges_max raises ValueError."""
        pc = seed_data["pc1"]
        with pytest.raises(ValueError, match="charges"):
            magic_effect_svc.create_effect(
                db,
                character_id=pc.id,
                name="No Charges Charged",
                description="Should fail.",
                effect_type="charged",
                power_level=1,
            )

    def test_create_noncharged_with_charges_raises(self, db: Session, seed_data: dict):
        """Passing charges to a permanent effect raises ValueError."""
        pc = seed_data["pc1"]
        with pytest.raises(ValueError, match="charges"):
            magic_effect_svc.create_effect(
                db,
                character_id=pc.id,
                name="Permanent with Charges",
                description="Should fail.",
                effect_type="permanent",
                power_level=1,
                charges_current=3,
                charges_max=3,
            )

    def test_create_effect_nonexistent_character_raises(
        self, db: Session, seed_data: dict
    ):
        """Creating an effect on a non-existent character raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            magic_effect_svc.create_effect(
                db,
                character_id="01DOESNOTEXIST0000000000000",
                name="Ghost Effect",
                description="Should fail.",
                effect_type="permanent",
                power_level=1,
            )


# ---------------------------------------------------------------------------
# Service layer — use_effect
# ---------------------------------------------------------------------------


class TestUseEffect:
    def test_use_decrements_charges(self, db: Session, seed_data: dict):
        """Using a charged effect decrements charges_current by 1."""
        pc = seed_data["pc1"]
        effect = _add_effect(db, pc.id, charges_current=3, charges_max=5)
        updated = magic_effect_svc.use_effect(db, effect.id)
        assert updated.charges_current == 2

    def test_use_effect_at_zero_raises(self, db: Session, seed_data: dict):
        """Using a charged effect with 0 charges raises ValueError."""
        pc = seed_data["pc1"]
        effect = _add_effect(db, pc.id, charges_current=0, charges_max=5)
        with pytest.raises(ValueError, match="no charges"):
            magic_effect_svc.use_effect(db, effect.id)

    def test_use_effect_not_charged_raises(self, db: Session, seed_data: dict):
        """Using a permanent effect (not 'charged') raises ValueError."""
        pc = seed_data["pc1"]
        effect = _add_effect(db, pc.id, effect_type="permanent", charges_current=None, charges_max=None)
        with pytest.raises(ValueError, match="charged"):
            magic_effect_svc.use_effect(db, effect.id)

    def test_use_effect_retired_raises(self, db: Session, seed_data: dict):
        """Using a retired effect raises ValueError."""
        pc = seed_data["pc1"]
        effect = _add_effect(db, pc.id, charges_current=3, charges_max=5)
        magic_effect_svc.retire_effect(db, effect.id)
        with pytest.raises(ValueError, match="not active"):
            magic_effect_svc.use_effect(db, effect.id)

    def test_use_effect_accepts_narrative(self, db: Session, seed_data: dict):
        """use_effect accepts an optional narrative without error."""
        pc = seed_data["pc1"]
        effect = _add_effect(db, pc.id, charges_current=2, charges_max=5)
        updated = magic_effect_svc.use_effect(
            db, effect.id, narrative="I invoke the shadows."
        )
        assert updated.charges_current == 1


# ---------------------------------------------------------------------------
# Service layer — retire_effect
# ---------------------------------------------------------------------------


class TestRetireEffect:
    def test_retire_sets_inactive(self, db: Session, seed_data: dict):
        """Retiring an effect sets is_active to False."""
        pc = seed_data["pc1"]
        effect = _add_effect(db, pc.id)
        retired = magic_effect_svc.retire_effect(db, effect.id)
        assert retired.is_active is False

    def test_retire_nonexistent_raises(self, db: Session, seed_data: dict):
        """Retiring a non-existent effect raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            magic_effect_svc.retire_effect(db, "01DOESNOTEXIST0000000000000")

    def test_retire_idempotent(self, db: Session, seed_data: dict):
        """Retiring an already-retired effect does not error."""
        pc = seed_data["pc1"]
        effect = _add_effect(db, pc.id)
        magic_effect_svc.retire_effect(db, effect.id)
        # Second retire should succeed without error.
        result = magic_effect_svc.retire_effect(db, effect.id)
        assert result.is_active is False


# ---------------------------------------------------------------------------
# Service layer — get_effects_for_character
# ---------------------------------------------------------------------------


class TestGetEffectsForCharacter:
    def test_returns_active_and_retired(self, db: Session, seed_data: dict):
        """get_effects_for_character returns both active and retired effects."""
        pc = seed_data["pc1"]
        active_effect = _add_effect(db, pc.id, name="Active", charges_current=3, charges_max=5)
        retired_effect = _add_effect(db, pc.id, name="Retired", charges_current=3, charges_max=5)
        magic_effect_svc.retire_effect(db, retired_effect.id)

        effects = magic_effect_svc.get_effects_for_character(db, pc.id)
        ids = {e.id for e in effects}
        assert active_effect.id in ids
        assert retired_effect.id in ids

    def test_returns_empty_for_no_effects(self, db: Session, seed_data: dict):
        """Returns an empty list when the character has no effects."""
        pc = seed_data["pc1"]
        effects = magic_effect_svc.get_effects_for_character(db, pc.id)
        assert effects == []


# ---------------------------------------------------------------------------
# API — POST /characters/{id}/effects/{effect_id}/use
# ---------------------------------------------------------------------------


class TestUseEffectAPI:
    def test_player_can_use_own_charged_effect(
        self, client: TestClient, seed_data: dict, db: Session
    ):
        """Player can use their own charged effect; 200 with charges decremented."""
        pc = seed_data["pc1"]
        player = seed_data["player1"]
        effect = _add_effect(db, pc.id, charges_current=3, charges_max=5)
        db.commit()

        auth_as(client, player)
        response = client.post(
            f"/api/v1/characters/{pc.id}/effects/{effect.id}/use",
            json={},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["charges_current"] == 2
        assert body["id"] == effect.id

    def test_player_can_use_with_narrative(
        self, client: TestClient, seed_data: dict, db: Session
    ):
        """Player can include a narrative in the use request."""
        pc = seed_data["pc1"]
        player = seed_data["player1"]
        effect = _add_effect(db, pc.id, charges_current=2, charges_max=5)
        db.commit()

        auth_as(client, player)
        response = client.post(
            f"/api/v1/characters/{pc.id}/effects/{effect.id}/use",
            json={"narrative": "I invoke the ward against the flames."},
        )
        assert response.status_code == 200
        assert response.json()["charges_current"] == 1

    def test_use_effect_at_zero_charges_returns_409(
        self, client: TestClient, seed_data: dict, db: Session
    ):
        """Using a charged effect with 0 charges returns 409."""
        pc = seed_data["pc1"]
        player = seed_data["player1"]
        effect = _add_effect(db, pc.id, charges_current=0, charges_max=5)
        db.commit()

        auth_as(client, player)
        response = client.post(
            f"/api/v1/characters/{pc.id}/effects/{effect.id}/use",
            json={},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "no_charges_remaining"

    def test_use_non_charged_effect_returns_400(
        self, client: TestClient, seed_data: dict, db: Session
    ):
        """Using a permanent effect returns 400."""
        pc = seed_data["pc1"]
        player = seed_data["player1"]
        effect = _add_effect(
            db, pc.id, effect_type="permanent", charges_current=None, charges_max=None
        )
        db.commit()

        auth_as(client, player)
        response = client.post(
            f"/api/v1/characters/{pc.id}/effects/{effect.id}/use",
            json={},
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "effect_not_charged"

    def test_player_cannot_use_another_players_effect_returns_403(
        self, client: TestClient, seed_data: dict, db: Session
    ):
        """Player cannot use another player's character's effect; returns 403."""
        pc2 = seed_data["pc2"]
        player1 = seed_data["player1"]
        effect = _add_effect(db, pc2.id, charges_current=3, charges_max=5)
        db.commit()

        auth_as(client, player1)
        response = client.post(
            f"/api/v1/characters/{pc2.id}/effects/{effect.id}/use",
            json={},
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"

    def test_gm_can_use_any_charged_effect(
        self, client: TestClient, seed_data: dict, db: Session
    ):
        """GM can use any character's charged effect."""
        pc2 = seed_data["pc2"]
        gm = seed_data["gm"]
        effect = _add_effect(db, pc2.id, charges_current=4, charges_max=5)
        db.commit()

        auth_as(client, gm)
        response = client.post(
            f"/api/v1/characters/{pc2.id}/effects/{effect.id}/use",
            json={},
        )
        assert response.status_code == 200
        assert response.json()["charges_current"] == 3

    def test_use_nonexistent_effect_returns_404(
        self, client: TestClient, seed_data: dict
    ):
        """Using a nonexistent effect ID returns 404."""
        pc = seed_data["pc1"]
        gm = seed_data["gm"]
        auth_as(client, gm)
        response = client.post(
            f"/api/v1/characters/{pc.id}/effects/01DOESNOTEXIST0000000000000/use",
            json={},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_use_effect_wrong_character_returns_404(
        self, client: TestClient, seed_data: dict, db: Session
    ):
        """Using an effect with the wrong character_id path returns 404."""
        pc1 = seed_data["pc1"]
        pc2 = seed_data["pc2"]
        gm = seed_data["gm"]
        # Create effect on pc2 but pass pc1's id in the URL.
        effect = _add_effect(db, pc2.id, charges_current=3, charges_max=5)
        db.commit()

        auth_as(client, gm)
        response = client.post(
            f"/api/v1/characters/{pc1.id}/effects/{effect.id}/use",
            json={},
        )
        assert response.status_code == 404

    def test_unauthenticated_use_returns_401(
        self, client: TestClient, seed_data: dict, db: Session
    ):
        """Unauthenticated request to use effect returns 401."""
        pc = seed_data["pc1"]
        effect = _add_effect(db, pc.id, charges_current=3, charges_max=5)
        db.commit()

        response = client.post(
            f"/api/v1/characters/{pc.id}/effects/{effect.id}/use",
            json={},
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# API — POST /characters/{id}/effects/{effect_id}/retire
# ---------------------------------------------------------------------------


class TestRetireEffectAPI:
    def test_player_can_retire_own_effect(
        self, client: TestClient, seed_data: dict, db: Session
    ):
        """Player can retire their own effect; 200 with is_active=False."""
        pc = seed_data["pc1"]
        player = seed_data["player1"]
        effect = _add_effect(db, pc.id, charges_current=3, charges_max=5)
        db.commit()

        auth_as(client, player)
        response = client.post(
            f"/api/v1/characters/{pc.id}/effects/{effect.id}/retire"
        )
        assert response.status_code == 200
        body = response.json()
        assert body["is_active"] is False
        assert body["id"] == effect.id

    def test_player_cannot_retire_another_players_effect(
        self, client: TestClient, seed_data: dict, db: Session
    ):
        """Player cannot retire another player's character's effect; 403."""
        pc2 = seed_data["pc2"]
        player1 = seed_data["player1"]
        effect = _add_effect(db, pc2.id, charges_current=3, charges_max=5)
        db.commit()

        auth_as(client, player1)
        response = client.post(
            f"/api/v1/characters/{pc2.id}/effects/{effect.id}/retire"
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"

    def test_gm_can_retire_any_effect(
        self, client: TestClient, seed_data: dict, db: Session
    ):
        """GM can retire any character's effect."""
        pc2 = seed_data["pc2"]
        gm = seed_data["gm"]
        effect = _add_effect(db, pc2.id, effect_type="permanent")
        db.commit()

        auth_as(client, gm)
        response = client.post(
            f"/api/v1/characters/{pc2.id}/effects/{effect.id}/retire"
        )
        assert response.status_code == 200
        assert response.json()["is_active"] is False

    def test_retire_nonexistent_effect_returns_404(
        self, client: TestClient, seed_data: dict
    ):
        """Retiring a nonexistent effect returns 404."""
        pc = seed_data["pc1"]
        gm = seed_data["gm"]
        auth_as(client, gm)
        response = client.post(
            f"/api/v1/characters/{pc.id}/effects/01DOESNOTEXIST0000000000000/retire"
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_unauthenticated_retire_returns_401(
        self, client: TestClient, seed_data: dict, db: Session
    ):
        """Unauthenticated request to retire effect returns 401."""
        pc = seed_data["pc1"]
        effect = _add_effect(db, pc.id, charges_current=3, charges_max=5)
        db.commit()

        response = client.post(
            f"/api/v1/characters/{pc.id}/effects/{effect.id}/retire"
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# API — retired effects visible in character detail
# ---------------------------------------------------------------------------


class TestRetiredEffectsInCharacterDetail:
    def test_retired_effect_appears_in_past_section(
        self, client: TestClient, seed_data: dict, db: Session
    ):
        """After retiring, effect appears under magic_effects.past in character detail."""
        pc = seed_data["pc1"]
        gm = seed_data["gm"]
        effect = _add_effect(db, pc.id, name="Past Spell", charges_current=2, charges_max=5)
        db.commit()

        # Retire via API.
        auth_as(client, gm)
        retire_resp = client.post(
            f"/api/v1/characters/{pc.id}/effects/{effect.id}/retire"
        )
        assert retire_resp.status_code == 200

        # Fetch character detail.
        detail_resp = client.get(f"/api/v1/characters/{pc.id}")
        assert detail_resp.status_code == 200
        body = detail_resp.json()
        past_ids = [e["id"] for e in body["magic_effects"]["past"]]
        active_ids = [e["id"] for e in body["magic_effects"]["active"]]
        assert effect.id in past_ids
        assert effect.id not in active_ids

    def test_active_effect_appears_in_active_section(
        self, client: TestClient, seed_data: dict, db: Session
    ):
        """Active effect appears under magic_effects.active in character detail."""
        pc = seed_data["pc1"]
        gm = seed_data["gm"]
        effect = _add_effect(db, pc.id, name="Active Ward", charges_current=5, charges_max=5)
        db.commit()

        auth_as(client, gm)
        detail_resp = client.get(f"/api/v1/characters/{pc.id}")
        assert detail_resp.status_code == 200
        body = detail_resp.json()
        active_ids = [e["id"] for e in body["magic_effects"]["active"]]
        assert effect.id in active_ids
