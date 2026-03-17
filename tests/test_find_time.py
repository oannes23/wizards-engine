"""Integration tests for Story 5.1.4 — POST /api/v1/characters/{id}/find-time.

Covers:
- Happy path: Plot >= 3, FT < 20 → converts correctly
- 409 insufficient_plot when Plot < 3
- 409 free_time_at_cap when FT = 20
- 403 if player doesn't own character
- 404 if character doesn't exist
- 404 if character is deleted
- 422 if character is not a full (PC) character
- Event created with correct type, visibility, changes, and targets
- Multiple consecutive find-time calls work (Plot going from 6 → 3 → 0)
- GM can execute find-time for any character
- Unauthenticated → 401
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import auth_as
from wizards_engine.models.event import Event, EventTarget


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_time(client: TestClient, character_id: str) -> "Response":  # type: ignore[name-defined]
    """POST to the find-time endpoint for a character."""
    return client.post(f"/api/v1/characters/{character_id}/find-time")


def _set_meters(db: Session, character, *, plot: int, free_time: int) -> None:
    """Directly update a character's meters and commit."""
    character.plot = plot
    character.free_time = free_time
    db.commit()
    db.refresh(character)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class TestFindTimeAuth:
    """Authentication and authorisation gates."""

    def test_unauthenticated_returns_401(self, client: TestClient, seed_data: dict) -> None:
        response = _find_time(client, seed_data["pc1"].id)
        assert response.status_code == 401

    def test_player_cannot_use_other_characters_find_time(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """player2 cannot call find-time for pc1 (owned by player1)."""
        _set_meters(db, seed_data["pc1"], plot=5, free_time=0)
        auth_as(client, seed_data["player2"])
        response = _find_time(client, seed_data["pc1"].id)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"

    def test_player_can_use_own_character(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        _set_meters(db, seed_data["pc1"], plot=3, free_time=0)
        auth_as(client, seed_data["player1"])
        response = _find_time(client, seed_data["pc1"].id)
        assert response.status_code == 200

    def test_gm_can_use_any_character(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """GM may call find-time on behalf of any character."""
        _set_meters(db, seed_data["pc2"], plot=3, free_time=0)
        auth_as(client, seed_data["gm"])
        response = _find_time(client, seed_data["pc2"].id)
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# 404 cases
# ---------------------------------------------------------------------------


class TestFindTimeNotFound:
    """404 error cases."""

    def test_nonexistent_character_returns_404(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = _find_time(client, "01AAAAAAAAAAAAAAAAAAAAAA")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_deleted_character_returns_404(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        pc = seed_data["pc3"]
        pc.is_deleted = True
        db.commit()
        db.refresh(pc)

        auth_as(client, seed_data["gm"])
        response = _find_time(client, pc.id)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"


# ---------------------------------------------------------------------------
# 422 — non-PC character
# ---------------------------------------------------------------------------


class TestFindTimeNotPc:
    """422 when target is not a full character."""

    def test_simplified_character_returns_422(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = _find_time(client, seed_data["npc1"].id)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "not_a_pc"


# ---------------------------------------------------------------------------
# 409 — business logic errors
# ---------------------------------------------------------------------------


class TestFindTimeBusinessErrors:
    """409 error cases for insufficient resources or caps."""

    def test_insufficient_plot_returns_409(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        _set_meters(db, seed_data["pc1"], plot=2, free_time=0)
        auth_as(client, seed_data["player1"])
        response = _find_time(client, seed_data["pc1"].id)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "insufficient_plot"

    def test_plot_zero_returns_409(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        _set_meters(db, seed_data["pc1"], plot=0, free_time=0)
        auth_as(client, seed_data["player1"])
        response = _find_time(client, seed_data["pc1"].id)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "insufficient_plot"

    def test_free_time_at_cap_returns_409(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        _set_meters(db, seed_data["pc1"], plot=10, free_time=20)
        auth_as(client, seed_data["player1"])
        response = _find_time(client, seed_data["pc1"].id)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "free_time_at_cap"


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestFindTimeHappyPath:
    """Successful find-time conversions."""

    def test_happy_path_converts_plot_to_free_time(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        _set_meters(db, seed_data["pc1"], plot=5, free_time=2)
        auth_as(client, seed_data["player1"])
        response = _find_time(client, seed_data["pc1"].id)
        assert response.status_code == 200
        body = response.json()
        assert body["plot"] == 2
        assert body["free_time"] == 3
        assert body["id"] == seed_data["pc1"].id

    def test_exact_three_plot_works(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Plot = 3 is the minimum valid value — should succeed."""
        _set_meters(db, seed_data["pc1"], plot=3, free_time=0)
        auth_as(client, seed_data["player1"])
        response = _find_time(client, seed_data["pc1"].id)
        assert response.status_code == 200
        body = response.json()
        assert body["plot"] == 0
        assert body["free_time"] == 1

    def test_free_time_at_19_succeeds(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """FT = 19 is just below cap — should succeed."""
        _set_meters(db, seed_data["pc1"], plot=3, free_time=19)
        auth_as(client, seed_data["player1"])
        response = _find_time(client, seed_data["pc1"].id)
        assert response.status_code == 200
        body = response.json()
        assert body["free_time"] == 20

    def test_consecutive_calls_work(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Two consecutive find-time calls: Plot 6 → 3 → 0."""
        _set_meters(db, seed_data["pc1"], plot=6, free_time=0)
        auth_as(client, seed_data["player1"])

        # First call
        r1 = _find_time(client, seed_data["pc1"].id)
        assert r1.status_code == 200
        assert r1.json()["plot"] == 3
        assert r1.json()["free_time"] == 1

        # Second call
        r2 = _find_time(client, seed_data["pc1"].id)
        assert r2.status_code == 200
        assert r2.json()["plot"] == 0
        assert r2.json()["free_time"] == 2

        # Third call should fail — insufficient_plot
        r3 = _find_time(client, seed_data["pc1"].id)
        assert r3.status_code == 409
        assert r3.json()["error"]["code"] == "insufficient_plot"

    def test_gm_find_time_happy_path(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """GM successfully calls find-time for pc2."""
        _set_meters(db, seed_data["pc2"], plot=6, free_time=5)
        auth_as(client, seed_data["gm"])
        response = _find_time(client, seed_data["pc2"].id)
        assert response.status_code == 200
        body = response.json()
        assert body["plot"] == 3
        assert body["free_time"] == 6


# ---------------------------------------------------------------------------
# Event creation
# ---------------------------------------------------------------------------


class TestFindTimeEvent:
    """Verify the event record created by find-time."""

    def test_event_created_with_correct_shape(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        pc = seed_data["pc1"]
        player = seed_data["player1"]
        _set_meters(db, pc, plot=5, free_time=1)

        auth_as(client, player)
        response = _find_time(client, pc.id)
        assert response.status_code == 200

        # Fetch the most recent event of type player.find_time
        event: Event | None = (
            db.query(Event)
            .filter(Event.type == "player.find_time")
            .order_by(Event.created_at.desc())
            .first()
        )
        assert event is not None
        assert event.type == "player.find_time"
        assert event.actor_type == "player"
        assert event.actor_id == player.id
        assert event.visibility == "private"

        # Changes dict
        changes = event.changes
        assert f"character.{pc.id}.plot" in changes
        assert f"character.{pc.id}.free_time" in changes

        plot_change = changes[f"character.{pc.id}.plot"]
        assert plot_change["op"] == "meter.delta"
        assert plot_change["before"] == 5
        assert plot_change["after"] == 2

        ft_change = changes[f"character.{pc.id}.free_time"]
        assert ft_change["op"] == "meter.delta"
        assert ft_change["before"] == 1
        assert ft_change["after"] == 2

    def test_event_has_primary_target(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        pc = seed_data["pc1"]
        _set_meters(db, pc, plot=3, free_time=0)

        auth_as(client, seed_data["player1"])
        _find_time(client, pc.id)

        event: Event | None = (
            db.query(Event)
            .filter(Event.type == "player.find_time")
            .order_by(Event.created_at.desc())
            .first()
        )
        assert event is not None

        targets = (
            db.query(EventTarget)
            .filter(EventTarget.event_id == event.id)
            .all()
        )
        assert len(targets) == 1
        assert targets[0].target_type == "character"
        assert targets[0].target_id == pc.id
        assert targets[0].is_primary is True

    def test_event_actor_is_authenticated_user(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Even when GM calls find-time, the actor_id is the GM's user id."""
        pc = seed_data["pc2"]
        gm = seed_data["gm"]
        _set_meters(db, pc, plot=3, free_time=0)

        auth_as(client, gm)
        _find_time(client, pc.id)

        event: Event | None = (
            db.query(Event)
            .filter(Event.type == "player.find_time")
            .order_by(Event.created_at.desc())
            .first()
        )
        assert event is not None
        assert event.actor_id == gm.id
