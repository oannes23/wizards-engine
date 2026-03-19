"""Integration tests for Story 5.5.4 — GET /api/v1/gm/dashboard.

Covers:
- Unauthenticated → 401
- Non-GM player → 403
- GM with no data → all lists empty
- Pending proposals returned, sorted system-origin first then by ULID
- Approved/rejected proposals NOT included
- PC summaries only include detail_level="full", not deleted
- PC summaries handle nullable meters (return 0)
- Near-completion clocks: clock at segments-1 included
- Near-completion clocks: completed clock (progress >= segments) NOT included
- Near-completion clocks: clock far from completion NOT included
- Near-completion clocks: deleted clock NOT included

Note: the ``client`` fixture defined in this module registers the
``gm_dashboard`` router locally so that tests can run before the router is
wired into the central ``api/__init__.py``.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from tests.conftest import auth_as
from wizards_engine.api.routes.gm_dashboard import router as gm_dashboard_router
from wizards_engine.app import create_app
from wizards_engine.db import get_db
from wizards_engine.models.character import Character
from wizards_engine.models.clock import Clock
from wizards_engine.models.proposal import Proposal


# ---------------------------------------------------------------------------
# Local client fixture — registers gm_dashboard router until it is wired
# centrally in api/__init__.py.
# ---------------------------------------------------------------------------


@pytest.fixture
def client(db_engine) -> TestClient:
    """TestClient with the gm_dashboard router registered."""
    TestSessionLocal = sessionmaker(
        bind=db_engine, autocommit=False, autoflush=False
    )

    def _get_test_db():
        session: Session = TestSessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_db] = _get_test_db
    # Register the dashboard router if it hasn't been included yet.
    registered_paths = {r.path for r in app.routes}  # type: ignore[attr-defined]
    if "/api/v1/gm/dashboard" not in registered_paths:
        app.include_router(gm_dashboard_router, prefix="/api/v1")

    return TestClient(app, raise_server_exceptions=True)


# ===========================================================================
# Helpers
# ===========================================================================


def _get(client: TestClient):
    """GET /api/v1/gm/dashboard."""
    return client.get("/api/v1/gm/dashboard")


def _make_proposal(
    db: Session,
    *,
    character_id: str | None = None,
    action_type: str = "use_skill",
    origin: str = "player",
    status: str = "pending",
    narrative: str | None = "Test narrative",
) -> Proposal:
    """Create and flush a Proposal in the current test session."""
    p = Proposal(
        character_id=character_id,
        action_type=action_type,
        origin=origin,
        narrative=narrative,
        selections={},
        calculated_effect={},
        status=status,
    )
    db.add(p)
    db.flush()
    db.refresh(p)
    return p


def _make_clock(
    db: Session,
    *,
    name: str = "Test Clock",
    segments: int = 4,
    progress: int = 0,
    is_deleted: bool = False,
) -> Clock:
    """Create and flush a Clock in the current test session."""
    c = Clock(
        name=name,
        segments=segments,
        progress=progress,
        is_deleted=is_deleted,
    )
    db.add(c)
    db.flush()
    db.refresh(c)
    return c


def _make_full_character(
    db: Session,
    *,
    name: str = "Extra PC",
    stress: int | None = 0,
    free_time: int | None = 0,
    plot: int | None = 0,
    gnosis: int | None = 0,
    is_deleted: bool = False,
) -> Character:
    """Create and flush a full Character."""
    c = Character(
        name=name,
        detail_level="full",
        stress=stress,
        free_time=free_time,
        plot=plot,
        gnosis=gnosis,
        skills={},
        magic_stats={},
        last_session_time_now=0,
        is_deleted=is_deleted,
    )
    db.add(c)
    db.flush()
    db.refresh(c)
    return c


# ===========================================================================
# Auth
# ===========================================================================


class TestGmDashboardAuth:
    """Authentication and authorisation gates."""

    def test_unauthenticated_returns_401(self, client: TestClient) -> None:
        response = _get(client)
        assert response.status_code == 401

    def test_player_returns_403(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["player1"])
        response = _get(client)
        assert response.status_code == 403


# ===========================================================================
# Empty database
# ===========================================================================


class TestGmDashboardEmpty:
    """GM with an otherwise empty database gets all empty lists."""

    def test_empty_db_returns_empty_lists(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        # seed_data creates 3 PCs — soft-delete them so we get a clean slate
        for key in ("pc1", "pc2", "pc3"):
            seed_data[key].is_deleted = True
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        data = response.json()
        assert data["pending_proposals"] == []
        assert data["pc_summaries"] == []
        assert data["near_completion_clocks"] == []


# ===========================================================================
# Pending proposals
# ===========================================================================


class TestGmDashboardPendingProposals:
    """Pending proposals ordering and filtering."""

    def test_pending_proposals_returned(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        p = _make_proposal(db, character_id=seed_data["pc1"].id)
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        proposals = response.json()["pending_proposals"]
        assert len(proposals) == 1
        assert proposals[0]["id"] == p.id
        assert proposals[0]["status"] == "pending"

    def test_approved_proposal_excluded(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        _make_proposal(db, character_id=seed_data["pc1"].id, status="approved")
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        assert response.json()["pending_proposals"] == []

    def test_rejected_proposal_excluded(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        _make_proposal(db, character_id=seed_data["pc1"].id, status="rejected")
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        assert response.json()["pending_proposals"] == []

    def test_system_proposals_ordered_before_player(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        # Create player proposal first (gets a lower ULID), then system proposal.
        p_player = _make_proposal(
            db,
            character_id=seed_data["pc1"].id,
            origin="player",
            action_type="use_skill",
        )
        p_system = _make_proposal(
            db,
            character_id=None,
            origin="system",
            action_type="resolve_clock",
            narrative=None,
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        proposals = response.json()["pending_proposals"]
        assert len(proposals) == 2
        # System proposal must come first despite being created after player proposal.
        assert proposals[0]["id"] == p_system.id
        assert proposals[0]["origin"] == "system"
        assert proposals[1]["id"] == p_player.id
        assert proposals[1]["origin"] == "player"

    def test_proposal_response_shape(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        p = _make_proposal(
            db,
            character_id=seed_data["pc1"].id,
            action_type="use_skill",
            narrative="I try to pick the lock.",
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        proposal_data = response.json()["pending_proposals"][0]
        assert proposal_data["id"] == p.id
        assert proposal_data["character_id"] == seed_data["pc1"].id
        assert proposal_data["action_type"] == "use_skill"
        assert proposal_data["origin"] == "player"
        assert proposal_data["narrative"] == "I try to pick the lock."
        assert proposal_data["status"] == "pending"
        assert "created_at" in proposal_data


# ===========================================================================
# PC summaries
# ===========================================================================


class TestGmDashboardPCSummaries:
    """PC summary filtering and content."""

    def test_full_characters_included(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        pc_ids = {s["id"] for s in response.json()["pc_summaries"]}
        # seed_data creates pc1, pc2, pc3 as full characters
        assert seed_data["pc1"].id in pc_ids
        assert seed_data["pc2"].id in pc_ids
        assert seed_data["pc3"].id in pc_ids

    def test_simplified_characters_excluded(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        pc_ids = {s["id"] for s in response.json()["pc_summaries"]}
        # npc1 and npc2 are simplified — must not appear
        assert seed_data["npc1"].id not in pc_ids
        assert seed_data["npc2"].id not in pc_ids

    def test_deleted_full_character_excluded(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        deleted_pc = _make_full_character(db, name="Deleted PC", is_deleted=True)
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        pc_ids = {s["id"] for s in response.json()["pc_summaries"]}
        assert deleted_pc.id not in pc_ids

    def test_nullable_meters_return_zero(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        # Create a full character with all meter columns explicitly None.
        null_meter_pc = Character(
            name="Null Meter PC",
            detail_level="full",
            stress=None,
            free_time=None,
            plot=None,
            gnosis=None,
            skills={},
            magic_stats={},
            last_session_time_now=0,
        )
        db.add(null_meter_pc)
        db.commit()
        db.refresh(null_meter_pc)

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        summaries = {s["id"]: s for s in response.json()["pc_summaries"]}
        assert null_meter_pc.id in summaries
        s = summaries[null_meter_pc.id]
        assert s["stress"] == 0
        assert s["free_time"] == 0
        assert s["plot"] == 0
        assert s["gnosis"] == 0

    def test_pc_summaries_sorted_by_name(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        # Soft-delete seed PCs and create two with known sort order.
        for key in ("pc1", "pc2", "pc3"):
            seed_data[key].is_deleted = True
        alpha = _make_full_character(db, name="Alpha")
        beta = _make_full_character(db, name="Beta")
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        names = [s["name"] for s in response.json()["pc_summaries"]]
        assert names == ["Alpha", "Beta"]
        _ = alpha, beta  # referenced to avoid unused-variable warnings


# ===========================================================================
# Near-completion clocks
# ===========================================================================


class TestGmDashboardNearCompletionClocks:
    """Near-completion clock filtering."""

    def test_clock_at_segments_minus_one_included(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        c = _make_clock(db, segments=4, progress=3)
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        clock_ids = {clk["id"] for clk in response.json()["near_completion_clocks"]}
        assert c.id in clock_ids

    def test_completed_clock_excluded(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        # progress == segments → completed
        c = _make_clock(db, segments=4, progress=4)
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        clock_ids = {clk["id"] for clk in response.json()["near_completion_clocks"]}
        assert c.id not in clock_ids

    def test_clock_far_from_completion_excluded(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        c = _make_clock(db, segments=6, progress=2)
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        clock_ids = {clk["id"] for clk in response.json()["near_completion_clocks"]}
        assert c.id not in clock_ids

    def test_deleted_clock_excluded(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        c = _make_clock(db, segments=4, progress=3, is_deleted=True)
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        clock_ids = {clk["id"] for clk in response.json()["near_completion_clocks"]}
        assert c.id not in clock_ids

    def test_near_completion_clock_response_shape(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        c = Clock(
            name="Ritual Completion",
            segments=5,
            progress=4,
            associated_type="group",
            associated_id=seed_data["group"].id,
        )
        db.add(c)
        db.commit()
        db.refresh(c)

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        clocks = {clk["id"]: clk for clk in response.json()["near_completion_clocks"]}
        assert c.id in clocks
        clk_data = clocks[c.id]
        assert clk_data["name"] == "Ritual Completion"
        assert clk_data["progress"] == 4
        assert clk_data["segments"] == 5
        assert clk_data["associated_type"] == "group"
        assert clk_data["associated_id"] == seed_data["group"].id
