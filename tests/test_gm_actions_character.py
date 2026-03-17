"""Integration tests for Story 4.2.1 — POST /api/v1/gm/actions (modify_character).

Covers:
- Auth: unauthenticated → 401, non-GM → 403
- Happy path: meter delta, meter set, skill set, magic stat xp/level, attributes merge,
  last_session_time_now, mixed changes
- Clamping: stress floor, stress ceiling, other meter floors/ceilings
- Skills and magic stats clamping
- Event shape: correct type derivation, changes dict, targets, visibility
- 404 for unknown character
- 422 for simplified character target
- 422 for invalid visibility
- Stress boundary: auto-generates resolve_trauma proposal at effective max
- Idempotency: second stress-at-max call does not create a second proposal
- Effective max with trauma bonds: adjusts boundary downward
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import auth_as
from wizards_engine.models.proposal import Proposal
from wizards_engine.models.slot import Slot


# ===========================================================================
# Helpers
# ===========================================================================


def _post(client: TestClient, body: dict) -> "Response":  # type: ignore[name-defined]
    """POST to /api/v1/gm/actions."""
    return client.post("/api/v1/gm/actions", json=body)


def _modify(
    client: TestClient,
    character_id: str,
    changes: dict,
    *,
    narrative: str | None = None,
    visibility: str = "bonded",
) -> "Response":  # type: ignore[name-defined]
    """Convenience wrapper for a modify_character action."""
    body: dict = {
        "action_type": "modify_character",
        "target_id": character_id,
        "changes": changes,
        "visibility": visibility,
    }
    if narrative is not None:
        body["narrative"] = narrative
    return _post(client, body)


# ===========================================================================
# Auth
# ===========================================================================


class TestGmActionsAuth:
    """Authentication and authorisation gates."""

    def test_unauthenticated_returns_401(self, client: TestClient) -> None:
        response = _post(client, {"action_type": "modify_character", "target_id": "x", "changes": {}})
        assert response.status_code == 401

    def test_player_returns_403(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["player1"])
        response = _modify(client, seed_data["pc1"].id, {"stress": {"op": "delta", "value": 1}})
        assert response.status_code == 403


# ===========================================================================
# 404 / 422 input validation
# ===========================================================================


class TestGmActionsValidation:
    """Input validation and error cases."""

    def test_unknown_character_returns_404(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = _modify(client, "01NONEXISTENTCHARACTERID00", {"stress": {"op": "set", "value": 3}})
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_simplified_character_returns_422(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = _modify(client, seed_data["npc1"].id, {"stress": {"op": "set", "value": 3}})
        assert response.status_code == 422

    def test_invalid_visibility_returns_422(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = _modify(
            client,
            seed_data["pc1"].id,
            {"stress": {"op": "delta", "value": 1}},
            visibility="invisible",
        )
        assert response.status_code == 422


# ===========================================================================
# Meter changes
# ===========================================================================


class TestGmActionsMeters:
    """Meter delta and set operations."""

    def test_stress_delta_applied(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["gm"])
        response = _modify(client, pc1.id, {"stress": {"op": "delta", "value": 3}})
        assert response.status_code == 200

        db.expire(pc1)
        db.refresh(pc1)
        assert pc1.stress == 3

    def test_stress_set_applied(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["gm"])
        response = _modify(client, pc1.id, {"stress": {"op": "set", "value": 5}})
        assert response.status_code == 200

        db.expire(pc1)
        db.refresh(pc1)
        assert pc1.stress == 5

    def test_free_time_delta(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["gm"])
        _modify(client, pc1.id, {"free_time": {"op": "delta", "value": 5}})
        db.expire(pc1)
        db.refresh(pc1)
        assert pc1.free_time == 5

    def test_gnosis_set(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc2 = seed_data["pc2"]
        auth_as(client, seed_data["gm"])
        _modify(client, pc2.id, {"gnosis": {"op": "set", "value": 12}})
        db.expire(pc2)
        db.refresh(pc2)
        assert pc2.gnosis == 12

    def test_plot_delta(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc3 = seed_data["pc3"]
        auth_as(client, seed_data["gm"])
        _modify(client, pc3.id, {"plot": {"op": "delta", "value": 2}})
        db.expire(pc3)
        db.refresh(pc3)
        assert pc3.plot == 2


# ===========================================================================
# Clamping
# ===========================================================================


class TestGmActionsClamping:
    """Range clamping behaviour."""

    def test_stress_clamped_at_floor(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["gm"])
        response = _modify(client, pc1.id, {"stress": {"op": "delta", "value": -10}})
        assert response.status_code == 200

        db.expire(pc1)
        db.refresh(pc1)
        assert pc1.stress == 0

        # The change dict should record clamped=true
        changes = response.json()["changes"]
        key = f"character.{pc1.id}.stress"
        assert changes[key]["after"] == 0
        assert changes[key]["clamped"] is True

    def test_stress_clamped_at_ceiling(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["gm"])
        # No trauma bonds on pc1, so effective max = 9
        response = _modify(client, pc1.id, {"stress": {"op": "set", "value": 99}})
        assert response.status_code == 200

        db.expire(pc1)
        db.refresh(pc1)
        assert pc1.stress == 9

        changes = response.json()["changes"]
        key = f"character.{pc1.id}.stress"
        assert changes[key]["after"] == 9
        assert changes[key]["clamped"] is True

    def test_gnosis_clamped_at_23(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["gm"])
        _modify(client, pc1.id, {"gnosis": {"op": "set", "value": 99}})
        db.expire(pc1)
        db.refresh(pc1)
        assert pc1.gnosis == 23

    def test_free_time_clamped_at_20(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["gm"])
        _modify(client, pc1.id, {"free_time": {"op": "set", "value": 100}})
        db.expire(pc1)
        db.refresh(pc1)
        assert pc1.free_time == 20

    def test_no_clamped_flag_when_not_clamped(
        self, client: TestClient, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["gm"])
        response = _modify(client, pc1.id, {"stress": {"op": "set", "value": 3}})
        changes = response.json()["changes"]
        key = f"character.{pc1.id}.stress"
        assert "clamped" not in changes[key]


# ===========================================================================
# Skills
# ===========================================================================


class TestGmActionsSkills:
    """Skill modification."""

    def test_skill_set(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["gm"])
        response = _modify(client, pc1.id, {"skills": {"awareness": 2}})
        assert response.status_code == 200

        db.expire(pc1)
        db.refresh(pc1)
        assert pc1.skills["awareness"] == 2

    def test_skill_clamped_at_3(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["gm"])
        response = _modify(client, pc1.id, {"skills": {"awareness": 5}})
        db.expire(pc1)
        db.refresh(pc1)
        assert pc1.skills["awareness"] == 3
        changes = response.json()["changes"]
        assert changes[f"character.{pc1.id}.skills.awareness"]["clamped"] is True

    def test_skill_clamped_at_0(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["gm"])
        response = _modify(client, pc1.id, {"skills": {"awareness": -1}})
        db.expire(pc1)
        db.refresh(pc1)
        assert pc1.skills["awareness"] == 0

    def test_multiple_skills_at_once(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["gm"])
        _modify(client, pc1.id, {"skills": {"awareness": 1, "power": 3}})
        db.expire(pc1)
        db.refresh(pc1)
        assert pc1.skills["awareness"] == 1
        assert pc1.skills["power"] == 3


# ===========================================================================
# Magic stats
# ===========================================================================


class TestGmActionsMagicStats:
    """Magic stat XP and level modification."""

    def test_magic_stat_xp_delta(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["gm"])
        response = _modify(client, pc1.id, {"magic_stats": {"being": {"xp": 3}}})
        assert response.status_code == 200

        db.expire(pc1)
        db.refresh(pc1)
        assert pc1.magic_stats["being"]["xp"] == 3

    def test_magic_stat_level_set(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["gm"])
        response = _modify(client, pc1.id, {"magic_stats": {"being": {"level": 2}}})
        assert response.status_code == 200

        db.expire(pc1)
        db.refresh(pc1)
        assert pc1.magic_stats["being"]["level"] == 2

    def test_magic_stat_xp_clamped_at_4(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["gm"])
        response = _modify(client, pc1.id, {"magic_stats": {"being": {"xp": 10}}})
        db.expire(pc1)
        db.refresh(pc1)
        assert pc1.magic_stats["being"]["xp"] == 4
        changes = response.json()["changes"]
        key = f"character.{pc1.id}.magic_stats.being.xp"
        assert changes[key]["clamped"] is True

    def test_magic_stat_level_clamped_at_5(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["gm"])
        response = _modify(client, pc1.id, {"magic_stats": {"being": {"level": 9}}})
        db.expire(pc1)
        db.refresh(pc1)
        assert pc1.magic_stats["being"]["level"] == 5


# ===========================================================================
# Attributes
# ===========================================================================


class TestGmActionsAttributes:
    """Attributes JSON merge."""

    def test_attributes_merged(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["gm"])
        response = _modify(client, pc1.id, {"attributes": {"hair_color": "red"}})
        assert response.status_code == 200

        db.expire(pc1)
        db.refresh(pc1)
        assert pc1.attributes["hair_color"] == "red"

    def test_existing_attributes_preserved_on_merge(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        # Pre-set an existing attribute.
        pc1.attributes = {"eye_color": "blue"}
        db.flush()
        db.commit()

        auth_as(client, seed_data["gm"])
        _modify(client, pc1.id, {"attributes": {"hair_color": "red"}})

        db.expire(pc1)
        db.refresh(pc1)
        assert pc1.attributes["eye_color"] == "blue"
        assert pc1.attributes["hair_color"] == "red"


# ===========================================================================
# last_session_time_now
# ===========================================================================


class TestGmActionsLastSessionTimeNow:
    """last_session_time_now field modification."""

    def test_last_session_time_now_set(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["gm"])
        response = _modify(client, pc1.id, {"last_session_time_now": 5})
        assert response.status_code == 200

        db.expire(pc1)
        db.refresh(pc1)
        assert pc1.last_session_time_now == 5


# ===========================================================================
# Event shape
# ===========================================================================


class TestGmActionsEventShape:
    """Returned event has the correct shape."""

    def test_returns_event_response_shape(
        self, client: TestClient, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["gm"])
        response = _modify(
            client,
            pc1.id,
            {"stress": {"op": "set", "value": 2}},
            narrative="Test narrative.",
            visibility="gm_only",
        )
        assert response.status_code == 200
        body = response.json()

        assert body["type"] == "character.stress_changed"
        assert body["actor_type"] == "gm"
        assert body["actor_id"] == seed_data["gm"].id
        assert body["narrative"] == "Test narrative."
        assert body["visibility"] == "gm_only"
        assert len(body["targets"]) == 1
        assert body["targets"][0]["target_type"] == "character"
        assert body["targets"][0]["target_id"] == pc1.id
        assert body["targets"][0]["is_primary"] is True

    def test_changes_dict_contains_before_and_after(
        self, client: TestClient, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["gm"])
        response = _modify(client, pc1.id, {"stress": {"op": "set", "value": 4}})
        changes = response.json()["changes"]
        key = f"character.{pc1.id}.stress"
        assert changes[key]["before"] == 0
        assert changes[key]["after"] == 4
        assert changes[key]["op"] == "meter.set"

    def test_delta_op_recorded_as_meter_delta(
        self, client: TestClient, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["gm"])
        response = _modify(client, pc1.id, {"stress": {"op": "delta", "value": 2}})
        changes = response.json()["changes"]
        key = f"character.{pc1.id}.stress"
        assert changes[key]["op"] == "meter.delta"

    def test_event_type_stress_changed_for_stress_only(
        self, client: TestClient, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["gm"])
        response = _modify(client, pc1.id, {"stress": {"op": "delta", "value": 1}})
        assert response.json()["type"] == "character.stress_changed"

    def test_event_type_gnosis_changed_for_gnosis_only(
        self, client: TestClient, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["gm"])
        response = _modify(client, pc1.id, {"gnosis": {"op": "delta", "value": 1}})
        assert response.json()["type"] == "character.gnosis_changed"

    def test_event_type_meter_updated_for_multi_meter(
        self, client: TestClient, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["gm"])
        response = _modify(
            client,
            pc1.id,
            {
                "stress": {"op": "delta", "value": 1},
                "free_time": {"op": "delta", "value": 1},
            },
        )
        assert response.json()["type"] == "character.meter_updated"

    def test_event_type_skill_changed(
        self, client: TestClient, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["gm"])
        response = _modify(client, pc1.id, {"skills": {"awareness": 2}})
        assert response.json()["type"] == "character.skill_changed"

    def test_event_type_magic_stat_changed(
        self, client: TestClient, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["gm"])
        response = _modify(client, pc1.id, {"magic_stats": {"being": {"xp": 1}}})
        assert response.json()["type"] == "character.magic_stat_changed"

    def test_event_type_updated_for_mixed_changes(
        self, client: TestClient, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["gm"])
        response = _modify(
            client,
            pc1.id,
            {
                "stress": {"op": "delta", "value": 1},
                "skills": {"awareness": 2},
            },
        )
        assert response.json()["type"] == "character.updated"

    def test_default_visibility_is_gm_only(
        self, client: TestClient, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["gm"])
        body = {
            "action_type": "modify_character",
            "target_id": pc1.id,
            "changes": {"stress": {"op": "delta", "value": 1}},
            # no visibility key
        }
        response = client.post("/api/v1/gm/actions", json=body)
        assert response.status_code == 200
        assert response.json()["visibility"] == "gm_only"


# ===========================================================================
# Stress boundary / resolve_trauma proposal
# ===========================================================================


class TestGmActionsStressBoundary:
    """Stress boundary detection and resolve_trauma auto-proposal."""

    def test_stress_at_max_creates_proposal(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["gm"])
        # No trauma bonds on pc1, effective max = 9
        response = _modify(client, pc1.id, {"stress": {"op": "set", "value": 9}})
        assert response.status_code == 200

        proposal = (
            db.query(Proposal)
            .filter(
                Proposal.character_id == pc1.id,
                Proposal.action_type == "resolve_trauma",
                Proposal.status == "pending",
            )
            .first()
        )
        assert proposal is not None
        assert proposal.origin == "system"

    def test_stress_below_max_no_proposal(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["gm"])
        _modify(client, pc1.id, {"stress": {"op": "set", "value": 8}})

        proposal = (
            db.query(Proposal)
            .filter(
                Proposal.character_id == pc1.id,
                Proposal.action_type == "resolve_trauma",
                Proposal.status == "pending",
            )
            .first()
        )
        assert proposal is None

    def test_second_stress_at_max_idempotent(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """A second call at stress max must not create a duplicate proposal."""
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["gm"])
        _modify(client, pc1.id, {"stress": {"op": "set", "value": 9}})
        _modify(client, pc1.id, {"stress": {"op": "set", "value": 9}})

        count = (
            db.query(Proposal)
            .filter(
                Proposal.character_id == pc1.id,
                Proposal.action_type == "resolve_trauma",
                Proposal.status == "pending",
            )
            .count()
        )
        assert count == 1

    def test_effective_max_reduced_by_trauma_bonds(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """With one trauma bond, effective max is 8 — proposal fires at stress=8."""
        pc1 = seed_data["pc1"]
        # Add a trauma bond to pc1.
        trauma_bond = Slot(
            slot_type="pc_bond",
            owner_type="character",
            owner_id=pc1.id,
            target_type="character",
            target_id=seed_data["pc2"].id,
            name="Trauma Bond",
            is_active=True,
            is_trauma=True,
            stress=0,
            stress_degradations=0,
            bidirectional=False,
        )
        db.add(trauma_bond)
        db.commit()

        auth_as(client, seed_data["gm"])
        _modify(client, pc1.id, {"stress": {"op": "set", "value": 8}})

        proposal = (
            db.query(Proposal)
            .filter(
                Proposal.character_id == pc1.id,
                Proposal.action_type == "resolve_trauma",
                Proposal.status == "pending",
            )
            .first()
        )
        assert proposal is not None

    def test_stress_change_not_at_max_no_boundary_trigger(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Non-stress changes don't trigger the boundary check."""
        pc1 = seed_data["pc1"]
        auth_as(client, seed_data["gm"])
        _modify(client, pc1.id, {"free_time": {"op": "set", "value": 5}})

        count = (
            db.query(Proposal)
            .filter(
                Proposal.character_id == pc1.id,
                Proposal.action_type == "resolve_trauma",
            )
            .count()
        )
        assert count == 0
