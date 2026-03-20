"""Tests for M8 — uncovered _apply_* handlers in proposal approval.

Covers:
- _apply_regain_gnosis: approve regain_gnosis, verify gnosis increased and FT decreased
- _apply_work_on_project: approve work_on_project, verify story entry created and FT decreased
- _apply_rest: approve rest, verify stress decreased and FT decreased
- _apply_new_trait: approve new_trait, verify new trait slot created and FT decreased
- _apply_new_bond: approve new_bond, verify new bond slot created and FT decreased

Each test creates a proposal via the DB (bypassing calculator to set exact effect),
then approves via API, then verifies character state changed.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import auth_as
from wizards_engine.models.proposal import Proposal
from wizards_engine.models.slot import Slot, TraitTemplate
from wizards_engine.models.story import Story, StoryEntry


# ===========================================================================
# Helpers
# ===========================================================================


def _pending_proposal(
    db: Session,
    *,
    character_id: str,
    action_type: str,
    calculated_effect: dict,
    narrative: str = "A downtime action.",
) -> Proposal:
    """Create and flush a pending Proposal with the given calculated_effect."""
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


def _core_template(db: Session, name: str = "Courageous") -> TraitTemplate:
    t = TraitTemplate(name=name, description=f"Desc: {name}", type="core", is_deleted=False)
    db.add(t)
    db.flush()
    db.refresh(t)
    return t


def _story(db: Session, name: str = "Test Project") -> Story:
    s = Story(name=name, status="active", is_deleted=False)
    db.add(s)
    db.flush()
    db.refresh(s)
    return s


# ===========================================================================
# _apply_regain_gnosis
# ===========================================================================


class TestApplyRegainGnosis:
    """Approval of regain_gnosis increases gnosis and deducts FT."""

    def test_gnosis_increased_ft_decreased(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """After approval, gnosis is incremented by gnosis_gained and FT drops by 1."""
        pc1 = seed_data["pc1"]
        pc1.gnosis = 5
        pc1.free_time = 2
        db.flush()

        effect = {
            "gnosis_gained": 4,
            "costs": {
                "free_time": 1,
                "trait_charges": [],
            },
        }
        p = _pending_proposal(db, character_id=pc1.id, action_type="regain_gnosis", calculated_effect=effect)
        db.commit()

        auth_as(client, seed_data["gm"])
        resp = _approve(client, p.id)
        assert resp.status_code == 200

        db.expire_all()
        db.refresh(pc1)
        assert pc1.gnosis == 9  # 5 + 4
        assert pc1.free_time == 1  # 2 - 1

    def test_gnosis_capped_at_max(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Gnosis is capped at 23 (GNOSIS_MAX) even if gnosis_gained would exceed it."""
        pc1 = seed_data["pc1"]
        pc1.gnosis = 22
        pc1.free_time = 1
        db.flush()

        effect = {
            "gnosis_gained": 3,
            "costs": {
                "free_time": 1,
                "trait_charges": [],
            },
        }
        p = _pending_proposal(db, character_id=pc1.id, action_type="regain_gnosis", calculated_effect=effect)
        db.commit()

        auth_as(client, seed_data["gm"])
        resp = _approve(client, p.id)
        assert resp.status_code == 200

        db.expire_all()
        db.refresh(pc1)
        assert pc1.gnosis == 23  # capped, not 25

    def test_approval_status_is_approved(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """After approval the proposal status is 'approved'."""
        pc1 = seed_data["pc1"]
        pc1.gnosis = 0
        pc1.free_time = 1
        db.flush()

        effect = {
            "gnosis_gained": 3,
            "costs": {"free_time": 1, "trait_charges": []},
        }
        p = _pending_proposal(db, character_id=pc1.id, action_type="regain_gnosis", calculated_effect=effect)
        db.commit()

        auth_as(client, seed_data["gm"])
        resp = _approve(client, p.id)
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"
        assert resp.json()["event_id"] is not None


# ===========================================================================
# _apply_work_on_project
# ===========================================================================


class TestApplyWorkOnProject:
    """Approval of work_on_project creates a story entry and deducts FT."""

    def test_story_entry_created_ft_decreased(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Approval creates a StoryEntry and deducts 1 FT."""
        pc1 = seed_data["pc1"]
        pc1.free_time = 1
        db.flush()
        story = _story(db)
        db.commit()

        effect = {
            "story_id": story.id,
            "entry_text": "Investigated the harbour records.",
            "costs": {"free_time": 1},
        }
        p = _pending_proposal(db, character_id=pc1.id, action_type="work_on_project", calculated_effect=effect)
        db.commit()

        auth_as(client, seed_data["gm"])
        resp = _approve(client, p.id)
        assert resp.status_code == 200

        db.expire_all()
        db.refresh(pc1)
        assert pc1.free_time == 0

        entry = db.query(StoryEntry).filter(StoryEntry.story_id == story.id).first()
        assert entry is not None
        assert entry.text == "Investigated the harbour records."
        assert entry.character_id == pc1.id

    def test_no_entry_when_no_story_id(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """When the effect has no story_id, no StoryEntry is created, but FT is still deducted."""
        pc1 = seed_data["pc1"]
        pc1.free_time = 1
        db.flush()

        effect = {
            "costs": {"free_time": 1},
        }
        p = _pending_proposal(db, character_id=pc1.id, action_type="work_on_project", calculated_effect=effect)
        db.commit()

        auth_as(client, seed_data["gm"])
        resp = _approve(client, p.id)
        assert resp.status_code == 200

        db.expire_all()
        db.refresh(pc1)
        assert pc1.free_time == 0

    def test_event_created_on_approval(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Approval returns event_id indicating an event was created."""
        from wizards_engine.models.event import Event

        pc1 = seed_data["pc1"]
        pc1.free_time = 1
        db.flush()
        story = _story(db)
        db.commit()

        effect = {
            "story_id": story.id,
            "entry_text": "Made progress.",
            "costs": {"free_time": 1},
        }
        p = _pending_proposal(db, character_id=pc1.id, action_type="work_on_project", calculated_effect=effect)
        db.commit()

        auth_as(client, seed_data["gm"])
        resp = _approve(client, p.id)
        assert resp.status_code == 200

        event_id = resp.json()["event_id"]
        assert event_id is not None

        db.expire_all()
        ev = db.get(Event, event_id)
        assert ev is not None
        assert ev.proposal_id == p.id


# ===========================================================================
# _apply_rest
# ===========================================================================


class TestApplyRest:
    """Approval of rest reduces stress and deducts FT."""

    def test_stress_decreased_ft_decreased(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Approval reduces stress by stress_healed and deducts 1 FT."""
        pc1 = seed_data["pc1"]
        pc1.stress = 6
        pc1.free_time = 2
        db.flush()

        effect = {
            "stress_healed": 3,
            "costs": {"free_time": 1, "trait_charges": []},
        }
        p = _pending_proposal(db, character_id=pc1.id, action_type="rest", calculated_effect=effect)
        db.commit()

        auth_as(client, seed_data["gm"])
        resp = _approve(client, p.id)
        assert resp.status_code == 200

        db.expire_all()
        db.refresh(pc1)
        assert pc1.stress == 3   # 6 - 3
        assert pc1.free_time == 1  # 2 - 1

    def test_stress_clamped_at_zero(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Stress cannot go below 0."""
        pc1 = seed_data["pc1"]
        pc1.stress = 2
        pc1.free_time = 1
        db.flush()

        effect = {
            "stress_healed": 5,
            "costs": {"free_time": 1, "trait_charges": []},
        }
        p = _pending_proposal(db, character_id=pc1.id, action_type="rest", calculated_effect=effect)
        db.commit()

        auth_as(client, seed_data["gm"])
        resp = _approve(client, p.id)
        assert resp.status_code == 200

        db.expire_all()
        db.refresh(pc1)
        assert pc1.stress == 0  # clamped, not -3

    def test_trait_charges_deducted_on_approval(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Trait modifier charges are deducted on approval."""
        pc1 = seed_data["pc1"]
        pc1.stress = 5
        pc1.free_time = 1
        db.flush()

        trait = Slot(
            slot_type="core_trait",
            owner_type="character",
            owner_id=pc1.id,
            name="Grounded",
            charge=4,
            is_active=True,
        )
        db.add(trait)
        db.flush()
        db.refresh(trait)

        effect = {
            "stress_healed": 4,
            "costs": {
                "free_time": 1,
                "trait_charges": [{"trait_id": trait.id, "cost": 1}],
            },
        }
        p = _pending_proposal(db, character_id=pc1.id, action_type="rest", calculated_effect=effect)
        db.commit()

        auth_as(client, seed_data["gm"])
        resp = _approve(client, p.id)
        assert resp.status_code == 200

        db.expire_all()
        db.refresh(trait)
        assert trait.charge == 3  # 4 - 1

    def test_approval_status_is_approved(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        pc1.stress = 3
        pc1.free_time = 1
        db.flush()

        effect = {
            "stress_healed": 3,
            "costs": {"free_time": 1, "trait_charges": []},
        }
        p = _pending_proposal(db, character_id=pc1.id, action_type="rest", calculated_effect=effect)
        db.commit()

        auth_as(client, seed_data["gm"])
        resp = _approve(client, p.id)
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"


# ===========================================================================
# _apply_new_trait
# ===========================================================================


class TestApplyNewTrait:
    """Approval of new_trait creates a trait slot and deducts FT."""

    def test_new_trait_created_ft_decreased(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Approval creates a new active core_trait slot and deducts 1 FT."""
        pc1 = seed_data["pc1"]
        pc1.free_time = 1
        db.flush()

        tmpl = _core_template(db, "Steadfast")
        db.commit()

        effect = {
            "slot_type": "core_trait",
            "template_id": tmpl.id,
            "proposed_name": None,
            "proposed_description": None,
            "retire_trait_id": None,
            "costs": {"free_time": 1},
        }
        p = _pending_proposal(db, character_id=pc1.id, action_type="new_trait", calculated_effect=effect)
        db.commit()

        auth_as(client, seed_data["gm"])
        resp = _approve(client, p.id)
        assert resp.status_code == 200

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
        assert new_slot.charge == 5

    def test_retire_trait_id_set_inactive_on_approval(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """When retire_trait_id is provided, the old trait is deactivated."""
        pc1 = seed_data["pc1"]
        pc1.free_time = 1
        db.flush()

        old_trait = Slot(
            slot_type="core_trait",
            owner_type="character",
            owner_id=pc1.id,
            name="Old Trait",
            charge=2,
            is_active=True,
        )
        db.add(old_trait)
        db.flush()

        tmpl = _core_template(db, "New Virtue")
        db.commit()

        effect = {
            "slot_type": "core_trait",
            "template_id": tmpl.id,
            "proposed_name": None,
            "proposed_description": None,
            "retire_trait_id": old_trait.id,
            "costs": {"free_time": 1},
        }
        p = _pending_proposal(db, character_id=pc1.id, action_type="new_trait", calculated_effect=effect)
        db.commit()

        auth_as(client, seed_data["gm"])
        resp = _approve(client, p.id)
        assert resp.status_code == 200

        db.expire_all()
        db.refresh(old_trait)
        assert old_trait.is_active is False

    def test_proposed_name_creates_template_and_trait(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """When proposed_name is provided (no template_id), a template is created then the trait."""
        pc1 = seed_data["pc1"]
        pc1.free_time = 1
        db.flush()
        db.commit()

        effect = {
            "slot_type": "core_trait",
            "template_id": None,
            "proposed_name": "Ironwilled",
            "proposed_description": "Never backs down.",
            "retire_trait_id": None,
            "costs": {"free_time": 1},
        }
        p = _pending_proposal(db, character_id=pc1.id, action_type="new_trait", calculated_effect=effect)
        db.commit()

        auth_as(client, seed_data["gm"])
        resp = _approve(client, p.id)
        assert resp.status_code == 200

        db.expire_all()
        created_tmpl = db.query(TraitTemplate).filter(TraitTemplate.name == "Ironwilled").first()
        assert created_tmpl is not None
        assert created_tmpl.type == "core"

        from sqlalchemy import and_, select
        new_slot = db.execute(
            select(Slot).where(
                and_(
                    Slot.owner_id == pc1.id,
                    Slot.template_id == created_tmpl.id,
                    Slot.is_active.is_(True),
                )
            )
        ).scalars().first()
        assert new_slot is not None

    def test_approval_returns_approved_status(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        pc1.free_time = 1
        db.flush()
        tmpl = _core_template(db, "Vigilant")
        db.commit()

        effect = {
            "slot_type": "core_trait",
            "template_id": tmpl.id,
            "proposed_name": None,
            "proposed_description": None,
            "retire_trait_id": None,
            "costs": {"free_time": 1},
        }
        p = _pending_proposal(db, character_id=pc1.id, action_type="new_trait", calculated_effect=effect)
        db.commit()

        auth_as(client, seed_data["gm"])
        resp = _approve(client, p.id)
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"


# ===========================================================================
# _apply_new_bond
# ===========================================================================


class TestApplyNewBond:
    """Approval of new_bond creates a bond slot and deducts FT."""

    def test_new_bond_created_ft_decreased(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Approval creates a new active pc_bond slot to the given target and deducts 1 FT."""
        pc3 = seed_data["pc3"]
        pc3.free_time = 2
        db.flush()
        group = seed_data["group"]
        db.commit()

        effect = {
            "target_type": "group",
            "target_id": group.id,
            "retire_bond_id": None,
            "costs": {"free_time": 1},
        }
        p = _pending_proposal(db, character_id=pc3.id, action_type="new_bond", calculated_effect=effect)
        db.commit()

        auth_as(client, seed_data["gm"])
        resp = _approve(client, p.id)
        assert resp.status_code == 200

        db.expire_all()
        db.refresh(pc3)
        assert pc3.free_time == 1  # 2 - 1

        from sqlalchemy import and_, select
        new_bond = db.execute(
            select(Slot).where(
                and_(
                    Slot.owner_id == pc3.id,
                    Slot.target_type == "group",
                    Slot.target_id == group.id,
                    Slot.is_active.is_(True),
                )
            )
        ).scalars().first()
        assert new_bond is not None
        assert new_bond.slot_type == "pc_bond"

    def test_retire_old_bond_on_new_bond_approval(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """When retire_bond_id is set, the old bond is deactivated."""
        pc1 = seed_data["pc1"]
        pc1.free_time = 1
        db.flush()

        old_bond = Slot(
            slot_type="pc_bond",
            owner_type="character",
            owner_id=pc1.id,
            target_type="character",
            target_id=seed_data["pc2"].id,
            name="Old Bond",
            charges=3,
            degradations=0,
            is_trauma=False,
            is_active=True,
        )
        db.add(old_bond)
        db.flush()
        db.refresh(old_bond)

        region = seed_data["region"]
        db.commit()

        effect = {
            "target_type": "location",
            "target_id": region.id,
            "retire_bond_id": old_bond.id,
            "costs": {"free_time": 1},
        }
        p = _pending_proposal(db, character_id=pc1.id, action_type="new_bond", calculated_effect=effect)
        db.commit()

        auth_as(client, seed_data["gm"])
        resp = _approve(client, p.id)
        assert resp.status_code == 200

        db.expire_all()
        db.refresh(old_bond)
        assert old_bond.is_active is False

    def test_approval_returns_approved_status_and_event_id(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc3 = seed_data["pc3"]
        pc3.free_time = 1
        db.flush()
        region = seed_data["region"]
        db.commit()

        effect = {
            "target_type": "location",
            "target_id": region.id,
            "retire_bond_id": None,
            "costs": {"free_time": 1},
        }
        p = _pending_proposal(db, character_id=pc3.id, action_type="new_bond", calculated_effect=effect)
        db.commit()

        auth_as(client, seed_data["gm"])
        resp = _approve(client, p.id)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "approved"
        assert body["event_id"] is not None

    def test_ft_deducted_even_when_no_target(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """FT is still deducted even if target_type/target_id are absent in the effect."""
        pc1 = seed_data["pc1"]
        pc1.free_time = 3
        db.flush()
        db.commit()

        effect = {
            "costs": {"free_time": 1},
        }
        p = _pending_proposal(db, character_id=pc1.id, action_type="new_bond", calculated_effect=effect)
        db.commit()

        auth_as(client, seed_data["gm"])
        resp = _approve(client, p.id)
        assert resp.status_code == 200

        db.expire_all()
        db.refresh(pc1)
        assert pc1.free_time == 2  # 3 - 1
