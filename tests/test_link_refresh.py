"""Tests for Story 3.1.3 — link refresh and token regeneration.

Covers:
- POST /api/v1/me/refresh-link (any authenticated user):
  - Returns 200 with {"login_url": "/login/<new_code>"}
  - New code is 43 chars (secrets.token_urlsafe(32) output)
  - Old cookie / link stops working immediately after refresh
  - Cookie is updated with the new code (Set-Cookie header present)
  - Works for both GM and player

- POST /api/v1/players/{id}/regenerate-token (GM only):
  - Returns 200 with {"login_url": "/login/<new_code>"}
  - Old link for the target player stops working immediately
  - GM's own cookie is NOT changed
  - 404 if player id not found
  - 403 if called by a player
"""

from tests.conftest import auth_as
from wizards_engine.api.auth import COOKIE_NAME
from wizards_engine.models.user import User

_REFRESH_URL = "/api/v1/me/refresh-link"
_REGEN_URL = "/api/v1/players/{id}/regenerate-token"


# ---------------------------------------------------------------------------
# POST /me/refresh-link — happy path
# ---------------------------------------------------------------------------


def test_refresh_link_returns_200(client, seed_data):
    """POST /me/refresh-link returns HTTP 200."""
    gm = seed_data["gm"]
    auth_as(client, gm)
    response = client.post(_REFRESH_URL)
    assert response.status_code == 200


def test_refresh_link_returns_login_url(client, seed_data):
    """Response contains a login_url key."""
    player = seed_data["player1"]
    auth_as(client, player)
    response = client.post(_REFRESH_URL)
    body = response.json()
    assert "login_url" in body
    assert body["login_url"].startswith("/login/")


def test_refresh_link_new_code_length(client, seed_data):
    """New code from secrets.token_urlsafe(32) is 43 characters."""
    player = seed_data["player1"]
    auth_as(client, player)
    response = client.post(_REFRESH_URL)
    login_url = response.json()["login_url"]
    new_code = login_url.split("/login/")[1]
    assert len(new_code) == 43, f"Expected 43-char token_urlsafe(32) code, got {len(new_code)}"


def test_refresh_link_updates_db_login_code(client, db, seed_data):
    """After refresh, the user's login_code in the DB is updated."""
    player = seed_data["player1"]
    old_code = player.login_code
    auth_as(client, player)
    response = client.post(_REFRESH_URL)
    new_code = response.json()["login_url"].split("/login/")[1]

    db.expire(player)
    refreshed = db.get(User, player.id)
    assert refreshed.login_code != old_code
    assert refreshed.login_code == new_code


def test_refresh_link_old_code_stops_working(client, seed_data):
    """After refresh, using the old login code returns 401."""
    player = seed_data["player1"]
    old_code = player.login_code
    auth_as(client, player)

    # Refresh the link.
    client.post(_REFRESH_URL)

    # Now use the old code — must be rejected.
    client.cookies.set(COOKIE_NAME, old_code)
    response = client.get("/api/v1/me")
    assert response.status_code == 401


def test_refresh_link_updates_cookie(client, seed_data):
    """POST /me/refresh-link sets a new Set-Cookie header with the new code."""
    player = seed_data["player1"]
    auth_as(client, player)
    response = client.post(_REFRESH_URL)
    set_cookie = response.headers.get("set-cookie", "")
    assert COOKIE_NAME in set_cookie


def test_refresh_link_cookie_value_is_new_code(client, seed_data):
    """The new cookie value matches the code in login_url."""
    player = seed_data["player1"]
    auth_as(client, player)
    response = client.post(_REFRESH_URL)
    new_code_from_url = response.json()["login_url"].split("/login/")[1]
    new_code_from_cookie = response.cookies.get(COOKIE_NAME)
    assert new_code_from_cookie == new_code_from_url


def test_refresh_link_cookie_is_httponly(client, seed_data):
    """Updated cookie is httpOnly."""
    player = seed_data["player1"]
    auth_as(client, player)
    response = client.post(_REFRESH_URL)
    set_cookie = response.headers.get("set-cookie", "")
    assert "HttpOnly" in set_cookie


def test_refresh_link_works_for_gm(client, seed_data):
    """GM can also refresh their own link."""
    gm = seed_data["gm"]
    auth_as(client, gm)
    response = client.post(_REFRESH_URL)
    assert response.status_code == 200
    assert "login_url" in response.json()


def test_refresh_link_unauthenticated_returns_401(client):
    """Unauthenticated POST /me/refresh-link returns 401."""
    client.cookies.clear()
    response = client.post(_REFRESH_URL)
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /players/{id}/regenerate-token — happy path
# ---------------------------------------------------------------------------


def test_regen_token_returns_200(client, seed_data):
    """GM POST /players/{id}/regenerate-token returns HTTP 200."""
    gm = seed_data["gm"]
    player = seed_data["player1"]
    auth_as(client, gm)
    response = client.post(_REGEN_URL.format(id=player.id))
    assert response.status_code == 200


def test_regen_token_returns_login_url(client, seed_data):
    """Response contains a login_url for the target player."""
    gm = seed_data["gm"]
    player = seed_data["player1"]
    auth_as(client, gm)
    response = client.post(_REGEN_URL.format(id=player.id))
    body = response.json()
    assert "login_url" in body
    assert body["login_url"].startswith("/login/")


def test_regen_token_new_code_length(client, seed_data):
    """Regenerated code is 43 characters (token_urlsafe(32))."""
    gm = seed_data["gm"]
    player = seed_data["player1"]
    auth_as(client, gm)
    response = client.post(_REGEN_URL.format(id=player.id))
    new_code = response.json()["login_url"].split("/login/")[1]
    assert len(new_code) == 43


def test_regen_token_updates_db_login_code(client, db, seed_data):
    """After regen, the target player's login_code in the DB is updated."""
    gm = seed_data["gm"]
    player = seed_data["player1"]
    old_code = player.login_code
    auth_as(client, gm)
    response = client.post(_REGEN_URL.format(id=player.id))
    new_code = response.json()["login_url"].split("/login/")[1]

    db.expire(player)
    refreshed = db.get(User, player.id)
    assert refreshed.login_code != old_code
    assert refreshed.login_code == new_code


def test_regen_token_old_code_stops_working(client, seed_data):
    """After regen, the player's old code returns 401."""
    gm = seed_data["gm"]
    player = seed_data["player1"]
    old_code = player.login_code
    auth_as(client, gm)

    client.post(_REGEN_URL.format(id=player.id))

    # Attempt to use the old code.
    client.cookies.set(COOKIE_NAME, old_code)
    response = client.get("/api/v1/me")
    assert response.status_code == 401


def test_regen_token_does_not_change_gm_cookie(client, seed_data):
    """Regenerating a player's token does NOT set a Set-Cookie for the GM."""
    gm = seed_data["gm"]
    player = seed_data["player1"]
    auth_as(client, gm)
    response = client.post(_REGEN_URL.format(id=player.id))
    # The response must not include a Set-Cookie header.
    assert "set-cookie" not in response.headers


def test_regen_token_gm_can_regen_own_token(client, seed_data):
    """GM can regenerate their own token via the players endpoint."""
    gm = seed_data["gm"]
    auth_as(client, gm)
    response = client.post(_REGEN_URL.format(id=gm.id))
    assert response.status_code == 200
    assert "login_url" in response.json()


# ---------------------------------------------------------------------------
# POST /players/{id}/regenerate-token — error cases
# ---------------------------------------------------------------------------


def test_regen_token_not_found_returns_404(client, seed_data):
    """An unknown player id returns 404 with player_not_found."""
    gm = seed_data["gm"]
    auth_as(client, gm)
    response = client.post(_REGEN_URL.format(id="01NONEXISTENTULID000000000"))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "player_not_found"


def test_regen_token_player_cannot_call_endpoint(client, seed_data):
    """A player calling the regen endpoint receives 403."""
    player1 = seed_data["player1"]
    player2 = seed_data["player2"]
    auth_as(client, player1)
    response = client.post(_REGEN_URL.format(id=player2.id))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "insufficient_role"


def test_regen_token_unauthenticated_returns_401(client, seed_data):
    """An unauthenticated regenerate-token request returns 401."""
    player = seed_data["player1"]
    client.cookies.clear()
    response = client.post(_REGEN_URL.format(id=player.id))
    assert response.status_code == 401
