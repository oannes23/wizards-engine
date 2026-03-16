"""Tests for Story 2.2.4 — Session CRUD (Draft Only).

Covers all acceptance criteria:

POST /api/v1/sessions
  - GM creates a session with no fields → 201, status=draft, empty participants
  - GM creates a session with all optional fields → 201, fields persisted
  - time_now is set correctly on create
  - date is set correctly (YYYY-MM-DD)
  - summary and notes are set correctly
  - Non-GM player cannot create → 403
  - Unauthenticated cannot create → 401
  - time_now < ended session's time_now → 400 (invalid_time_now)
  - time_now == ended session's time_now → 201 (equal is allowed)
  - time_now > ended session's time_now → 201 (strictly greater is fine)
  - No ended sessions → no time_now constraint, any value accepted

GET /api/v1/sessions
  - Returns paginated list of sessions
  - ULID cursor pagination works
  - Unauthenticated → 401

GET /api/v1/sessions/{id}
  - Returns session detail with participants list
  - Non-existent ID → 404
  - Unauthenticated → 401

PATCH /api/v1/sessions/{id}
  - GM updates time_now → 200, updated
  - GM updates date → 200
  - GM updates summary → 200
  - GM updates notes → 200
  - GM clears summary with null → 200, summary=null
  - Omitted fields are unchanged (exclude_unset semantics)
  - Active session can be patched → 200
  - Ended session cannot be patched → 400 (session_ended)
  - time_now < ended session's time_now on PATCH → 400
  - Non-existent session → 404
  - Non-GM player cannot patch → 403
  - Unauthenticated → 401

DELETE /api/v1/sessions/{id}
  - GM hard-deletes a draft session → 204
  - Session no longer retrievable after delete → 404
  - Active session cannot be deleted → 400 (session_not_draft)
  - Ended session cannot be deleted → 400 (session_not_draft)
  - Non-existent session → 404
  - Non-GM player cannot delete → 403
  - Unauthenticated → 401
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as DBSession

from tests.conftest import auth_as
from wizards_engine.models.session import Session as SessionModel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(db: DBSession, status: str = "draft", time_now: int | None = None) -> SessionModel:
    """Insert a Session row directly into the DB with the given status.

    Used by tests that need sessions in a particular lifecycle state (e.g.
    ``active`` or ``ended``) without going through the Start/End endpoints
    (which are deferred to Epic 5.1).
    """
    session = SessionModel(
        status=status,
        time_now=time_now,
        summary=None,
        notes=None,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


# ---------------------------------------------------------------------------
# POST /api/v1/sessions
# ---------------------------------------------------------------------------


class TestCreateSession:
    def test_gm_creates_session_with_no_fields(
        self, client: TestClient, seed_data: dict
    ):
        """GM creates a session with empty body; returns 201, status=draft."""
        auth_as(client, seed_data["gm"])
        response = client.post("/api/v1/sessions", json={})

        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "draft"
        assert body["time_now"] is None
        assert body["date"] is None
        assert body["summary"] is None
        assert body["notes"] is None
        assert body["participants"] == []
        assert "id" in body
        assert "created_at" in body
        assert "updated_at" in body

    def test_gm_creates_session_with_all_fields(
        self, client: TestClient, seed_data: dict
    ):
        """GM creates a session with all optional fields populated."""
        auth_as(client, seed_data["gm"])
        response = client.post(
            "/api/v1/sessions",
            json={
                "time_now": 10,
                "date": "2026-04-01",
                "summary": "The party arrived at the keep.",
                "notes": "Players brought snacks.",
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "draft"
        assert body["time_now"] == 10
        assert body["date"] == "2026-04-01"
        assert body["summary"] == "The party arrived at the keep."
        assert body["notes"] == "Players brought snacks."
        assert body["participants"] == []

    def test_create_session_status_always_draft(
        self, client: TestClient, seed_data: dict
    ):
        """Sessions are always created as draft regardless of body contents."""
        auth_as(client, seed_data["gm"])
        response = client.post("/api/v1/sessions", json={"time_now": 1})
        assert response.status_code == 201
        assert response.json()["status"] == "draft"

    def test_non_gm_cannot_create_session(
        self, client: TestClient, seed_data: dict
    ):
        """Non-GM player receives 403 when attempting to create a session."""
        auth_as(client, seed_data["player1"])
        response = client.post("/api/v1/sessions", json={})
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "insufficient_role"

    def test_unauthenticated_cannot_create_session(
        self, client: TestClient, seed_data: dict
    ):
        """Unauthenticated request to create session receives 401."""
        response = client.post("/api/v1/sessions", json={})
        assert response.status_code == 401

    def test_time_now_before_ended_session_returns_400(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """time_now < ended session's time_now returns 400."""
        _make_session(db, status="ended", time_now=20)

        auth_as(client, seed_data["gm"])
        response = client.post("/api/v1/sessions", json={"time_now": 5})

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_time_now"

    def test_time_now_equal_to_ended_session_is_allowed(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """time_now == ended session's time_now is valid (0 delta)."""
        _make_session(db, status="ended", time_now=20)

        auth_as(client, seed_data["gm"])
        response = client.post("/api/v1/sessions", json={"time_now": 20})

        assert response.status_code == 201
        assert response.json()["time_now"] == 20

    def test_time_now_greater_than_ended_session_is_allowed(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """time_now > ended session's time_now is valid."""
        _make_session(db, status="ended", time_now=20)

        auth_as(client, seed_data["gm"])
        response = client.post("/api/v1/sessions", json={"time_now": 25})

        assert response.status_code == 201
        assert response.json()["time_now"] == 25

    def test_no_ended_sessions_any_time_now_accepted(
        self, client: TestClient, seed_data: dict
    ):
        """When no ended sessions exist, any time_now value is valid."""
        auth_as(client, seed_data["gm"])
        response = client.post("/api/v1/sessions", json={"time_now": 1})
        assert response.status_code == 201
        assert response.json()["time_now"] == 1

    def test_time_now_constraint_ignores_draft_and_active(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Draft and active sessions do not count toward the time_now floor."""
        # Draft and active sessions with high time_now — should not constrain.
        _make_session(db, status="draft", time_now=100)
        _make_session(db, status="active", time_now=100)

        auth_as(client, seed_data["gm"])
        # Low time_now should still be OK since there are no ended sessions.
        response = client.post("/api/v1/sessions", json={"time_now": 1})
        assert response.status_code == 201

    def test_create_session_time_now_none_no_constraint(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Omitting time_now skips validation even when ended sessions exist."""
        _make_session(db, status="ended", time_now=50)

        auth_as(client, seed_data["gm"])
        response = client.post("/api/v1/sessions", json={})
        assert response.status_code == 201
        assert response.json()["time_now"] is None


# ---------------------------------------------------------------------------
# GET /api/v1/sessions
# ---------------------------------------------------------------------------


class TestListSessions:
    def test_list_returns_sessions(self, client: TestClient, seed_data: dict, db: DBSession):
        """Authenticated user can list sessions; response has items/next_cursor/has_more."""
        _make_session(db)
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/sessions")

        assert response.status_code == 200
        body = response.json()
        assert "items" in body
        assert "next_cursor" in body
        assert "has_more" in body
        assert isinstance(body["items"], list)
        assert len(body["items"]) >= 1

    def test_list_empty_returns_empty_items(
        self, client: TestClient, seed_data: dict
    ):
        """Empty DB returns an empty items list."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/sessions")
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []
        assert body["has_more"] is False
        assert body["next_cursor"] is None

    def test_list_pagination_limit(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """limit parameter caps the page size."""
        for _ in range(5):
            _make_session(db)

        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/sessions?limit=2")
        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) <= 2

    def test_list_pagination_cursor(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """After fetching the first page, the cursor returns the next page."""
        for _ in range(4):
            _make_session(db)

        auth_as(client, seed_data["gm"])
        page1 = client.get("/api/v1/sessions?limit=2").json()
        assert len(page1["items"]) == 2
        assert page1["has_more"] is True
        assert page1["next_cursor"] is not None

        page2 = client.get(
            f"/api/v1/sessions?limit=2&after={page1['next_cursor']}"
        ).json()
        page1_ids = {s["id"] for s in page1["items"]}
        page2_ids = {s["id"] for s in page2["items"]}
        assert page1_ids.isdisjoint(page2_ids)

    def test_unauthenticated_list_returns_401(
        self, client: TestClient, seed_data: dict
    ):
        """Unauthenticated request to list sessions receives 401."""
        response = client.get("/api/v1/sessions")
        assert response.status_code == 401

    def test_player_can_list_sessions(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Non-GM players can also list sessions."""
        _make_session(db)
        auth_as(client, seed_data["player1"])
        response = client.get("/api/v1/sessions")
        assert response.status_code == 200

    def test_list_session_items_include_participants_field(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """List items include the participants field (empty list for fresh sessions)."""
        _make_session(db)
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/sessions")
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) >= 1
        assert "participants" in items[0]
        assert isinstance(items[0]["participants"], list)


# ---------------------------------------------------------------------------
# GET /api/v1/sessions/{id}
# ---------------------------------------------------------------------------


class TestGetSession:
    def test_get_returns_session_detail(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """GET /sessions/{id} returns full session detail with participants."""
        session = _make_session(db, time_now=5)
        auth_as(client, seed_data["gm"])
        response = client.get(f"/api/v1/sessions/{session.id}")

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == session.id
        assert body["status"] == "draft"
        assert body["time_now"] == 5
        assert body["participants"] == []

    def test_get_nonexistent_session_returns_404(
        self, client: TestClient, seed_data: dict
    ):
        """GET /sessions/{id} returns 404 for a non-existent ID."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/sessions/01DOESNOTEXIST0000000000000")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_unauthenticated_get_returns_401(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Unauthenticated GET /sessions/{id} returns 401."""
        session = _make_session(db)
        response = client.get(f"/api/v1/sessions/{session.id}")
        assert response.status_code == 401

    def test_player_can_get_session_detail(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Non-GM players can retrieve session detail."""
        session = _make_session(db, time_now=3)
        auth_as(client, seed_data["player1"])
        response = client.get(f"/api/v1/sessions/{session.id}")
        assert response.status_code == 200
        assert response.json()["id"] == session.id

    def test_get_malformed_id_returns_404(
        self, client: TestClient, seed_data: dict
    ):
        """GET with a non-ULID path segment returns 404."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/sessions/not-a-valid-ulid")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"


# ---------------------------------------------------------------------------
# PATCH /api/v1/sessions/{id}
# ---------------------------------------------------------------------------


class TestUpdateSession:
    def test_gm_updates_time_now(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """GM can update a session's time_now."""
        session = _make_session(db)
        auth_as(client, seed_data["gm"])
        response = client.patch(
            f"/api/v1/sessions/{session.id}", json={"time_now": 42}
        )
        assert response.status_code == 200
        assert response.json()["time_now"] == 42

    def test_gm_updates_date(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """GM can update a session's date."""
        session = _make_session(db)
        auth_as(client, seed_data["gm"])
        response = client.patch(
            f"/api/v1/sessions/{session.id}", json={"date": "2026-05-10"}
        )
        assert response.status_code == 200
        assert response.json()["date"] == "2026-05-10"

    def test_gm_updates_summary(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """GM can update a session's summary."""
        session = _make_session(db)
        auth_as(client, seed_data["gm"])
        response = client.patch(
            f"/api/v1/sessions/{session.id}", json={"summary": "Epic events unfolded."}
        )
        assert response.status_code == 200
        assert response.json()["summary"] == "Epic events unfolded."

    def test_gm_updates_notes(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """GM can update a session's notes."""
        session = _make_session(db)
        auth_as(client, seed_data["gm"])
        response = client.patch(
            f"/api/v1/sessions/{session.id}", json={"notes": "Remember to bring extra dice."}
        )
        assert response.status_code == 200
        assert response.json()["notes"] == "Remember to bring extra dice."

    def test_gm_clears_summary_with_null(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Sending summary=null clears the field."""
        session = _make_session(db)
        auth_as(client, seed_data["gm"])
        # Set a summary first.
        client.patch(
            f"/api/v1/sessions/{session.id}", json={"summary": "Initial summary"}
        )
        # Now clear it.
        response = client.patch(
            f"/api/v1/sessions/{session.id}", json={"summary": None}
        )
        assert response.status_code == 200
        assert response.json()["summary"] is None

    def test_omitted_fields_are_unchanged(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Omitted fields in PATCH body remain unchanged (exclude_unset semantics)."""
        session = _make_session(db)
        auth_as(client, seed_data["gm"])
        # Set initial state.
        client.patch(
            f"/api/v1/sessions/{session.id}",
            json={"summary": "Original summary", "notes": "Original notes"},
        )
        # Update only notes; summary should be unchanged.
        response = client.patch(
            f"/api/v1/sessions/{session.id}", json={"notes": "New notes only"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["summary"] == "Original summary"
        assert body["notes"] == "New notes only"

    def test_patch_active_session_allowed(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Active sessions can be patched (summary/notes during play)."""
        session = _make_session(db, status="active")
        auth_as(client, seed_data["gm"])
        response = client.patch(
            f"/api/v1/sessions/{session.id}",
            json={"summary": "Mid-session update"},
        )
        assert response.status_code == 200
        assert response.json()["summary"] == "Mid-session update"

    def test_patch_ended_session_returns_400(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Ended sessions are read-only — PATCH returns 400."""
        session = _make_session(db, status="ended")
        auth_as(client, seed_data["gm"])
        response = client.patch(
            f"/api/v1/sessions/{session.id}", json={"summary": "Should fail"}
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "session_ended"

    def test_patch_time_now_before_ended_session_returns_400(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """PATCH time_now < ended session's time_now returns 400."""
        _make_session(db, status="ended", time_now=50)
        draft = _make_session(db, status="draft")

        auth_as(client, seed_data["gm"])
        response = client.patch(
            f"/api/v1/sessions/{draft.id}", json={"time_now": 10}
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_time_now"

    def test_patch_time_now_equal_to_ended_session_allowed(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """PATCH time_now == ended session's time_now is valid."""
        _make_session(db, status="ended", time_now=50)
        draft = _make_session(db, status="draft")

        auth_as(client, seed_data["gm"])
        response = client.patch(
            f"/api/v1/sessions/{draft.id}", json={"time_now": 50}
        )
        assert response.status_code == 200
        assert response.json()["time_now"] == 50

    def test_patch_nonexistent_session_returns_404(
        self, client: TestClient, seed_data: dict
    ):
        """PATCH /sessions/{id} returns 404 for a non-existent ID."""
        auth_as(client, seed_data["gm"])
        response = client.patch(
            "/api/v1/sessions/01DOESNOTEXIST0000000000000",
            json={"summary": "Ghost"},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_non_gm_cannot_patch_session(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Non-GM player receives 403 when attempting to PATCH a session."""
        session = _make_session(db)
        auth_as(client, seed_data["player1"])
        response = client.patch(
            f"/api/v1/sessions/{session.id}", json={"summary": "Player attempt"}
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "insufficient_role"

    def test_unauthenticated_patch_returns_401(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Unauthenticated PATCH returns 401."""
        session = _make_session(db)
        response = client.patch(
            f"/api/v1/sessions/{session.id}", json={"summary": "No auth"}
        )
        assert response.status_code == 401

    def test_patch_empty_body_is_noop(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """PATCH with an empty JSON object {} is valid; no fields are changed."""
        session = _make_session(db)
        auth_as(client, seed_data["gm"])
        # Set initial state.
        client.patch(f"/api/v1/sessions/{session.id}", json={"summary": "Initial"})

        response = client.patch(f"/api/v1/sessions/{session.id}", json={})
        assert response.status_code == 200
        assert response.json()["summary"] == "Initial"

    def test_patch_time_now_null_clears_field(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Sending time_now=null clears the field (skips time_now validation)."""
        session = _make_session(db, time_now=10)
        auth_as(client, seed_data["gm"])
        response = client.patch(
            f"/api/v1/sessions/{session.id}", json={"time_now": None}
        )
        assert response.status_code == 200
        assert response.json()["time_now"] is None


# ---------------------------------------------------------------------------
# DELETE /api/v1/sessions/{id}
# ---------------------------------------------------------------------------


class TestDeleteSession:
    def test_gm_hard_deletes_draft_session(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """GM can hard-delete a draft session; returns 204."""
        session = _make_session(db)
        auth_as(client, seed_data["gm"])
        response = client.delete(f"/api/v1/sessions/{session.id}")
        assert response.status_code == 204
        assert response.content == b""

    def test_deleted_session_not_retrievable(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """After hard delete, the session is gone — GET returns 404."""
        session = _make_session(db)
        session_id = session.id
        auth_as(client, seed_data["gm"])
        client.delete(f"/api/v1/sessions/{session_id}")

        get_resp = client.get(f"/api/v1/sessions/{session_id}")
        assert get_resp.status_code == 404

    def test_deleted_session_removed_from_list(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Hard-deleted session no longer appears in the list."""
        session = _make_session(db)
        session_id = session.id
        auth_as(client, seed_data["gm"])
        client.delete(f"/api/v1/sessions/{session_id}")

        list_resp = client.get("/api/v1/sessions")
        ids = [s["id"] for s in list_resp.json()["items"]]
        assert session_id not in ids

    def test_delete_active_session_returns_400(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Active session cannot be deleted — returns 400."""
        session = _make_session(db, status="active")
        auth_as(client, seed_data["gm"])
        response = client.delete(f"/api/v1/sessions/{session.id}")
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "session_not_draft"

    def test_delete_ended_session_returns_400(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Ended session cannot be deleted — returns 400."""
        session = _make_session(db, status="ended")
        auth_as(client, seed_data["gm"])
        response = client.delete(f"/api/v1/sessions/{session.id}")
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "session_not_draft"

    def test_delete_nonexistent_session_returns_404(
        self, client: TestClient, seed_data: dict
    ):
        """DELETE /sessions/{id} returns 404 for a non-existent ID."""
        auth_as(client, seed_data["gm"])
        response = client.delete("/api/v1/sessions/01DOESNOTEXIST0000000000000")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_non_gm_cannot_delete_session(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Non-GM player receives 403 when attempting to delete a session."""
        session = _make_session(db)
        auth_as(client, seed_data["player1"])
        response = client.delete(f"/api/v1/sessions/{session.id}")
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "insufficient_role"

    def test_unauthenticated_delete_returns_401(
        self, client: TestClient, seed_data: dict, db: DBSession
    ):
        """Unauthenticated DELETE returns 401."""
        session = _make_session(db)
        response = client.delete(f"/api/v1/sessions/{session.id}")
        assert response.status_code == 401

    def test_delete_malformed_id_returns_404(
        self, client: TestClient, seed_data: dict
    ):
        """DELETE with a non-ULID path segment returns 404."""
        auth_as(client, seed_data["gm"])
        response = client.delete("/api/v1/sessions/not-a-valid-ulid")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"
