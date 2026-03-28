"""Tests for Story 9.1.7 — Route Permission Audit: Write Endpoints & Player Roster.

Verifies that viewer users are blocked from all write actions that are
restricted to players (and optionally GMs), and that the player roster
applies correct role-aware filtering.

Endpoints tested:
  POST /proposals                           — viewer must receive 403
  POST /proposals/calculate                 — viewer must receive 403
  POST /characters/{id}/find-time          — viewer must receive 403
  POST /characters/{id}/recharge-trait     — viewer must receive 403
  POST /characters/{id}/maintain-bond      — viewer must receive 403
  POST /characters/{id}/effects/{id}/use   — viewer must receive 403
  POST /characters/{id}/effects/{id}/retire — viewer must receive 403
  POST /sessions/{id}/participants         — viewer must receive 403
  DELETE /sessions/{id}/participants/{id}  — viewer must receive 403
  PATCH /sessions/{id}/participants/{id}   — viewer must receive 403

Player roster filtering:
  GET /players as viewer  — sees all users (no viewer filtering)
  GET /players as player  — viewers are excluded
  GET /players as gm      — sees all users with login_url
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import auth_as
from wizards_engine.models.magic_effect import MagicEffect
from wizards_engine.models.session import Session as SessionModel, SessionParticipant


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_session(db: Session, *, status: str = "draft") -> SessionModel:
    """Create a minimal session with the given status."""
    session = SessionModel(status=status, time_now=1)
    db.add(session)
    db.flush()
    db.refresh(session)
    return session


def _seed_participant(
    db: Session, session_id: str, character_id: str
) -> SessionParticipant:
    """Register a character as a session participant."""
    participant = SessionParticipant(
        session_id=session_id,
        character_id=character_id,
        additional_contribution=False,
    )
    db.add(participant)
    db.flush()
    db.refresh(participant)
    return participant


def _seed_charged_effect(db: Session, character_id: str) -> MagicEffect:
    """Create a charged magic effect owned by character_id."""
    effect = MagicEffect(
        character_id=character_id,
        name="Test Charged Effect",
        description="A test effect.",
        effect_type="charged",
        power_level=1,
        charges_current=3,
        charges_max=3,
        is_active=True,
    )
    db.add(effect)
    db.flush()
    db.refresh(effect)
    return effect


# ===========================================================================
# Proposals — viewer blocked
# ===========================================================================


class TestViewerBlockedOnProposals:
    """Viewer cannot submit proposals or use the calculate endpoint."""

    def test_viewer_cannot_create_proposal(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """POST /proposals returns 403 for viewer callers."""
        auth_as(client, seed_data["viewer"])
        response = client.post(
            "/api/v1/proposals",
            json={
                "character_id": seed_data["pc1"].id,
                "action_type": "use_skill",
                "narrative": "Viewer trying to propose.",
            },
        )
        assert response.status_code == 403

    def test_viewer_cannot_calculate_proposal(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """POST /proposals/calculate returns 403 for viewer callers."""
        auth_as(client, seed_data["viewer"])
        response = client.post(
            "/api/v1/proposals/calculate",
            json={
                "character_id": seed_data["pc1"].id,
                "action_type": "use_skill",
                "narrative": "Viewer trying to calculate.",
            },
        )
        assert response.status_code == 403


# ===========================================================================
# Find Time — viewer blocked
# ===========================================================================


class TestViewerBlockedOnFindTime:
    """Viewer cannot call the find-time action."""

    def test_viewer_returns_403(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """POST /characters/{id}/find-time returns 403 for viewer."""
        # Give pc1 enough Plot to trigger the action if auth passes.
        seed_data["pc1"].plot = 6
        db.commit()

        auth_as(client, seed_data["viewer"])
        response = client.post(
            f"/api/v1/characters/{seed_data['pc1'].id}/find-time"
        )
        assert response.status_code == 403


# ===========================================================================
# Recharge Trait — viewer blocked
# ===========================================================================


class TestViewerBlockedOnRechargeTrait:
    """Viewer cannot call the recharge-trait action."""

    def test_viewer_returns_403(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """POST /characters/{id}/recharge-trait returns 403 for viewer."""
        auth_as(client, seed_data["viewer"])
        response = client.post(
            f"/api/v1/characters/{seed_data['pc1'].id}/recharge-trait",
            json={"trait_instance_id": "00000000000000000000000001", "narrative": "test"},
        )
        assert response.status_code == 403


# ===========================================================================
# Maintain Bond — viewer blocked
# ===========================================================================


class TestViewerBlockedOnMaintainBond:
    """Viewer cannot call the maintain-bond action."""

    def test_viewer_returns_403(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """POST /characters/{id}/maintain-bond returns 403 for viewer."""
        auth_as(client, seed_data["viewer"])
        response = client.post(
            f"/api/v1/characters/{seed_data['pc1'].id}/maintain-bond",
            json={"bond_instance_id": "00000000000000000000000001", "narrative": "test"},
        )
        assert response.status_code == 403


# ===========================================================================
# Magic Effects (use/retire) — viewer blocked
# ===========================================================================


class TestViewerBlockedOnEffects:
    """Viewer cannot use or retire magic effects."""

    def test_viewer_cannot_use_effect(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """POST /characters/{id}/effects/{id}/use returns 403 for viewer."""
        effect = _seed_charged_effect(db, seed_data["pc1"].id)

        auth_as(client, seed_data["viewer"])
        response = client.post(
            f"/api/v1/characters/{seed_data['pc1'].id}/effects/{effect.id}/use",
            json={"narrative": "viewer tries to use effect"},
        )
        assert response.status_code == 403

    def test_viewer_cannot_retire_effect(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """POST /characters/{id}/effects/{id}/retire returns 403 for viewer."""
        effect = _seed_charged_effect(db, seed_data["pc1"].id)

        auth_as(client, seed_data["viewer"])
        response = client.post(
            f"/api/v1/characters/{seed_data['pc1'].id}/effects/{effect.id}/retire"
        )
        assert response.status_code == 403


# ===========================================================================
# Session participants — viewer blocked
# ===========================================================================


class TestViewerBlockedOnSessionParticipants:
    """Viewer cannot add, remove, or update session participants."""

    def test_viewer_cannot_add_participant(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """POST /sessions/{id}/participants returns 403 for viewer."""
        session = _seed_session(db)

        auth_as(client, seed_data["viewer"])
        response = client.post(
            f"/api/v1/sessions/{session.id}/participants",
            json={"character_id": seed_data["pc1"].id},
        )
        assert response.status_code == 403

    def test_viewer_cannot_remove_participant(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """DELETE /sessions/{id}/participants/{char_id} returns 403 for viewer."""
        session = _seed_session(db)
        _seed_participant(db, session.id, seed_data["pc1"].id)

        auth_as(client, seed_data["viewer"])
        response = client.delete(
            f"/api/v1/sessions/{session.id}/participants/{seed_data['pc1'].id}"
        )
        assert response.status_code == 403

    def test_viewer_cannot_update_participant(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """PATCH /sessions/{id}/participants/{char_id} returns 403 for viewer."""
        session = _seed_session(db)
        _seed_participant(db, session.id, seed_data["pc1"].id)

        auth_as(client, seed_data["viewer"])
        response = client.patch(
            f"/api/v1/sessions/{session.id}/participants/{seed_data['pc1'].id}",
            json={"additional_contribution": True},
        )
        assert response.status_code == 403


# ===========================================================================
# Player roster filtering (role-aware)
# ===========================================================================
#
# Note: Detailed roster tests are in test_players.py.  These tests verify the
# cross-cutting concern that the viewer fixture is correctly filtered.


class TestRosterFilteringCrossCheck:
    """Cross-check roster filtering for all three roles."""

    def test_gm_sees_five_users(self, client: TestClient, seed_data: dict) -> None:
        """GM sees GM + 3 players + 1 viewer = 5 entries."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/players")
        assert response.status_code == 200
        assert len(response.json()) == 5

    def test_player_sees_four_users(self, client: TestClient, seed_data: dict) -> None:
        """Player sees GM + 3 players = 4 entries (viewer excluded)."""
        auth_as(client, seed_data["player1"])
        response = client.get("/api/v1/players")
        assert response.status_code == 200
        assert len(response.json()) == 4

    def test_viewer_sees_five_users(self, client: TestClient, seed_data: dict) -> None:
        """Viewer sees all 5 users but without login_url."""
        auth_as(client, seed_data["viewer"])
        response = client.get("/api/v1/players")
        assert response.status_code == 200
        assert len(response.json()) == 5
        for entry in response.json():
            assert "login_url" not in entry
