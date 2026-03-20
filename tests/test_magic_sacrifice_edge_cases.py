"""Magic sacrifice edge cases — L16.

Covers gaps in test_magic_actions.py:
- Sacrifice all gnosis (amount equals current gnosis)
- Mixed source sacrifice (gnosis + stress + free_time in one proposal)
- Boundary values: stress exactly at effective max after sacrifice
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import auth_as
from wizards_engine.models.event import Event
from wizards_engine.models.proposal import Proposal
from wizards_engine.models.slot import Slot


# ===========================================================================
# Helpers (minimal copies from test_magic_actions.py patterns)
# ===========================================================================


def _pending_proposal(
    db: Session,
    *,
    character_id: str,
    action_type: str = "use_magic",
    calculated_effect: dict | None = None,
    narrative: str = "I work magic.",
) -> Proposal:
    """Create and flush a minimal pending Proposal."""
    p = Proposal(
        character_id=character_id,
        action_type=action_type,
        origin="player",
        narrative=narrative,
        selections={},
        calculated_effect=calculated_effect or {},
        status="pending",
    )
    db.add(p)
    db.flush()
    db.refresh(p)
    return p


def _use_magic_effect(
    *,
    costs: dict | None = None,
) -> dict:
    """Build a minimal calculated_effect for a use_magic proposal."""
    return {
        "suggested_stat": "being",
        "stat_level": 0,
        "dice_pool": 1,
        "sacrifice_dice": 0,
        "total_gnosis_equivalent": 0,
        "sacrifice_details": [],
        "modifiers": [],
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


# ===========================================================================
# Sacrifice all gnosis
# ===========================================================================


class TestSacrificeAllGnosis:
    """Edge case: sacrifice the entire gnosis pool in one action."""

    def test_sacrifice_all_gnosis_reduces_to_zero(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Sacrificing exactly current gnosis leaves gnosis at 0."""
        pc1 = seed_data["pc1"]
        pc1.gnosis = 6
        db.flush()

        effect = _use_magic_effect(
            costs={
                "gnosis": 6,  # exactly all gnosis
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
        resp = client.post(f"/api/v1/proposals/{p.id}/approve", json={})
        assert resp.status_code == 200

        db.expire_all()
        db.refresh(pc1)
        assert pc1.gnosis == 0

    def test_sacrifice_more_than_gnosis_clamps_at_zero(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Sacrificing more gnosis than available clamps to 0, not negative."""
        pc1 = seed_data["pc1"]
        pc1.gnosis = 3
        db.flush()

        effect = _use_magic_effect(
            costs={
                "gnosis": 10,  # far exceeds available
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
        resp = client.post(
            f"/api/v1/proposals/{p.id}/approve",
            json={"gm_overrides": {"force": True}},
        )
        assert resp.status_code == 200

        db.expire_all()
        db.refresh(pc1)
        assert pc1.gnosis == 0  # clamped, not negative

    def test_event_records_gnosis_before_after_on_full_sacrifice(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """The event changes dict records the gnosis before/after transition."""
        pc1 = seed_data["pc1"]
        pc1.gnosis = 5
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
        client.post(f"/api/v1/proposals/{p.id}/approve", json={})

        db.expire_all()
        ev = db.query(Event).filter(Event.proposal_id == p.id).first()
        assert ev is not None
        gnosis_key = f"character.{pc1.id}.gnosis"
        assert gnosis_key in ev.changes
        assert ev.changes[gnosis_key]["before"] == 5
        assert ev.changes[gnosis_key]["after"] == 0


# ===========================================================================
# Mixed source sacrifice (gnosis + stress + free_time)
# ===========================================================================


class TestMixedSourceSacrifice:
    """Edge case: sacrifice from multiple sources in a single proposal."""

    def test_all_three_sources_deducted_on_approval(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Gnosis, stress, and free_time are all deducted when all three are sacrificed."""
        pc1 = seed_data["pc1"]
        pc1.gnosis = 10
        pc1.stress = 2
        pc1.free_time = 3
        db.flush()

        effect = _use_magic_effect(
            costs={
                "gnosis": 3,
                "stress": 2,
                "free_time": 1,
                "bond_sacrifices": [],
                "trait_sacrifices": [],
                "trait_charges": [],
                "plot": 0,
            }
        )
        p = _pending_proposal(db, character_id=pc1.id, calculated_effect=effect)
        db.commit()

        auth_as(client, seed_data["gm"])
        resp = client.post(f"/api/v1/proposals/{p.id}/approve", json={})
        assert resp.status_code == 200

        db.expire_all()
        db.refresh(pc1)
        assert pc1.gnosis == 7    # 10 - 3
        assert pc1.stress == 4    # 2 + 2 (stress sacrifice adds, not removes)
        assert pc1.free_time == 2  # 3 - 1

    def test_mixed_sacrifice_event_records_all_changes(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Event changes dict records all three meter changes."""
        pc1 = seed_data["pc1"]
        pc1.gnosis = 8
        pc1.stress = 1
        pc1.free_time = 2
        db.flush()

        effect = _use_magic_effect(
            costs={
                "gnosis": 2,
                "stress": 1,
                "free_time": 1,
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
        ev = db.query(Event).filter(Event.proposal_id == p.id).first()
        assert ev is not None

        gnosis_key = f"character.{pc1.id}.gnosis"
        stress_key = f"character.{pc1.id}.stress"
        ft_key = f"character.{pc1.id}.free_time"

        assert gnosis_key in ev.changes
        assert ev.changes[gnosis_key]["before"] == 8
        assert ev.changes[gnosis_key]["after"] == 6

        assert stress_key in ev.changes
        assert ev.changes[stress_key]["before"] == 1
        assert ev.changes[stress_key]["after"] == 2  # 1 + 1

        assert ft_key in ev.changes
        assert ev.changes[ft_key]["before"] == 2
        assert ev.changes[ft_key]["after"] == 1

    def test_gnosis_plus_stress_sacrifice_at_boundary(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Gnosis + stress sacrifice where stress hits effective max creates resolve_trauma."""
        pc1 = seed_data["pc1"]
        pc1.gnosis = 5
        pc1.stress = 7   # effective_max = 9; 7 + 2 >= 9
        pc1.free_time = 0
        db.flush()

        effect = _use_magic_effect(
            costs={
                "gnosis": 2,
                "stress": 2,   # pushes 7 + 2 = 9 = effective_max
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
        resp = client.post(f"/api/v1/proposals/{p.id}/approve", json={})
        assert resp.status_code == 200

        db.expire_all()
        db.refresh(pc1)
        assert pc1.gnosis == 3     # 5 - 2
        assert pc1.stress == 9     # clamped at effective_max

        # resolve_trauma auto-generated.
        trauma_p = (
            db.query(Proposal)
            .filter(
                Proposal.character_id == pc1.id,
                Proposal.action_type == "resolve_trauma",
                Proposal.status == "pending",
            )
            .first()
        )
        assert trauma_p is not None


# ===========================================================================
# Boundary values: stress exactly at effective max
# ===========================================================================


class TestStressBoundaryAfterSacrifice:
    """Edge cases around the stress boundary after magic sacrifice."""

    def test_stress_exactly_at_effective_max_generates_trauma(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Stress sacrifice that lands exactly on effective max (not over) triggers trauma."""
        pc1 = seed_data["pc1"]
        pc1.stress = 7
        pc1.gnosis = 0
        db.flush()

        effect = _use_magic_effect(
            costs={
                "gnosis": 0,
                "stress": 2,   # 7 + 2 = 9 = effective_max (no traumas)
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
        resp = client.post(f"/api/v1/proposals/{p.id}/approve", json={})
        assert resp.status_code == 200

        db.expire_all()
        db.refresh(pc1)
        assert pc1.stress == 9  # exactly at max, not over

        trauma_p = (
            db.query(Proposal)
            .filter(
                Proposal.character_id == pc1.id,
                Proposal.action_type == "resolve_trauma",
            )
            .first()
        )
        assert trauma_p is not None
        assert trauma_p.status == "pending"

    def test_stress_one_below_max_does_not_generate_trauma(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Stress sacrifice that reaches exactly effective_max - 1 does not trigger trauma."""
        pc1 = seed_data["pc1"]
        pc1.stress = 6
        pc1.gnosis = 0
        db.flush()

        effect = _use_magic_effect(
            costs={
                "gnosis": 0,
                "stress": 2,   # 6 + 2 = 8 = effective_max - 1
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
        resp = client.post(f"/api/v1/proposals/{p.id}/approve", json={})
        assert resp.status_code == 200

        db.expire_all()
        db.refresh(pc1)
        assert pc1.stress == 8  # 1 below max

        trauma_p = (
            db.query(Proposal)
            .filter(
                Proposal.character_id == pc1.id,
                Proposal.action_type == "resolve_trauma",
            )
            .first()
        )
        assert trauma_p is None

    def test_stress_boundary_clamped_when_sacrifice_exceeds_max(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Stress is clamped to effective_max even if sacrifice amount would exceed it."""
        pc1 = seed_data["pc1"]
        pc1.stress = 6
        pc1.gnosis = 0
        db.flush()

        effect = _use_magic_effect(
            costs={
                "gnosis": 0,
                "stress": 5,   # 6 + 5 = 11, but effective_max = 9
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
        resp = client.post(f"/api/v1/proposals/{p.id}/approve", json={})
        assert resp.status_code == 200

        db.expire_all()
        db.refresh(pc1)
        assert pc1.stress == 9  # clamped at effective_max

    def test_stress_sacrifice_clamped_event_has_clamped_flag(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """When stress is clamped, the event changes entry includes clamped=True."""
        pc1 = seed_data["pc1"]
        pc1.stress = 8
        db.flush()

        effect = _use_magic_effect(
            costs={
                "gnosis": 0,
                "stress": 3,   # would push to 11, clamped to 9
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
        ev = db.query(Event).filter(Event.proposal_id == p.id).first()
        stress_key = f"character.{pc1.id}.stress"
        assert stress_key in ev.changes
        assert ev.changes[stress_key].get("clamped") is True
