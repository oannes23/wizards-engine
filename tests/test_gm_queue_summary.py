"""Integration tests for Story 8.2.1 — GET /api/v1/gm/queue-summary.

Covers:
- Unauthenticated → 401
- Non-GM player → 403
- GM with no data → empty pc_cards and group_cards
- PC cards include correct meter values and maximums
- Stress max reduced by trauma bond count
- Low-charge traits: only active core/role traits with charge <= 2
- Low-charge bonds: only active non-trauma pc_bonds with charges <= 2
- Trauma bonds excluded from low_charge_bonds even at low charge
- Inactive slots excluded from low-charge lists
- Recent events: at most 3, newest first
- Groups sorted by most-recent-event desc; groups with no events at end
- Group cards include active (non-completed) clocks only
- Completed clocks excluded from group active_clocks
- Deleted clocks excluded from group active_clocks
- Response shape validation for pc_cards and group_cards
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from tests.conftest import auth_as
from wizards_engine.app import create_app
from wizards_engine.db import get_db
from wizards_engine.models.character import Character
from wizards_engine.models.clock import Clock
from wizards_engine.models.event import Event, EventTarget
from wizards_engine.models.group import Group
from wizards_engine.models.slot import Slot


# ---------------------------------------------------------------------------
# Local client fixture (the queue-summary endpoint is wired centrally)
# ---------------------------------------------------------------------------


@pytest.fixture
def client(db_engine) -> TestClient:
    """TestClient with the full app (gm_dashboard router already included)."""
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
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get(client: TestClient):
    """GET /api/v1/gm/queue-summary."""
    return client.get("/api/v1/gm/queue-summary")


def _make_full_character(
    db: Session,
    *,
    name: str = "Extra PC",
    stress: int = 0,
    free_time: int = 0,
    plot: int = 0,
    gnosis: int = 0,
    is_deleted: bool = False,
) -> Character:
    """Create and flush a full (PC-level) Character."""
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


def _make_group(
    db: Session,
    *,
    name: str = "Test Group",
    tier: int = 1,
    is_deleted: bool = False,
) -> Group:
    """Create and flush a Group."""
    g = Group(name=name, tier=tier, is_deleted=is_deleted)
    db.add(g)
    db.flush()
    db.refresh(g)
    return g


def _make_slot(
    db: Session,
    *,
    slot_type: str,
    owner_id: str,
    owner_type: str = "character",
    name: str = "Test Slot",
    is_active: bool = True,
    charge: int | None = None,
    charges: int | None = None,
    is_trauma: bool | None = None,
) -> Slot:
    """Create and flush a Slot."""
    s = Slot(
        slot_type=slot_type,
        owner_type=owner_type,
        owner_id=owner_id,
        name=name,
        is_active=is_active,
        charge=charge,
        charges=charges,
        is_trauma=is_trauma,
    )
    db.add(s)
    db.flush()
    db.refresh(s)
    return s


def _make_event_for_target(
    db: Session,
    target_type: str,
    target_id: str,
    event_type: str = "gm_direct_action",
) -> Event:
    """Create an Event with a target entry and flush."""
    evt = Event(
        type=event_type,
        actor_type="gm",
        changes={},
        visibility="gm",
    )
    db.add(evt)
    db.flush()

    tgt = EventTarget(
        event_id=evt.id,
        target_type=target_type,
        target_id=target_id,
        is_primary=True,
    )
    db.add(tgt)
    db.flush()
    db.refresh(evt)
    return evt


def _make_clock(
    db: Session,
    group_id: str,
    *,
    name: str = "Test Clock",
    segments: int = 4,
    progress: int = 0,
    is_deleted: bool = False,
) -> Clock:
    """Create and flush a Clock associated with a group."""
    c = Clock(
        name=name,
        segments=segments,
        progress=progress,
        associated_type="group",
        associated_id=group_id,
        is_deleted=is_deleted,
    )
    db.add(c)
    db.flush()
    db.refresh(c)
    return c


# ===========================================================================
# Auth
# ===========================================================================


class TestQueueSummaryAuth:
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


class TestQueueSummaryEmpty:
    """GM with no relevant data gets empty lists."""

    def test_empty_returns_empty_lists(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        # Soft-delete seed PCs and the seed group so we get a clean slate.
        for key in ("pc1", "pc2", "pc3"):
            seed_data[key].is_deleted = True
        seed_data["group"].is_deleted = True
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        data = response.json()
        assert data["pc_cards"] == []
        assert data["group_cards"] == []


# ===========================================================================
# PC cards — meter values and maximums
# ===========================================================================


class TestQueueSummaryPCMeters:
    """PC cards include correct meter values and computed maximums."""

    def test_pc_card_meter_values(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        # Soft-delete seed PCs; create one with known meter values.
        for key in ("pc1", "pc2", "pc3"):
            seed_data[key].is_deleted = True
        pc = _make_full_character(
            db, name="Test PC", stress=3, free_time=5, plot=2, gnosis=10
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        cards = {c["id"]: c for c in response.json()["pc_cards"]}
        assert pc.id in cards
        card = cards[pc.id]
        assert card["stress"] == 3
        assert card["free_time"] == 5
        assert card["plot"] == 2
        assert card["gnosis"] == 10

    def test_pc_card_meter_maximums(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        # A character with no trauma bonds → stress_max = 9.
        for key in ("pc1", "pc2", "pc3"):
            seed_data[key].is_deleted = True
        pc = _make_full_character(db, name="Test PC")
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        card = next(c for c in response.json()["pc_cards"] if c["id"] == pc.id)
        assert card["stress_max"] == 9
        assert card["free_time_max"] == 20
        assert card["plot_max"] == 5
        assert card["gnosis_max"] == 23

    def test_trauma_bond_reduces_stress_max(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        # One trauma bond → stress_max = 8.
        for key in ("pc1", "pc2", "pc3"):
            seed_data[key].is_deleted = True
        pc = _make_full_character(db, name="Traumatised PC")
        _make_slot(
            db,
            slot_type="pc_bond",
            owner_id=pc.id,
            name="Trauma Bond",
            is_trauma=True,
            charges=3,
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        card = next(c for c in response.json()["pc_cards"] if c["id"] == pc.id)
        assert card["stress_max"] == 8

    def test_two_trauma_bonds_reduce_stress_max_by_two(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        for key in ("pc1", "pc2", "pc3"):
            seed_data[key].is_deleted = True
        pc = _make_full_character(db, name="Double Trauma PC")
        _make_slot(db, slot_type="pc_bond", owner_id=pc.id, name="Trauma 1", is_trauma=True, charges=1)
        _make_slot(db, slot_type="pc_bond", owner_id=pc.id, name="Trauma 2", is_trauma=True, charges=2)
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        card = next(c for c in response.json()["pc_cards"] if c["id"] == pc.id)
        assert card["stress_max"] == 7

    def test_simplified_characters_excluded(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        pc_ids = {c["id"] for c in response.json()["pc_cards"]}
        assert seed_data["npc1"].id not in pc_ids
        assert seed_data["npc2"].id not in pc_ids

    def test_deleted_pc_excluded(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        deleted = _make_full_character(db, name="Ghost PC", is_deleted=True)
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        pc_ids = {c["id"] for c in response.json()["pc_cards"]}
        assert deleted.id not in pc_ids

    def test_pc_cards_sorted_by_name(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        for key in ("pc1", "pc2", "pc3"):
            seed_data[key].is_deleted = True
        _make_full_character(db, name="Zebra")
        _make_full_character(db, name="Alpha")
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        names = [c["name"] for c in response.json()["pc_cards"]]
        assert names == ["Alpha", "Zebra"]


# ===========================================================================
# PC cards — low-charge traits
# ===========================================================================


class TestQueueSummaryLowChargeTraits:
    """Low-charge trait indicators on PC cards."""

    def test_low_charge_core_trait_included(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        for key in ("pc1", "pc2", "pc3"):
            seed_data[key].is_deleted = True
        pc = _make_full_character(db, name="Test PC")
        slot = _make_slot(
            db, slot_type="core_trait", owner_id=pc.id,
            name="Iron Will", charge=1
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        card = next(c for c in response.json()["pc_cards"] if c["id"] == pc.id)
        trait_ids = {t["id"] for t in card["low_charge_traits"]}
        assert slot.id in trait_ids

    def test_low_charge_role_trait_included(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        for key in ("pc1", "pc2", "pc3"):
            seed_data[key].is_deleted = True
        pc = _make_full_character(db, name="Test PC")
        slot = _make_slot(
            db, slot_type="role_trait", owner_id=pc.id,
            name="Street Wisdom", charge=2
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        card = next(c for c in response.json()["pc_cards"] if c["id"] == pc.id)
        trait_ids = {t["id"] for t in card["low_charge_traits"]}
        assert slot.id in trait_ids

    def test_full_charge_trait_excluded(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        for key in ("pc1", "pc2", "pc3"):
            seed_data[key].is_deleted = True
        pc = _make_full_character(db, name="Test PC")
        _make_slot(
            db, slot_type="core_trait", owner_id=pc.id,
            name="Strong Trait", charge=3
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        card = next(c for c in response.json()["pc_cards"] if c["id"] == pc.id)
        assert card["low_charge_traits"] == []

    def test_inactive_trait_excluded(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        for key in ("pc1", "pc2", "pc3"):
            seed_data[key].is_deleted = True
        pc = _make_full_character(db, name="Test PC")
        _make_slot(
            db, slot_type="core_trait", owner_id=pc.id,
            name="Inactive Trait", charge=0, is_active=False
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        card = next(c for c in response.json()["pc_cards"] if c["id"] == pc.id)
        assert card["low_charge_traits"] == []

    def test_low_charge_trait_response_shape(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        for key in ("pc1", "pc2", "pc3"):
            seed_data[key].is_deleted = True
        pc = _make_full_character(db, name="Test PC")
        slot = _make_slot(
            db, slot_type="core_trait", owner_id=pc.id,
            name="Iron Will", charge=1
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        card = next(c for c in response.json()["pc_cards"] if c["id"] == pc.id)
        trait = next(t for t in card["low_charge_traits"] if t["id"] == slot.id)
        assert trait["name"] == "Iron Will"
        assert trait["slot_type"] == "core_trait"
        assert trait["charge"] == 1


# ===========================================================================
# PC cards — low-charge bonds
# ===========================================================================


class TestQueueSummaryLowChargeBonds:
    """Low-charge bond indicators on PC cards."""

    def test_low_charge_pc_bond_included(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        for key in ("pc1", "pc2", "pc3"):
            seed_data[key].is_deleted = True
        pc = _make_full_character(db, name="Test PC")
        slot = _make_slot(
            db, slot_type="pc_bond", owner_id=pc.id,
            name="Old Friend", charges=1, is_trauma=False
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        card = next(c for c in response.json()["pc_cards"] if c["id"] == pc.id)
        bond_ids = {b["id"] for b in card["low_charge_bonds"]}
        assert slot.id in bond_ids

    def test_full_charge_bond_excluded(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        for key in ("pc1", "pc2", "pc3"):
            seed_data[key].is_deleted = True
        pc = _make_full_character(db, name="Test PC")
        _make_slot(
            db, slot_type="pc_bond", owner_id=pc.id,
            name="Strong Bond", charges=3, is_trauma=False
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        card = next(c for c in response.json()["pc_cards"] if c["id"] == pc.id)
        assert card["low_charge_bonds"] == []

    def test_trauma_bond_excluded_from_low_charge_bonds(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        for key in ("pc1", "pc2", "pc3"):
            seed_data[key].is_deleted = True
        pc = _make_full_character(db, name="Test PC")
        # Trauma bond with low charges — must NOT appear in low_charge_bonds.
        _make_slot(
            db, slot_type="pc_bond", owner_id=pc.id,
            name="Trauma Bond", charges=0, is_trauma=True
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        card = next(c for c in response.json()["pc_cards"] if c["id"] == pc.id)
        assert card["low_charge_bonds"] == []

    def test_inactive_bond_excluded(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        for key in ("pc1", "pc2", "pc3"):
            seed_data[key].is_deleted = True
        pc = _make_full_character(db, name="Test PC")
        _make_slot(
            db, slot_type="pc_bond", owner_id=pc.id,
            name="Inactive Bond", charges=1, is_trauma=False, is_active=False
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        card = next(c for c in response.json()["pc_cards"] if c["id"] == pc.id)
        assert card["low_charge_bonds"] == []

    def test_low_charge_bond_response_shape(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        for key in ("pc1", "pc2", "pc3"):
            seed_data[key].is_deleted = True
        pc = _make_full_character(db, name="Test PC")
        slot = _make_slot(
            db, slot_type="pc_bond", owner_id=pc.id,
            name="Old Friend", charges=2, is_trauma=False
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        card = next(c for c in response.json()["pc_cards"] if c["id"] == pc.id)
        bond = next(b for b in card["low_charge_bonds"] if b["id"] == slot.id)
        assert bond["name"] == "Old Friend"
        assert bond["slot_type"] == "pc_bond"
        assert bond["charge"] == 2


# ===========================================================================
# PC cards — recent events
# ===========================================================================


class TestQueueSummaryPCRecentEvents:
    """Recent events per PC card."""

    def test_recent_events_returned_newest_first(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        for key in ("pc1", "pc2", "pc3"):
            seed_data[key].is_deleted = True
        pc = _make_full_character(db, name="Test PC")
        e1 = _make_event_for_target(db, "character", pc.id, "use_skill")
        db.commit()
        # Brief delay to ensure ordering via ULID / commit order.
        e2 = _make_event_for_target(db, "character", pc.id, "gm_direct_action")
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        card = next(c for c in response.json()["pc_cards"] if c["id"] == pc.id)
        event_ids = [e["id"] for e in card["recent_events"]]
        # Newest first: e2 has higher ULID (created later).
        assert event_ids[0] == e2.id
        assert event_ids[1] == e1.id

    def test_recent_events_capped_at_3(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        for key in ("pc1", "pc2", "pc3"):
            seed_data[key].is_deleted = True
        pc = _make_full_character(db, name="Test PC")
        for _ in range(5):
            _make_event_for_target(db, "character", pc.id)
            db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        card = next(c for c in response.json()["pc_cards"] if c["id"] == pc.id)
        assert len(card["recent_events"]) == 3

    def test_no_events_returns_empty_list(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        for key in ("pc1", "pc2", "pc3"):
            seed_data[key].is_deleted = True
        pc = _make_full_character(db, name="Test PC")
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        card = next(c for c in response.json()["pc_cards"] if c["id"] == pc.id)
        assert card["recent_events"] == []

    def test_recent_event_response_shape(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        for key in ("pc1", "pc2", "pc3"):
            seed_data[key].is_deleted = True
        pc = _make_full_character(db, name="Test PC")
        evt = _make_event_for_target(db, "character", pc.id, "use_skill")
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        card = next(c for c in response.json()["pc_cards"] if c["id"] == pc.id)
        assert len(card["recent_events"]) == 1
        e = card["recent_events"][0]
        assert e["id"] == evt.id
        assert e["type"] == "use_skill"
        assert "created_at" in e

    def test_events_for_other_characters_not_included(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        for key in ("pc1", "pc2", "pc3"):
            seed_data[key].is_deleted = True
        pc_a = _make_full_character(db, name="PC A")
        pc_b = _make_full_character(db, name="PC B")
        evt_a = _make_event_for_target(db, "character", pc_a.id)
        db.commit()
        evt_b = _make_event_for_target(db, "character", pc_b.id)
        db.commit()
        _ = evt_a, evt_b

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        cards = {c["id"]: c for c in response.json()["pc_cards"]}
        # Each PC only sees its own event.
        assert len(cards[pc_a.id]["recent_events"]) == 1
        assert cards[pc_a.id]["recent_events"][0]["id"] == evt_a.id
        assert len(cards[pc_b.id]["recent_events"]) == 1
        assert cards[pc_b.id]["recent_events"][0]["id"] == evt_b.id


# ===========================================================================
# Group cards
# ===========================================================================


class TestQueueSummaryGroupCards:
    """Group cards: clocks, events, and sorting."""

    def test_group_cards_returned(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        group_ids = {g["id"] for g in response.json()["group_cards"]}
        assert seed_data["group"].id in group_ids

    def test_deleted_group_excluded(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        deleted = _make_group(db, name="Deleted Group", is_deleted=True)
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        group_ids = {g["id"] for g in response.json()["group_cards"]}
        assert deleted.id not in group_ids

    def test_group_card_response_shape(
        self, client: TestClient, seed_data: dict
    ) -> None:
        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        group_card = next(
            g for g in response.json()["group_cards"]
            if g["id"] == seed_data["group"].id
        )
        assert group_card["name"] == "The Syndicate"
        assert group_card["tier"] == 2
        assert "active_clocks" in group_card
        assert "recent_events" in group_card
        assert "most_recent_event_at" in group_card

    def test_active_clock_included(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        group = seed_data["group"]
        clock = _make_clock(db, group.id, name="Active Clock", segments=4, progress=2)
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        group_card = next(
            g for g in response.json()["group_cards"] if g["id"] == group.id
        )
        clock_ids = {c["id"] for c in group_card["active_clocks"]}
        assert clock.id in clock_ids

    def test_completed_clock_excluded(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        group = seed_data["group"]
        # progress == segments → completed
        completed = _make_clock(db, group.id, name="Completed", segments=4, progress=4)
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        group_card = next(
            g for g in response.json()["group_cards"] if g["id"] == group.id
        )
        clock_ids = {c["id"] for c in group_card["active_clocks"]}
        assert completed.id not in clock_ids

    def test_deleted_clock_excluded(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        group = seed_data["group"]
        deleted_clk = _make_clock(
            db, group.id, name="Deleted Clock", segments=4, progress=1, is_deleted=True
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        group_card = next(
            g for g in response.json()["group_cards"] if g["id"] == group.id
        )
        clock_ids = {c["id"] for c in group_card["active_clocks"]}
        assert deleted_clk.id not in clock_ids

    def test_active_clock_response_shape(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        group = seed_data["group"]
        clock = _make_clock(
            db, group.id, name="Ritual Clock", segments=6, progress=3
        )
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        group_card = next(
            g for g in response.json()["group_cards"] if g["id"] == group.id
        )
        clk = next(c for c in group_card["active_clocks"] if c["id"] == clock.id)
        assert clk["name"] == "Ritual Clock"
        assert clk["progress"] == 3
        assert clk["segments"] == 6

    def test_group_recent_events_capped_at_3(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        group = seed_data["group"]
        for _ in range(5):
            _make_event_for_target(db, "group", group.id)
            db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        group_card = next(
            g for g in response.json()["group_cards"] if g["id"] == group.id
        )
        assert len(group_card["recent_events"]) == 3

    def test_group_recent_events_newest_first(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        group = seed_data["group"]
        e1 = _make_event_for_target(db, "group", group.id, "use_skill")
        db.commit()
        e2 = _make_event_for_target(db, "group", group.id, "gm_direct_action")
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        group_card = next(
            g for g in response.json()["group_cards"] if g["id"] == group.id
        )
        event_ids = [e["id"] for e in group_card["recent_events"]]
        assert event_ids[0] == e2.id
        assert event_ids[1] == e1.id

    def test_group_no_events_most_recent_event_at_is_null(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        seed_data["group"].is_deleted = True
        group = _make_group(db, name="Quiet Group")
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        group_card = next(
            g for g in response.json()["group_cards"] if g["id"] == group.id
        )
        assert group_card["most_recent_event_at"] is None
        assert group_card["recent_events"] == []


# ===========================================================================
# Group sorting
# ===========================================================================


class TestQueueSummaryGroupSorting:
    """Groups are sorted by most-recent-event descending; no-event groups last."""

    def test_groups_with_events_before_groups_without(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        seed_data["group"].is_deleted = True
        group_active = _make_group(db, name="Active Group")
        group_quiet = _make_group(db, name="Quiet Group")
        _make_event_for_target(db, "group", group_active.id)
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        group_ids = [g["id"] for g in response.json()["group_cards"]]
        active_idx = group_ids.index(group_active.id)
        quiet_idx = group_ids.index(group_quiet.id)
        assert active_idx < quiet_idx

    def test_more_recent_group_before_less_recent(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        seed_data["group"].is_deleted = True
        group_old = _make_group(db, name="Old Activity Group")
        group_new = _make_group(db, name="New Activity Group")

        _make_event_for_target(db, "group", group_old.id)
        db.commit()
        # Small sleep so the second event gets a later created_at.
        time.sleep(0.01)
        _make_event_for_target(db, "group", group_new.id)
        db.commit()

        auth_as(client, seed_data["gm"])
        response = _get(client)

        assert response.status_code == 200
        group_ids = [g["id"] for g in response.json()["group_cards"]]
        new_idx = group_ids.index(group_new.id)
        old_idx = group_ids.index(group_old.id)
        assert new_idx < old_idx
