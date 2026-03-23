"""Tests for Story 8.4.1 — Backend: Add Sort/Filter Params to List Endpoints.

Covers acceptance criteria:

1. GET /characters?sort_by=name&sort_dir=desc returns characters Z→A
2. GET /groups?name=guild&sort_by=created_at returns matching groups sorted by creation
3. GET /locations?name=tower&sort_by=name returns matching locations sorted alphabetically
4. GET /stories?sort_by=updated_at&sort_dir=desc returns stories most-recently-updated first
5. Default behavior unchanged (existing tests pass — covered by existing test files)
6. Pagination cursor works correctly with non-default sort orders
7. Backend tests cover sort params and name filters for all four endpoints

Also covers:
- Invalid sort_by / sort_dir return 422
- Name filter (groups, locations) is case-insensitive partial match
"""

import pytest
from fastapi.testclient import TestClient

from tests.conftest import auth_as


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_group(client, seed_data, name: str, tier: int = 1) -> dict:
    """Create a group and return the response body."""
    auth_as(client, seed_data["gm"])
    resp = client.post("/api/v1/groups", json={"name": name, "tier": tier})
    assert resp.status_code == 201
    return resp.json()


def _create_location(client, seed_data, name: str) -> dict:
    """Create a location and return the response body."""
    auth_as(client, seed_data["gm"])
    resp = client.post("/api/v1/locations", json={"name": name})
    assert resp.status_code == 201
    return resp.json()


def _create_story(client, seed_data, name: str) -> dict:
    """Create a story and return the response body."""
    auth_as(client, seed_data["gm"])
    resp = client.post("/api/v1/stories", json={"name": name})
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# Characters — sort_by / sort_dir
# ---------------------------------------------------------------------------


class TestCharactersSortParams:
    def test_sort_by_name_asc_default(self, client: TestClient, seed_data: dict):
        """GET /characters returns names in ascending order by default."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/characters")
        assert response.status_code == 200
        items = response.json()["items"]
        names = [c["name"] for c in items]
        assert names == sorted(names)

    def test_sort_by_name_desc(self, client: TestClient, seed_data: dict):
        """GET /characters?sort_by=name&sort_dir=desc returns names Z→A."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/characters?sort_by=name&sort_dir=desc")
        assert response.status_code == 200
        items = response.json()["items"]
        names = [c["name"] for c in items]
        assert names == sorted(names, reverse=True)

    def test_sort_by_created_at_asc(self, client: TestClient, seed_data: dict):
        """GET /characters?sort_by=created_at&sort_dir=asc returns oldest-first."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/characters?sort_by=created_at&sort_dir=asc")
        assert response.status_code == 200
        items = response.json()["items"]
        created_ats = [c["created_at"] for c in items]
        assert created_ats == sorted(created_ats)

    def test_sort_by_created_at_desc(self, client: TestClient, seed_data: dict):
        """GET /characters?sort_by=created_at&sort_dir=desc returns newest-first."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/characters?sort_by=created_at&sort_dir=desc")
        assert response.status_code == 200
        items = response.json()["items"]
        created_ats = [c["created_at"] for c in items]
        assert created_ats == sorted(created_ats, reverse=True)

    def test_sort_by_updated_at(self, client: TestClient, seed_data: dict):
        """GET /characters?sort_by=updated_at&sort_dir=desc returns recently-updated first."""
        auth_as(client, seed_data["gm"])
        # Touch pc1 to move its updated_at to newest.
        pc1_id = seed_data["pc1"].id
        client.patch(f"/api/v1/characters/{pc1_id}", json={"notes": "touched"})

        response = client.get("/api/v1/characters?sort_by=updated_at&sort_dir=desc")
        assert response.status_code == 200
        items = response.json()["items"]
        updated_ats = [c["updated_at"] for c in items]
        assert updated_ats == sorted(updated_ats, reverse=True)
        # The most-recently-updated character should appear first.
        assert items[0]["id"] == pc1_id

    def test_sort_by_invalid_returns_422(self, client: TestClient, seed_data: dict):
        """Invalid sort_by value returns 422."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/characters?sort_by=invalid_column")
        assert response.status_code == 422
        assert "sort_by" in str(response.json())

    def test_sort_dir_invalid_returns_422(self, client: TestClient, seed_data: dict):
        """Invalid sort_dir value returns 422."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/characters?sort_dir=sideways")
        assert response.status_code == 422
        assert "sort_dir" in str(response.json())

    def test_sort_pagination_cursor_name_asc(self, client: TestClient, seed_data: dict):
        """Cursor pagination works correctly with name ascending sort."""
        auth_as(client, seed_data["gm"])
        # Seed has 5 characters; fetch 2 at a time sorted by name.
        page1 = client.get(
            "/api/v1/characters?sort_by=name&sort_dir=asc&limit=2"
        ).json()
        assert len(page1["items"]) == 2
        assert page1["has_more"] is True
        assert page1["next_cursor"] is not None

        page2 = client.get(
            f"/api/v1/characters?sort_by=name&sort_dir=asc&limit=2&after={page1['next_cursor']}"
        ).json()
        assert len(page2["items"]) == 2

        # No overlapping IDs between pages.
        page1_ids = {c["id"] for c in page1["items"]}
        page2_ids = {c["id"] for c in page2["items"]}
        assert page1_ids.isdisjoint(page2_ids)

        # Page 2 names must be alphabetically >= page 1 names.
        assert min(c["name"] for c in page2["items"]) >= max(
            c["name"] for c in page1["items"]
        )

    def test_sort_pagination_cursor_name_desc(self, client: TestClient, seed_data: dict):
        """Cursor pagination works correctly with name descending sort."""
        auth_as(client, seed_data["gm"])
        page1 = client.get(
            "/api/v1/characters?sort_by=name&sort_dir=desc&limit=2"
        ).json()
        assert len(page1["items"]) == 2
        assert page1["has_more"] is True

        page2 = client.get(
            f"/api/v1/characters?sort_by=name&sort_dir=desc&limit=2&after={page1['next_cursor']}"
        ).json()
        assert len(page2["items"]) == 2

        page1_ids = {c["id"] for c in page1["items"]}
        page2_ids = {c["id"] for c in page2["items"]}
        assert page1_ids.isdisjoint(page2_ids)

        # Page 2 names must be alphabetically <= page 1 names (descending).
        assert max(c["name"] for c in page2["items"]) <= min(
            c["name"] for c in page1["items"]
        )


# ---------------------------------------------------------------------------
# Groups — name filter, sort_by, sort_dir
# ---------------------------------------------------------------------------


class TestGroupsSortFilterParams:
    def test_name_filter_partial_match(self, client: TestClient, seed_data: dict):
        """GET /groups?name=guild returns groups whose name contains 'guild'."""
        auth_as(client, seed_data["gm"])
        _create_group(client, seed_data, "The Merchant Guild")
        _create_group(client, seed_data, "The Thieves Guild")
        _create_group(client, seed_data, "The Syndicate")  # should not match

        response = client.get("/api/v1/groups?name=guild")
        assert response.status_code == 200
        items = response.json()["items"]
        names = [g["name"] for g in items]
        assert "The Merchant Guild" in names
        assert "The Thieves Guild" in names
        assert "The Syndicate" not in names

    def test_name_filter_case_insensitive(self, client: TestClient, seed_data: dict):
        """Name filter is case-insensitive."""
        auth_as(client, seed_data["gm"])
        _create_group(client, seed_data, "The Merchant Guild")

        response = client.get("/api/v1/groups?name=GUILD")
        assert response.status_code == 200
        names = [g["name"] for g in response.json()["items"]]
        assert "The Merchant Guild" in names

    def test_name_filter_no_match_returns_empty(self, client: TestClient, seed_data: dict):
        """Name filter with no matches returns empty items list."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/groups?name=xyzzy_no_match_xyzzy")
        assert response.status_code == 200
        assert response.json()["items"] == []

    def test_sort_by_name_asc_default(self, client: TestClient, seed_data: dict):
        """Groups are returned in name ascending order by default."""
        auth_as(client, seed_data["gm"])
        _create_group(client, seed_data, "Alpha Group")
        _create_group(client, seed_data, "Zeta Group")

        response = client.get("/api/v1/groups")
        assert response.status_code == 200
        names = [g["name"] for g in response.json()["items"]]
        assert names == sorted(names)

    def test_sort_by_name_desc(self, client: TestClient, seed_data: dict):
        """GET /groups?sort_by=name&sort_dir=desc returns groups Z→A."""
        auth_as(client, seed_data["gm"])
        _create_group(client, seed_data, "Alpha Group")
        _create_group(client, seed_data, "Zeta Group")

        response = client.get("/api/v1/groups?sort_by=name&sort_dir=desc")
        assert response.status_code == 200
        names = [g["name"] for g in response.json()["items"]]
        assert names == sorted(names, reverse=True)

    def test_sort_by_created_at_with_name_filter(self, client: TestClient, seed_data: dict):
        """Acceptance criterion 2: GET /groups?name=guild&sort_by=created_at works."""
        auth_as(client, seed_data["gm"])
        _create_group(client, seed_data, "Merchants Guild")
        _create_group(client, seed_data, "Thieves Guild")

        response = client.get("/api/v1/groups?name=guild&sort_by=created_at&sort_dir=asc")
        assert response.status_code == 200
        items = response.json()["items"]
        names = [g["name"] for g in items]
        assert all("guild" in n.lower() for n in names)
        created_ats = [g["created_at"] for g in items]
        assert created_ats == sorted(created_ats)

    def test_sort_by_invalid_returns_422(self, client: TestClient, seed_data: dict):
        """Invalid sort_by value returns 422."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/groups?sort_by=tier")
        assert response.status_code == 422

    def test_sort_dir_invalid_returns_422(self, client: TestClient, seed_data: dict):
        """Invalid sort_dir value returns 422."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/groups?sort_dir=random")
        assert response.status_code == 422

    def test_sort_pagination_cursor_name_asc(self, client: TestClient, seed_data: dict):
        """Cursor pagination works with name-sorted groups."""
        auth_as(client, seed_data["gm"])
        # Create 3 more groups: seed has 1 ("The Syndicate"), total = 4.
        for letter in ["Alpha", "Beta", "Gamma"]:
            _create_group(client, seed_data, f"{letter} Faction")

        page1 = client.get("/api/v1/groups?sort_by=name&sort_dir=asc&limit=2").json()
        assert len(page1["items"]) == 2
        assert page1["has_more"] is True

        page2 = client.get(
            f"/api/v1/groups?sort_by=name&sort_dir=asc&limit=2&after={page1['next_cursor']}"
        ).json()
        assert len(page2["items"]) == 2

        page1_ids = {g["id"] for g in page1["items"]}
        page2_ids = {g["id"] for g in page2["items"]}
        assert page1_ids.isdisjoint(page2_ids)

        # All 4 unique groups covered between the two pages.
        assert len(page1_ids | page2_ids) == 4


# ---------------------------------------------------------------------------
# Locations — name filter, sort_by, sort_dir
# ---------------------------------------------------------------------------


class TestLocationsSortFilterParams:
    def test_name_filter_partial_match(self, client: TestClient, seed_data: dict):
        """GET /locations?name=tower returns locations whose name contains 'tower'."""
        auth_as(client, seed_data["gm"])
        _create_location(client, seed_data, "Dark Tower")
        _create_location(client, seed_data, "Watch Tower")
        _create_location(client, seed_data, "The Harbour")  # should not match

        response = client.get("/api/v1/locations?name=tower")
        assert response.status_code == 200
        items = response.json()["items"]
        names = [loc["name"] for loc in items]
        assert "Dark Tower" in names
        assert "Watch Tower" in names
        assert "The Harbour" not in names

    def test_name_filter_case_insensitive(self, client: TestClient, seed_data: dict):
        """Name filter is case-insensitive for locations."""
        auth_as(client, seed_data["gm"])
        _create_location(client, seed_data, "Stone Tower")

        response = client.get("/api/v1/locations?name=TOWER")
        assert response.status_code == 200
        names = [loc["name"] for loc in response.json()["items"]]
        assert "Stone Tower" in names

    def test_name_filter_no_match_returns_empty(self, client: TestClient, seed_data: dict):
        """Name filter with no matches returns empty for locations."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/locations?name=xyzzy_no_match_xyzzy")
        assert response.status_code == 200
        assert response.json()["items"] == []

    def test_sort_by_name_asc_default(self, client: TestClient, seed_data: dict):
        """Locations returned in name ascending order by default."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/locations")
        assert response.status_code == 200
        names = [loc["name"] for loc in response.json()["items"]]
        assert names == sorted(names)

    def test_sort_by_name_desc(self, client: TestClient, seed_data: dict):
        """GET /locations?sort_by=name&sort_dir=desc returns locations Z→A."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/locations?sort_by=name&sort_dir=desc")
        assert response.status_code == 200
        names = [loc["name"] for loc in response.json()["items"]]
        assert names == sorted(names, reverse=True)

    def test_sort_by_name_with_name_filter(self, client: TestClient, seed_data: dict):
        """Acceptance criterion 3: GET /locations?name=tower&sort_by=name works."""
        auth_as(client, seed_data["gm"])
        _create_location(client, seed_data, "Dark Tower")
        _create_location(client, seed_data, "Watch Tower")
        _create_location(client, seed_data, "Amber Tower")

        response = client.get("/api/v1/locations?name=tower&sort_by=name&sort_dir=asc")
        assert response.status_code == 200
        items = response.json()["items"]
        names = [loc["name"] for loc in items]
        assert all("tower" in n.lower() for n in names)
        assert names == sorted(names)

    def test_sort_by_invalid_returns_422(self, client: TestClient, seed_data: dict):
        """Invalid sort_by returns 422 for locations."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/locations?sort_by=parent_id")
        assert response.status_code == 422

    def test_sort_dir_invalid_returns_422(self, client: TestClient, seed_data: dict):
        """Invalid sort_dir returns 422 for locations."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/locations?sort_dir=sideways")
        assert response.status_code == 422

    def test_sort_pagination_cursor_name_asc(self, client: TestClient, seed_data: dict):
        """Cursor pagination works with name-sorted locations."""
        auth_as(client, seed_data["gm"])
        # Seed has 2 locations; add 2 more = 4 total.
        _create_location(client, seed_data, "Alpha Plains")
        _create_location(client, seed_data, "Zeta Mountains")

        page1 = client.get("/api/v1/locations?sort_by=name&sort_dir=asc&limit=2").json()
        assert len(page1["items"]) == 2
        assert page1["has_more"] is True

        page2 = client.get(
            f"/api/v1/locations?sort_by=name&sort_dir=asc&limit=2&after={page1['next_cursor']}"
        ).json()
        assert len(page2["items"]) == 2

        page1_ids = {loc["id"] for loc in page1["items"]}
        page2_ids = {loc["id"] for loc in page2["items"]}
        assert page1_ids.isdisjoint(page2_ids)
        assert len(page1_ids | page2_ids) == 4


# ---------------------------------------------------------------------------
# Stories — sort_by, sort_dir
# ---------------------------------------------------------------------------


class TestStoriesSortParams:
    def test_sort_by_name_asc_default(self, client: TestClient, seed_data: dict):
        """Stories returned in name ascending order by default."""
        auth_as(client, seed_data["gm"])
        _create_story(client, seed_data, "Amber Arc")
        _create_story(client, seed_data, "Zephyr Quest")

        response = client.get("/api/v1/stories")
        assert response.status_code == 200
        names = [s["name"] for s in response.json()["items"]]
        assert names == sorted(names)

    def test_sort_by_name_desc(self, client: TestClient, seed_data: dict):
        """GET /stories?sort_by=name&sort_dir=desc returns stories Z→A."""
        auth_as(client, seed_data["gm"])
        _create_story(client, seed_data, "Amber Arc")
        _create_story(client, seed_data, "Zephyr Quest")

        response = client.get("/api/v1/stories?sort_by=name&sort_dir=desc")
        assert response.status_code == 200
        names = [s["name"] for s in response.json()["items"]]
        assert names == sorted(names, reverse=True)

    def test_sort_by_updated_at_desc(self, client: TestClient, seed_data: dict):
        """Acceptance criterion 4: GET /stories?sort_by=updated_at&sort_dir=desc works."""
        auth_as(client, seed_data["gm"])
        story1 = _create_story(client, seed_data, "Old Story")
        story2 = _create_story(client, seed_data, "New Story")
        # Touch story1 to make its updated_at the newest.
        client.patch(f"/api/v1/stories/{story1['id']}", json={"name": "Old Story Updated"})

        response = client.get("/api/v1/stories?sort_by=updated_at&sort_dir=desc")
        assert response.status_code == 200
        items = response.json()["items"]
        updated_ats = [s["updated_at"] for s in items]
        assert updated_ats == sorted(updated_ats, reverse=True)
        # The most recently updated story should appear first.
        assert items[0]["id"] == story1["id"]

    def test_sort_by_created_at_asc(self, client: TestClient, seed_data: dict):
        """GET /stories?sort_by=created_at&sort_dir=asc returns oldest-first."""
        auth_as(client, seed_data["gm"])
        _create_story(client, seed_data, "Story A")
        _create_story(client, seed_data, "Story B")

        response = client.get("/api/v1/stories?sort_by=created_at&sort_dir=asc")
        assert response.status_code == 200
        items = response.json()["items"]
        created_ats = [s["created_at"] for s in items]
        assert created_ats == sorted(created_ats)

    def test_sort_by_invalid_returns_422(self, client: TestClient, seed_data: dict):
        """Invalid sort_by returns 422 for stories."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/stories?sort_by=status")
        assert response.status_code == 422

    def test_sort_dir_invalid_returns_422(self, client: TestClient, seed_data: dict):
        """Invalid sort_dir returns 422 for stories."""
        auth_as(client, seed_data["gm"])
        response = client.get("/api/v1/stories?sort_dir=reverse")
        assert response.status_code == 422

    def test_sort_with_status_filter(self, client: TestClient, seed_data: dict):
        """Sort params combine correctly with existing status filter."""
        auth_as(client, seed_data["gm"])
        _create_story(client, seed_data, "Active Amber")
        _create_story(client, seed_data, "Active Zephyr")
        completed = _create_story(client, seed_data, "Completed Story")
        client.patch(
            f"/api/v1/stories/{completed['id']}", json={"status": "completed"}
        )

        response = client.get("/api/v1/stories?status=active&sort_by=name&sort_dir=asc")
        assert response.status_code == 200
        items = response.json()["items"]
        names = [s["name"] for s in items]
        assert "Completed Story" not in names
        assert names == sorted(names)

    def test_sort_pagination_cursor_name_asc(self, client: TestClient, seed_data: dict):
        """Cursor pagination works with name-sorted stories."""
        auth_as(client, seed_data["gm"])
        for letter in ["Alpha", "Beta", "Gamma", "Delta"]:
            _create_story(client, seed_data, f"{letter} Chronicle")

        page1 = client.get("/api/v1/stories?sort_by=name&sort_dir=asc&limit=2").json()
        assert len(page1["items"]) == 2
        assert page1["has_more"] is True

        page2 = client.get(
            f"/api/v1/stories?sort_by=name&sort_dir=asc&limit=2&after={page1['next_cursor']}"
        ).json()
        assert len(page2["items"]) == 2

        page1_ids = {s["id"] for s in page1["items"]}
        page2_ids = {s["id"] for s in page2["items"]}
        assert page1_ids.isdisjoint(page2_ids)
        assert len(page1_ids | page2_ids) == 4
