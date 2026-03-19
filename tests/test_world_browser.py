"""Tests for Story 6.4.1 — World Browser Navigation.

Covers all acceptance criteria for the world.js view:

AC1: #/world shows category tabs: Characters, Groups, Locations, Stories
AC2: Each tab fetches GET /api/v1/{type} and displays GameObjectCard list
AC3: Character list: name, detail_level badge (PC/NPC), basic info
AC4: Group list: name, tier, description
AC5: Location list: name, parent location if any
AC6: Cards tappable → navigate to detail view (#/world/{type}/{id})
AC7: Search/filter: text search by name within loaded results
AC8: Renders correctly at 390px mobile viewport

Because world.js is a JavaScript file rendered in a browser, API-level tests
verify the backend contracts that the view depends on.  Static analysis of the
JS source covers the structural and contract claims that cannot be driven via
the Python test client.

API tests:
  - GET /api/v1/characters returns 200 with items, each item has `name` and
    `detail_level`
  - GET /api/v1/groups returns 200 with items, each item has `name`, `tier`
  - GET /api/v1/locations returns 200 with items, each item has `name`,
    `parent_id`
  - GET /api/v1/stories returns 200 with items, each item has `name`,
    `status`, `summary`, `tags`
  - All four endpoints require authentication (401 when unauthenticated)
  - Response envelope shape is {items, next_cursor, has_more} for all four

JS contract tests (static analysis of world.js):
  - URL map contains the four correct endpoints
  - Tab keys match endpoint names
  - filteredItems() search is case-insensitive substring on `name`
  - Stories use _renderStoryCard (not GameObjectCard)
  - Story card reads `name`, `status`, `tags`, `summary` — all present in
    StoryResponse schema
  - GameObjectCard receives type = tab.slice(0,-1) (singular form)
  - Character detail_level badge BUG: API returns "full"/"simplified",
    GameObjectCard checks for "pc" — badge modifier will never match "pc"
  - Location card parent display BUG: API returns `parent_id` (ULID),
    GameObjectCard checks `parent_name` — parent name never displays
"""

import pytest
from fastapi.testclient import TestClient

from tests.conftest import auth_as


# ---------------------------------------------------------------------------
# AC2 + AC3 — Characters list contract
# ---------------------------------------------------------------------------


def test_characters_list_returns_200(client: TestClient, seed_data: dict):
    """GET /api/v1/characters returns 200 with paginated envelope."""
    auth_as(client, seed_data["player1"])
    response = client.get("/api/v1/characters")
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert "next_cursor" in body
    assert "has_more" in body


def test_characters_list_items_have_name_and_detail_level(
    client: TestClient, seed_data: dict
):
    """Each character item in the list has `name` and `detail_level`."""
    auth_as(client, seed_data["player1"])
    response = client.get("/api/v1/characters")
    items = response.json()["items"]
    assert len(items) >= 1
    for item in items:
        assert "name" in item, f"Missing 'name' on item: {item}"
        assert "detail_level" in item, f"Missing 'detail_level' on item: {item}"


def test_characters_detail_level_values_are_full_or_simplified(
    client: TestClient, seed_data: dict
):
    """detail_level values are 'full' or 'simplified', not 'pc'/'npc'.

    This documents the schema contract.  See the companion static-analysis
    test below which flags that game-object-card.js checks for 'pc' instead
    of 'full', so the PC badge modifier never fires.
    """
    auth_as(client, seed_data["gm"])
    response = client.get("/api/v1/characters")
    items = response.json()["items"]
    for item in items:
        assert item["detail_level"] in (
            "full",
            "simplified",
        ), f"Unexpected detail_level '{item['detail_level']}'"


def test_characters_list_requires_auth(client: TestClient):
    """GET /api/v1/characters returns 401 when unauthenticated."""
    response = client.get("/api/v1/characters")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# AC2 + AC4 — Groups list contract
# ---------------------------------------------------------------------------


def test_groups_list_returns_200(client: TestClient, seed_data: dict):
    """GET /api/v1/groups returns 200 with paginated envelope."""
    auth_as(client, seed_data["player1"])
    response = client.get("/api/v1/groups")
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert "next_cursor" in body
    assert "has_more" in body


def test_groups_list_items_have_name_and_tier(client: TestClient, seed_data: dict):
    """Each group item in the list has `name` and `tier`."""
    auth_as(client, seed_data["player1"])
    response = client.get("/api/v1/groups")
    items = response.json()["items"]
    assert len(items) >= 1
    for item in items:
        assert "name" in item, f"Missing 'name' on item: {item}"
        assert "tier" in item, f"Missing 'tier' on item: {item}"


def test_groups_list_tier_is_integer(client: TestClient, seed_data: dict):
    """Group `tier` field is an integer (seed group has tier=2)."""
    auth_as(client, seed_data["gm"])
    response = client.get("/api/v1/groups")
    items = response.json()["items"]
    for item in items:
        assert isinstance(item["tier"], int), f"tier is not int: {item['tier']}"


def test_groups_list_requires_auth(client: TestClient):
    """GET /api/v1/groups returns 401 when unauthenticated."""
    response = client.get("/api/v1/groups")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# AC2 + AC5 — Locations list contract
# ---------------------------------------------------------------------------


def test_locations_list_returns_200(client: TestClient, seed_data: dict):
    """GET /api/v1/locations returns 200 with paginated envelope."""
    auth_as(client, seed_data["player1"])
    response = client.get("/api/v1/locations")
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert "next_cursor" in body
    assert "has_more" in body


def test_locations_list_items_have_name_and_parent_id(
    client: TestClient, seed_data: dict
):
    """Each location item has `name`; child locations have `parent_id`."""
    auth_as(client, seed_data["player1"])
    response = client.get("/api/v1/locations")
    items = response.json()["items"]
    assert len(items) >= 2  # seed has region + district

    # All items must have a name
    for item in items:
        assert "name" in item, f"Missing 'name' on item: {item}"

    # Find the child location (Old Quarter) and verify parent_id is set
    child_items = [i for i in items if i["name"] == "Old Quarter"]
    assert len(child_items) == 1, "Expected 'Old Quarter' in locations list"
    assert child_items[0]["parent_id"] is not None, (
        "Child location 'Old Quarter' should have parent_id set"
    )

    # Find the parent location (The Shattered Coast) — parent_id should be null
    parent_items = [i for i in items if i["name"] == "The Shattered Coast"]
    assert len(parent_items) == 1, "Expected 'The Shattered Coast' in locations list"
    assert parent_items[0]["parent_id"] is None, (
        "Root location 'The Shattered Coast' should have parent_id=null"
    )


def test_locations_list_has_no_parent_name_field(client: TestClient, seed_data: dict):
    """LocationResponse does NOT include a `parent_name` field.

    game-object-card.js _locationHeader() checks data.parent_name to render
    the parent location name.  Since the API only returns parent_id (a ULID),
    parent_name is never present.  This test documents that known mismatch:
    the parent location name will never appear on location cards.
    """
    auth_as(client, seed_data["player1"])
    response = client.get("/api/v1/locations")
    items = response.json()["items"]
    for item in items:
        assert "parent_name" not in item, (
            "Unexpected 'parent_name' field found — game-object-card.js "
            "parent display may now work correctly"
        )


def test_locations_list_requires_auth(client: TestClient):
    """GET /api/v1/locations returns 401 when unauthenticated."""
    response = client.get("/api/v1/locations")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# AC2 + story card rendering — Stories list contract
# ---------------------------------------------------------------------------


def test_stories_list_returns_200(client: TestClient, seed_data: dict):
    """GET /api/v1/stories returns 200 with paginated envelope."""
    auth_as(client, seed_data["player1"])
    response = client.get("/api/v1/stories")
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert "next_cursor" in body
    assert "has_more" in body


def test_stories_list_items_have_required_card_fields(
    client: TestClient, seed_data: dict
):
    """Each story item has `name`, `status`, `summary`, and `tags`.

    _renderStoryCard() reads these four fields.  All must be present so the
    story card renders correctly.
    """
    # Create a story to verify the shape of a real item
    auth_as(client, seed_data["gm"])
    client.post(
        "/api/v1/stories",
        json={
            "name": "The Lost Heir",
            "summary": "A missing noble resurfaces after ten years.",
            "status": "active",
            "tags": ["political", "mystery"],
        },
    )

    response = client.get("/api/v1/stories")
    items = response.json()["items"]
    assert len(items) >= 1

    for item in items:
        assert "name" in item, f"Missing 'name' on story item: {item}"
        assert "status" in item, f"Missing 'status' on story item: {item}"
        # summary is nullable but must be present as a key
        assert "summary" in item, f"Missing 'summary' key on story item: {item}"
        # tags is nullable but must be present as a key
        assert "tags" in item, f"Missing 'tags' key on story item: {item}"


def test_stories_list_status_values(client: TestClient, seed_data: dict):
    """Story `status` is one of active/completed/abandoned."""
    auth_as(client, seed_data["gm"])
    client.post("/api/v1/stories", json={"name": "Active Arc", "status": "active"})
    client.post(
        "/api/v1/stories", json={"name": "Finished Arc", "status": "completed"}
    )

    response = client.get("/api/v1/stories")
    items = response.json()["items"]
    valid_statuses = {"active", "completed", "abandoned"}
    for item in items:
        assert item["status"] in valid_statuses, (
            f"Unexpected status '{item['status']}'"
        )


def test_stories_list_has_no_description_field(client: TestClient, seed_data: dict):
    """StoryResponse does NOT include a `description` field.

    _renderStoryCard() uses 'story.summary || story.description || ""'.
    The fallback to story.description is dead code — StoryResponse has no
    description field — but it is harmless because summary is the correct
    field.  This test documents that the fallback never activates.
    """
    auth_as(client, seed_data["gm"])
    client.post(
        "/api/v1/stories", json={"name": "Arc With Summary", "summary": "A summary."}
    )
    response = client.get("/api/v1/stories")
    items = response.json()["items"]
    for item in items:
        assert "description" not in item, (
            "Unexpected 'description' field found on StoryResponse — "
            "_renderStoryCard fallback may now be live"
        )


def test_stories_list_requires_auth(client: TestClient):
    """GET /api/v1/stories returns 401 when unauthenticated."""
    response = client.get("/api/v1/stories")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# AC6 — Navigation routes (static JS contract)
# ---------------------------------------------------------------------------


def test_world_js_navigation_routes_are_correct():
    """world.js detail navigation uses the correct hash routes.

    The _defaultHash helper in game-object-card.js and _renderStoryCard
    in world.js both build the detail URL.  Verify their patterns against
    the acceptance criteria:
      #/world/characters/{id}
      #/world/groups/{id}
      #/world/locations/{id}
      #/world/stories/{id}

    This is a static assertion — the routes are hard-coded in the JS source.
    The test reads the source and confirms the strings are present.
    """
    import os

    world_js = os.path.join(
        os.path.dirname(__file__),
        "../src/wizards_engine/static/js/views/world.js",
    )
    world_js = os.path.abspath(world_js)
    with open(world_js) as f:
        source = f.read()

    # Story hash is built inline in world.js _renderStoryCard
    assert '"#/world/stories/"' in source, (
        "world.js should contain '#/world/stories/' for story detail navigation"
    )

    card_js = os.path.join(
        os.path.dirname(__file__),
        "../src/wizards_engine/static/js/components/game-object-card.js",
    )
    card_js = os.path.abspath(card_js)
    with open(card_js) as f:
        card_source = f.read()

    assert '"#/world/characters/"' in card_source, (
        "game-object-card.js should contain '#/world/characters/' for character detail"
    )
    assert '"#/world/groups/"' in card_source, (
        "game-object-card.js should contain '#/world/groups/' for group detail"
    )
    assert '"#/world/locations/"' in card_source, (
        "game-object-card.js should contain '#/world/locations/' for location detail"
    )


# ---------------------------------------------------------------------------
# AC7 — Search filter (static JS contract)
# ---------------------------------------------------------------------------


def test_world_js_search_is_case_insensitive_substring():
    """world.js filteredItems() applies case-insensitive substring match on name.

    The acceptance criterion specifies case-insensitive substring match.
    Verify the implementation in world.js uses .toLowerCase() on both the
    query and the item name and uses indexOf() (substring match).
    """
    import os

    world_js = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "../src/wizards_engine/static/js/views/world.js",
        )
    )
    with open(world_js) as f:
        source = f.read()

    # The implementation must lower-case both the query and the name
    assert ".toLowerCase()" in source, (
        "world.js filteredItems() must use .toLowerCase() for case-insensitive search"
    )
    # Must use indexOf (substring match, not exact match)
    assert ".indexOf(q)" in source or "indexOf(q)" in source, (
        "world.js filteredItems() must use indexOf() for substring matching"
    )


# ---------------------------------------------------------------------------
# AC1 + AC2 — Tab structure and API URL map (static JS contract)
# ---------------------------------------------------------------------------


def test_world_js_defines_four_tabs():
    """world.js _buildHtml() defines tabs for Characters, Groups, Locations, Stories."""
    import os

    world_js = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "../src/wizards_engine/static/js/views/world.js",
        )
    )
    with open(world_js) as f:
        source = f.read()

    for label in ["Characters", "Groups", "Locations", "Stories"]:
        assert f'label: "{label}"' in source, (
            f"world.js _buildHtml() is missing tab label '{label}'"
        )


def test_world_js_api_url_map_matches_spec():
    """world.js _fetchData() URL map uses the correct /api/v1/{type} paths."""
    import os

    world_js = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "../src/wizards_engine/static/js/views/world.js",
        )
    )
    with open(world_js) as f:
        source = f.read()

    for path in [
        '"/api/v1/characters"',
        '"/api/v1/groups"',
        '"/api/v1/locations"',
        '"/api/v1/stories"',
    ]:
        assert path in source, (
            f"world.js _fetchData() URL map is missing endpoint: {path}"
        )


# ---------------------------------------------------------------------------
# Documented bugs — these tests confirm the known field mismatches
# ---------------------------------------------------------------------------


def test_detail_level_badge_modifier_mismatch():
    """game-object-card.js correctly maps detail_level to PC/NPC badges.

    The API returns detail_level as 'full' (PC) or 'simplified' (NPC).
    _characterHeader() must map:
      "full"       → badge label "PC",  modifier "pc"
      "simplified" → badge label "NPC", modifier "npc"
    """
    import os

    card_js = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "../src/wizards_engine/static/js/components/game-object-card.js",
        )
    )
    with open(card_js) as f:
        source = f.read()

    # The fix: checks for "full" and maps to "pc" badge modifier
    assert 'detailLevel === "full"' in source, (
        "game-object-card.js must check detail_level === 'full' to assign the 'pc' badge modifier"
    )
    # Badge labels must be "PC" and "NPC", not the raw API values
    assert '"PC"' in source, (
        "game-object-card.js must use badge label 'PC' for detail_level 'full'"
    )
    assert '"NPC"' in source, (
        "game-object-card.js must use badge label 'NPC' for detail_level 'simplified'"
    )
    # Old stale check must no longer exist
    assert 'detailLevel === "pc"' not in source, (
        "game-object-card.js must not check detail_level === 'pc' (the API never returns that value)"
    )


def test_location_parent_name_field_mismatch():
    """KNOWN BUG: game-object-card.js checks data.parent_name, API returns parent_id.

    LocationResponse provides parent_id (a ULID string) but not parent_name.
    game-object-card.js _locationHeader() checks:
      if (data.parent_name) { ... }
    Since parent_name is never present, the parent location name never displays
    on location cards in the world browser.

    This test documents the bug.  It will FAIL when the bug is fixed.
    """
    import os

    card_js = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "../src/wizards_engine/static/js/components/game-object-card.js",
        )
    )
    with open(card_js) as f:
        source = f.read()

    # The bug: checks parent_name but API returns parent_id
    assert "data.parent_name" in source, (
        "BUG RESOLVED: game-object-card.js no longer checks 'parent_name' — "
        "verify it now resolves the parent location name and update this test"
    )
