"""Full proposal lifecycle integration tests — L15.

For each of the 8 player-submittable action types, tests the full lifecycle:
  1. Player submits proposal → status is "pending"
  2. GM approves → status is "approved", character state changes
  3. Event created on approval

System proposals (resolve_clock, resolve_trauma) are tested for auto-generation:
  - resolve_clock: triggered by advancing a clock to completion via GM action
  - resolve_trauma: triggered by magic stress sacrifice hitting effective stress max

Action types covered: use_skill, use_magic, charge_magic, regain_gnosis,
work_on_project, rest, new_trait, new_bond, resolve_clock, resolve_trauma.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import auth_as
from wizards_engine.models.clock import Clock
from wizards_engine.models.event import Event
from wizards_engine.models.magic_effect import MagicEffect
from wizards_engine.models.proposal import Proposal
from wizards_engine.models.slot import Slot, TraitTemplate
from wizards_engine.models.story import Story


# ===========================================================================
# Shared helpers
# ===========================================================================


def _submit(client: TestClient, character_id: str, action_type: str, selections: dict, narrative: str = "A narrative."):
    """POST a proposal and return the response."""
    return client.post(
        "/api/v1/proposals",
        json={
            "character_id": character_id,
            "action_type": action_type,
            "narrative": narrative,
            "selections": selections,
        },
    )


def _approve(client: TestClient, proposal_id: str, body: dict | None = None):
    """POST approve and return the response."""
    return client.post(f"/api/v1/proposals/{proposal_id}/approve", json=body or {})


def _core_template(db: Session, name: str = "Courageous") -> TraitTemplate:
    t = TraitTemplate(name=name, description=f"Desc: {name}", type="core", is_deleted=False)
    db.add(t)
    db.flush()
    db.refresh(t)
    return t


def _core_trait(db: Session, character_id: str, name: str = "Brave", charge: int = 5) -> Slot:
    tmpl = _core_template(db, name)
    slot = Slot(
        slot_type="core_trait",
        owner_type="character",
        owner_id=character_id,
        name=name,
        template_id=tmpl.id,
        charge=charge,
        is_active=True,
    )
    db.add(slot)
    db.flush()
    db.refresh(slot)
    return slot


def _story(db: Session, name: str = "Test Project") -> Story:
    s = Story(name=name, status="active", is_deleted=False)
    db.add(s)
    db.flush()
    db.refresh(s)
    return s


def _magic_effect(
    db: Session,
    character_id: str,
    name: str = "Test Effect",
    effect_type: str = "charged",
    charges_current: int = 3,
    charges_max: int = 5,
) -> MagicEffect:
    eff = MagicEffect(
        character_id=character_id,
        name=name,
        description="A test magical effect.",
        effect_type=effect_type,
        power_level=2,
        charges_current=charges_current,
        charges_max=charges_max,
        is_active=True,
    )
    db.add(eff)
    db.flush()
    db.refresh(eff)
    return eff


# ===========================================================================
# use_skill lifecycle
# ===========================================================================


class TestUseSkillLifecycle:
    """Full lifecycle for use_skill proposals."""

    def test_submit_pending_approve_approved_event_created(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        pc1.plot = 3
        db.commit()

        # 1. Submit.
        auth_as(client, seed_data["player1"])
        submit_resp = _submit(client, pc1.id, "use_skill", {"skill": "awareness"})
        assert submit_resp.status_code == 201
        proposal_id = submit_resp.json()["id"]
        assert submit_resp.json()["status"] == "pending"

        # 2. Approve.
        auth_as(client, seed_data["gm"])
        approve_resp = _approve(client, proposal_id)
        assert approve_resp.status_code == 200
        body = approve_resp.json()
        assert body["status"] == "approved"
        event_id = body["event_id"]

        # 3. Event created.
        assert event_id is not None
        db.expire_all()
        ev = db.get(Event, event_id)
        assert ev is not None
        assert ev.type == "proposal.approved"
        assert ev.proposal_id == proposal_id

    def test_plot_deducted_on_approval_with_plot_spend(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Plot is deducted when the proposal includes a plot spend."""
        pc1 = seed_data["pc1"]
        pc1.plot = 5
        db.commit()

        auth_as(client, seed_data["player1"])
        submit_resp = _submit(
            client, pc1.id, "use_skill",
            {"skill": "awareness", "plot_spend": 2},
        )
        assert submit_resp.status_code == 201

        auth_as(client, seed_data["gm"])
        _approve(client, submit_resp.json()["id"])

        db.expire_all()
        db.refresh(pc1)
        assert pc1.plot == 3  # 5 - 2


# ===========================================================================
# use_magic lifecycle
# ===========================================================================


class TestUseMagicLifecycle:
    """Full lifecycle for use_magic proposals."""

    def test_submit_pending_approve_approved(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        pc1.gnosis = 10
        db.commit()

        auth_as(client, seed_data["player1"])
        submit_resp = _submit(
            client, pc1.id, "use_magic",
            {
                "suggested_stat": "being",
                "sacrifice": [{"type": "gnosis", "amount": 3}],
            },
        )
        assert submit_resp.status_code == 201
        assert submit_resp.json()["status"] == "pending"

        auth_as(client, seed_data["gm"])
        approve_resp = _approve(client, submit_resp.json()["id"])
        assert approve_resp.status_code == 200
        assert approve_resp.json()["status"] == "approved"
        assert approve_resp.json()["event_id"] is not None

    def test_gnosis_deducted_on_approval(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        pc1.gnosis = 10
        db.commit()

        auth_as(client, seed_data["player1"])
        submit_resp = _submit(
            client, pc1.id, "use_magic",
            {
                "suggested_stat": "being",
                "sacrifice": [{"type": "gnosis", "amount": 3}],
            },
        )
        assert submit_resp.status_code == 201
        proposal_id = submit_resp.json()["id"]

        auth_as(client, seed_data["gm"])
        _approve(client, proposal_id)

        db.expire_all()
        db.refresh(pc1)
        assert pc1.gnosis == 7  # 10 - 3


# ===========================================================================
# charge_magic lifecycle
# ===========================================================================


class TestChargeMagicLifecycle:
    """Full lifecycle for charge_magic proposals."""

    def test_submit_pending_approve_approved(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        eff = _magic_effect(db, pc1.id, charges_current=2, charges_max=5)
        db.commit()

        auth_as(client, seed_data["player1"])
        submit_resp = _submit(
            client, pc1.id, "charge_magic",
            {"effect_id": eff.id, "suggested_stat": "enchanting"},
        )
        assert submit_resp.status_code == 201
        assert submit_resp.json()["status"] == "pending"

        auth_as(client, seed_data["gm"])
        approve_resp = _approve(
            client, submit_resp.json()["id"],
            body={"gm_overrides": {"charges_added": 2}},
        )
        assert approve_resp.status_code == 200
        assert approve_resp.json()["status"] == "approved"
        assert approve_resp.json()["event_id"] is not None

    def test_charges_added_on_approval(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        eff = _magic_effect(db, pc1.id, charges_current=2, charges_max=5)
        db.commit()

        auth_as(client, seed_data["player1"])
        submit_resp = _submit(
            client, pc1.id, "charge_magic",
            {"effect_id": eff.id, "suggested_stat": "enchanting"},
        )
        assert submit_resp.status_code == 201

        auth_as(client, seed_data["gm"])
        _approve(client, submit_resp.json()["id"], body={"gm_overrides": {"charges_added": 3}})

        db.expire_all()
        db.refresh(eff)
        assert eff.charges_current == 5  # 2 + 3


# ===========================================================================
# regain_gnosis lifecycle
# ===========================================================================


class TestRegainGnosisLifecycle:
    """Full lifecycle for regain_gnosis proposals."""

    def test_submit_pending_approve_approved_gnosis_increased_ft_decreased(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        pc1.gnosis = 5
        pc1.free_time = 1
        db.commit()

        auth_as(client, seed_data["player1"])
        submit_resp = _submit(client, pc1.id, "regain_gnosis", {})
        assert submit_resp.status_code == 201
        assert submit_resp.json()["status"] == "pending"

        auth_as(client, seed_data["gm"])
        approve_resp = _approve(client, submit_resp.json()["id"])
        assert approve_resp.status_code == 200
        assert approve_resp.json()["status"] == "approved"
        assert approve_resp.json()["event_id"] is not None

        db.expire_all()
        db.refresh(pc1)
        assert pc1.gnosis == 8   # 5 + 3 base
        assert pc1.free_time == 0  # 1 - 1


# ===========================================================================
# work_on_project lifecycle
# ===========================================================================


class TestWorkOnProjectLifecycle:
    """Full lifecycle for work_on_project proposals."""

    def test_submit_pending_approve_story_entry_created_ft_decreased(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        from wizards_engine.models.story import StoryEntry

        pc1 = seed_data["pc1"]
        pc1.free_time = 1
        db.flush()
        story = _story(db)
        db.commit()

        auth_as(client, seed_data["player1"])
        submit_resp = _submit(
            client, pc1.id, "work_on_project",
            {"story_id": story.id, "entry_text": "We found the hidden vault."},
        )
        assert submit_resp.status_code == 201
        assert submit_resp.json()["status"] == "pending"

        auth_as(client, seed_data["gm"])
        approve_resp = _approve(client, submit_resp.json()["id"])
        assert approve_resp.status_code == 200
        assert approve_resp.json()["status"] == "approved"

        db.expire_all()
        db.refresh(pc1)
        assert pc1.free_time == 0

        entry = db.query(StoryEntry).filter(StoryEntry.story_id == story.id).first()
        assert entry is not None
        assert entry.text == "We found the hidden vault."


# ===========================================================================
# rest lifecycle
# ===========================================================================


class TestRestLifecycle:
    """Full lifecycle for rest proposals."""

    def test_submit_pending_approve_stress_decreased_ft_decreased(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        pc1.stress = 6
        pc1.free_time = 1
        db.commit()

        auth_as(client, seed_data["player1"])
        submit_resp = _submit(client, pc1.id, "rest", {})
        assert submit_resp.status_code == 201
        assert submit_resp.json()["status"] == "pending"

        auth_as(client, seed_data["gm"])
        approve_resp = _approve(client, submit_resp.json()["id"])
        assert approve_resp.status_code == 200
        assert approve_resp.json()["status"] == "approved"
        assert approve_resp.json()["event_id"] is not None

        db.expire_all()
        db.refresh(pc1)
        assert pc1.stress == 3   # 6 - 3 base healed
        assert pc1.free_time == 0


# ===========================================================================
# new_trait lifecycle
# ===========================================================================


class TestNewTraitLifecycle:
    """Full lifecycle for new_trait proposals."""

    def test_submit_pending_approve_trait_created_ft_decreased(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        pc1.free_time = 1
        db.flush()
        tmpl = _core_template(db, "Tenacious")
        db.commit()

        auth_as(client, seed_data["player1"])
        submit_resp = _submit(
            client, pc1.id, "new_trait",
            {"slot_type": "core_trait", "template_id": tmpl.id},
        )
        assert submit_resp.status_code == 201
        assert submit_resp.json()["status"] == "pending"

        auth_as(client, seed_data["gm"])
        approve_resp = _approve(client, submit_resp.json()["id"])
        assert approve_resp.status_code == 200
        assert approve_resp.json()["status"] == "approved"
        assert approve_resp.json()["event_id"] is not None

        db.expire_all()
        db.refresh(pc1)
        assert pc1.free_time == 0

        from sqlalchemy import and_, select
        new_slot = db.execute(
            select(Slot).where(
                and_(
                    Slot.owner_id == pc1.id,
                    Slot.template_id == tmpl.id,
                    Slot.is_active.is_(True),
                )
            )
        ).scalars().first()
        assert new_slot is not None
        assert new_slot.slot_type == "core_trait"


# ===========================================================================
# new_bond lifecycle
# ===========================================================================


class TestNewBondLifecycle:
    """Full lifecycle for new_bond proposals."""

    def test_submit_pending_approve_bond_created_ft_decreased(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc3 = seed_data["pc3"]
        pc3.free_time = 1
        db.commit()

        region = seed_data["region"]

        auth_as(client, seed_data["player3"])
        submit_resp = _submit(
            client, pc3.id, "new_bond",
            {"target_type": "location", "target_id": region.id},
        )
        assert submit_resp.status_code == 201
        assert submit_resp.json()["status"] == "pending"

        auth_as(client, seed_data["gm"])
        approve_resp = _approve(client, submit_resp.json()["id"])
        assert approve_resp.status_code == 200
        assert approve_resp.json()["status"] == "approved"
        assert approve_resp.json()["event_id"] is not None

        db.expire_all()
        db.refresh(pc3)
        assert pc3.free_time == 0

        from sqlalchemy import and_, select
        new_bond = db.execute(
            select(Slot).where(
                and_(
                    Slot.owner_id == pc3.id,
                    Slot.target_type == "location",
                    Slot.target_id == region.id,
                    Slot.is_active.is_(True),
                )
            )
        ).scalars().first()
        assert new_bond is not None
        assert new_bond.slot_type == "pc_bond"


# ===========================================================================
# System proposal: resolve_clock (auto-generated)
# ===========================================================================


class TestResolveClockAutoGenerated:
    """resolve_clock proposals are auto-generated when a clock completes."""

    def test_resolve_clock_generated_on_clock_completion(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Advancing a clock to its segments count auto-generates a resolve_clock proposal."""
        clock = Clock(name="Test Clock", segments=3, progress=2)
        db.add(clock)
        db.commit()
        db.refresh(clock)

        auth_as(client, seed_data["gm"])
        resp = client.post(
            "/api/v1/gm/actions",
            json={
                "action_type": "modify_clock",
                "target_id": clock.id,
                "changes": {"progress": {"op": "delta", "value": 1}},
                "visibility": "public",
            },
        )
        assert resp.status_code == 200

        db.expire_all()
        proposal = (
            db.query(Proposal)
            .filter(
                Proposal.clock_id == clock.id,
                Proposal.action_type == "resolve_clock",
            )
            .first()
        )
        assert proposal is not None
        assert proposal.status == "pending"
        assert proposal.origin == "system"

    def test_resolve_clock_approved_returns_approved_status(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """After auto-generation, a resolve_clock proposal can be approved."""
        clock = Clock(name="Finale Clock", segments=1, progress=0)
        db.add(clock)
        db.commit()
        db.refresh(clock)

        auth_as(client, seed_data["gm"])
        client.post(
            "/api/v1/gm/actions",
            json={
                "action_type": "modify_clock",
                "target_id": clock.id,
                "changes": {"progress": {"op": "delta", "value": 1}},
                "visibility": "public",
            },
        )

        db.expire_all()
        proposal = (
            db.query(Proposal)
            .filter(Proposal.clock_id == clock.id, Proposal.action_type == "resolve_clock")
            .first()
        )
        assert proposal is not None

        approve_resp = _approve(client, proposal.id)
        assert approve_resp.status_code == 200
        assert approve_resp.json()["status"] == "approved"
        assert approve_resp.json()["event_id"] is not None


# ===========================================================================
# System proposal: resolve_trauma (auto-generated)
# ===========================================================================


class TestResolveTraumaAutoGenerated:
    """resolve_trauma proposals are auto-generated when Stress hits effective max."""

    def test_resolve_trauma_generated_when_stress_hits_max_via_magic_sacrifice(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """When stress sacrifice in a magic proposal pushes stress to 9 (max),
        a resolve_trauma proposal is auto-generated."""
        pc1 = seed_data["pc1"]
        # Set stress to 8 (effective_max = 9 with no traumas), so 1 stress sacrifice hits max.
        pc1.stress = 8
        pc1.gnosis = 0
        pc1.free_time = 0
        db.commit()

        # Create a pending proposal with a stress sacrifice of 1 directly in DB.
        p = Proposal(
            character_id=pc1.id,
            action_type="use_magic",
            origin="player",
            narrative="I push myself to the limit.",
            selections={},
            calculated_effect={
                "suggested_stat": "being",
                "stat_level": 0,
                "dice_pool": 1,
                "sacrifice_dice": 1,
                "total_gnosis_equivalent": 2,
                "sacrifice_details": [{"type": "stress", "amount": 1}],
                "modifiers": [],
                "costs": {
                    "gnosis": 0,
                    "stress": 1,
                    "free_time": 0,
                    "bond_sacrifices": [],
                    "trait_sacrifices": [],
                    "trait_charges": [],
                    "plot": 0,
                },
            },
            status="pending",
        )
        db.add(p)
        db.commit()

        auth_as(client, seed_data["gm"])
        approve_resp = _approve(client, p.id)
        assert approve_resp.status_code == 200

        db.expire_all()
        db.refresh(pc1)
        assert pc1.stress == 9  # clamped at effective_max

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
        assert trauma_proposal.origin == "system"
