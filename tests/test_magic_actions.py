"""Integration tests for Story 4.3.5 — Magic Actions + Sacrifice.

Covers:
- ``calculate_use_magic``: stat validation, sacrifice processing, tiered
  dice conversion, modifier validation, dice pool assembly.
- ``calculate_charge_magic``: effect validation, same sacrifice/modifier
  logic as use_magic.
- ``_apply_use_magic`` (via proposal approval): Gnosis deduction, Stress
  deduction + boundary detection, Free Time deduction, bond sacrifice
  (retire), trait sacrifice (retire), trait modifier charge deduction,
  MagicEffect creation from effect_details.
- ``_apply_charge_magic`` (via proposal approval): same sacrifice handling
  plus charges_added on charged effects (current + max growth) and
  power_boost on permanent effects.

All tests use the function-scoped ``client`` + ``seed_data`` fixtures
or the bare ``db`` fixture for pure service-layer tests.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import auth_as
from wizards_engine.models.event import Event
from wizards_engine.models.magic_effect import MagicEffect
from wizards_engine.models.proposal import Proposal
from wizards_engine.models.slot import Slot
from wizards_engine.services.proposal import (
    calculate_charge_magic,
    calculate_use_magic,
    _gnosis_equiv_to_sacrifice_dice,
)


# ===========================================================================
# Helpers
# ===========================================================================


def _pending_proposal(
    db: Session,
    *,
    character_id: str,
    action_type: str = "use_magic",
    narrative: str = "I work magic.",
    selections: dict | None = None,
    calculated_effect: dict | None = None,
) -> Proposal:
    """Create and flush a minimal pending Proposal."""
    p = Proposal(
        character_id=character_id,
        action_type=action_type,
        origin="player",
        narrative=narrative,
        selections=selections or {},
        calculated_effect=calculated_effect or {},
        status="pending",
    )
    db.add(p)
    db.flush()
    db.refresh(p)
    return p


def _core_trait_slot(
    db: Session,
    *,
    owner_id: str,
    name: str = "Brave",
    charge: int = 3,
) -> Slot:
    slot = Slot(
        slot_type="core_trait",
        owner_type="character",
        owner_id=owner_id,
        name=name,
        charge=charge,
        is_active=True,
    )
    db.add(slot)
    db.flush()
    db.refresh(slot)
    return slot


def _role_trait_slot(
    db: Session,
    *,
    owner_id: str,
    name: str = "Cunning",
    charge: int = 3,
) -> Slot:
    slot = Slot(
        slot_type="role_trait",
        owner_type="character",
        owner_id=owner_id,
        name=name,
        charge=charge,
        is_active=True,
    )
    db.add(slot)
    db.flush()
    db.refresh(slot)
    return slot


def _pc_bond_slot(
    db: Session,
    *,
    owner_id: str,
    name: str = "A Bond",
    charges: int = 0,
    is_trauma: bool = False,
) -> Slot:
    slot = Slot(
        slot_type="pc_bond",
        owner_type="character",
        owner_id=owner_id,
        name=name,
        charges=charges,
        degradations=0,
        is_trauma=is_trauma,
        is_active=True,
    )
    db.add(slot)
    db.flush()
    db.refresh(slot)
    return slot


def _magic_effect(
    db: Session,
    *,
    character_id: str,
    name: str = "Test Effect",
    effect_type: str = "charged",
    power_level: int = 2,
    charges_current: int | None = 3,
    charges_max: int | None = 5,
    is_active: bool = True,
) -> MagicEffect:
    eff = MagicEffect(
        character_id=character_id,
        name=name,
        description="A test magical effect.",
        effect_type=effect_type,
        power_level=power_level,
        charges_current=charges_current,
        charges_max=charges_max,
        is_active=is_active,
    )
    db.add(eff)
    db.flush()
    db.refresh(eff)
    return eff


def _use_magic_effect(
    *,
    suggested_stat: str = "being",
    stat_level: int = 0,
    sacrifice_dice: int = 0,
    total_gnosis_equiv: int = 0,
    sacrifice_details: list | None = None,
    modifiers: list | None = None,
    costs: dict | None = None,
) -> dict:
    """Build a minimal calculated_effect for a use_magic proposal."""
    modifier_count = len(modifiers or [])
    trait_charges = [
        {"trait_id": m["id"], "cost": 1}
        for m in (modifiers or [])
        if m["type"] in ("core_trait", "role_trait")
    ]
    return {
        "suggested_stat": suggested_stat,
        "stat_level": stat_level,
        "dice_pool": stat_level + sacrifice_dice + modifier_count,
        "sacrifice_dice": sacrifice_dice,
        "total_gnosis_equivalent": total_gnosis_equiv,
        "sacrifice_details": sacrifice_details or [],
        "modifiers": modifiers or [],
        "costs": costs or {
            "gnosis": 0,
            "stress": 0,
            "free_time": 0,
            "bond_sacrifices": [],
            "trait_sacrifices": [],
            "trait_charges": trait_charges,
            "plot": 0,
        },
    }


# ===========================================================================
# Tiered Gnosis-to-dice conversion
# ===========================================================================


class TestGnosisEquivToDice:
    """Unit tests for the tiered triangular-number conversion."""

    def test_zero_gnosis_gives_zero_dice(self) -> None:
        assert _gnosis_equiv_to_sacrifice_dice(0) == 0

    def test_negative_gnosis_gives_zero_dice(self) -> None:
        assert _gnosis_equiv_to_sacrifice_dice(-5) == 0

    def test_one_gnosis_gives_one_die(self) -> None:
        assert _gnosis_equiv_to_sacrifice_dice(1) == 1

    def test_two_gnosis_gives_one_die(self) -> None:
        # 2 dice cost 3, so 2 gnosis only buys 1 die
        assert _gnosis_equiv_to_sacrifice_dice(2) == 1

    def test_three_gnosis_gives_two_dice(self) -> None:
        assert _gnosis_equiv_to_sacrifice_dice(3) == 2

    def test_five_gnosis_gives_two_dice(self) -> None:
        # 3 dice cost 6, so 5 gnosis buys 2 dice
        assert _gnosis_equiv_to_sacrifice_dice(5) == 2

    def test_six_gnosis_gives_three_dice(self) -> None:
        assert _gnosis_equiv_to_sacrifice_dice(6) == 3

    def test_ten_gnosis_gives_four_dice(self) -> None:
        assert _gnosis_equiv_to_sacrifice_dice(10) == 4

    def test_fifteen_gnosis_gives_five_dice(self) -> None:
        assert _gnosis_equiv_to_sacrifice_dice(15) == 5

    def test_twenty_one_gnosis_gives_six_dice(self) -> None:
        assert _gnosis_equiv_to_sacrifice_dice(21) == 6

    def test_twenty_gnosis_gives_five_dice(self) -> None:
        # 21 needed for 6 dice
        assert _gnosis_equiv_to_sacrifice_dice(20) == 5


# ===========================================================================
# calculate_use_magic — stat validation
# ===========================================================================


class TestCalculateUseMagicStatValidation:
    """Stat validation on calculate_use_magic."""

    def test_missing_suggested_stat_raises_422(
        self, db: Session, seed_data: dict
    ) -> None:
        from fastapi import HTTPException
        pc1 = seed_data["pc1"]
        with pytest.raises(HTTPException) as exc_info:
            calculate_use_magic(db, character_id=pc1.id, selections={})
        assert exc_info.value.status_code == 422

    def test_invalid_stat_raises_422(self, db: Session, seed_data: dict) -> None:
        from fastapi import HTTPException
        pc1 = seed_data["pc1"]
        with pytest.raises(HTTPException) as exc_info:
            calculate_use_magic(
                db,
                character_id=pc1.id,
                selections={"suggested_stat": "fireball"},
            )
        assert exc_info.value.status_code == 422

    def test_valid_stats_accepted(self, db: Session, seed_data: dict) -> None:
        pc1 = seed_data["pc1"]
        for stat in ("being", "wyrding", "summoning", "enchanting", "dreaming"):
            result = calculate_use_magic(
                db,
                character_id=pc1.id,
                selections={"suggested_stat": stat},
            )
            assert result["suggested_stat"] == stat

    def test_stat_level_reflects_character_magic_stats(
        self, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        new_stats = {k: dict(v) for k, v in pc1.magic_stats.items()}
        new_stats["being"]["level"] = 3
        pc1.magic_stats = new_stats
        db.flush()
        result = calculate_use_magic(
            db,
            character_id=pc1.id,
            selections={"suggested_stat": "being"},
        )
        assert result["stat_level"] == 3


# ===========================================================================
# calculate_use_magic — sacrifice processing
# ===========================================================================


class TestCalculateUseMagicSacrifice:
    """Sacrifice processing in calculate_use_magic."""

    def test_gnosis_sacrifice_converted_1_to_1(
        self, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        result = calculate_use_magic(
            db,
            character_id=pc1.id,
            selections={
                "suggested_stat": "being",
                "sacrifice": [{"type": "gnosis", "amount": 5}],
            },
        )
        detail = result["sacrifice_details"][0]
        assert detail["gnosis_equivalent"] == 5
        assert result["total_gnosis_equivalent"] == 5
        assert result["costs"]["gnosis"] == 5

    def test_stress_sacrifice_converted_2_to_1(
        self, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        result = calculate_use_magic(
            db,
            character_id=pc1.id,
            selections={
                "suggested_stat": "being",
                "sacrifice": [{"type": "stress", "amount": 2}],
            },
        )
        detail = result["sacrifice_details"][0]
        assert detail["gnosis_equivalent"] == 4
        assert result["costs"]["stress"] == 2

    def test_free_time_sacrifice_uses_lowest_magic_stat(
        self, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        # All stats at 0 (default from fixtures): 3 + 0 = 3 Gnosis per FT
        result = calculate_use_magic(
            db,
            character_id=pc1.id,
            selections={
                "suggested_stat": "being",
                "sacrifice": [{"type": "free_time", "amount": 2}],
            },
        )
        assert result["sacrifice_details"][0]["gnosis_equivalent"] == 6  # 2 * (3+0)
        assert result["costs"]["free_time"] == 2

    def test_free_time_with_non_zero_lowest_stat(
        self, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        pc1.magic_stats = {
            "being": {"level": 2, "xp": 0},
            "wyrding": {"level": 1, "xp": 0},
            "summoning": {"level": 0, "xp": 0},  # lowest = 0
            "enchanting": {"level": 3, "xp": 0},
            "dreaming": {"level": 2, "xp": 0},
        }
        # Must assign a new dict to trigger SQLAlchemy mutation tracking.
        db.flush()
        # lowest = 0 (summoning) → 3 + 0 = 3 per FT
        result = calculate_use_magic(
            db,
            character_id=pc1.id,
            selections={
                "suggested_stat": "being",
                "sacrifice": [{"type": "free_time", "amount": 1}],
            },
        )
        assert result["sacrifice_details"][0]["gnosis_equivalent"] == 3

    def test_bond_sacrifice_gives_10_gnosis_equiv(
        self, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        bond = _pc_bond_slot(db, owner_id=pc1.id, name="Sacrifice Bond")
        db.commit()
        result = calculate_use_magic(
            db,
            character_id=pc1.id,
            selections={
                "suggested_stat": "being",
                "sacrifice": [{"type": "bond", "target_id": bond.id}],
            },
        )
        assert result["sacrifice_details"][0]["gnosis_equivalent"] == 10
        assert result["costs"]["bond_sacrifices"][0]["bond_id"] == bond.id

    def test_trait_sacrifice_gives_10_gnosis_equiv(
        self, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        trait = _core_trait_slot(db, owner_id=pc1.id, name="Sacrifice Trait")
        db.commit()
        result = calculate_use_magic(
            db,
            character_id=pc1.id,
            selections={
                "suggested_stat": "being",
                "sacrifice": [{"type": "trait", "target_id": trait.id}],
            },
        )
        assert result["sacrifice_details"][0]["gnosis_equivalent"] == 10
        assert result["costs"]["trait_sacrifices"][0]["trait_id"] == trait.id

    def test_other_sacrifice_gives_zero_gnosis_equiv(
        self, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        result = calculate_use_magic(
            db,
            character_id=pc1.id,
            selections={
                "suggested_stat": "being",
                "sacrifice": [{"type": "other", "description": "A rare gem"}],
            },
        )
        assert result["sacrifice_details"][0]["gnosis_equivalent"] == 0

    def test_combined_sacrifice_sums_gnosis_equiv(
        self, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        bond = _pc_bond_slot(db, owner_id=pc1.id)
        db.commit()
        result = calculate_use_magic(
            db,
            character_id=pc1.id,
            selections={
                "suggested_stat": "being",
                "sacrifice": [
                    {"type": "gnosis", "amount": 3},   # 3
                    {"type": "stress", "amount": 1},   # 2
                    {"type": "bond", "target_id": bond.id},  # 10
                ],
            },
        )
        assert result["total_gnosis_equivalent"] == 15

    def test_unknown_sacrifice_type_raises_422(
        self, db: Session, seed_data: dict
    ) -> None:
        from fastapi import HTTPException
        pc1 = seed_data["pc1"]
        with pytest.raises(HTTPException) as exc_info:
            calculate_use_magic(
                db,
                character_id=pc1.id,
                selections={
                    "suggested_stat": "being",
                    "sacrifice": [{"type": "gold_coin", "amount": 5}],
                },
            )
        assert exc_info.value.status_code == 422

    def test_bond_not_owned_raises_422(self, db: Session, seed_data: dict) -> None:
        from fastapi import HTTPException
        pc1 = seed_data["pc1"]
        other_bond = seed_data["pc2_bond"]
        with pytest.raises(HTTPException) as exc_info:
            calculate_use_magic(
                db,
                character_id=pc1.id,
                selections={
                    "suggested_stat": "being",
                    "sacrifice": [{"type": "bond", "target_id": other_bond.id}],
                },
            )
        assert exc_info.value.status_code == 422


# ===========================================================================
# calculate_use_magic — dice pool assembly
# ===========================================================================


class TestCalculateUseMagicDicePool:
    """Dice pool: stat_level + sacrifice_dice + modifier_count."""

    def test_zero_everything_gives_zero_pool(
        self, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        result = calculate_use_magic(
            db, character_id=pc1.id, selections={"suggested_stat": "being"}
        )
        assert result["dice_pool"] == 0
        assert result["sacrifice_dice"] == 0

    def test_stat_level_adds_to_pool(self, db: Session, seed_data: dict) -> None:
        pc1 = seed_data["pc1"]
        new_stats = {k: dict(v) for k, v in pc1.magic_stats.items()}
        new_stats["being"]["level"] = 3
        pc1.magic_stats = new_stats
        db.flush()
        result = calculate_use_magic(
            db, character_id=pc1.id, selections={"suggested_stat": "being"}
        )
        assert result["dice_pool"] == 3

    def test_sacrifice_adds_to_pool_via_tiered_conversion(
        self, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        # 6 gnosis → 3 sacrifice dice
        result = calculate_use_magic(
            db,
            character_id=pc1.id,
            selections={
                "suggested_stat": "being",
                "sacrifice": [{"type": "gnosis", "amount": 6}],
            },
        )
        assert result["sacrifice_dice"] == 3
        assert result["dice_pool"] == 3

    def test_modifier_adds_to_pool(self, db: Session, seed_data: dict) -> None:
        pc1 = seed_data["pc1"]
        core = _core_trait_slot(db, owner_id=pc1.id)
        db.commit()
        result = calculate_use_magic(
            db,
            character_id=pc1.id,
            selections={
                "suggested_stat": "being",
                "modifiers": {"core_trait_id": core.id},
            },
        )
        assert result["dice_pool"] == 1  # 0 stat + 0 sacrifice + 1 modifier
        assert len(result["modifiers"]) == 1

    def test_full_dice_pool_stat_plus_sacrifice_plus_modifiers(
        self, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        # Must replace the whole dict to trigger SQLAlchemy JSON mutation tracking.
        new_stats = {k: dict(v) for k, v in pc1.magic_stats.items()}
        new_stats["being"]["level"] = 2
        pc1.magic_stats = new_stats
        db.flush()
        core = _core_trait_slot(db, owner_id=pc1.id)
        db.commit()
        # 3 gnosis → 2 sacrifice dice; stat=2; 1 modifier = total 5
        result = calculate_use_magic(
            db,
            character_id=pc1.id,
            selections={
                "suggested_stat": "being",
                "sacrifice": [{"type": "gnosis", "amount": 3}],
                "modifiers": {"core_trait_id": core.id},
            },
        )
        assert result["sacrifice_dice"] == 2
        assert result["dice_pool"] == 5  # 2 + 2 + 1

    def test_costs_include_trait_charges(self, db: Session, seed_data: dict) -> None:
        pc1 = seed_data["pc1"]
        core = _core_trait_slot(db, owner_id=pc1.id)
        db.commit()
        result = calculate_use_magic(
            db,
            character_id=pc1.id,
            selections={
                "suggested_stat": "being",
                "modifiers": {"core_trait_id": core.id},
            },
        )
        assert result["costs"]["trait_charges"] == [{"trait_id": core.id, "cost": 1}]
        assert result["costs"]["plot"] == 0


# ===========================================================================
# calculate_charge_magic — validation
# ===========================================================================


class TestCalculateChargeMagic:
    """Validation and structure of calculate_charge_magic."""

    def test_missing_effect_id_raises_422(self, db: Session, seed_data: dict) -> None:
        from fastapi import HTTPException
        pc1 = seed_data["pc1"]
        with pytest.raises(HTTPException) as exc_info:
            calculate_charge_magic(
                db,
                character_id=pc1.id,
                selections={"suggested_stat": "enchanting"},
            )
        assert exc_info.value.status_code == 422

    def test_effect_not_found_raises_422(self, db: Session, seed_data: dict) -> None:
        from fastapi import HTTPException
        pc1 = seed_data["pc1"]
        with pytest.raises(HTTPException) as exc_info:
            calculate_charge_magic(
                db,
                character_id=pc1.id,
                selections={
                    "effect_id": "01FAKEEFFECTID00000000001",
                    "suggested_stat": "enchanting",
                },
            )
        assert exc_info.value.status_code == 422

    def test_instant_effect_raises_422(self, db: Session, seed_data: dict) -> None:
        from fastapi import HTTPException
        pc1 = seed_data["pc1"]
        eff = _magic_effect(
            db,
            character_id=pc1.id,
            effect_type="instant",
            charges_current=None,
            charges_max=None,
        )
        db.commit()
        with pytest.raises(HTTPException) as exc_info:
            calculate_charge_magic(
                db,
                character_id=pc1.id,
                selections={
                    "effect_id": eff.id,
                    "suggested_stat": "enchanting",
                },
            )
        assert exc_info.value.status_code == 422

    def test_charged_effect_accepted(self, db: Session, seed_data: dict) -> None:
        pc1 = seed_data["pc1"]
        eff = _magic_effect(db, character_id=pc1.id, effect_type="charged")
        db.commit()
        result = calculate_charge_magic(
            db,
            character_id=pc1.id,
            selections={
                "effect_id": eff.id,
                "suggested_stat": "enchanting",
            },
        )
        assert result["target_effect"]["id"] == eff.id
        assert result["target_effect"]["effect_type"] == "charged"

    def test_permanent_effect_accepted(self, db: Session, seed_data: dict) -> None:
        pc1 = seed_data["pc1"]
        eff = _magic_effect(
            db,
            character_id=pc1.id,
            effect_type="permanent",
            charges_current=None,
            charges_max=None,
        )
        db.commit()
        result = calculate_charge_magic(
            db,
            character_id=pc1.id,
            selections={
                "effect_id": eff.id,
                "suggested_stat": "enchanting",
            },
        )
        assert result["target_effect"]["id"] == eff.id

    def test_effect_not_belonging_to_character_raises_422(
        self, db: Session, seed_data: dict
    ) -> None:
        from fastapi import HTTPException
        pc1 = seed_data["pc1"]
        pc2 = seed_data["pc2"]
        eff = _magic_effect(db, character_id=pc2.id, effect_type="charged")
        db.commit()
        with pytest.raises(HTTPException) as exc_info:
            calculate_charge_magic(
                db,
                character_id=pc1.id,
                selections={
                    "effect_id": eff.id,
                    "suggested_stat": "enchanting",
                },
            )
        assert exc_info.value.status_code == 422

    def test_inactive_effect_raises_422(self, db: Session, seed_data: dict) -> None:
        from fastapi import HTTPException
        pc1 = seed_data["pc1"]
        eff = _magic_effect(
            db, character_id=pc1.id, effect_type="charged", is_active=False
        )
        db.commit()
        with pytest.raises(HTTPException) as exc_info:
            calculate_charge_magic(
                db,
                character_id=pc1.id,
                selections={
                    "effect_id": eff.id,
                    "suggested_stat": "enchanting",
                },
            )
        assert exc_info.value.status_code == 422


# ===========================================================================
# Proposal creation — use_magic and charge_magic
# ===========================================================================


class TestUseMagicProposalCreation:
    """End-to-end proposal creation via the API for use_magic."""

    def test_use_magic_proposal_created_with_calculated_effect(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        pc1.gnosis = 10
        db.commit()

        auth_as(client, seed_data["player1"])
        response = client.post(
            "/api/v1/proposals",
            json={
                "character_id": pc1.id,
                "action_type": "use_magic",
                "narrative": "I summon a spirit.",
                "selections": {
                    "suggested_stat": "summoning",
                    "sacrifice": [{"type": "gnosis", "amount": 3}],
                },
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["calculated_effect"]["suggested_stat"] == "summoning"
        assert body["calculated_effect"]["sacrifice_dice"] == 2
        assert body["calculated_effect"]["total_gnosis_equivalent"] == 3

    def test_charge_magic_proposal_created_with_calculated_effect(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        eff = _magic_effect(db, character_id=pc1.id, effect_type="charged")
        db.commit()

        auth_as(client, seed_data["player1"])
        response = client.post(
            "/api/v1/proposals",
            json={
                "character_id": pc1.id,
                "action_type": "charge_magic",
                "narrative": "I recharge my crystal.",
                "selections": {
                    "effect_id": eff.id,
                    "suggested_stat": "enchanting",
                },
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["calculated_effect"]["target_effect"]["id"] == eff.id


# ===========================================================================
# use_magic approval — resource deductions
# ===========================================================================


class TestUseMagicApprovalGnosis:
    """Gnosis deducted on use_magic approval."""

    def test_gnosis_deducted_on_approval(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        pc1.gnosis = 10
        db.flush()

        effect = _use_magic_effect(
            costs={
                "gnosis": 5,
                "stress": 0,
                "free_time": 0,
                "bond_sacrifices": [],
                "trait_sacrifices": [],
                "trait_charges": [],
                "plot": 0,
            }
        )
        p = _pending_proposal(db, character_id=pc1.id, calculated_effect=effect)
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.post(f"/api/v1/proposals/{p.id}/approve", json={})
        assert response.status_code == 200

        db.expire_all()
        db.refresh(pc1)
        assert pc1.gnosis == 5

    def test_gnosis_change_recorded_in_event(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        pc1.gnosis = 10
        db.flush()

        effect = _use_magic_effect(
            costs={
                "gnosis": 3,
                "stress": 0,
                "free_time": 0,
                "bond_sacrifices": [],
                "trait_sacrifices": [],
                "trait_charges": [],
                "plot": 0,
            }
        )
        p = _pending_proposal(db, character_id=pc1.id, calculated_effect=effect)
        db.commit()

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/proposals/{p.id}/approve", json={})

        db.expire_all()
        event = db.query(Event).filter(Event.proposal_id == p.id).first()
        assert f"character.{pc1.id}.gnosis" in event.changes
        assert event.changes[f"character.{pc1.id}.gnosis"]["before"] == 10
        assert event.changes[f"character.{pc1.id}.gnosis"]["after"] == 7

    def test_gnosis_clamped_to_zero_not_negative(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        pc1.gnosis = 2
        db.flush()

        effect = _use_magic_effect(
            costs={
                "gnosis": 10,
                "stress": 0,
                "free_time": 0,
                "bond_sacrifices": [],
                "trait_sacrifices": [],
                "trait_charges": [],
                "plot": 0,
            }
        )
        p = _pending_proposal(db, character_id=pc1.id, calculated_effect=effect)
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.post(f"/api/v1/proposals/{p.id}/approve", json={})
        assert response.status_code == 200

        db.expire_all()
        db.refresh(pc1)
        assert pc1.gnosis == 0  # clamped, not negative


class TestUseMagicApprovalStress:
    """Stress deducted and boundary detection on use_magic approval."""

    def test_stress_added_on_sacrifice(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        pc1.stress = 0
        db.flush()

        effect = _use_magic_effect(
            costs={
                "gnosis": 0,
                "stress": 2,
                "free_time": 0,
                "bond_sacrifices": [],
                "trait_sacrifices": [],
                "trait_charges": [],
                "plot": 0,
            }
        )
        p = _pending_proposal(db, character_id=pc1.id, calculated_effect=effect)
        db.commit()

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/proposals/{p.id}/approve", json={})

        db.expire_all()
        db.refresh(pc1)
        assert pc1.stress == 2

    def test_stress_sacrifice_at_boundary_generates_resolve_trauma_proposal(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Stress sacrifice that pushes to effective max auto-generates a resolve_trauma."""
        pc1 = seed_data["pc1"]
        pc1.stress = 7  # Effective max = 9 - 0 trauma = 9; 7 + 3 >= 9
        db.flush()

        effect = _use_magic_effect(
            costs={
                "gnosis": 0,
                "stress": 3,
                "free_time": 0,
                "bond_sacrifices": [],
                "trait_sacrifices": [],
                "trait_charges": [],
                "plot": 0,
            }
        )
        p = _pending_proposal(db, character_id=pc1.id, calculated_effect=effect)
        db.commit()

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/proposals/{p.id}/approve", json={})

        db.expire_all()
        trauma_proposal = (
            db.query(Proposal)
            .filter(
                Proposal.character_id == pc1.id,
                Proposal.action_type == "resolve_trauma",
                Proposal.status == "pending",
            )
            .first()
        )
        assert trauma_proposal is not None

    def test_stress_sacrifice_below_boundary_does_not_generate_trauma_proposal(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        pc1.stress = 0
        db.flush()

        effect = _use_magic_effect(
            costs={
                "gnosis": 0,
                "stress": 2,
                "free_time": 0,
                "bond_sacrifices": [],
                "trait_sacrifices": [],
                "trait_charges": [],
                "plot": 0,
            }
        )
        p = _pending_proposal(db, character_id=pc1.id, calculated_effect=effect)
        db.commit()

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/proposals/{p.id}/approve", json={})

        db.expire_all()
        trauma_proposal = (
            db.query(Proposal)
            .filter(
                Proposal.character_id == pc1.id,
                Proposal.action_type == "resolve_trauma",
            )
            .first()
        )
        assert trauma_proposal is None

    def test_stress_boundary_idempotent_no_duplicate_trauma_proposals(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Only one pending resolve_trauma proposal per character."""
        pc1 = seed_data["pc1"]
        pc1.stress = 8
        db.flush()

        effect = _use_magic_effect(
            costs={
                "gnosis": 0,
                "stress": 2,
                "free_time": 0,
                "bond_sacrifices": [],
                "trait_sacrifices": [],
                "trait_charges": [],
                "plot": 0,
            }
        )
        p1 = _pending_proposal(db, character_id=pc1.id, calculated_effect=effect)
        p2 = _pending_proposal(db, character_id=pc1.id, calculated_effect=effect)
        db.commit()

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/proposals/{p1.id}/approve", json={})

        # Reset stress so second approval can trigger again
        db.expire_all()
        db.refresh(pc1)
        pc1.stress = 8
        db.commit()

        client.post(f"/api/v1/proposals/{p2.id}/approve", json={})

        db.expire_all()
        count = (
            db.query(Proposal)
            .filter(
                Proposal.character_id == pc1.id,
                Proposal.action_type == "resolve_trauma",
                Proposal.status == "pending",
            )
            .count()
        )
        assert count == 1  # Idempotent — still only one


class TestUseMagicApprovalFreeTime:
    """Free Time deducted on use_magic approval."""

    def test_free_time_deducted_on_sacrifice(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        pc1.free_time = 5
        db.flush()

        effect = _use_magic_effect(
            costs={
                "gnosis": 0,
                "stress": 0,
                "free_time": 2,
                "bond_sacrifices": [],
                "trait_sacrifices": [],
                "trait_charges": [],
                "plot": 0,
            }
        )
        p = _pending_proposal(db, character_id=pc1.id, calculated_effect=effect)
        db.commit()

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/proposals/{p.id}/approve", json={})

        db.expire_all()
        db.refresh(pc1)
        assert pc1.free_time == 3


class TestUseMagicApprovalBondSacrifice:
    """Bond sacrifice retires the bond on approval."""

    def test_bond_retired_on_sacrifice(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        bond = _pc_bond_slot(db, owner_id=pc1.id, name="Sacrifice Bond")
        db.flush()

        effect = _use_magic_effect(
            costs={
                "gnosis": 0,
                "stress": 0,
                "free_time": 0,
                "bond_sacrifices": [{"bond_id": bond.id, "name": bond.name}],
                "trait_sacrifices": [],
                "trait_charges": [],
                "plot": 0,
            }
        )
        p = _pending_proposal(db, character_id=pc1.id, calculated_effect=effect)
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.post(f"/api/v1/proposals/{p.id}/approve", json={})
        assert response.status_code == 200

        db.expire_all()
        db.refresh(bond)
        assert bond.is_active is False

    def test_bond_retire_change_recorded_in_event(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        bond = _pc_bond_slot(db, owner_id=pc1.id, name="Sacrifice Bond")
        db.flush()

        effect = _use_magic_effect(
            costs={
                "gnosis": 0,
                "stress": 0,
                "free_time": 0,
                "bond_sacrifices": [{"bond_id": bond.id, "name": bond.name}],
                "trait_sacrifices": [],
                "trait_charges": [],
                "plot": 0,
            }
        )
        p = _pending_proposal(db, character_id=pc1.id, calculated_effect=effect)
        db.commit()

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/proposals/{p.id}/approve", json={})

        db.expire_all()
        event = db.query(Event).filter(Event.proposal_id == p.id).first()
        key = f"slot.{bond.id}.is_active"
        assert key in event.changes
        assert event.changes[key]["before"] is True
        assert event.changes[key]["after"] is False


class TestUseMagicApprovalTraitSacrifice:
    """Trait sacrifice retires the trait on approval."""

    def test_trait_retired_on_sacrifice(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        trait = _core_trait_slot(db, owner_id=pc1.id, name="Sacrificed Trait")
        db.flush()

        effect = _use_magic_effect(
            costs={
                "gnosis": 0,
                "stress": 0,
                "free_time": 0,
                "bond_sacrifices": [],
                "trait_sacrifices": [{"trait_id": trait.id, "name": trait.name}],
                "trait_charges": [],
                "plot": 0,
            }
        )
        p = _pending_proposal(db, character_id=pc1.id, calculated_effect=effect)
        db.commit()

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/proposals/{p.id}/approve", json={})

        db.expire_all()
        db.refresh(trait)
        assert trait.is_active is False


class TestUseMagicApprovalModifierCharges:
    """Trait modifier charges deducted on use_magic approval."""

    def test_trait_modifier_charge_deducted(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        core = _core_trait_slot(db, owner_id=pc1.id, charge=3)
        db.flush()

        effect = _use_magic_effect(
            modifiers=[{"type": "core_trait", "id": core.id, "name": core.name, "bonus": 1}],
            costs={
                "gnosis": 0,
                "stress": 0,
                "free_time": 0,
                "bond_sacrifices": [],
                "trait_sacrifices": [],
                "trait_charges": [{"trait_id": core.id, "cost": 1}],
                "plot": 0,
            },
        )
        p = _pending_proposal(db, character_id=pc1.id, calculated_effect=effect)
        db.commit()

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/proposals/{p.id}/approve", json={})

        db.expire_all()
        db.refresh(core)
        assert core.charge == 2


class TestUseMagicApprovalEffectCreation:
    """MagicEffect is created when GM provides effect_details."""

    def test_magic_effect_created_on_approval(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        effect = _use_magic_effect()
        p = _pending_proposal(db, character_id=pc1.id, calculated_effect=effect)
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.post(
            f"/api/v1/proposals/{p.id}/approve",
            json={
                "gm_overrides": {
                    "effect_details": {
                        "name": "Ball of Fire",
                        "description": "A sphere of arcane flame.",
                        "effect_type": "instant",
                        "power_level": 2,
                    }
                }
            },
        )
        assert response.status_code == 200

        db.expire_all()
        created = (
            db.query(MagicEffect)
            .filter(
                MagicEffect.character_id == pc1.id,
                MagicEffect.name == "Ball of Fire",
            )
            .first()
        )
        assert created is not None
        assert created.effect_type == "instant"
        assert created.power_level == 2

    def test_charged_effect_created_with_charges(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        effect = _use_magic_effect()
        p = _pending_proposal(db, character_id=pc1.id, calculated_effect=effect)
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.post(
            f"/api/v1/proposals/{p.id}/approve",
            json={
                "gm_overrides": {
                    "effect_details": {
                        "name": "Crystal Focus",
                        "description": "Stores magical charge.",
                        "effect_type": "charged",
                        "power_level": 1,
                        "charges_current": 5,
                        "charges_max": 5,
                    }
                }
            },
        )
        assert response.status_code == 200

        db.expire_all()
        created = (
            db.query(MagicEffect)
            .filter(
                MagicEffect.character_id == pc1.id,
                MagicEffect.name == "Crystal Focus",
            )
            .first()
        )
        assert created is not None
        assert created.charges_current == 5
        assert created.charges_max == 5

    def test_effect_creation_recorded_in_event_changes(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        effect = _use_magic_effect()
        p = _pending_proposal(db, character_id=pc1.id, calculated_effect=effect)
        db.commit()

        auth_as(client, seed_data["gm"])
        client.post(
            f"/api/v1/proposals/{p.id}/approve",
            json={
                "gm_overrides": {
                    "effect_details": {
                        "name": "Flame Shield",
                        "description": "Protective aura.",
                        "effect_type": "permanent",
                        "power_level": 3,
                    }
                }
            },
        )

        db.expire_all()
        created = (
            db.query(MagicEffect)
            .filter(MagicEffect.character_id == pc1.id, MagicEffect.name == "Flame Shield")
            .first()
        )
        event = db.query(Event).filter(Event.proposal_id == p.id).first()
        change_key = f"magic_effect.{created.id}.created"
        assert change_key in event.changes

    def test_no_effect_created_when_effect_details_omitted(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        effect = _use_magic_effect()
        p = _pending_proposal(db, character_id=pc1.id, calculated_effect=effect)
        db.commit()

        auth_as(client, seed_data["gm"])
        client.post(f"/api/v1/proposals/{p.id}/approve", json={})

        db.expire_all()
        all_effects = (
            db.query(MagicEffect)
            .filter(MagicEffect.character_id == pc1.id)
            .all()
        )
        assert len(all_effects) == 0


# ===========================================================================
# charge_magic approval — charged effects
# ===========================================================================


class TestChargeMagicApprovalChargedEffect:
    """Charges added to charged effects on charge_magic approval."""

    def _charge_magic_effect(
        self,
        *,
        target_effect: dict,
        costs: dict | None = None,
    ) -> dict:
        return {
            "suggested_stat": "enchanting",
            "stat_level": 0,
            "dice_pool": 0,
            "sacrifice_dice": 0,
            "total_gnosis_equivalent": 0,
            "sacrifice_details": [],
            "modifiers": [],
            "target_effect": target_effect,
            "costs": costs or {
                "gnosis": 0,
                "stress": 0,
                "free_time": 0,
                "bond_sacrifices": [],
                "trait_sacrifices": [],
                "trait_charges": [],
                "plot": 0,
            },
        }

    def test_charges_added_to_current(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        eff = _magic_effect(
            db, character_id=pc1.id, effect_type="charged", charges_current=2, charges_max=5
        )
        db.flush()

        calc = self._charge_magic_effect(
            target_effect={
                "id": eff.id,
                "name": eff.name,
                "effect_type": "charged",
                "power_level": eff.power_level,
                "charges_current": eff.charges_current,
                "charges_max": eff.charges_max,
            }
        )
        p = _pending_proposal(
            db, character_id=pc1.id, action_type="charge_magic", calculated_effect=calc
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.post(
            f"/api/v1/proposals/{p.id}/approve",
            json={"gm_overrides": {"charges_added": 2}},
        )
        assert response.status_code == 200

        db.expire_all()
        db.refresh(eff)
        assert eff.charges_current == 4
        assert eff.charges_max == 5  # no growth needed

    def test_charges_added_grows_max_when_current_exceeds_max(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        eff = _magic_effect(
            db, character_id=pc1.id, effect_type="charged", charges_current=4, charges_max=5
        )
        db.flush()

        calc = self._charge_magic_effect(
            target_effect={
                "id": eff.id,
                "name": eff.name,
                "effect_type": "charged",
                "power_level": eff.power_level,
                "charges_current": eff.charges_current,
                "charges_max": eff.charges_max,
            }
        )
        p = _pending_proposal(
            db, character_id=pc1.id, action_type="charge_magic", calculated_effect=calc
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.post(
            f"/api/v1/proposals/{p.id}/approve",
            json={"gm_overrides": {"charges_added": 3}},
        )
        assert response.status_code == 200

        db.expire_all()
        db.refresh(eff)
        assert eff.charges_current == 7  # 4 + 3
        assert eff.charges_max == 7    # grew to match

    def test_charges_max_growth_recorded_in_event(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        eff = _magic_effect(
            db, character_id=pc1.id, effect_type="charged", charges_current=4, charges_max=5
        )
        db.flush()

        calc = self._charge_magic_effect(
            target_effect={
                "id": eff.id,
                "name": eff.name,
                "effect_type": "charged",
                "power_level": eff.power_level,
                "charges_current": eff.charges_current,
                "charges_max": eff.charges_max,
            }
        )
        p = _pending_proposal(
            db, character_id=pc1.id, action_type="charge_magic", calculated_effect=calc
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        client.post(
            f"/api/v1/proposals/{p.id}/approve",
            json={"gm_overrides": {"charges_added": 3}},
        )

        db.expire_all()
        event = db.query(Event).filter(Event.proposal_id == p.id).first()
        max_key = f"magic_effect.{eff.id}.charges_max"
        current_key = f"magic_effect.{eff.id}.charges_current"
        assert current_key in event.changes
        assert max_key in event.changes
        assert event.changes[max_key]["before"] == 5
        assert event.changes[max_key]["after"] == 7


# ===========================================================================
# charge_magic approval — permanent effects
# ===========================================================================


class TestChargeMagicApprovalPermanentEffect:
    """Power level boosted on permanent effects via charge_magic approval."""

    def _charge_magic_effect(
        self,
        *,
        target_effect: dict,
        costs: dict | None = None,
    ) -> dict:
        return {
            "suggested_stat": "enchanting",
            "stat_level": 0,
            "dice_pool": 0,
            "sacrifice_dice": 0,
            "total_gnosis_equivalent": 0,
            "sacrifice_details": [],
            "modifiers": [],
            "target_effect": target_effect,
            "costs": costs or {
                "gnosis": 0,
                "stress": 0,
                "free_time": 0,
                "bond_sacrifices": [],
                "trait_sacrifices": [],
                "trait_charges": [],
                "plot": 0,
            },
        }

    def test_power_level_increased_on_permanent_effect(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        eff = _magic_effect(
            db,
            character_id=pc1.id,
            effect_type="permanent",
            power_level=2,
            charges_current=None,
            charges_max=None,
        )
        db.flush()

        calc = self._charge_magic_effect(
            target_effect={
                "id": eff.id,
                "name": eff.name,
                "effect_type": "permanent",
                "power_level": eff.power_level,
                "charges_current": None,
                "charges_max": None,
            }
        )
        p = _pending_proposal(
            db, character_id=pc1.id, action_type="charge_magic", calculated_effect=calc
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.post(
            f"/api/v1/proposals/{p.id}/approve",
            json={"gm_overrides": {"power_boost": 2}},
        )
        assert response.status_code == 200

        db.expire_all()
        db.refresh(eff)
        assert eff.power_level == 4

    def test_power_level_capped_at_5(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        eff = _magic_effect(
            db,
            character_id=pc1.id,
            effect_type="permanent",
            power_level=4,
            charges_current=None,
            charges_max=None,
        )
        db.flush()

        calc = self._charge_magic_effect(
            target_effect={
                "id": eff.id,
                "name": eff.name,
                "effect_type": "permanent",
                "power_level": eff.power_level,
                "charges_current": None,
                "charges_max": None,
            }
        )
        p = _pending_proposal(
            db, character_id=pc1.id, action_type="charge_magic", calculated_effect=calc
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.post(
            f"/api/v1/proposals/{p.id}/approve",
            json={"gm_overrides": {"power_boost": 10}},
        )
        assert response.status_code == 200

        db.expire_all()
        db.refresh(eff)
        assert eff.power_level == 5  # capped

    def test_power_change_recorded_in_event(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        eff = _magic_effect(
            db,
            character_id=pc1.id,
            effect_type="permanent",
            power_level=1,
            charges_current=None,
            charges_max=None,
        )
        db.flush()

        calc = self._charge_magic_effect(
            target_effect={
                "id": eff.id,
                "name": eff.name,
                "effect_type": "permanent",
                "power_level": eff.power_level,
                "charges_current": None,
                "charges_max": None,
            }
        )
        p = _pending_proposal(
            db, character_id=pc1.id, action_type="charge_magic", calculated_effect=calc
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        client.post(
            f"/api/v1/proposals/{p.id}/approve",
            json={"gm_overrides": {"power_boost": 1}},
        )

        db.expire_all()
        event = db.query(Event).filter(Event.proposal_id == p.id).first()
        power_key = f"magic_effect.{eff.id}.power_level"
        assert power_key in event.changes
        assert event.changes[power_key]["before"] == 1
        assert event.changes[power_key]["after"] == 2


# ===========================================================================
# charge_magic — sacrifice costs applied identically to use_magic
# ===========================================================================


class TestChargeMagicSacrificeDeduction:
    """Sacrifice deductions work the same as use_magic."""

    def _charge_magic_effect(self, *, target_id: str, target_name: str, costs: dict) -> dict:
        return {
            "suggested_stat": "enchanting",
            "stat_level": 0,
            "dice_pool": 0,
            "sacrifice_dice": 0,
            "total_gnosis_equivalent": 0,
            "sacrifice_details": [],
            "modifiers": [],
            "target_effect": {
                "id": target_id,
                "name": target_name,
                "effect_type": "charged",
                "power_level": 1,
                "charges_current": 0,
                "charges_max": 5,
            },
            "costs": costs,
        }

    def test_gnosis_deducted_on_charge_magic_approval(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        pc1.gnosis = 8
        db.flush()
        eff = _magic_effect(
            db, character_id=pc1.id, effect_type="charged", charges_current=0, charges_max=5
        )
        db.flush()

        calc = self._charge_magic_effect(
            target_id=eff.id,
            target_name=eff.name,
            costs={
                "gnosis": 4,
                "stress": 0,
                "free_time": 0,
                "bond_sacrifices": [],
                "trait_sacrifices": [],
                "trait_charges": [],
                "plot": 0,
            },
        )
        p = _pending_proposal(
            db, character_id=pc1.id, action_type="charge_magic", calculated_effect=calc
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.post(
            f"/api/v1/proposals/{p.id}/approve",
            json={"gm_overrides": {"charges_added": 3}},
        )
        assert response.status_code == 200

        db.expire_all()
        db.refresh(pc1)
        assert pc1.gnosis == 4


# ===========================================================================
# plot_spend support in magic actions
# ===========================================================================


class TestUseMagicPlotSpend:
    """Plot spend is validated on submission and deducted on approval."""

    def test_plot_spend_recorded_in_calculated_effect(
        self, db: Session, seed_data: dict
    ) -> None:
        """plot_spend is reflected in costs.plot and in the top-level plot_spend field."""
        pc1 = seed_data["pc1"]
        pc1.plot = 3
        db.flush()

        result = calculate_use_magic(
            db,
            character_id=pc1.id,
            selections={
                "suggested_stat": "being",
                "plot_spend": 2,
            },
        )

        assert result["plot_spend"] == 2
        assert result["costs"]["plot"] == 2

    def test_plot_spend_deducted_on_approval(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Approving a use_magic proposal with plot cost deducts Plot from the character."""
        pc1 = seed_data["pc1"]
        pc1.plot = 5
        db.flush()

        effect = _use_magic_effect(
            costs={
                "gnosis": 0,
                "stress": 0,
                "free_time": 0,
                "bond_sacrifices": [],
                "trait_sacrifices": [],
                "trait_charges": [],
                "plot": 3,
            }
        )
        p = _pending_proposal(db, character_id=pc1.id, calculated_effect=effect)
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.post(f"/api/v1/proposals/{p.id}/approve", json={})
        assert response.status_code == 200

        db.expire_all()
        db.refresh(pc1)
        assert pc1.plot == 2

    def test_plot_spend_zero_not_validated_when_absent(
        self, db: Session, seed_data: dict
    ) -> None:
        """plot_spend defaults to 0 if omitted; no Plot is deducted."""
        pc1 = seed_data["pc1"]
        pc1.plot = 1
        db.flush()

        result = calculate_use_magic(
            db,
            character_id=pc1.id,
            selections={
                "suggested_stat": "being",
            },
        )
        assert result["costs"]["plot"] == 0

    def test_plot_spend_exceeds_available_returns_422(
        self, db: Session, seed_data: dict
    ) -> None:
        """Requesting more Plot than available raises 422."""
        from fastapi import HTTPException  # noqa: PLC0415

        pc1 = seed_data["pc1"]
        pc1.plot = 1
        db.flush()

        with pytest.raises(HTTPException) as exc_info:
            calculate_use_magic(
                db,
                character_id=pc1.id,
                selections={
                    "suggested_stat": "being",
                    "plot_spend": 5,
                },
            )
        assert exc_info.value.status_code == 422

    def test_charge_magic_plot_spend_deducted_on_approval(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """charge_magic also deducts Plot when costs.plot > 0."""
        pc1 = seed_data["pc1"]
        pc1.plot = 4
        db.flush()
        eff = _magic_effect(
            db, character_id=pc1.id, effect_type="charged", charges_current=1, charges_max=5
        )
        db.flush()

        calc = {
            "suggested_stat": "enchanting",
            "stat_level": 0,
            "dice_pool": 0,
            "sacrifice_dice": 0,
            "total_gnosis_equivalent": 0,
            "sacrifice_details": [],
            "modifiers": [],
            "target_effect": {
                "id": eff.id,
                "name": eff.name,
                "effect_type": "charged",
                "power_level": 1,
                "charges_current": 1,
                "charges_max": 5,
            },
            "costs": {
                "gnosis": 0,
                "stress": 0,
                "free_time": 0,
                "bond_sacrifices": [],
                "trait_sacrifices": [],
                "trait_charges": [],
                "plot": 2,
            },
        }
        p = _pending_proposal(
            db, character_id=pc1.id, action_type="charge_magic", calculated_effect=calc
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.post(
            f"/api/v1/proposals/{p.id}/approve",
            json={"gm_overrides": {"charges_added": 2}},
        )
        assert response.status_code == 200

        db.expire_all()
        db.refresh(pc1)
        assert pc1.plot == 2


# ===========================================================================
# bond_strained on magic actions
# ===========================================================================


class TestUseMagicBondStrained:
    """bond_strained GM override strains the modifier bond on use_magic approval."""

    def test_bond_charges_decremented_on_use_magic_with_bond_strained(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """bond_strained=True decrements charges on the modifier bond."""
        pc1 = seed_data["pc1"]
        bond = _pc_bond_slot(db, owner_id=pc1.id, name="My Bond", charges=5)
        db.flush()

        effect = _use_magic_effect(
            modifiers=[{"type": "bond", "id": bond.id, "name": bond.name, "bonus": 1}],
            costs={
                "gnosis": 0,
                "stress": 0,
                "free_time": 0,
                "bond_sacrifices": [],
                "trait_sacrifices": [],
                "trait_charges": [],
                "plot": 0,
            },
        )
        p = _pending_proposal(db, character_id=pc1.id, calculated_effect=effect)
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.post(
            f"/api/v1/proposals/{p.id}/approve",
            json={"gm_overrides": {"bond_strained": True}},
        )
        assert response.status_code == 200

        db.expire_all()
        db.refresh(bond)
        assert bond.charges == 4

    def test_bond_strained_no_modifier_bond_does_nothing(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """bond_strained=True without a bond modifier is a no-op."""
        pc1 = seed_data["pc1"]

        effect = _use_magic_effect()
        p = _pending_proposal(db, character_id=pc1.id, calculated_effect=effect)
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.post(
            f"/api/v1/proposals/{p.id}/approve",
            json={"gm_overrides": {"bond_strained": True}},
        )
        assert response.status_code == 200

    def test_bond_strained_at_zero_triggers_degradation_on_use_magic(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """bond_strained fires degradation when charges hit 0."""
        pc1 = seed_data["pc1"]
        # charges=1 means one more decrement (to 0) triggers degradation.
        bond = _pc_bond_slot(db, owner_id=pc1.id, name="Strained Bond", charges=1)
        db.flush()

        effect = _use_magic_effect(
            modifiers=[{"type": "bond", "id": bond.id, "name": bond.name, "bonus": 1}],
            costs={
                "gnosis": 0,
                "stress": 0,
                "free_time": 0,
                "bond_sacrifices": [],
                "trait_sacrifices": [],
                "trait_charges": [],
                "plot": 0,
            },
        )
        p = _pending_proposal(db, character_id=pc1.id, calculated_effect=effect)
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.post(
            f"/api/v1/proposals/{p.id}/approve",
            json={"gm_overrides": {"bond_strained": True}},
        )
        assert response.status_code == 200

        db.expire_all()
        db.refresh(bond)
        # Degradation fired: charges reset to new effective max (4), degradations incremented.
        assert bond.charges == 4
        assert bond.degradations == 1

    def test_charge_magic_bond_strained_decrements_charges(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """bond_strained also works for charge_magic approvals."""
        pc1 = seed_data["pc1"]
        bond = _pc_bond_slot(db, owner_id=pc1.id, name="My Bond", charges=3)
        eff = _magic_effect(
            db, character_id=pc1.id, effect_type="charged", charges_current=1, charges_max=5
        )
        db.flush()

        calc = {
            "suggested_stat": "enchanting",
            "stat_level": 0,
            "dice_pool": 1,
            "sacrifice_dice": 0,
            "total_gnosis_equivalent": 0,
            "sacrifice_details": [],
            "modifiers": [{"type": "bond", "id": bond.id, "name": bond.name, "bonus": 1}],
            "target_effect": {
                "id": eff.id,
                "name": eff.name,
                "effect_type": "charged",
                "power_level": 1,
                "charges_current": 1,
                "charges_max": 5,
            },
            "costs": {
                "gnosis": 0,
                "stress": 0,
                "free_time": 0,
                "bond_sacrifices": [],
                "trait_sacrifices": [],
                "trait_charges": [],
                "plot": 0,
            },
        }
        p = _pending_proposal(
            db, character_id=pc1.id, action_type="charge_magic", calculated_effect=calc
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = client.post(
            f"/api/v1/proposals/{p.id}/approve",
            json={"gm_overrides": {"bond_strained": True, "charges_added": 1}},
        )
        assert response.status_code == 200

        db.expire_all()
        db.refresh(bond)
        assert bond.charges == 2
