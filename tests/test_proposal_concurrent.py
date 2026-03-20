"""Concurrent proposal tests — L17.

Tests scenarios where two proposals try to consume the same resource:
- Two proposals both need Plot, character has enough for one but not both:
  submit both, approve first, second fails affordability on approval.
- Two rest proposals, character has 1 FT:
  submit both, approve first, second fails affordability on approval.

Note: SQLite doesn't support true concurrency in tests, so these tests
simulate the race-condition outcome: two proposals are submitted while
the resource is available, then approved sequentially.  The second
approval must fail with 409 insufficient_resources.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import auth_as
from wizards_engine.models.proposal import Proposal
from wizards_engine.models.slot import Slot, TraitTemplate
from wizards_engine.models.story import Story


# ===========================================================================
# Helpers
# ===========================================================================


def _pending_proposal(
    db: Session,
    *,
    character_id: str,
    action_type: str,
    calculated_effect: dict,
    narrative: str = "A concurrent proposal.",
) -> Proposal:
    """Create and flush a minimal pending Proposal."""
    p = Proposal(
        character_id=character_id,
        action_type=action_type,
        origin="player",
        narrative=narrative,
        selections={},
        calculated_effect=calculated_effect,
        status="pending",
    )
    db.add(p)
    db.flush()
    db.refresh(p)
    return p


def _approve(client: TestClient, proposal_id: str, body: dict | None = None):
    """POST approve on a proposal and return the response."""
    return client.post(
        f"/api/v1/proposals/{proposal_id}/approve",
        json=body or {},
    )


# ===========================================================================
# Two proposals competing for Plot
# ===========================================================================


class TestConcurrentPlotProposals:
    """Two use_skill proposals both spending Plot: only the first approval succeeds."""

    def test_first_approved_second_fails_insufficient_plot(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Character has 3 Plot. Both proposals cost 2 Plot each.
        First approval succeeds and spends 2 Plot (leaving 1).
        Second approval fails with 409 insufficient_resources because
        only 1 Plot remains but 2 is required."""
        pc1 = seed_data["pc1"]
        pc1.plot = 3
        db.flush()

        effect_plot_2 = {
            "dice_pool": 0,
            "skill": "awareness",
            "skill_level": 0,
            "modifiers": [],
            "plot_spend": 2,
            "costs": {
                "trait_charges": [],
                "plot": 2,
            },
        }

        p1 = _pending_proposal(
            db, character_id=pc1.id, action_type="use_skill", calculated_effect=effect_plot_2
        )
        p2 = _pending_proposal(
            db, character_id=pc1.id, action_type="use_skill", calculated_effect=effect_plot_2
        )
        db.commit()

        auth_as(client, seed_data["gm"])

        # First approval: should succeed.
        resp1 = _approve(client, p1.id)
        assert resp1.status_code == 200
        assert resp1.json()["status"] == "approved"

        db.expire_all()
        db.refresh(pc1)
        assert pc1.plot == 1  # 3 - 2

        # Second approval: character now only has 1 Plot, needs 2.
        resp2 = _approve(client, p2.id)
        assert resp2.status_code == 409
        assert resp2.json()["error"]["code"] == "insufficient_resources"
        assert "plot" in resp2.json()["error"]["details"]

    def test_second_can_succeed_with_force_override(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """With force=True, the second approval can bypass the check."""
        pc1 = seed_data["pc1"]
        pc1.plot = 3
        db.flush()

        effect_plot_2 = {
            "dice_pool": 0,
            "skill": "awareness",
            "skill_level": 0,
            "modifiers": [],
            "plot_spend": 2,
            "costs": {
                "trait_charges": [],
                "plot": 2,
            },
        }

        p1 = _pending_proposal(
            db, character_id=pc1.id, action_type="use_skill", calculated_effect=effect_plot_2
        )
        p2 = _pending_proposal(
            db, character_id=pc1.id, action_type="use_skill", calculated_effect=effect_plot_2
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        _approve(client, p1.id)

        # Second with force=True bypasses affordability check.
        resp2 = _approve(client, p2.id, body={"gm_overrides": {"force": True}})
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "approved"

    def test_second_proposal_status_remains_pending_after_failure(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """A 409 on approval does not change the proposal's status from pending."""
        pc1 = seed_data["pc1"]
        pc1.plot = 2
        db.flush()

        effect_plot_2 = {
            "dice_pool": 0,
            "skill": "awareness",
            "skill_level": 0,
            "modifiers": [],
            "plot_spend": 2,
            "costs": {
                "trait_charges": [],
                "plot": 2,
            },
        }

        p1 = _pending_proposal(
            db, character_id=pc1.id, action_type="use_skill", calculated_effect=effect_plot_2
        )
        p2 = _pending_proposal(
            db, character_id=pc1.id, action_type="use_skill", calculated_effect=effect_plot_2
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        _approve(client, p1.id)  # Uses all plot.

        # Second fails.
        _approve(client, p2.id)

        # p2 must still be pending — 409 is a check error, not a state change.
        db.expire_all()
        db.refresh(p2)
        assert p2.status == "pending"


# ===========================================================================
# Two rest proposals competing for 1 FT
# ===========================================================================


class TestConcurrentRestProposals:
    """Two rest proposals submitted when character has exactly 1 FT."""

    def test_first_rest_approved_second_fails_insufficient_ft(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Both proposals submitted with 1 FT. First approval deducts FT to 0.
        Second approval fails with insufficient_resources."""
        pc1 = seed_data["pc1"]
        pc1.stress = 5
        pc1.free_time = 1
        db.flush()

        rest_effect = {
            "stress_healed": 3,
            "costs": {"free_time": 1, "trait_charges": []},
        }

        p1 = _pending_proposal(
            db, character_id=pc1.id, action_type="rest", calculated_effect=rest_effect
        )
        p2 = _pending_proposal(
            db, character_id=pc1.id, action_type="rest", calculated_effect=rest_effect
        )
        db.commit()

        auth_as(client, seed_data["gm"])

        # First approval: succeeds.
        resp1 = _approve(client, p1.id)
        assert resp1.status_code == 200

        db.expire_all()
        db.refresh(pc1)
        assert pc1.free_time == 0  # FT consumed

        # Second approval: character has 0 FT.
        resp2 = _approve(client, p2.id)
        assert resp2.status_code == 409
        assert resp2.json()["error"]["code"] == "insufficient_resources"
        assert "free_time" in resp2.json()["error"]["details"]

    def test_two_rest_proposals_both_fail_when_zero_ft_from_start(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Edge case: both proposals submitted while FT=0 (shouldn't happen via submit,
        but if directly created, both fail at approval time)."""
        pc1 = seed_data["pc1"]
        pc1.stress = 5
        pc1.free_time = 0
        db.flush()

        rest_effect = {
            "stress_healed": 3,
            "costs": {"free_time": 1, "trait_charges": []},
        }

        p1 = _pending_proposal(
            db, character_id=pc1.id, action_type="rest", calculated_effect=rest_effect
        )
        p2 = _pending_proposal(
            db, character_id=pc1.id, action_type="rest", calculated_effect=rest_effect
        )
        db.commit()

        auth_as(client, seed_data["gm"])

        resp1 = _approve(client, p1.id)
        assert resp1.status_code == 409
        assert resp1.json()["error"]["code"] == "insufficient_resources"

        resp2 = _approve(client, p2.id)
        assert resp2.status_code == 409
        assert resp2.json()["error"]["code"] == "insufficient_resources"

    def test_second_rest_can_still_be_approved_after_ft_replenished(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """After the second proposal fails, if FT is replenished it can be approved."""
        pc1 = seed_data["pc1"]
        pc1.stress = 6
        pc1.free_time = 1
        db.flush()

        rest_effect = {
            "stress_healed": 3,
            "costs": {"free_time": 1, "trait_charges": []},
        }

        p1 = _pending_proposal(
            db, character_id=pc1.id, action_type="rest", calculated_effect=rest_effect
        )
        p2 = _pending_proposal(
            db, character_id=pc1.id, action_type="rest", calculated_effect=rest_effect
        )
        db.commit()

        auth_as(client, seed_data["gm"])

        # First approval succeeds.
        _approve(client, p1.id)

        # Second fails.
        resp2 = _approve(client, p2.id)
        assert resp2.status_code == 409

        # Replenish FT.
        db.expire_all()
        pc1.free_time = 2
        db.commit()

        # Now second proposal can be approved.
        resp2_retry = _approve(client, p2.id)
        assert resp2_retry.status_code == 200
        assert resp2_retry.json()["status"] == "approved"


# ===========================================================================
# Two proposals competing for a trait charge
# ===========================================================================


class TestConcurrentTraitChargeProposals:
    """Two use_skill proposals both needing the same trait with 1 charge."""

    def test_first_approved_second_fails_insufficient_trait_charge(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Character has a trait with 1 charge. Both proposals use that trait.
        First approval succeeds and spends the charge.
        Second approval fails with 409 insufficient_resources."""
        pc1 = seed_data["pc1"]
        trait = Slot(
            slot_type="core_trait",
            owner_type="character",
            owner_id=pc1.id,
            name="Last Charge",
            charge=1,
            is_active=True,
        )
        db.add(trait)
        db.flush()
        db.refresh(trait)

        effect_with_trait = {
            "dice_pool": 1,
            "skill": "awareness",
            "skill_level": 0,
            "modifiers": [{"type": "core_trait", "id": trait.id, "name": "Last Charge", "bonus": 1}],
            "plot_spend": 0,
            "costs": {
                "trait_charges": [{"trait_id": trait.id, "cost": 1}],
                "plot": 0,
            },
        }

        p1 = _pending_proposal(
            db, character_id=pc1.id, action_type="use_skill", calculated_effect=effect_with_trait
        )
        p2 = _pending_proposal(
            db, character_id=pc1.id, action_type="use_skill", calculated_effect=effect_with_trait
        )
        db.commit()

        auth_as(client, seed_data["gm"])

        # First approval: succeeds, trait charge goes to 0.
        resp1 = _approve(client, p1.id)
        assert resp1.status_code == 200

        db.expire_all()
        db.refresh(trait)
        assert trait.charge == 0

        # Second approval: trait has 0 charges.
        resp2 = _approve(client, p2.id)
        assert resp2.status_code == 409
        assert resp2.json()["error"]["code"] == "insufficient_resources"
        error_details = resp2.json()["error"]["details"]
        # The error should mention the trait.
        assert any("trait" in k for k in error_details)
