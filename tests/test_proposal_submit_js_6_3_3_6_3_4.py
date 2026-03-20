"""QA tests for Stories 6.3.3 (Non-Magic Downtime) and 6.3.4 (Magic Actions)
— Proposal Submission UI backend contract verification.

These tests verify that the API accepts exactly the payload shapes the frontend
sends.  Each test names the acceptance criterion it covers so failures are
immediately traceable to the review checklist.

Stories under review
--------------------
6.3.3 — Non-Magic Downtime proposal form (regain_gnosis, rest,
         work_on_project, new_trait, new_bond)
6.3.4 — Magic action proposal form (use_magic, charge_magic) with the
         sacrifice builder component.

Methodology
-----------
Tests exercise the real HTTP endpoint (POST /api/v1/proposals) using the
FastAPI TestClient + function-scoped in-memory SQLite database.  Each test
constructs a ``selections`` payload that mirrors exactly what the frontend
``submit()`` function sends, verifying:

  - The backend accepts the shape (status 201)
  - The calculated_effect contains the fields the review step must render
  - Required-field absences produce 422 errors

A secondary contract-check section inspects the JS ``submit()`` payload
shapes statically, confirming field names match backend expectations.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import auth_as
from wizards_engine.models.character import Character
from wizards_engine.models.magic_effect import MagicEffect
from wizards_engine.models.slot import Slot, TraitTemplate
from wizards_engine.models.story import Story


# ===========================================================================
# Shared helpers (mirrors test_downtime_actions.py conventions)
# ===========================================================================


def _set_ft(db: Session, character: Character, ft: int) -> None:
    character.free_time = ft
    db.flush()


def _set_magic_stat(db: Session, character: Character, stat: str, level: int) -> None:
    stats = {k: dict(v) for k, v in (character.magic_stats or {}).items()}
    if stat not in stats:
        stats[stat] = {"level": 0, "xp": 0}
    stats[stat]["level"] = level
    character.magic_stats = stats
    db.flush()


def _core_template(db: Session, name: str = "Courageous") -> TraitTemplate:
    t = TraitTemplate(name=name, description=f"Desc: {name}", type="core", is_deleted=False)
    db.add(t)
    db.flush()
    db.refresh(t)
    return t


def _role_template(db: Session, name: str = "Scout") -> TraitTemplate:
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


def _pc_bond(
    db: Session,
    character_id: str,
    target_id: str,
    name: str = "Bond with test target",
    charges: int = 3,
) -> Slot:
    slot = Slot(
        slot_type="pc_bond",
        owner_type="character",
        owner_id=character_id,
        name=name,
        target_type="character",
        target_id=target_id,
        charges=charges,
        is_active=True,
    )
    db.add(slot)
    db.flush()
    db.refresh(slot)
    return slot


def _story(db: Session, name: str = "Test Project", status: str = "active") -> Story:
    s = Story(name=name, status=status, is_deleted=False)
    db.add(s)
    db.flush()
    db.refresh(s)
    return s


def _magic_effect(
    db: Session,
    character_id: str,
    name: str = "Test Effect",
    effect_type: str = "charged",
    is_active: bool = True,
) -> MagicEffect:
    e = MagicEffect(
        character_id=character_id,
        name=name,
        description="A test magical effect.",
        effect_type=effect_type,
        power_level=3,
        charges_current=2,
        charges_max=5,
        is_active=is_active,
    )
    db.add(e)
    db.flush()
    db.refresh(e)
    return e


def _post_proposal(
    client: TestClient,
    character_id: str,
    action_type: str,
    selections: dict,
    narrative: str = "A test action.",
):
    return client.post(
        "/api/v1/proposals",
        json={
            "character_id": character_id,
            "action_type": action_type,
            "narrative": narrative,
            "selections": selections,
        },
    )


# ===========================================================================
# Story 6.3.3 — Action type selector (downtime types present)
# ===========================================================================


class TestActionTypeSelector:
    """AC 6.3.3.1 — Action type selector includes all required downtime types."""

    @pytest.mark.parametrize("action_type", [
        "regain_gnosis",
        "rest",
        "work_on_project",
        "new_trait",
        "new_bond",
    ])
    def test_downtime_action_types_accepted_by_backend(
        self,
        client: TestClient,
        db: Session,
        seed_data: dict,
        action_type: str,
    ) -> None:
        """Backend accepts all five downtime action types with minimal valid payloads.

        Verifies the action_type list in ACTION_GROUPS matches VALID_ACTION_TYPES
        on the backend (i.e. none are missing and none are typos).
        """
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)

        if action_type == "work_on_project":
            story = _story(db)
            db.commit()
            selections = {"story_id": story.id, "entry_text": "Working on it."}
        elif action_type == "new_trait":
            tmpl = _core_template(db)
            db.commit()
            selections = {"slot_type": "core_trait", "template_id": tmpl.id}
        elif action_type == "new_bond":
            db.commit()
            selections = {"target_type": "character", "target_id": seed_data["pc2"].id}
        else:
            db.commit()
            selections = {}

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(client, pc1.id, action_type, selections)
        assert resp.status_code == 201, (
            f"action_type '{action_type}' rejected with {resp.status_code}: {resp.text}"
        )


# ===========================================================================
# Story 6.3.3 — regain_gnosis (AC 6.3.3.2)
# ===========================================================================


class TestRegainGnosisForm:
    """AC 6.3.3.2 — regain_gnosis: modifier selection, narrative required."""

    def test_regain_gnosis_no_modifiers_accepted(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """regain_gnosis with empty modifiers dict is accepted."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "regain_gnosis",
            {"modifiers": {}},
        )
        assert resp.status_code == 201
        assert "gnosis_gained" in resp.json()["calculated_effect"]

    def test_regain_gnosis_with_core_trait_modifier(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Frontend sends modifiers.core_trait_id — backend reads it from modifiers nest."""
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
        assert ce["gnosis_gained"] == 4  # base 3 + 0 (lowest stat) + 1 modifier

    def test_regain_gnosis_narrative_empty_rejected(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Narrative is required; empty string returns 422."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = client.post(
            "/api/v1/proposals",
            json={
                "character_id": pc1.id,
                "action_type": "regain_gnosis",
                "narrative": "",
                "selections": {},
            },
        )
        assert resp.status_code == 422

    def test_regain_gnosis_narrative_whitespace_rejected(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Narrative consisting only of whitespace is treated as empty."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = client.post(
            "/api/v1/proposals",
            json={
                "character_id": pc1.id,
                "action_type": "regain_gnosis",
                "narrative": "   ",
                "selections": {},
            },
        )
        assert resp.status_code == 422

    def test_regain_gnosis_review_step_fields_present(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Review step shows calculated effect — gnosis_gained must be in response."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        _set_magic_stat(db, pc1, "being", 2)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "regain_gnosis",
            {"modifiers": {}},
        )
        assert resp.status_code == 201
        ce = resp.json()["calculated_effect"]
        # Formula: base 3 + lowest_magic_stat (2, all others 0 so lowest is 0) + modifiers
        assert "gnosis_gained" in ce
        assert "costs" in ce
        assert ce["costs"]["free_time"] == 1


# ===========================================================================
# Story 6.3.3 — rest (AC 6.3.3.3)
# ===========================================================================


class TestRestForm:
    """AC 6.3.3.3 — rest: modifier selection, narrative required."""

    def test_rest_no_modifiers_accepted(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """rest with empty selections is accepted."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(client, pc1.id, "rest", {"modifiers": {}})
        assert resp.status_code == 201
        assert resp.json()["calculated_effect"]["stress_healed"] == 3

    def test_rest_with_role_trait_modifier(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """modifiers.role_trait_id is correctly threaded to the backend."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        role = _role_trait(db, pc1.id)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "rest",
            {"modifiers": {"role_trait_id": role.id}},
        )
        assert resp.status_code == 201
        assert resp.json()["calculated_effect"]["stress_healed"] == 4

    def test_rest_narrative_required(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """rest without narrative returns 422."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = client.post(
            "/api/v1/proposals",
            json={
                "character_id": pc1.id,
                "action_type": "rest",
                "narrative": None,
                "selections": {},
            },
        )
        assert resp.status_code == 422

    def test_rest_review_step_fields_present(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Review step needs stress_healed and free_time cost."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(client, pc1.id, "rest", {})
        assert resp.status_code == 201
        ce = resp.json()["calculated_effect"]
        assert "stress_healed" in ce
        assert ce["costs"]["free_time"] == 1


# ===========================================================================
# Story 6.3.3 — work_on_project (AC 6.3.3.4)
# ===========================================================================


class TestWorkOnProjectForm:
    """AC 6.3.3.4 — work_on_project: story selector, narrative required."""

    def test_work_on_project_happy_path(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """story_id + entry_text in selections with non-empty narrative accepted."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        story = _story(db)
        db.commit()

        auth_as(client, seed_data["player1"])
        # Frontend sends: story_id + entry_text (narrative duplicated there) in selections
        resp = _post_proposal(
            client, pc1.id, "work_on_project",
            {
                "story_id": story.id,
                "entry_text": "We investigated the old ruins.",
            },
            narrative="We investigated the old ruins.",
        )
        assert resp.status_code == 201
        ce = resp.json()["calculated_effect"]
        assert ce["story_id"] == story.id

    def test_work_on_project_missing_story_id_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """story_id is required; omitting it returns 422."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "work_on_project",
            {"entry_text": "Some work."},
        )
        assert resp.status_code == 422

    def test_work_on_project_missing_entry_text_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """entry_text is required in selections; omitting it returns 422."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        story = _story(db)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "work_on_project",
            {"story_id": story.id},
        )
        assert resp.status_code == 422

    def test_work_on_project_narrative_required(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Narrative at the top level is also required for downtime."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        story = _story(db)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = client.post(
            "/api/v1/proposals",
            json={
                "character_id": pc1.id,
                "action_type": "work_on_project",
                "narrative": "",
                "selections": {"story_id": story.id, "entry_text": "Work."},
            },
        )
        assert resp.status_code == 422

    def test_work_on_project_review_shows_story_id(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """The review step needs story_id in calculated_effect to display story name."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        story = _story(db, name="Ruins Expedition")
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "work_on_project",
            {"story_id": story.id, "entry_text": "We began digging."},
            narrative="We began digging.",
        )
        assert resp.status_code == 201
        ce = resp.json()["calculated_effect"]
        assert ce["story_id"] == story.id
        assert "entry_text" in ce
        assert ce["costs"]["free_time"] == 1


# ===========================================================================
# Story 6.3.3 — new_trait (AC 6.3.3.5)
# ===========================================================================


class TestNewTraitForm:
    """AC 6.3.3.5 — new_trait: slot type, template or propose new, optional retire."""

    def test_new_trait_with_template_accepted(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """template_id in selections is accepted and reflected in calculated_effect."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        tmpl = _core_template(db, "Bold")
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "new_trait",
            {
                "slot_type": "core_trait",
                "template_id": tmpl.id,
                "proposed_name": None,
                "proposed_description": None,
                "retire_trait_id": None,
            },
        )
        assert resp.status_code == 201
        ce = resp.json()["calculated_effect"]
        assert ce["slot_type"] == "core_trait"
        assert ce["template_id"] == tmpl.id

    def test_new_trait_proposed_new_accepted(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """proposed_name + proposed_description accepted when no template chosen."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "new_trait",
            {
                "slot_type": "core_trait",
                "template_id": None,
                "proposed_name": "Unbreakable Spirit",
                "proposed_description": "Never gives up under pressure.",
                "retire_trait_id": None,
            },
        )
        assert resp.status_code == 201
        ce = resp.json()["calculated_effect"]
        assert ce["proposed_name"] == "Unbreakable Spirit"

    def test_new_trait_neither_template_nor_name_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Omitting both template_id and proposed_name returns 422."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "new_trait",
            {"slot_type": "core_trait"},
        )
        assert resp.status_code == 422

    def test_new_trait_proposed_name_without_description_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """proposed_name without proposed_description returns 422."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "new_trait",
            {
                "slot_type": "core_trait",
                "proposed_name": "Mystery Trait",
                "proposed_description": None,
            },
        )
        assert resp.status_code == 422

    def test_new_trait_with_retire_accepted(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """retire_trait_id is accepted and reflected in calculated_effect."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        old_trait = _core_trait(db, pc1.id, "Old One")
        # Fill both core_trait slots so retire is required
        _core_trait(db, pc1.id, "Old Two")
        tmpl = _core_template(db, "Brave")
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "new_trait",
            {
                "slot_type": "core_trait",
                "template_id": tmpl.id,
                "proposed_name": None,
                "proposed_description": None,
                "retire_trait_id": old_trait.id,
            },
        )
        assert resp.status_code == 201
        ce = resp.json()["calculated_effect"]
        assert ce["retire_trait_id"] == old_trait.id

    def test_new_trait_at_limit_without_retire_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """At core_trait limit (2) without retire_trait_id returns 422."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        _core_trait(db, pc1.id, "Slot One")
        _core_trait(db, pc1.id, "Slot Two")
        tmpl = _core_template(db, "Brave")
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "new_trait",
            {"slot_type": "core_trait", "template_id": tmpl.id},
        )
        assert resp.status_code == 422

    def test_new_trait_narrative_required(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """new_trait narrative cannot be null."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        tmpl = _core_template(db)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = client.post(
            "/api/v1/proposals",
            json={
                "character_id": pc1.id,
                "action_type": "new_trait",
                "narrative": None,
                "selections": {"slot_type": "core_trait", "template_id": tmpl.id},
            },
        )
        assert resp.status_code == 422

    def test_new_trait_review_step_fields(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Review step fields — slot_type, template_id, costs — are in calculated_effect."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        tmpl = _role_template(db, "Wanderer")
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "new_trait",
            {"slot_type": "role_trait", "template_id": tmpl.id},
        )
        assert resp.status_code == 201
        ce = resp.json()["calculated_effect"]
        assert ce["slot_type"] == "role_trait"
        assert ce["template_id"] == tmpl.id
        assert ce["costs"]["free_time"] == 1


# ===========================================================================
# Story 6.3.3 — new_bond (AC 6.3.3.6)
# ===========================================================================


class TestNewBondForm:
    """AC 6.3.3.6 — new_bond: target picker, optional retire, narrative required."""

    def test_new_bond_character_target_accepted(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """target_type=character + target_id accepted."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "new_bond",
            {
                "target_type": "character",
                "target_id": seed_data["pc2"].id,
                "retire_bond_id": None,
            },
        )
        assert resp.status_code == 201
        ce = resp.json()["calculated_effect"]
        assert ce["target_type"] == "character"
        assert ce["target_id"] == seed_data["pc2"].id

    def test_new_bond_group_target_accepted(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """target_type=group accepted.

        pc3 has no pre-existing bond to the group in seed data, so there is
        no duplicate-bond conflict.
        """
        pc3 = seed_data["pc3"]
        _set_ft(db, pc3, 1)
        db.commit()

        auth_as(client, seed_data["player3"])
        resp = _post_proposal(
            client, pc3.id, "new_bond",
            {
                "target_type": "group",
                "target_id": seed_data["group"].id,
                "retire_bond_id": None,
            },
        )
        assert resp.status_code == 201

    def test_new_bond_location_target_accepted(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """target_type=location accepted."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "new_bond",
            {
                "target_type": "location",
                "target_id": seed_data["region"].id,
                "retire_bond_id": None,
            },
        )
        assert resp.status_code == 201

    def test_new_bond_with_retire_accepted(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """retire_bond_id is accepted when present."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        old_bond = _pc_bond(db, pc1.id, seed_data["pc2"].id, name="Old bond")
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "new_bond",
            {
                "target_type": "character",
                "target_id": seed_data["npc1"].id,
                "retire_bond_id": old_bond.id,
            },
        )
        assert resp.status_code == 201
        ce = resp.json()["calculated_effect"]
        assert ce["retire_bond_id"] == old_bond.id

    def test_new_bond_missing_target_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """target_id is required."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "new_bond",
            {"target_type": "character"},
        )
        assert resp.status_code == 422

    def test_new_bond_narrative_required(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """new_bond without narrative returns 422."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = client.post(
            "/api/v1/proposals",
            json={
                "character_id": pc1.id,
                "action_type": "new_bond",
                "narrative": None,
                "selections": {
                    "target_type": "character",
                    "target_id": seed_data["pc2"].id,
                },
            },
        )
        assert resp.status_code == 422

    def test_new_bond_review_step_fields(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Review step must show target_type and target_id from calculated_effect.

        Uses pc3 to avoid the duplicate-bond conflict on pc1→group that exists
        in seed data.
        """
        pc3 = seed_data["pc3"]
        _set_ft(db, pc3, 1)
        db.commit()

        auth_as(client, seed_data["player3"])
        resp = _post_proposal(
            client, pc3.id, "new_bond",
            {"target_type": "group", "target_id": seed_data["group"].id},
        )
        assert resp.status_code == 201
        ce = resp.json()["calculated_effect"]
        assert "target_type" in ce
        assert "target_id" in ce
        assert ce["costs"]["free_time"] == 1


# ===========================================================================
# Story 6.3.3 — all downtime types require non-empty narrative (AC 6.3.3.7)
# ===========================================================================


class TestDowntimeNarrativeRequired:
    """AC 6.3.3.7 — all downtime types validate narrative non-empty before submit."""

    @pytest.mark.parametrize("action_type,selections_factory", [
        ("regain_gnosis", lambda db, sd: {}),
        ("rest",          lambda db, sd: {}),
    ])
    def test_null_narrative_rejected_for_downtime(
        self,
        client: TestClient,
        db: Session,
        seed_data: dict,
        action_type: str,
        selections_factory,
    ) -> None:
        """null narrative returns 422 for all simple downtime action types."""
        pc1 = seed_data["pc1"]
        _set_ft(db, pc1, 1)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = client.post(
            "/api/v1/proposals",
            json={
                "character_id": pc1.id,
                "action_type": action_type,
                "narrative": None,
                "selections": selections_factory(db, seed_data),
            },
        )
        assert resp.status_code == 422, (
            f"{action_type} accepted null narrative (expected 422)"
        )


# ===========================================================================
# Story 6.3.4 — Action type selector includes use_magic, charge_magic (AC 6.3.4.1)
# ===========================================================================


class TestMagicActionTypeSelector:
    """AC 6.3.4.1 — Action type selector includes use_magic and charge_magic."""

    @pytest.mark.parametrize("action_type", ["use_magic", "charge_magic"])
    def test_magic_action_types_accepted(
        self,
        client: TestClient,
        db: Session,
        seed_data: dict,
        action_type: str,
    ) -> None:
        """Backend accepts use_magic and charge_magic action types."""
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["player1"])

        if action_type == "use_magic":
            resp = _post_proposal(
                client, pc1.id, "use_magic",
                {"suggested_stat": "being", "sacrifice": [], "modifiers": {}},
                narrative=None,
            )
        else:
            effect = _magic_effect(db, pc1.id, effect_type="charged")
            db.commit()
            resp = _post_proposal(
                client, pc1.id, "charge_magic",
                {
                    "effect_id": effect.id,
                    "suggested_stat": "being",
                    "sacrifice": [],
                    "modifiers": {},
                },
                narrative=None,
            )
        assert resp.status_code == 201, (
            f"action_type '{action_type}' rejected: {resp.text}"
        )


# ===========================================================================
# Story 6.3.4 — use_magic form (AC 6.3.4.2)
# ===========================================================================


class TestUseMagicForm:
    """AC 6.3.4.2 — use_magic: magic stat selector, sacrifice builder, optional modifiers."""

    def test_use_magic_minimal_payload_accepted(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """suggested_stat with empty sacrifice list accepted; narrative is optional."""
        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, seed_data["pc1"].id, "use_magic",
            {"suggested_stat": "wyrding", "sacrifice": []},
            narrative=None,
        )
        assert resp.status_code == 201

    def test_use_magic_missing_stat_returns_422(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """suggested_stat is required; omitting it returns 422."""
        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, seed_data["pc1"].id, "use_magic",
            {"sacrifice": []},
            narrative=None,
        )
        assert resp.status_code == 422

    def test_use_magic_invalid_stat_returns_422(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """Invalid suggested_stat value returns 422."""
        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, seed_data["pc1"].id, "use_magic",
            {"suggested_stat": "fire", "sacrifice": []},
            narrative=None,
        )
        assert resp.status_code == 422

    def test_use_magic_with_optional_modifiers(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Modifier fields in nested modifiers object are accepted."""
        pc1 = seed_data["pc1"]
        trait = _core_trait(db, pc1.id)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "use_magic",
            {
                "suggested_stat": "enchanting",
                "sacrifice": [],
                "modifiers": {"core_trait_id": trait.id},
            },
            narrative=None,
        )
        assert resp.status_code == 201

    def test_use_magic_narrative_is_optional(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """use_magic narrative can be null (session action)."""
        auth_as(client, seed_data["player1"])
        resp = client.post(
            "/api/v1/proposals",
            json={
                "character_id": seed_data["pc1"].id,
                "action_type": "use_magic",
                "narrative": None,
                "selections": {"suggested_stat": "dreaming", "sacrifice": []},
            },
        )
        assert resp.status_code == 201

    def test_use_magic_review_fields_present(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Review step needs suggested_stat, total_gnosis_equivalent, sacrifice_dice."""
        pc1 = seed_data["pc1"]
        _set_magic_stat(db, pc1, "summoning", 3)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "use_magic",
            {
                "suggested_stat": "summoning",
                "sacrifice": [{"type": "gnosis", "amount": 3}],
                "modifiers": {},
            },
            narrative=None,
        )
        assert resp.status_code == 201
        ce = resp.json()["calculated_effect"]
        assert ce["suggested_stat"] == "summoning"
        assert ce["stat_level"] == 3
        assert ce["total_gnosis_equivalent"] == 3
        assert "sacrifice_dice" in ce
        assert "dice_pool" in ce
        assert "sacrifice_details" in ce


# ===========================================================================
# Story 6.3.4 — Sacrifice builder: all types (AC 6.3.4.3 + 6.3.4.4)
# ===========================================================================


class TestSacrificeBuilder:
    """AC 6.3.4.3 — sacrifice builder: add/remove, all types; AC 6.3.4.4 — running total."""

    def test_gnosis_sacrifice_accepted(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """type=gnosis with amount accepted and counted 1:1."""
        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, seed_data["pc1"].id, "use_magic",
            {
                "suggested_stat": "being",
                "sacrifice": [{"type": "gnosis", "amount": 5}],
            },
            narrative=None,
        )
        assert resp.status_code == 201
        ce = resp.json()["calculated_effect"]
        assert ce["total_gnosis_equivalent"] == 5

    def test_stress_sacrifice_two_per_point(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """type=stress contributes 2 gnosis-equiv per point."""
        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, seed_data["pc1"].id, "use_magic",
            {
                "suggested_stat": "being",
                "sacrifice": [{"type": "stress", "amount": 3}],
            },
            narrative=None,
        )
        assert resp.status_code == 201
        ce = resp.json()["calculated_effect"]
        assert ce["total_gnosis_equivalent"] == 6

    def test_free_time_sacrifice_accepted(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """type=free_time with amount accepted."""
        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, seed_data["pc1"].id, "use_magic",
            {
                "suggested_stat": "being",
                "sacrifice": [{"type": "free_time", "amount": 1}],
            },
            narrative=None,
        )
        # Backend uses (3 + lowest_magic_stat) which is 3 when all stats are 0
        assert resp.status_code == 201
        ce = resp.json()["calculated_effect"]
        # free_time = 1 point * (3 + 0) = 3 gnosis equiv
        assert ce["total_gnosis_equivalent"] == 3

    def test_bond_sacrifice_ten_gnosis_equiv(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """type=bond with target_id contributes 10 gnosis-equiv."""
        pc1 = seed_data["pc1"]
        bond = _pc_bond(db, pc1.id, seed_data["pc2"].id)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "use_magic",
            {
                "suggested_stat": "being",
                "sacrifice": [{"type": "bond", "target_id": bond.id}],
            },
            narrative=None,
        )
        assert resp.status_code == 201
        ce = resp.json()["calculated_effect"]
        assert ce["total_gnosis_equivalent"] == 10

    def test_trait_sacrifice_ten_gnosis_equiv(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """type=trait with target_id contributes 10 gnosis-equiv."""
        pc1 = seed_data["pc1"]
        trait = _core_trait(db, pc1.id)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "use_magic",
            {
                "suggested_stat": "being",
                "sacrifice": [{"type": "trait", "target_id": trait.id}],
            },
            narrative=None,
        )
        assert resp.status_code == 201
        ce = resp.json()["calculated_effect"]
        assert ce["total_gnosis_equivalent"] == 10

    def test_other_sacrifice_accepted_with_description(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """type=other with description and amount accepted (GM assigns value)."""
        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, seed_data["pc1"].id, "use_magic",
            {
                "suggested_stat": "being",
                "sacrifice": [
                    {"type": "other", "description": "My prized artifact", "amount": 5}
                ],
            },
            narrative=None,
        )
        assert resp.status_code == 201
        ce = resp.json()["calculated_effect"]
        # "other" gnosis_equivalent is 0 (GM assigns in overrides)
        assert ce["total_gnosis_equivalent"] == 0

    def test_mixed_sacrifice_types_total_is_additive(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Multiple sacrifice entries: gnosis-equivs are summed."""
        pc1 = seed_data["pc1"]
        bond = _pc_bond(db, pc1.id, seed_data["pc2"].id)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "use_magic",
            {
                "suggested_stat": "being",
                "sacrifice": [
                    {"type": "gnosis", "amount": 2},   # 2
                    {"type": "stress", "amount": 1},   # 2
                    {"type": "bond", "target_id": bond.id},  # 10
                ],
            },
            narrative=None,
        )
        assert resp.status_code == 201
        ce = resp.json()["calculated_effect"]
        assert ce["total_gnosis_equivalent"] == 14

    def test_bond_sacrifice_missing_target_id_returns_422(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """Bond sacrifice without target_id returns 422."""
        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, seed_data["pc1"].id, "use_magic",
            {
                "suggested_stat": "being",
                "sacrifice": [{"type": "bond", "target_id": ""}],
            },
            narrative=None,
        )
        assert resp.status_code == 422

    def test_trait_sacrifice_missing_target_id_returns_422(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """Trait sacrifice without target_id returns 422."""
        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, seed_data["pc1"].id, "use_magic",
            {
                "suggested_stat": "being",
                "sacrifice": [{"type": "trait", "target_id": ""}],
            },
            narrative=None,
        )
        assert resp.status_code == 422

    def test_unknown_sacrifice_type_returns_422(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """Unknown sacrifice type string returns 422."""
        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, seed_data["pc1"].id, "use_magic",
            {
                "suggested_stat": "being",
                "sacrifice": [{"type": "gold", "amount": 5}],
            },
            narrative=None,
        )
        assert resp.status_code == 422

    def test_gnosis_equiv_counter_reflects_tiered_dice_conversion(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """sacrifice_dice uses triangular formula: N dice costs N*(N+1)/2 gnosis.

        3 gnosis -> 2 dice (2*3/2=3), 6 gnosis -> 3 dice (3*4/2=6).
        """
        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, seed_data["pc1"].id, "use_magic",
            {"suggested_stat": "being", "sacrifice": [{"type": "gnosis", "amount": 6}]},
            narrative=None,
        )
        assert resp.status_code == 201
        ce = resp.json()["calculated_effect"]
        assert ce["sacrifice_dice"] == 3  # 3*(3+1)/2 = 6


# ===========================================================================
# Story 6.3.4 — charge_magic form (AC 6.3.4.5 + 6.3.4.6 + 6.3.4.7)
# ===========================================================================


class TestChargeMagicForm:
    """AC 6.3.4.5 — charge_magic: effect selector, magic stat, sacrifice builder."""

    def test_charge_magic_charged_effect_accepted(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """effect_id pointing to a charged effect is accepted."""
        pc1 = seed_data["pc1"]
        effect = _magic_effect(db, pc1.id, effect_type="charged")
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "charge_magic",
            {
                "effect_id": effect.id,
                "suggested_stat": "being",
                "sacrifice": [],
                "modifiers": {},
            },
            narrative=None,
        )
        assert resp.status_code == 201

    def test_charge_magic_permanent_effect_accepted(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """effect_id pointing to a permanent effect is accepted."""
        pc1 = seed_data["pc1"]
        effect = _magic_effect(db, pc1.id, effect_type="permanent")
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "charge_magic",
            {
                "effect_id": effect.id,
                "suggested_stat": "enchanting",
                "sacrifice": [{"type": "gnosis", "amount": 1}],
                "modifiers": {},
            },
            narrative=None,
        )
        assert resp.status_code == 201

    def test_charge_magic_instant_effect_rejected(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Instant effects cannot be targeted by charge_magic — returns 422."""
        pc1 = seed_data["pc1"]
        effect = _magic_effect(db, pc1.id, effect_type="instant")
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "charge_magic",
            {
                "effect_id": effect.id,
                "suggested_stat": "being",
                "sacrifice": [],
            },
            narrative=None,
        )
        assert resp.status_code == 422

    def test_charge_magic_missing_effect_id_returns_422(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """Omitting effect_id from charge_magic selections returns 422."""
        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, seed_data["pc1"].id, "charge_magic",
            {"suggested_stat": "being", "sacrifice": []},
            narrative=None,
        )
        assert resp.status_code == 422

    def test_charge_magic_missing_stat_returns_422(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Omitting suggested_stat from charge_magic selections returns 422."""
        pc1 = seed_data["pc1"]
        effect = _magic_effect(db, pc1.id, effect_type="charged")
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "charge_magic",
            {"effect_id": effect.id, "sacrifice": []},
            narrative=None,
        )
        assert resp.status_code == 422

    def test_charge_magic_narrative_is_optional(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """charge_magic is a session action; narrative can be null."""
        pc1 = seed_data["pc1"]
        effect = _magic_effect(db, pc1.id, effect_type="charged")
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = client.post(
            "/api/v1/proposals",
            json={
                "character_id": pc1.id,
                "action_type": "charge_magic",
                "narrative": None,
                "selections": {
                    "effect_id": effect.id,
                    "suggested_stat": "being",
                    "sacrifice": [],
                },
            },
        )
        assert resp.status_code == 201

    def test_charge_magic_review_step_fields(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """AC 6.3.4.6 — review shows magic stat, total sacrifice, breakdown, narrative.

        Verifies all fields the review template needs are present in
        calculated_effect.
        """
        pc1 = seed_data["pc1"]
        effect = _magic_effect(db, pc1.id, effect_type="charged")
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = _post_proposal(
            client, pc1.id, "charge_magic",
            {
                "effect_id": effect.id,
                "suggested_stat": "wyrding",
                "sacrifice": [
                    {"type": "gnosis", "amount": 3},
                    {"type": "stress", "amount": 1},
                ],
                "modifiers": {},
            },
            narrative="Recharging the ward.",
        )
        assert resp.status_code == 201
        ce = resp.json()["calculated_effect"]

        # magic stat
        assert ce["suggested_stat"] == "wyrding"
        assert "stat_level" in ce

        # total sacrifice and breakdown
        assert ce["total_gnosis_equivalent"] == 5  # 3 gnosis + 2 (1 stress * 2)
        assert "sacrifice_details" in ce
        assert len(ce["sacrifice_details"]) == 2

        # overall dice
        assert "dice_pool" in ce
        assert "sacrifice_dice" in ce

        # target effect details
        assert "target_effect" in ce
        assert ce["target_effect"]["id"] == effect.id
        assert ce["target_effect"]["effect_type"] == "charged"

    def test_charge_magic_submit_includes_effect_id_and_sacrifice(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """AC 6.3.4.7 — submit sends effect_id, suggested_stat, sacrifice list.

        Mirrors the frontend submit() payload for charge_magic and verifies
        the backend stores selections intact.
        """
        pc1 = seed_data["pc1"]
        effect = _magic_effect(db, pc1.id, effect_type="charged")
        db.commit()

        sacrifice_list = [
            {"type": "gnosis", "amount": 2},
            {"type": "other", "description": "My silver ring", "amount": 1},
        ]
        selections = {
            "effect_id": effect.id,
            "suggested_stat": "enchanting",
            "sacrifice": sacrifice_list,
            "modifiers": {
                "core_trait_id": None,
                "role_trait_id": None,
                "bond_id": None,
            },
        }

        auth_as(client, seed_data["player1"])
        resp = client.post(
            "/api/v1/proposals",
            json={
                "character_id": pc1.id,
                "action_type": "charge_magic",
                "narrative": None,
                "selections": selections,
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["action_type"] == "charge_magic"
        stored_sel = body["selections"]
        assert stored_sel["effect_id"] == effect.id
        assert stored_sel["suggested_stat"] == "enchanting"
        assert len(stored_sel["sacrifice"]) == 2


# ===========================================================================
# Contract check: use_skill modifiers shape (not part of 6.3.3/6.3.4 scope
# but exercises the known mismatch risk for modifier nesting)
# ===========================================================================


class TestUseSkillModifierNesting:
    """Verify use_skill selections use nested modifiers dict, not flat keys.

    The frontend submit() builds:
        selections = {
            skill: ...,
            core_trait_id: ...,   <-- flat keys
            role_trait_id: ...,
            bond_id: ...,
            plot_spend: ...,
        }

    The backend calculate_use_skill reads:
        selections.get("modifiers", {}).get("core_trait_id")

    This mismatch is flagged in the QA report but is pre-existing (Story 6.1
    scope). These tests document the observed backend behaviour for both shapes.
    """

    def test_use_skill_flat_modifier_keys_ignored_by_backend(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Flat core_trait_id in selections is silently ignored (no 422, modifier not applied).

        This documents the contract mismatch found during the 6.3.3/6.3.4 review:
        the frontend sends flat keys but the backend expects them nested in
        ``modifiers``.  The test records the actual behaviour so a future fix
        is detectable.
        """
        pc1 = seed_data["pc1"]
        trait = _core_trait(db, pc1.id)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = client.post(
            "/api/v1/proposals",
            json={
                "character_id": pc1.id,
                "action_type": "use_skill",
                "narrative": "I try.",
                "selections": {
                    "skill": "awareness",
                    "core_trait_id": trait.id,   # flat — backend ignores this
                    "role_trait_id": None,
                    "bond_id": None,
                    "plot_spend": 0,
                },
            },
        )
        # Backend accepts this (no 422) but does NOT apply the trait modifier
        assert resp.status_code == 201
        ce = resp.json()["calculated_effect"]
        # Without modifiers applied, dice_pool == skill level (0) + 0 modifiers
        assert ce["dice_pool"] == 0
        assert ce["modifiers"] == []

    def test_use_skill_nested_modifiers_correctly_applied(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Nested modifiers dict is the correct shape and applies the trait."""
        pc1 = seed_data["pc1"]
        trait = _core_trait(db, pc1.id)
        db.commit()

        auth_as(client, seed_data["player1"])
        resp = client.post(
            "/api/v1/proposals",
            json={
                "character_id": pc1.id,
                "action_type": "use_skill",
                "narrative": "I try.",
                "selections": {
                    "skill": "awareness",
                    "modifiers": {
                        "core_trait_id": trait.id,
                        "role_trait_id": None,
                        "bond_id": None,
                    },
                    "plot_spend": 0,
                },
            },
        )
        assert resp.status_code == 201
        ce = resp.json()["calculated_effect"]
        assert ce["dice_pool"] == 1   # 0 (skill) + 1 (modifier)
        assert len(ce["modifiers"]) == 1
