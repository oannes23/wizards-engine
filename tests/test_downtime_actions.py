"""Integration tests for Story 4.3.4 — Downtime Action Types.

Covers submission (calculated_effect shape), validation errors, and approval
resource effects for all 7 downtime action types:

  - regain_gnosis
  - recharge_trait
  - maintain_bond
  - work_on_project
  - rest
  - new_trait
  - new_bond

All tests use the function-scoped ``client`` + ``seed_data`` + ``db`` fixtures.
Tests that need traits, bonds, or stories beyond seed data create them in-line.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import auth_as
from wizards_engine.models.character import Character
from wizards_engine.models.proposal import Proposal
from wizards_engine.models.slot import Slot, TraitTemplate
from wizards_engine.models.story import Story


# ===========================================================================
# Fixture helpers
# ===========================================================================


def _set_ft(db: Session, character: Character, ft: int) -> None:
    """Set free_time on a character and flush."""
    character.free_time = ft
    db.flush()


def _set_gnosis(db: Session, character: Character, gnosis: int) -> None:
    """Set gnosis on a character and flush."""
    character.gnosis = gnosis
    db.flush()


def _set_stress(db: Session, character: Character, stress: int) -> None:
    """Set stress on a character and flush."""
    character.stress = stress
    db.flush()


def _set_magic_stat(db: Session, character: Character, stat: str, level: int) -> None:
    """Set a single magic stat level on a character and flush."""
    stats = {k: dict(v) for k, v in (character.magic_stats or {}).items()}
    if stat not in stats:
        stats[stat] = {"level": 0, "xp": 0}
    stats[stat]["level"] = level
    character.magic_stats = stats
    db.flush()


def _core_template(db: Session, name: str = "Courageous") -> TraitTemplate:
    """Create and flush a core TraitTemplate."""
    t = TraitTemplate(name=name, description=f"Desc: {name}", type="core", is_deleted=False)
    db.add(t)
    db.flush()
    db.refresh(t)
    return t


def _role_template(db: Session, name: str = "Scout") -> TraitTemplate:
    """Create and flush a role TraitTemplate."""
    t = TraitTemplate(name=name, description=f"Desc: {name}", type="role", is_deleted=False)
    db.add(t)
    db.flush()
    db.refresh(t)
    return t


def _core_trait(
    db: Session,
    character_id: str,
    name: str = "Courageous",
    charge: int = 5,
    is_active: bool = True,
    template: TraitTemplate | None = None,
) -> Slot:
    """Create and flush a core_trait slot on a character."""
    if template is None:
        template = _core_template(db, name)
    slot = Slot(
        slot_type="core_trait",
        owner_type="character",
        owner_id=character_id,
        name=name,
        template_id=template.id,
        charge=charge,
        is_active=is_active,
    )
    db.add(slot)
    db.flush()
    db.refresh(slot)
    return slot


def _role_trait(
    db: Session,
    character_id: str,
    name: str = "Scout",
    charge: int = 5,
    is_active: bool = True,
    template: TraitTemplate | None = None,
) -> Slot:
    """Create and flush a role_trait slot on a character."""
    if template is None:
        template = _role_template(db, name)
    slot = Slot(
        slot_type="role_trait",
        owner_type="character",
        owner_id=character_id,
        name=name,
        template_id=template.id,
        charge=charge,
        is_active=is_active,
    )
    db.add(slot)
    db.flush()
    db.refresh(slot)
    return slot


def _pc_bond_slot(
    db: Session,
    character_id: str,
    target_type: str = "character",
    target_id: str | None = None,
    name: str = "Test Bond",
    stress: int = 3,
    is_active: bool = True,
) -> Slot:
    """Create and flush a pc_bond slot on a character."""
    slot = Slot(
        slot_type="pc_bond",
        owner_type="character",
        owner_id=character_id,
        target_type=target_type,
        target_id=target_id or character_id,
        name=name,
        stress=stress,
        stress_degradations=0,
        is_trauma=False,
        is_active=is_active,
    )
    db.add(slot)
    db.flush()
    db.refresh(slot)
    return slot


def _story(db: Session, name: str = "Test Project") -> Story:
    """Create and flush a Story."""
    s = Story(name=name, status="active", is_deleted=False)
    db.add(s)
    db.flush()
    db.refresh(s)
    return s


def _pending_proposal(
    db: Session,
    *,
    character_id: str,
    action_type: str,
    selections: dict | None = None,
    calculated_effect: dict | None = None,
    narrative: str = "A downtime action.",
) -> Proposal:
    """Create and flush a minimal pending Proposal with a given calculated_effect."""
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


def _post_proposal(
    client: TestClient,
    character_id: str,
    action_type: str,
    selections: dict,
    narrative: str = "A downtime action.",
):
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
    """POST approve on a proposal and return the response."""
    return client.post(
        f"/api/v1/proposals/{proposal_id}/approve",
        json=body or {},
    )


# ===========================================================================
# regain_gnosis
# ===========================================================================


class TestRegainGnosisSubmission:
    """Submission validation and calculated_effect for regain_gnosis."""

    def test_no_modifiers_basic_effect(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Base gnosis gained = 3 + lowest magic stat level (0) = 3."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(client, pc1.id, "regain_gnosis", {})

        assert resp.status_code == 201
        ce = resp.json()["calculated_effect"]
        assert ce["gnosis_gained"] == 3
        assert ce["costs"]["free_time"] == 1
        assert ce["costs"]["trait_charges"] == []

    def test_magic_stat_adds_to_base(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """gnosis_gained = 3 + lowest_magic_stat_level."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        # Set all magic stats to 2 — lowest is 2.
        for stat in ("being", "wyrding", "summoning", "enchanting", "dreaming"):
            _set_magic_stat(db, pc1, stat, 2)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(client, pc1.id, "regain_gnosis", {})

        assert resp.status_code == 201
        assert resp.json()["calculated_effect"]["gnosis_gained"] == 5  # 3 + 2

    def test_lowest_magic_stat_used(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Lowest stat is used even if others are higher."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        for stat in ("being", "wyrding", "summoning", "enchanting", "dreaming"):
            _set_magic_stat(db, pc1, stat, 3)
        _set_magic_stat(db, pc1, "dreaming", 1)  # dreaming is lowest
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(client, pc1.id, "regain_gnosis", {})

        assert resp.status_code == 201
        assert resp.json()["calculated_effect"]["gnosis_gained"] == 4  # 3 + 1

    def test_core_trait_modifier_adds_one(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """A core_trait modifier adds 1 to gnosis_gained and costs 1 charge."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        trait = _core_trait(db, pc1.id)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "regain_gnosis",
            {"modifiers": {"core_trait_id": trait.id}},
        )

        assert resp.status_code == 201
        ce = resp.json()["calculated_effect"]
        assert ce["gnosis_gained"] == 4  # 3 + 0 + 1
        assert len(ce["costs"]["trait_charges"]) == 1
        assert ce["costs"]["trait_charges"][0]["trait_id"] == trait.id

    def test_all_three_modifiers(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """All three modifiers add 3 to gnosis_gained."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        core = _core_trait(db, pc1.id, "Courageous")
        role = _role_trait(db, pc1.id, "Scout")
        bond = _pc_bond_slot(db, pc1.id, target_type="character", target_id=seed_data["pc2"].id)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "regain_gnosis",
            {"modifiers": {"core_trait_id": core.id, "role_trait_id": role.id, "bond_id": bond.id}},
        )

        assert resp.status_code == 201
        ce = resp.json()["calculated_effect"]
        assert ce["gnosis_gained"] == 6  # 3 + 0 + 3

    def test_missing_ft_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """FT=0 should return 422."""
        pc1 = seed_data["pc1"]
        # pc1.free_time is 0 by default in seed data
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(client, pc1.id, "regain_gnosis", {})

        assert resp.status_code == 422
        assert "free_time" in resp.json()["error"]["details"]["fields"]


class TestRegainGnosisApproval:
    """Approval effects for regain_gnosis."""

    def test_gnosis_increased_on_approval(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Approval adds gnosis_gained to the character's gnosis."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        _set_gnosis(db, pc1, 5)
        db.commit()

        auth_as(client, seed_data["player1"])
        submit_resp = _post_proposal(client, pc1.id, "regain_gnosis", {})
        assert submit_resp.status_code == 201
        proposal_id = submit_resp.json()["id"]

        auth_as(client, seed_data["gm"])
        approve_resp = _approve(client, proposal_id)
        assert approve_resp.status_code == 200

        db.expire_all()
        assert pc1.gnosis == 8  # 5 + 3
        assert pc1.free_time == 0  # 1 - 1

    def test_gnosis_capped_at_23(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Gnosis cannot exceed 23 on approval."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        _set_gnosis(db, pc1, 22)
        db.commit()

        auth_as(client, seed_data["player1"])
        submit_resp = _post_proposal(client, pc1.id, "regain_gnosis", {})
        assert submit_resp.status_code == 201
        proposal_id = submit_resp.json()["id"]

        auth_as(client, seed_data["gm"])
        _approve(client, proposal_id)

        db.expire_all()
        assert pc1.gnosis == 23  # capped, not 25

    def test_trait_charges_deducted_on_approval(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Modifier trait charges are deducted on approval."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        trait = _core_trait(db, pc1.id, charge=5)
        db.commit()

        auth_as(client, seed_data["player1"])
        submit_resp = _post_proposal(
            client, pc1.id, "regain_gnosis",
            {"modifiers": {"core_trait_id": trait.id}},
        )
        assert submit_resp.status_code == 201
        proposal_id = submit_resp.json()["id"]

        auth_as(client, seed_data["gm"])
        _approve(client, proposal_id)

        db.expire_all()
        db.refresh(trait)
        assert trait.charge == 4


# ===========================================================================
# recharge_trait — now a direct action (Story 5.5.1)
# ===========================================================================
# recharge_trait was converted from a proposal-based downtime action to a
# direct action in Story 5.5.1.  Submitting it as a proposal is now rejected
# with 422.  See tests/test_recharge_trait.py for the direct-action tests.


class TestRechargeTraitProposalRejected:
    """recharge_trait is no longer a valid proposal action_type (direct action only)."""

    def test_proposal_submission_rejected_with_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Submitting recharge_trait as a proposal returns 422 (invalid action type)."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        trait = _core_trait(db, pc1.id, charge=2)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(client, pc1.id, "recharge_trait", {"trait_id": trait.id})

        assert resp.status_code == 422


# ===========================================================================
# maintain_bond — now a direct action (Story 5.5.2)
# ===========================================================================
# maintain_bond was converted from a proposal-based downtime action to a
# direct action in Story 5.5.2.  Submitting it as a proposal is now rejected
# with 422.  See tests/test_maintain_bond.py for the direct-action tests.


class TestMaintainBondProposalRejected:
    """maintain_bond is no longer a valid proposal action_type (direct action only)."""

    def test_proposal_submission_rejected_with_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Submitting maintain_bond as a proposal returns 422 (invalid action type)."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        bond = seed_data["pc1_bond"]
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(client, pc1.id, "maintain_bond", {"bond_id": bond.id})

        assert resp.status_code == 422


# ===========================================================================
# work_on_project
# ===========================================================================


class TestWorkOnProjectSubmission:
    """Submission validation for work_on_project."""

    def test_happy_path(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        story = _story(db)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "work_on_project",
            {"story_id": story.id, "entry_text": "Made progress on the investigation."},
        )

        assert resp.status_code == 201
        ce = resp.json()["calculated_effect"]
        assert ce["story_id"] == story.id
        assert ce["entry_text"] == "Made progress on the investigation."
        assert ce["costs"]["free_time"] == 1

    def test_missing_story_id_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "work_on_project", {"entry_text": "Some text."}
        )

        assert resp.status_code == 422
        assert "story_id" in resp.json()["error"]["details"]["fields"]

    def test_missing_entry_text_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        story = _story(db)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "work_on_project", {"story_id": story.id}
        )

        assert resp.status_code == 422
        assert "entry_text" in resp.json()["error"]["details"]["fields"]

    def test_nonexistent_story_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "work_on_project",
            {"story_id": "01NONEXISTENTULID0000000000", "entry_text": "Text."},
        )

        assert resp.status_code == 422

    def test_missing_ft_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        story = _story(db)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "work_on_project",
            {"story_id": story.id, "entry_text": "Text."},
        )

        assert resp.status_code == 422


class TestWorkOnProjectApproval:
    """Approval effects for work_on_project."""

    def test_story_entry_created_on_approval(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Approval creates a StoryEntry on the story and deducts 1 FT."""
        from wizards_engine.models.story import StoryEntry  # noqa: PLC0415

        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        story = _story(db)
        db.commit()

        auth_as(client, seed_data["player1"])
        submit_resp = _post_proposal(
            client, pc1.id, "work_on_project",
            {"story_id": story.id, "entry_text": "Found the hidden archive."},
        )
        assert submit_resp.status_code == 201
        proposal_id = submit_resp.json()["id"]

        auth_as(client, seed_data["gm"])
        approve_resp = _approve(client, proposal_id)
        assert approve_resp.status_code == 200

        db.expire_all()
        entry = db.query(StoryEntry).filter(StoryEntry.story_id == story.id).first()
        assert entry is not None
        assert entry.text == "Found the hidden archive."
        assert entry.character_id == pc1.id
        assert pc1.free_time == 0


# ===========================================================================
# rest
# ===========================================================================


class TestRestSubmission:
    """Submission validation for rest."""

    def test_no_modifiers_stress_healed_3(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Base stress healed = 3 with no modifiers."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(client, pc1.id, "rest", {})

        assert resp.status_code == 201
        ce = resp.json()["calculated_effect"]
        assert ce["stress_healed"] == 3
        assert ce["costs"]["free_time"] == 1
        assert ce["costs"]["trait_charges"] == []

    def test_all_three_modifiers_stress_healed_6(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """All three modifiers increase stress healed to 6."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        core = _core_trait(db, pc1.id, "Grounded")
        role = _role_trait(db, pc1.id, "Healer")
        bond = _pc_bond_slot(db, pc1.id, target_type="character", target_id=seed_data["pc2"].id)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "rest",
            {"modifiers": {"core_trait_id": core.id, "role_trait_id": role.id, "bond_id": bond.id}},
        )

        assert resp.status_code == 201
        ce = resp.json()["calculated_effect"]
        assert ce["stress_healed"] == 6
        assert len(ce["costs"]["trait_charges"]) == 2

    def test_missing_ft_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(client, pc1.id, "rest", {})

        assert resp.status_code == 422


class TestRestApproval:
    """Approval effects for rest."""

    def test_stress_reduced_on_approval(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        _set_stress(db, pc1, 5)
        db.commit()

        auth_as(client, seed_data["player1"])
        submit_resp = _post_proposal(client, pc1.id, "rest", {})
        assert submit_resp.status_code == 201

        auth_as(client, seed_data["gm"])
        _approve(client, submit_resp.json()["id"])

        db.expire_all()
        assert pc1.stress == 2  # 5 - 3
        assert pc1.free_time == 0

    def test_stress_clamped_at_0(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Stress never goes below 0."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        _set_stress(db, pc1, 1)  # less than 3
        db.commit()

        auth_as(client, seed_data["player1"])
        submit_resp = _post_proposal(client, pc1.id, "rest", {})
        assert submit_resp.status_code == 201

        auth_as(client, seed_data["gm"])
        _approve(client, submit_resp.json()["id"])

        db.expire_all()
        assert pc1.stress == 0  # clamped

    def test_trait_charges_deducted_on_approval(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        _set_stress(db, pc1, 5)
        trait = _core_trait(db, pc1.id, charge=3)
        db.commit()

        auth_as(client, seed_data["player1"])
        submit_resp = _post_proposal(
            client, pc1.id, "rest", {"modifiers": {"core_trait_id": trait.id}}
        )
        assert submit_resp.status_code == 201

        auth_as(client, seed_data["gm"])
        _approve(client, submit_resp.json()["id"])

        db.expire_all()
        db.refresh(trait)
        assert trait.charge == 2


# ===========================================================================
# new_trait
# ===========================================================================


class TestNewTraitSubmission:
    """Submission validation for new_trait."""

    def test_with_existing_template_under_limit(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Providing a valid template_id below the slot limit returns 201."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        tmpl = _core_template(db, "Resilient")
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "new_trait",
            {"slot_type": "core_trait", "template_id": tmpl.id},
        )

        assert resp.status_code == 201
        ce = resp.json()["calculated_effect"]
        assert ce["slot_type"] == "core_trait"
        assert ce["template_id"] == tmpl.id
        assert ce["retire_trait_id"] is None
        assert ce["costs"]["free_time"] == 1

    def test_with_proposed_name(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Providing proposed_name + proposed_description stores them in effect."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "new_trait",
            {
                "slot_type": "role_trait",
                "proposed_name": "Shadow Walker",
                "proposed_description": "Moves unseen through the dark.",
            },
        )

        assert resp.status_code == 201
        ce = resp.json()["calculated_effect"]
        assert ce["proposed_name"] == "Shadow Walker"
        assert ce["template_id"] is None

    def test_missing_slot_type_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        tmpl = _core_template(db)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "new_trait", {"template_id": tmpl.id}
        )

        assert resp.status_code == 422
        assert "slot_type" in resp.json()["error"]["details"]["fields"]

    def test_no_template_or_proposed_name_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "new_trait", {"slot_type": "core_trait"}
        )

        assert resp.status_code == 422

    def test_proposed_name_without_description_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "new_trait",
            {"slot_type": "core_trait", "proposed_name": "Brave"},
        )

        assert resp.status_code == 422
        assert "proposed_description" in resp.json()["error"]["details"]["fields"]

    def test_at_core_limit_requires_retire_trait_id(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Submitting new_trait when at the 2-core-trait limit requires retire_trait_id."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        # Fill the core_trait limit (2 slots).
        _core_trait(db, pc1.id, "Brave")
        _core_trait(db, pc1.id, "Kind")
        tmpl = _core_template(db, "Bold")
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "new_trait",
            {"slot_type": "core_trait", "template_id": tmpl.id},
        )

        assert resp.status_code == 422
        assert "retire_trait_id" in resp.json()["error"]["details"]["fields"]

    def test_at_limit_with_retire_trait_id_accepted(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """At the limit, providing retire_trait_id is accepted."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        old_trait_1 = _core_trait(db, pc1.id, "Brave")
        _core_trait(db, pc1.id, "Kind")
        tmpl = _core_template(db, "Bold")
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "new_trait",
            {
                "slot_type": "core_trait",
                "template_id": tmpl.id,
                "retire_trait_id": old_trait_1.id,
            },
        )

        assert resp.status_code == 201
        ce = resp.json()["calculated_effect"]
        assert ce["retire_trait_id"] == old_trait_1.id


class TestNewTraitApproval:
    """Approval effects for new_trait."""

    def test_trait_created_on_approval(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Approval creates a new trait instance with charge=5 and deducts 1 FT."""
        from wizards_engine.models.slot import Slot  # noqa: F811

        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        tmpl = _core_template(db, "Indomitable")
        db.commit()

        auth_as(client, seed_data["player1"])
        submit_resp = _post_proposal(
            client, pc1.id, "new_trait",
            {"slot_type": "core_trait", "template_id": tmpl.id},
        )
        assert submit_resp.status_code == 201
        proposal_id = submit_resp.json()["id"]

        auth_as(client, seed_data["gm"])
        approve_resp = _approve(client, proposal_id)
        assert approve_resp.status_code == 200

        db.expire_all()
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
        assert new_slot.charge == 5
        assert pc1.free_time == 0

    def test_old_trait_retired_on_approval(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """The retire_trait_id slot is set to inactive on approval."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        old1 = _core_trait(db, pc1.id, "Brave")
        _core_trait(db, pc1.id, "Kind")
        new_tmpl = _core_template(db, "Bold")
        db.commit()

        auth_as(client, seed_data["player1"])
        submit_resp = _post_proposal(
            client, pc1.id, "new_trait",
            {
                "slot_type": "core_trait",
                "template_id": new_tmpl.id,
                "retire_trait_id": old1.id,
            },
        )
        assert submit_resp.status_code == 201

        auth_as(client, seed_data["gm"])
        _approve(client, submit_resp.json()["id"])

        db.expire_all()
        db.refresh(old1)
        assert old1.is_active is False

    def test_proposed_name_creates_template_on_approval(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """When proposed_name is used, a TraitTemplate is created on approval."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        db.commit()

        auth_as(client, seed_data["player1"])
        submit_resp = _post_proposal(
            client, pc1.id, "new_trait",
            {
                "slot_type": "core_trait",
                "proposed_name": "Unbreakable",
                "proposed_description": "Cannot be bent by fear.",
            },
        )
        assert submit_resp.status_code == 201

        auth_as(client, seed_data["gm"])
        _approve(client, submit_resp.json()["id"])

        db.expire_all()
        tmpl = db.query(TraitTemplate).filter(TraitTemplate.name == "Unbreakable").first()
        assert tmpl is not None
        assert tmpl.type == "core"


# ===========================================================================
# new_bond
# ===========================================================================


class TestNewBondSubmission:
    """Submission validation for new_bond."""

    def test_happy_path_to_character(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Valid target returns 201 with correct calculated_effect."""
        pc1, pc2 = seed_data["pc1"], seed_data["pc2"]
        _set_ft(db, pc1, 1)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "new_bond",
            {"target_type": "character", "target_id": pc2.id},
        )

        assert resp.status_code == 201
        ce = resp.json()["calculated_effect"]
        assert ce["target_type"] == "character"
        assert ce["target_id"] == pc2.id
        assert ce["retire_bond_id"] is None
        assert ce["costs"]["free_time"] == 1

    def test_happy_path_to_group(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Bonding to a group is valid."""
        pc2 = seed_data["pc2"]
        _set_ft(db, pc2, 1)
        # pc2 has a bond to group already — use a different character.
        pc3 = seed_data["pc3"]
        _set_ft(db, pc3, 1)
        db.commit()

        auth_as(client, seed_data["player3"])
        resp = _post_proposal(
            client, pc3.id, "new_bond",
            {"target_type": "group", "target_id": seed_data["group"].id},
        )

        assert resp.status_code == 201

    def test_duplicate_bond_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Creating a bond to a target where one already exists returns 422."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        db.commit()

        auth_as(client, seed_data["player1"])
        # pc1 already has a bond to group (pc1_bond in seed data).
        resp = _post_proposal(
            client, pc1.id, "new_bond",
            {"target_type": "group", "target_id": seed_data["group"].id},
        )

        assert resp.status_code == 422
        assert "target_id" in resp.json()["error"]["details"]["fields"]

    def test_missing_target_type_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "new_bond", {"target_id": seed_data["pc2"].id}
        )

        assert resp.status_code == 422

    def test_invalid_target_type_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "new_bond",
            {"target_type": "alien_type", "target_id": seed_data["pc2"].id},
        )

        assert resp.status_code == 422

    def test_nonexistent_target_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "new_bond",
            {"target_type": "character", "target_id": "01NONEXISTENTULID0000000000"},
        )

        assert resp.status_code == 422

    def test_at_8_bond_limit_requires_retire_bond_id(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """At the 8-bond limit, retire_bond_id is required."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        # pc1 already has 1 bond from seed data; add 7 more to reach limit=8.
        for i in range(7):
            _pc_bond_slot(db, pc1.id, name=f"Extra Bond {i}")
        new_target = seed_data["pc2"]
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "new_bond",
            {"target_type": "character", "target_id": new_target.id},
        )

        assert resp.status_code == 422
        assert "retire_bond_id" in resp.json()["error"]["details"]["fields"]

    def test_missing_ft_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "new_bond",
            {"target_type": "character", "target_id": seed_data["pc2"].id},
        )

        assert resp.status_code == 422


class TestNewBondApproval:
    """Approval effects for new_bond."""

    def test_bond_created_on_approval(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Approval creates a new pc_bond slot and deducts 1 FT."""
        from sqlalchemy import and_, select  # noqa: PLC0415

        pc1, pc2 = seed_data["pc1"], seed_data["pc2"]
        _set_ft(db, pc1, 1)
        db.commit()

        auth_as(client, seed_data["player1"])
        submit_resp = _post_proposal(
            client, pc1.id, "new_bond",
            {"target_type": "character", "target_id": pc2.id},
        )
        assert submit_resp.status_code == 201
        proposal_id = submit_resp.json()["id"]

        auth_as(client, seed_data["gm"])
        approve_resp = _approve(client, proposal_id)
        assert approve_resp.status_code == 200

        db.expire_all()
        new_bond = db.execute(
            select(Slot).where(
                and_(
                    Slot.owner_id == pc1.id,
                    Slot.target_id == pc2.id,
                    Slot.slot_type == "pc_bond",
                    Slot.is_active.is_(True),
                )
            )
        ).scalars().first()
        assert new_bond is not None
        assert pc1.free_time == 0

    def test_old_bond_retired_on_approval(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """The retire_bond_id bond is set to inactive on approval."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        # Fill to 8 bonds.
        extra_bonds = []
        for i in range(7):
            b = _pc_bond_slot(db, pc1.id, name=f"Filler Bond {i}")
            extra_bonds.append(b)
        retire_bond = seed_data["pc1_bond"]  # existing bond to retire
        db.commit()

        auth_as(client, seed_data["player1"])
        submit_resp = _post_proposal(
            client, pc1.id, "new_bond",
            {
                "target_type": "character",
                "target_id": seed_data["pc2"].id,
                "retire_bond_id": retire_bond.id,
            },
        )
        assert submit_resp.status_code == 201

        auth_as(client, seed_data["gm"])
        _approve(client, submit_resp.json()["id"])

        db.expire_all()
        db.refresh(retire_bond)
        assert retire_bond.is_active is False


# ===========================================================================
# Shared: FT affordability check at approval time
# ===========================================================================


class TestDowntimeFTAffordabilityCheck:
    """FT is re-checked at approval time; force=True bypasses it."""

    def test_insufficient_ft_at_approval_blocked(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """If FT is now 0 at approval time, the approval is blocked."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        db.commit()

        # Submit while FT=1 (valid).
        auth_as(client, seed_data["player1"])
        submit_resp = _post_proposal(client, pc1.id, "rest", {})
        assert submit_resp.status_code == 201
        proposal_id = submit_resp.json()["id"]

        # Drain FT between submission and approval.
        db.expire_all()
        pc1_fresh = db.get(type(pc1), pc1.id)
        pc1_fresh.free_time = 0
        db.commit()

        auth_as(client, seed_data["gm"])
        approve_resp = _approve(client, proposal_id)
        assert approve_resp.status_code == 409
        assert approve_resp.json()["error"]["code"] == "insufficient_resources"

    def test_force_overrides_insufficient_ft(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """gm_overrides.force=True bypasses the FT check at approval time."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        db.commit()

        auth_as(client, seed_data["player1"])
        submit_resp = _post_proposal(client, pc1.id, "rest", {})
        assert submit_resp.status_code == 201
        proposal_id = submit_resp.json()["id"]

        # Drain FT.
        db.expire_all()
        pc1_fresh = db.get(type(pc1), pc1.id)
        pc1_fresh.free_time = 0
        db.commit()

        auth_as(client, seed_data["gm"])
        approve_resp = _approve(client, proposal_id, {"gm_overrides": {"force": True}})
        assert approve_resp.status_code == 200


# ===========================================================================
# new_bond — is_trauma validation on retire_bond_id
# ===========================================================================


class TestNewBondTraumaRetireGuard:
    """Trauma bonds cannot be retired via the new_bond downtime action."""

    def test_retire_trauma_bond_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Providing a trauma bond as retire_bond_id should fail with 422."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)

        # Create a trauma bond for pc1.
        trauma_bond = Slot(
            slot_type="pc_bond",
            owner_type="character",
            owner_id=pc1.id,
            target_type=None,
            target_id=None,
            name="The Weight of Loss",
            stress=5,
            stress_degradations=0,
            is_trauma=True,
            is_active=True,
        )
        db.add(trauma_bond)
        db.flush()
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "new_bond",
            {
                "target_type": "character",
                "target_id": seed_data["pc2"].id,
                "retire_bond_id": trauma_bond.id,
            },
        )

        assert resp.status_code == 422
        fields = resp.json()["error"]["details"]["fields"]
        assert "retire_bond_id" in fields
        assert "trauma" in fields["retire_bond_id"].lower()

    def test_retire_normal_bond_succeeds(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """A non-trauma pc_bond can be provided as retire_bond_id."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)

        # Create a normal (non-trauma) pc_bond to retire.
        normal_bond = _pc_bond_slot(db, pc1.id, name="Old Friend")
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "new_bond",
            {
                "target_type": "character",
                "target_id": seed_data["pc2"].id,
                "retire_bond_id": normal_bond.id,
            },
        )

        assert resp.status_code == 201
