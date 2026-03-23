"""Integration tests for sort_by / sort_dir keyset pagination on GET /api/v1/events.

Verifies that the events list endpoint correctly:
- Sorts by ``created_at``, ``type``, and ``actor_type`` in both directions.
- Falls back to default id-DESC order when ``sort_by`` is omitted.
- Ignores an unknown ``sort_by`` value (falls back to id-DESC).
- Ignores an invalid ``sort_dir`` (falls back to desc).
- Paginates correctly across pages when a sort column is specified.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import auth_as
from wizards_engine.models.event import Event


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _event(
    db: Session,
    *,
    type: str = "test.event",
    actor_type: str = "gm",
    visibility: str = "global",
) -> Event:
    """Create, flush, and refresh a minimal Event row."""
    ev = Event(
        type=type,
        actor_type=actor_type,
        changes={},
        visibility=visibility,
    )
    db.add(ev)
    db.flush()
    db.refresh(ev)
    return ev


# ---------------------------------------------------------------------------
# Default ordering (no sort_by)
# ---------------------------------------------------------------------------


class TestDefaultOrder:
    """Without sort_by the endpoint orders by id DESC (newest-first)."""

    def test_newest_first_by_default(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        _event(db, type="event.first")
        _event(db, type="event.second")
        _event(db, type="event.third")
        db.commit()

        auth_as(client, seed_data["gm"])
        resp = client.get("/api/v1/events")
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.json()["items"]]
        assert ids == sorted(ids, reverse=True)


# ---------------------------------------------------------------------------
# sort_by=created_at
# ---------------------------------------------------------------------------


class TestSortByCreatedAt:
    """Sorting by created_at in both directions."""

    def test_sort_created_at_desc(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Newest events appear first (desc)."""
        _event(db, type="a")
        time.sleep(0.01)
        _event(db, type="b")
        time.sleep(0.01)
        _event(db, type="c")
        db.commit()

        auth_as(client, seed_data["gm"])
        resp = client.get("/api/v1/events?sort_by=created_at&sort_dir=desc")
        assert resp.status_code == 200
        items = resp.json()["items"]
        timestamps = [item["created_at"] for item in items]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_sort_created_at_asc(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Oldest events appear first (asc)."""
        _event(db, type="a")
        time.sleep(0.01)
        _event(db, type="b")
        time.sleep(0.01)
        _event(db, type="c")
        db.commit()

        auth_as(client, seed_data["gm"])
        resp = client.get("/api/v1/events?sort_by=created_at&sort_dir=asc")
        assert resp.status_code == 200
        items = resp.json()["items"]
        timestamps = [item["created_at"] for item in items]
        assert timestamps == sorted(timestamps)


# ---------------------------------------------------------------------------
# sort_by=type
# ---------------------------------------------------------------------------


class TestSortByType:
    """Sorting by event type string in both directions."""

    def test_sort_type_asc(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        _event(db, type="zzz.event")
        _event(db, type="aaa.event")
        _event(db, type="mmm.event")
        db.commit()

        auth_as(client, seed_data["gm"])
        resp = client.get("/api/v1/events?sort_by=type&sort_dir=asc")
        assert resp.status_code == 200
        types = [item["type"] for item in resp.json()["items"]]
        assert types == sorted(types)

    def test_sort_type_desc(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        _event(db, type="zzz.event")
        _event(db, type="aaa.event")
        _event(db, type="mmm.event")
        db.commit()

        auth_as(client, seed_data["gm"])
        resp = client.get("/api/v1/events?sort_by=type&sort_dir=desc")
        assert resp.status_code == 200
        types = [item["type"] for item in resp.json()["items"]]
        assert types == sorted(types, reverse=True)


# ---------------------------------------------------------------------------
# sort_by=actor_type
# ---------------------------------------------------------------------------


class TestSortByActorType:
    """Sorting by actor_type string in both directions."""

    def test_sort_actor_type_asc(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        _event(db, actor_type="system")
        _event(db, actor_type="gm")
        _event(db, actor_type="player")
        db.commit()

        auth_as(client, seed_data["gm"])
        resp = client.get("/api/v1/events?sort_by=actor_type&sort_dir=asc")
        assert resp.status_code == 200
        actor_types = [item["actor_type"] for item in resp.json()["items"]]
        assert actor_types == sorted(actor_types)

    def test_sort_actor_type_desc(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        _event(db, actor_type="system")
        _event(db, actor_type="gm")
        _event(db, actor_type="player")
        db.commit()

        auth_as(client, seed_data["gm"])
        resp = client.get("/api/v1/events?sort_by=actor_type&sort_dir=desc")
        assert resp.status_code == 200
        actor_types = [item["actor_type"] for item in resp.json()["items"]]
        assert actor_types == sorted(actor_types, reverse=True)


# ---------------------------------------------------------------------------
# Unknown / invalid parameters
# ---------------------------------------------------------------------------


class TestInvalidSortParams:
    """Unknown sort_by and invalid sort_dir values are handled gracefully."""

    def test_unknown_sort_by_falls_back_to_id_desc(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """An unrecognised sort_by value silently falls back to default order."""
        _event(db, type="a")
        _event(db, type="b")
        db.commit()

        auth_as(client, seed_data["gm"])
        resp = client.get("/api/v1/events?sort_by=nonexistent_column")
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.json()["items"]]
        assert ids == sorted(ids, reverse=True)

    def test_invalid_sort_dir_falls_back_to_desc(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """An invalid sort_dir value falls back to desc."""
        _event(db, type="zzz")
        _event(db, type="aaa")
        db.commit()

        auth_as(client, seed_data["gm"])
        # sort_dir=BADVAL should be treated as desc.
        resp = client.get("/api/v1/events?sort_by=type&sort_dir=BADVAL")
        assert resp.status_code == 200
        types = [item["type"] for item in resp.json()["items"]]
        assert types == sorted(types, reverse=True)


# ---------------------------------------------------------------------------
# Pagination with sort_by
# ---------------------------------------------------------------------------


class TestSortPagination:
    """Keyset cursor pagination works correctly when sort_by is active."""

    def test_paginate_by_type_asc_no_overlap(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Two pages together contain all events, no duplicates."""
        for letter in ["aaa", "bbb", "ccc", "ddd", "eee"]:
            _event(db, type=f"{letter}.event")
        db.commit()

        auth_as(client, seed_data["gm"])

        page1 = client.get(
            "/api/v1/events?sort_by=type&sort_dir=asc&limit=3"
        ).json()
        assert len(page1["items"]) == 3
        assert page1["has_more"] is True
        cursor = page1["next_cursor"]

        page2 = client.get(
            f"/api/v1/events?sort_by=type&sort_dir=asc&limit=3&after={cursor}"
        ).json()
        assert len(page2["items"]) == 2
        assert page2["has_more"] is False

        # No ID overlap across pages.
        ids1 = {item["id"] for item in page1["items"]}
        ids2 = {item["id"] for item in page2["items"]}
        assert not ids1 & ids2

        # Together they cover all 5 events.
        all_ids = ids1 | ids2
        assert len(all_ids) == 5

    def test_paginate_by_type_asc_correct_order(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Items across pages are in correct ascending type order."""
        for letter in ["aaa", "bbb", "ccc", "ddd", "eee"]:
            _event(db, type=f"{letter}.event")
        db.commit()

        auth_as(client, seed_data["gm"])

        page1 = client.get(
            "/api/v1/events?sort_by=type&sort_dir=asc&limit=3"
        ).json()
        cursor = page1["next_cursor"]
        page2 = client.get(
            f"/api/v1/events?sort_by=type&sort_dir=asc&limit=3&after={cursor}"
        ).json()

        all_types = [item["type"] for item in page1["items"]] + [
            item["type"] for item in page2["items"]
        ]
        assert all_types == sorted(all_types)

    def test_paginate_by_created_at_desc_no_overlap(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        """Newest-first pagination by created_at spans pages without overlap."""
        for i in range(5):
            _event(db, type=f"event.{i}")
            db.flush()
        db.commit()

        auth_as(client, seed_data["gm"])

        page1 = client.get(
            "/api/v1/events?sort_by=created_at&sort_dir=desc&limit=3"
        ).json()
        assert len(page1["items"]) == 3
        assert page1["has_more"] is True
        cursor = page1["next_cursor"]

        page2 = client.get(
            f"/api/v1/events?sort_by=created_at&sort_dir=desc&limit=3&after={cursor}"
        ).json()
        assert len(page2["items"]) == 2
        assert page2["has_more"] is False

        ids1 = {item["id"] for item in page1["items"]}
        ids2 = {item["id"] for item in page2["items"]}
        assert not ids1 & ids2
        assert len(ids1 | ids2) == 5
