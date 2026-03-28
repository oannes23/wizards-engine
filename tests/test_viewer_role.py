"""Comprehensive tests for the viewer role — Story 9.1.10.

Covers all viewer role scenarios not already tested in other files:

  test_viewer_onboarding.py  — invite creation + join flow (17 tests)
  test_route_permission_audit.py — write endpoint blocking, roster (13 tests)
  test_players.py            — viewer roster rows (5 tests)

This file targets the remaining gaps:

1. Auth & Identity
   - Viewer can log in via magic link (POST /auth/login)
   - GET /me returns role="viewer", character_id=null, can_view_gm_content=True,
     can_take_gm_actions=False
   - PATCH /me works for viewer (can update display_name)
   - POST /me/refresh-link works for viewer (can rotate own login code)

2. Visibility
   - Viewer sees events with gm_only visibility (personal feed)
   - Viewer sees events with private, bonded, familiar, public, global visibility
   - Viewer does NOT see events with silent visibility (personal feed)
   - GET /me/feed/silent returns 403 for viewer

3. GM Read Access (confirm viewer has it)
   - GET /gm/dashboard → 200
   - GET /gm/queue-summary → 200
   - GET /game/invites → 200
   - GET /proposals → 200, returns all proposals (not filtered by character)
   - GET /proposals/{id} → 200
   - GET /sessions → 200
   - GET /sessions/{id} → 200
   - GET /characters → 200
   - GET /characters/{id} → 200
   - GET /characters/summary → 200

4. Write Blocking (exhaustive)
   - POST /gm/actions → 403
   - POST /gm/actions/batch → 403
   - POST /proposals → 403
   - POST /proposals/calculate → 403
   - POST /proposals/{id}/approve → 403
   - POST /proposals/{id}/reject → 403
   - POST /characters → 403
   - PATCH /characters/{id} → 403
   - DELETE /characters/{id} → 403
   - POST /groups → 403
   - PATCH /groups/{id} → 403
   - DELETE /groups/{id} → 403
   - POST /locations → 403
   - PATCH /locations/{id} → 403
   - DELETE /locations/{id} → 403
   - POST /clocks → 403
   - PATCH /clocks/{id} → 403
   - DELETE /clocks/{id} → 403
   - POST /trait-templates → 403
   - PATCH /trait-templates/{id} → 403
   - DELETE /trait-templates/{id} → 403
   - POST /sessions → 403
   - PATCH /sessions/{id} → 403
   - DELETE /sessions/{id} → 403
   - POST /sessions/{id}/start → 403
   - POST /sessions/{id}/end → 403
   - POST /players/{id}/regenerate-token → 403
   - POST /me/character → 403
   - DELETE /game/invites/{id} → 403
   - POST /stories → 403
   - PATCH /stories/{id} → 403
   - DELETE /stories/{id} → 403
   - PATCH /events/{id}/visibility → 403

5. Starring (viewer CAN do this)
   - POST /me/starred works for viewer
   - GET /me/starred works for viewer
   - DELETE /me/starred/{type}/{id} works for viewer
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import auth_as
from wizards_engine.api.auth import COOKIE_NAME
from wizards_engine.models.event import Event, EventTarget
from wizards_engine.models.proposal import Proposal
from wizards_engine.models.session import Session as SessionModel
from wizards_engine.models.starred import StarredObject


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _event(
    db: Session,
    *,
    visibility: str = "global",
    targets: list[tuple[str, str, bool]] | None = None,
) -> Event:
    """Create and flush a minimal Event with the given visibility."""
    ev = Event(
        type="test.event",
        actor_type="gm",
        changes={},
        visibility=visibility,
    )
    db.add(ev)
    db.flush()

    for t_type, t_id, is_primary in (targets or []):
        db.add(
            EventTarget(
                event_id=ev.id,
                target_type=t_type,
                target_id=t_id,
                is_primary=is_primary,
            )
        )

    db.flush()
    db.refresh(ev)
    return ev


def _pending_proposal(db: Session, character_id: str) -> Proposal:
    """Create and flush a pending proposal for the given character."""
    p = Proposal(
        character_id=character_id,
        action_type="use_skill",
        narrative="Test narrative",
        status="pending",
        origin="player",
        selections={},
    )
    db.add(p)
    db.flush()
    db.refresh(p)
    return p


def _draft_session(db: Session) -> SessionModel:
    """Create and flush a minimal draft session."""
    s = SessionModel(status="draft", time_now=1)
    db.add(s)
    db.flush()
    db.refresh(s)
    return s


# ===========================================================================
# 1. Auth & Identity
# ===========================================================================


class TestViewerAuthAndIdentity:
    """Viewer auth cookie, /me shape, PATCH /me, and link refresh."""

    def test_login_via_magic_link_returns_200(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """Viewer login code is accepted by POST /auth/login → 200."""
        viewer = seed_data["viewer"]
        response = client.post(
            "/api/v1/auth/login", json={"code": viewer.login_code}
        )
        assert response.status_code == 200

    def test_login_returns_role_viewer(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """Login response has role='viewer' for a viewer account."""
        viewer = seed_data["viewer"]
        response = client.post(
            "/api/v1/auth/login", json={"code": viewer.login_code}
        )
        body = response.json()
        assert body["role"] == "viewer"

    def test_login_returns_null_character_id(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """Login response has character_id=null for a viewer (no character linked)."""
        viewer = seed_data["viewer"]
        response = client.post(
            "/api/v1/auth/login", json={"code": viewer.login_code}
        )
        body = response.json()
        assert body["character_id"] is None

    def test_login_sets_auth_cookie(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """Login sets the httpOnly auth cookie for a viewer account."""
        viewer = seed_data["viewer"]
        response = client.post(
            "/api/v1/auth/login", json={"code": viewer.login_code}
        )
        assert COOKIE_NAME in response.headers.get("set-cookie", "")

    def test_get_me_returns_viewer_role(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """GET /me returns role='viewer' for a viewer user."""
        auth_as(client, seed_data["viewer"])
        response = client.get("/api/v1/me")

        assert response.status_code == 200
        assert response.json()["role"] == "viewer"

    def test_get_me_returns_null_character_id(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """GET /me returns character_id=null for a viewer (no character linked)."""
        auth_as(client, seed_data["viewer"])
        response = client.get("/api/v1/me")

        assert response.status_code == 200
        assert response.json()["character_id"] is None

    def test_get_me_can_view_gm_content_true(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """GET /me returns can_view_gm_content=true for a viewer."""
        auth_as(client, seed_data["viewer"])
        response = client.get("/api/v1/me")

        assert response.status_code == 200
        assert response.json()["can_view_gm_content"] is True

    def test_get_me_can_take_gm_actions_false(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """GET /me returns can_take_gm_actions=false for a viewer."""
        auth_as(client, seed_data["viewer"])
        response = client.get("/api/v1/me")

        assert response.status_code == 200
        assert response.json()["can_take_gm_actions"] is False

    def test_patch_me_updates_display_name_for_viewer(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """Viewer can update their own display_name via PATCH /me."""
        auth_as(client, seed_data["viewer"])
        response = client.patch(
            "/api/v1/me", json={"display_name": "Updated Viewer Name"}
        )

        assert response.status_code == 200
        assert response.json()["display_name"] == "Updated Viewer Name"

    def test_patch_me_returns_viewer_role_in_response(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """PATCH /me response preserves role='viewer' after a display_name update."""
        auth_as(client, seed_data["viewer"])
        response = client.patch(
            "/api/v1/me", json={"display_name": "Another Name"}
        )

        assert response.status_code == 200
        assert response.json()["role"] == "viewer"

    def test_refresh_link_works_for_viewer(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """POST /me/refresh-link returns 200 for a viewer."""
        auth_as(client, seed_data["viewer"])
        response = client.post("/api/v1/me/refresh-link")

        assert response.status_code == 200

    def test_refresh_link_returns_login_url(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """POST /me/refresh-link response has a login_url key."""
        auth_as(client, seed_data["viewer"])
        response = client.post("/api/v1/me/refresh-link")

        body = response.json()
        assert "login_url" in body
        assert body["login_url"].startswith("/login/")

    def test_refresh_link_updates_cookie_for_viewer(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """POST /me/refresh-link sets a new Set-Cookie header for a viewer."""
        auth_as(client, seed_data["viewer"])
        response = client.post("/api/v1/me/refresh-link")

        assert COOKIE_NAME in response.headers.get("set-cookie", "")


# ===========================================================================
# 2. Visibility — viewer sees all non-silent events
# ===========================================================================


class TestViewerVisibility:
    """Viewer's personal feed should include all non-silent event visibilities."""

    def test_viewer_sees_gm_only_events(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """A gm_only event appears in the viewer's personal feed."""
        pc1 = seed_data["pc1"]
        ev = _event(
            db,
            visibility="gm_only",
            targets=[("character", pc1.id, True)],
        )
        db.commit()

        auth_as(client, seed_data["viewer"])
        resp = client.get("/api/v1/me/feed")

        assert resp.status_code == 200
        ids = [item["id"] for item in resp.json()["items"]]
        assert ev.id in ids

    def test_viewer_sees_private_events(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """A private event appears in the viewer's personal feed."""
        pc1 = seed_data["pc1"]
        ev = _event(
            db,
            visibility="private",
            targets=[("character", pc1.id, True)],
        )
        db.commit()

        auth_as(client, seed_data["viewer"])
        resp = client.get("/api/v1/me/feed")

        assert resp.status_code == 200
        ids = [item["id"] for item in resp.json()["items"]]
        assert ev.id in ids

    def test_viewer_sees_bonded_events(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """A bonded-visibility event appears in the viewer's personal feed."""
        pc1 = seed_data["pc1"]
        ev = _event(
            db,
            visibility="bonded",
            targets=[("character", pc1.id, True)],
        )
        db.commit()

        auth_as(client, seed_data["viewer"])
        resp = client.get("/api/v1/me/feed")

        assert resp.status_code == 200
        ids = [item["id"] for item in resp.json()["items"]]
        assert ev.id in ids

    def test_viewer_sees_familiar_events(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """A familiar-visibility event appears in the viewer's personal feed."""
        pc1 = seed_data["pc1"]
        ev = _event(
            db,
            visibility="familiar",
            targets=[("character", pc1.id, True)],
        )
        db.commit()

        auth_as(client, seed_data["viewer"])
        resp = client.get("/api/v1/me/feed")

        assert resp.status_code == 200
        ids = [item["id"] for item in resp.json()["items"]]
        assert ev.id in ids

    def test_viewer_sees_public_events(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """A public-visibility event appears in the viewer's personal feed."""
        pc1 = seed_data["pc1"]
        ev = _event(
            db,
            visibility="public",
            targets=[("character", pc1.id, True)],
        )
        db.commit()

        auth_as(client, seed_data["viewer"])
        resp = client.get("/api/v1/me/feed")

        assert resp.status_code == 200
        ids = [item["id"] for item in resp.json()["items"]]
        assert ev.id in ids

    def test_viewer_sees_global_events(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """A global-visibility event appears in the viewer's personal feed."""
        pc1 = seed_data["pc1"]
        ev = _event(
            db,
            visibility="global",
            targets=[("character", pc1.id, True)],
        )
        db.commit()

        auth_as(client, seed_data["viewer"])
        resp = client.get("/api/v1/me/feed")

        assert resp.status_code == 200
        ids = [item["id"] for item in resp.json()["items"]]
        assert ev.id in ids

    def test_viewer_does_not_see_silent_events_in_personal_feed(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Silent events are excluded from the viewer's personal feed."""
        pc1 = seed_data["pc1"]
        silent_ev = _event(
            db,
            visibility="silent",
            targets=[("character", pc1.id, True)],
        )
        db.commit()

        auth_as(client, seed_data["viewer"])
        resp = client.get("/api/v1/me/feed")

        assert resp.status_code == 200
        ids = [item["id"] for item in resp.json()["items"]]
        assert silent_ev.id not in ids

    def test_viewer_silent_feed_returns_403(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """GET /me/feed/silent returns 403 for a viewer (GM-only endpoint)."""
        auth_as(client, seed_data["viewer"])
        resp = client.get("/api/v1/me/feed/silent")

        assert resp.status_code == 403


# ===========================================================================
# 3. GM Read Access — viewer has it
# ===========================================================================


class TestViewerGMReadAccess:
    """Viewer can call all GM-readable (require_privileged) endpoints."""

    def test_gm_dashboard_returns_200(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """GET /gm/dashboard returns 200 for a viewer."""
        auth_as(client, seed_data["viewer"])
        response = client.get("/api/v1/gm/dashboard")
        assert response.status_code == 200

    def test_gm_queue_summary_returns_200(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """GET /gm/queue-summary returns 200 for a viewer."""
        auth_as(client, seed_data["viewer"])
        response = client.get("/api/v1/gm/queue-summary")
        assert response.status_code == 200

    def test_game_invites_returns_200(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """GET /game/invites returns 200 for a viewer."""
        auth_as(client, seed_data["viewer"])
        response = client.get("/api/v1/game/invites")
        assert response.status_code == 200

    def test_proposals_list_returns_200(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """GET /proposals returns 200 for a viewer."""
        auth_as(client, seed_data["viewer"])
        response = client.get("/api/v1/proposals")
        assert response.status_code == 200

    def test_proposals_list_returns_all_proposals_not_filtered(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Viewer sees all proposals, not just their own (no character to own proposals)."""
        # Create proposals for two different PCs.
        p1 = _pending_proposal(db, seed_data["pc1"].id)
        p2 = _pending_proposal(db, seed_data["pc2"].id)
        db.commit()

        auth_as(client, seed_data["viewer"])
        response = client.get("/api/v1/proposals")

        assert response.status_code == 200
        ids = [item["id"] for item in response.json()["items"]]
        assert p1.id in ids
        assert p2.id in ids

    def test_proposal_detail_returns_200(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """GET /proposals/{id} returns 200 for a viewer."""
        p = _pending_proposal(db, seed_data["pc1"].id)
        db.commit()

        auth_as(client, seed_data["viewer"])
        response = client.get(f"/api/v1/proposals/{p.id}")
        assert response.status_code == 200

    def test_sessions_list_returns_200(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """GET /sessions returns 200 for a viewer."""
        auth_as(client, seed_data["viewer"])
        response = client.get("/api/v1/sessions")
        assert response.status_code == 200

    def test_session_detail_returns_200(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """GET /sessions/{id} returns 200 for a viewer."""
        session = _draft_session(db)
        db.commit()

        auth_as(client, seed_data["viewer"])
        response = client.get(f"/api/v1/sessions/{session.id}")
        assert response.status_code == 200

    def test_characters_list_returns_200(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """GET /characters returns 200 for a viewer."""
        auth_as(client, seed_data["viewer"])
        response = client.get("/api/v1/characters")
        assert response.status_code == 200

    def test_character_detail_returns_200(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """GET /characters/{id} returns 200 for a viewer."""
        auth_as(client, seed_data["viewer"])
        response = client.get(f"/api/v1/characters/{seed_data['pc1'].id}")
        assert response.status_code == 200

    def test_characters_summary_returns_200(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """GET /characters/summary returns 200 for a viewer."""
        auth_as(client, seed_data["viewer"])
        response = client.get("/api/v1/characters/summary")
        assert response.status_code == 200


# ===========================================================================
# 4. Write Blocking — parametrized where possible, individual where not
# ===========================================================================


_PLACEHOLDER_ID = "01AAAAAAAAAAAAAAAAAAAAAA01"


@pytest.mark.parametrize(
    "method,url",
    [
        # GM action endpoints — require_gm fires before body validation
        ("POST", "/api/v1/gm/actions"),
        ("POST", "/api/v1/gm/actions/batch"),
        # Proposals — approve/reject (require_gm)
        ("POST", f"/api/v1/proposals/{_PLACEHOLDER_ID}/approve"),
        ("POST", f"/api/v1/proposals/{_PLACEHOLDER_ID}/reject"),
        # Characters — create/delete (require_gm)
        ("POST", "/api/v1/characters"),
        ("DELETE", f"/api/v1/characters/{_PLACEHOLDER_ID}"),
        # Groups — create/update/delete (require_gm)
        ("POST", "/api/v1/groups"),
        ("PATCH", f"/api/v1/groups/{_PLACEHOLDER_ID}"),
        ("DELETE", f"/api/v1/groups/{_PLACEHOLDER_ID}"),
        # Locations — create/update/delete (require_gm)
        ("POST", "/api/v1/locations"),
        ("PATCH", f"/api/v1/locations/{_PLACEHOLDER_ID}"),
        ("DELETE", f"/api/v1/locations/{_PLACEHOLDER_ID}"),
        # Clocks — create/update/delete (require_gm)
        ("POST", "/api/v1/clocks"),
        ("PATCH", f"/api/v1/clocks/{_PLACEHOLDER_ID}"),
        ("DELETE", f"/api/v1/clocks/{_PLACEHOLDER_ID}"),
        # Trait templates — create/update/delete (require_gm)
        ("POST", "/api/v1/trait-templates"),
        ("PATCH", f"/api/v1/trait-templates/{_PLACEHOLDER_ID}"),
        ("DELETE", f"/api/v1/trait-templates/{_PLACEHOLDER_ID}"),
        # Sessions — create/update/delete/lifecycle (require_gm)
        ("POST", "/api/v1/sessions"),
        ("PATCH", f"/api/v1/sessions/{_PLACEHOLDER_ID}"),
        ("DELETE", f"/api/v1/sessions/{_PLACEHOLDER_ID}"),
        ("POST", f"/api/v1/sessions/{_PLACEHOLDER_ID}/start"),
        ("POST", f"/api/v1/sessions/{_PLACEHOLDER_ID}/end"),
        # Players — regenerate-token (require_gm)
        ("POST", f"/api/v1/players/{_PLACEHOLDER_ID}/regenerate-token"),
        # Me — create character (require_gm)
        ("POST", "/api/v1/me/character"),
        # Invites — delete (require_gm)
        ("DELETE", f"/api/v1/game/invites/{_PLACEHOLDER_ID}"),
        # Stories — create/update/delete (require_gm)
        ("POST", "/api/v1/stories"),
        ("PATCH", f"/api/v1/stories/{_PLACEHOLDER_ID}"),
        ("DELETE", f"/api/v1/stories/{_PLACEHOLDER_ID}"),
        # Events — change visibility (require_gm)
        ("PATCH", f"/api/v1/events/{_PLACEHOLDER_ID}/visibility"),
    ],
)
def test_viewer_write_endpoint_returns_403(
    client: TestClient, seed_data: dict, method: str, url: str
) -> None:
    """Viewer receives 403 on every mutating endpoint.

    No valid body is sent — role/auth checks fire before body validation for
    all endpoints in this list (they use require_gm / require_privileged
    dependencies which run before the handler).
    """
    auth_as(client, seed_data["viewer"])
    response = client.request(method, url, json={})
    assert response.status_code == 403, (
        f"{method} {url} returned {response.status_code}, expected 403"
    )


# ---------------------------------------------------------------------------
# Write blocking — special cases requiring real seed IDs or valid bodies
# ---------------------------------------------------------------------------


class TestViewerWriteBlockingSpecialCases:
    """Blocking tests for endpoints that need real IDs or validated request bodies."""

    def test_viewer_cannot_create_proposal(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """POST /proposals returns 403 for viewer.

        The route uses get_current_user (not require_gm) and checks role inside
        the handler, so a valid Pydantic body is needed to reach the role check.
        """
        auth_as(client, seed_data["viewer"])
        response = client.post(
            "/api/v1/proposals",
            json={
                "character_id": seed_data["pc1"].id,
                "action_type": "use_skill",
            },
        )
        assert response.status_code == 403

    def test_viewer_cannot_calculate_proposal(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """POST /proposals/calculate returns 403 for viewer.

        The route uses get_current_user and checks role inside the handler,
        so a valid Pydantic body is needed to reach the role check.
        """
        auth_as(client, seed_data["viewer"])
        response = client.post(
            "/api/v1/proposals/calculate",
            json={
                "character_id": seed_data["pc1"].id,
                "action_type": "use_skill",
            },
        )
        assert response.status_code == 403

    def test_viewer_cannot_patch_character(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """PATCH /characters/{id} returns 403 for viewer.

        The route fetches the character before the role check (returning 404 if
        not found), so a real character ID from seed data is required.
        """
        auth_as(client, seed_data["viewer"])
        response = client.patch(
            f"/api/v1/characters/{seed_data['pc1'].id}",
            json={"name": "Renamed"},
        )
        assert response.status_code == 403


# ===========================================================================
# 5. Starring — viewer CAN do this
# ===========================================================================


class TestViewerStarring:
    """Viewer can star, list, and unstar game objects."""

    def test_viewer_can_star_a_character(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """POST /me/starred returns 201 when a viewer stars a character."""
        auth_as(client, seed_data["viewer"])
        response = client.post(
            "/api/v1/me/starred",
            json={"type": "character", "id": seed_data["pc1"].id},
        )
        assert response.status_code == 201

    def test_viewer_star_response_shape(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """Viewer starring response includes type, id, and name."""
        auth_as(client, seed_data["viewer"])
        response = client.post(
            "/api/v1/me/starred",
            json={"type": "character", "id": seed_data["pc1"].id},
        )
        body = response.json()
        assert body["type"] == "character"
        assert body["id"] == seed_data["pc1"].id
        assert body["name"] == seed_data["pc1"].name

    def test_viewer_can_star_a_group(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """POST /me/starred returns 201 when a viewer stars a group."""
        auth_as(client, seed_data["viewer"])
        response = client.post(
            "/api/v1/me/starred",
            json={"type": "group", "id": seed_data["group"].id},
        )
        assert response.status_code == 201

    def test_viewer_can_star_a_location(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """POST /me/starred returns 201 when a viewer stars a location."""
        auth_as(client, seed_data["viewer"])
        response = client.post(
            "/api/v1/me/starred",
            json={"type": "location", "id": seed_data["region"].id},
        )
        assert response.status_code == 201

    def test_viewer_can_list_starred(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """GET /me/starred returns 200 and the viewer's starred items."""
        viewer = seed_data["viewer"]
        db.add(
            StarredObject(
                user_id=viewer.id,
                object_type="group",
                object_id=seed_data["group"].id,
            )
        )
        db.commit()

        auth_as(client, viewer)
        response = client.get("/api/v1/me/starred")

        assert response.status_code == 200
        items = response.json()
        assert len(items) == 1
        assert items[0]["type"] == "group"
        assert items[0]["id"] == seed_data["group"].id

    def test_viewer_starred_list_is_isolated(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """Viewer only sees their own starred objects, not other users'."""
        # Player1 stars the group.
        db.add(
            StarredObject(
                user_id=seed_data["player1"].id,
                object_type="group",
                object_id=seed_data["group"].id,
            )
        )
        db.commit()

        auth_as(client, seed_data["viewer"])
        response = client.get("/api/v1/me/starred")

        assert response.status_code == 200
        assert response.json() == []

    def test_viewer_can_unstar(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """DELETE /me/starred/{type}/{id} returns 204 for a viewer."""
        viewer = seed_data["viewer"]
        group = seed_data["group"]

        db.add(
            StarredObject(
                user_id=viewer.id,
                object_type="group",
                object_id=group.id,
            )
        )
        db.commit()

        auth_as(client, viewer)
        response = client.delete(f"/api/v1/me/starred/group/{group.id}")

        assert response.status_code == 204

    def test_viewer_unstar_removes_row(
        self, client: TestClient, seed_data: dict, db: Session
    ) -> None:
        """After viewer unstar, the starred_objects row is gone."""
        viewer = seed_data["viewer"]
        group = seed_data["group"]

        db.add(
            StarredObject(
                user_id=viewer.id,
                object_type="group",
                object_id=group.id,
            )
        )
        db.commit()

        auth_as(client, viewer)
        client.delete(f"/api/v1/me/starred/group/{group.id}")

        db.expire_all()
        row = db.get(
            StarredObject,
            {"user_id": viewer.id, "object_type": "group", "object_id": group.id},
        )
        assert row is None

    def test_viewer_unstar_not_starred_returns_204(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """DELETE /me/starred is idempotent for viewers — 204 even if not starred."""
        auth_as(client, seed_data["viewer"])
        response = client.delete(
            f"/api/v1/me/starred/group/{seed_data['group'].id}"
        )
        assert response.status_code == 204

    def test_viewer_star_then_list_then_unstar_roundtrip(
        self, client: TestClient, seed_data: dict
    ) -> None:
        """Full viewer starring round-trip: star → list → unstar → empty list."""
        viewer = seed_data["viewer"]
        region = seed_data["region"]

        auth_as(client, viewer)

        r1 = client.post(
            "/api/v1/me/starred", json={"type": "location", "id": region.id}
        )
        assert r1.status_code == 201

        r2 = client.get("/api/v1/me/starred")
        assert r2.status_code == 200
        assert any(item["id"] == region.id for item in r2.json())

        r3 = client.delete(f"/api/v1/me/starred/location/{region.id}")
        assert r3.status_code == 204

        r4 = client.get("/api/v1/me/starred")
        assert r4.status_code == 200
        assert not any(item["id"] == region.id for item in r4.json())
