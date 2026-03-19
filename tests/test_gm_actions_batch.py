"""Integration tests for Story 5.5.5 — POST /api/v1/gm/actions/batch.

Covers:
- Auth: unauthenticated → 401, non-GM → 403
- Input validation: empty array → 422 with batch_empty, >50 items → 422 with batch_too_large
- Single valid action → 200, returns 1 event
- Multiple valid actions → 200, returns N events in order
- Atomicity: valid + invalid action → 422, DB unchanged (no events created, no state changes)
- Response event shape (type, changes, targets, etc.)
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from wizards_engine.api import router as api_router
from wizards_engine.api.auth import COOKIE_NAME
from wizards_engine.api.routes.gm_actions_batch import router as batch_router
from wizards_engine.db import get_db
from wizards_engine.models.base import Base
from wizards_engine.models.event import Event
from wizards_engine.models.user import User

from tests.fixtures import seed_data as _seed_data_fn


# ===========================================================================
# Fixtures — local client that includes the batch router
# ===========================================================================


@pytest.fixture
def db_engine_batch():
    """In-memory SQLite engine with all tables created for batch tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    Base.metadata.create_all(engine)

    yield engine

    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db(db_engine_batch) -> Session:
    """Open SQLAlchemy session bound to the isolated test engine."""
    TestSessionLocal = sessionmaker(
        bind=db_engine_batch, autocommit=False, autoflush=False
    )
    session: Session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_engine_batch) -> TestClient:
    """TestClient backed by the isolated test database, with the batch router registered."""
    TestSessionLocal = sessionmaker(
        bind=db_engine_batch, autocommit=False, autoflush=False
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

    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import JSONResponse

    app = FastAPI(title="Wizards Engine Test")

    @app.exception_handler(HTTPException)
    async def _http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    app.include_router(api_router, prefix="/api/v1")
    app.include_router(batch_router, prefix="/api/v1")
    app.dependency_overrides[get_db] = _get_test_db

    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture
def seed_data(db) -> dict:
    """Populate the test database with canonical seed data."""
    return _seed_data_fn(db)


def _auth_as(client: TestClient, user: User) -> None:
    """Set the auth cookie on the client."""
    client.cookies.set(COOKIE_NAME, user.login_code)


def _batch(client: TestClient, actions: list[dict]) -> "Response":  # type: ignore[name-defined]
    """POST to /api/v1/gm/actions/batch."""
    return client.post("/api/v1/gm/actions/batch", json={"actions": actions})


def _modify_character_action(character_id: str, changes: dict, visibility: str = "bonded") -> dict:
    """Build a modify_character action dict."""
    return {
        "action_type": "modify_character",
        "target_id": character_id,
        "changes": changes,
        "visibility": visibility,
    }


# ===========================================================================
# Auth
# ===========================================================================


class TestBatchGmActionsAuth:
    """Authentication and authorisation gates."""

    def test_unauthenticated_returns_401(self, client: TestClient) -> None:
        response = _batch(client, [])
        assert response.status_code == 401

    def test_player_returns_403(self, client: TestClient, seed_data: dict) -> None:
        _auth_as(client, seed_data["player1"])
        # Valid body shape — auth check happens before input validation
        action = _modify_character_action(
            seed_data["pc1"].id, {"stress": {"op": "delta", "value": 1}}
        )
        response = _batch(client, [action])
        assert response.status_code == 403


# ===========================================================================
# Input validation
# ===========================================================================


class TestBatchGmActionsValidation:
    """Input validation before any actions execute."""

    def test_empty_actions_returns_422_with_batch_empty(
        self, client: TestClient, seed_data: dict
    ) -> None:
        _auth_as(client, seed_data["gm"])
        response = _batch(client, [])
        assert response.status_code == 422
        body = response.json()
        # Pydantic validation errors include the message in the detail array
        detail_str = str(body)
        assert "batch_empty" in detail_str

    def test_over_50_actions_returns_422_with_batch_too_large(
        self, client: TestClient, seed_data: dict
    ) -> None:
        _auth_as(client, seed_data["gm"])
        # Build 51 modify_character actions
        action = _modify_character_action(
            seed_data["pc1"].id, {"stress": {"op": "delta", "value": 0}}
        )
        actions = [action] * 51
        response = _batch(client, actions)
        assert response.status_code == 422
        body = response.json()
        detail_str = str(body)
        assert "batch_too_large" in detail_str


# ===========================================================================
# Happy path
# ===========================================================================


class TestBatchGmActionsHappyPath:
    """Successful batch execution."""

    def test_single_action_returns_200_with_one_event(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        _auth_as(client, seed_data["gm"])

        action = _modify_character_action(pc1.id, {"stress": {"op": "set", "value": 3}})
        response = _batch(client, [action])

        assert response.status_code == 200
        body = response.json()
        assert "events" in body
        assert len(body["events"]) == 1

        db.expire(pc1)
        db.refresh(pc1)
        assert pc1.stress == 3

    def test_multiple_actions_returns_n_events(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        pc2 = seed_data["pc2"]
        _auth_as(client, seed_data["gm"])

        actions = [
            _modify_character_action(pc1.id, {"stress": {"op": "set", "value": 4}}),
            _modify_character_action(pc2.id, {"free_time": {"op": "set", "value": 7}}),
        ]
        response = _batch(client, actions)

        assert response.status_code == 200
        body = response.json()
        assert len(body["events"]) == 2

        db.expire(pc1)
        db.refresh(pc1)
        db.expire(pc2)
        db.refresh(pc2)
        assert pc1.stress == 4
        assert pc2.free_time == 7

    def test_events_returned_in_input_order(
        self, client: TestClient, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        pc2 = seed_data["pc2"]
        pc3 = seed_data["pc3"]
        _auth_as(client, seed_data["gm"])

        actions = [
            _modify_character_action(pc1.id, {"stress": {"op": "set", "value": 1}}),
            _modify_character_action(pc2.id, {"stress": {"op": "set", "value": 2}}),
            _modify_character_action(pc3.id, {"stress": {"op": "set", "value": 3}}),
        ]
        response = _batch(client, actions)

        assert response.status_code == 200
        events = response.json()["events"]
        assert len(events) == 3
        # Verify targets match input order
        assert events[0]["targets"][0]["target_id"] == pc1.id
        assert events[1]["targets"][0]["target_id"] == pc2.id
        assert events[2]["targets"][0]["target_id"] == pc3.id

    def test_event_shape_is_correct(
        self, client: TestClient, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        _auth_as(client, seed_data["gm"])

        action = _modify_character_action(
            pc1.id,
            {"stress": {"op": "set", "value": 2}},
            visibility="gm_only",
        )
        response = _batch(client, [action])

        assert response.status_code == 200
        evt = response.json()["events"][0]

        assert evt["type"] == "character.stress_changed"
        assert evt["actor_type"] == "gm"
        assert evt["actor_id"] == seed_data["gm"].id
        assert evt["visibility"] == "gm_only"
        assert len(evt["targets"]) == 1
        assert evt["targets"][0]["target_type"] == "character"
        assert evt["targets"][0]["target_id"] == pc1.id
        assert evt["targets"][0]["is_primary"] is True
        assert f"character.{pc1.id}.stress" in evt["changes"]


# ===========================================================================
# Atomicity
# ===========================================================================


class TestBatchGmActionsAtomicity:
    """Full-batch rollback when any action fails."""

    def test_failing_second_action_rolls_back_first(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        initial_stress = pc1.stress  # should be 0 from seed data

        _auth_as(client, seed_data["gm"])

        actions = [
            # Action 0: valid — modify pc1 stress
            _modify_character_action(pc1.id, {"stress": {"op": "set", "value": 5}}),
            # Action 1: invalid — target does not exist
            _modify_character_action("01NONEXISTENTCHARACTERID00", {"stress": {"op": "set", "value": 1}}),
        ]
        response = _batch(client, actions)

        assert response.status_code == 422
        body = response.json()
        assert body["error"]["code"] == "batch_failed"
        assert body["error"]["failed_index"] == 1

        # pc1 stress must be unchanged — the first action was rolled back
        db.expire(pc1)
        db.refresh(pc1)
        assert pc1.stress == initial_stress

    def test_failing_second_action_creates_no_events(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        event_count_before = db.execute(select(Event)).scalars().all()

        _auth_as(client, seed_data["gm"])

        actions = [
            _modify_character_action(pc1.id, {"stress": {"op": "set", "value": 3}}),
            _modify_character_action("01NONEXISTENTCHARACTERID00", {"stress": {"op": "set", "value": 1}}),
        ]
        response = _batch(client, actions)

        assert response.status_code == 422

        event_count_after = db.execute(select(Event)).scalars().all()
        assert len(event_count_after) == len(event_count_before)

    def test_first_action_invalid_returns_422_with_index_0(
        self, client: TestClient, seed_data: dict
    ) -> None:
        _auth_as(client, seed_data["gm"])

        actions = [
            # Action 0: invalid target
            _modify_character_action("01NONEXISTENTCHARACTERID00", {"stress": {"op": "set", "value": 1}}),
            # Action 1: would be valid but never runs
            _modify_character_action(seed_data["pc1"].id, {"stress": {"op": "set", "value": 2}}),
        ]
        response = _batch(client, actions)

        assert response.status_code == 422
        body = response.json()
        assert body["error"]["code"] == "batch_failed"
        assert body["error"]["failed_index"] == 0

    def test_batch_failed_error_includes_detail_message(
        self, client: TestClient, seed_data: dict
    ) -> None:
        _auth_as(client, seed_data["gm"])

        actions = [
            _modify_character_action("01NONEXISTENTCHARACTERID00", {"stress": {"op": "set", "value": 1}}),
        ]
        response = _batch(client, actions)

        assert response.status_code == 422
        body = response.json()
        assert "detail" in body["error"]
        assert len(body["error"]["detail"]) > 0

    def test_three_actions_third_fails_all_rolled_back(
        self, client: TestClient, db: Session, seed_data: dict
    ) -> None:
        pc1 = seed_data["pc1"]
        pc2 = seed_data["pc2"]

        _auth_as(client, seed_data["gm"])

        actions = [
            _modify_character_action(pc1.id, {"stress": {"op": "set", "value": 5}}),
            _modify_character_action(pc2.id, {"free_time": {"op": "set", "value": 10}}),
            # Action 2: invalid — target does not exist
            _modify_character_action("01NONEXISTENTCHARACTERID00", {"stress": {"op": "set", "value": 1}}),
        ]
        response = _batch(client, actions)

        assert response.status_code == 422
        body = response.json()
        assert body["error"]["failed_index"] == 2

        # Both pc1 and pc2 should be unchanged
        db.expire(pc1)
        db.refresh(pc1)
        db.expire(pc2)
        db.refresh(pc2)
        assert pc1.stress == 0
        assert pc2.free_time == 0
