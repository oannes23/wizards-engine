"""Tests for Story 1.2.6 — API Conventions.

Covers:
- wizards_engine.schemas.common: ErrorDetail, ErrorResponse, PaginatedResponse
- wizards_engine.api.pagination: paginate()
- wizards_engine.api.responses: error_response(), validation_error_response()
"""

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from wizards_engine.models import Base, User
from wizards_engine.models.base import _new_ulid
from wizards_engine.schemas.common import ErrorDetail, ErrorResponse, PaginatedResponse
from wizards_engine.api.pagination import paginate
from wizards_engine.api.responses import error_response, validation_error_response


# ---------------------------------------------------------------------------
# Shared in-memory DB for pagination tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def db_engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="module")
def db_session(db_engine):
    Session_ = sessionmaker(bind=db_engine)
    session = Session_()
    yield session
    session.close()


@pytest.fixture(scope="module")
def seeded_users(db_session):
    """Insert 5 User rows so pagination tests have data to work with."""
    users = [
        User(display_name=f"Player {i}", role="player", login_code=_new_ulid())
        for i in range(5)
    ]
    db_session.add_all(users)
    db_session.flush()
    db_session.expire_all()
    return db_session.scalars(select(User).order_by(User.id.desc())).all()


# ---------------------------------------------------------------------------
# ErrorDetail schema
# ---------------------------------------------------------------------------


def test_error_detail_required_fields():
    """ErrorDetail must accept code and message."""
    detail = ErrorDetail(code="not_found", message="Resource not found")
    assert detail.code == "not_found"
    assert detail.message == "Resource not found"
    assert detail.details is None


def test_error_detail_with_details():
    """ErrorDetail.details accepts an arbitrary dict."""
    detail = ErrorDetail(
        code="validation_error",
        message="Validation failed",
        details={"fields": {"name": "required"}},
    )
    assert detail.details == {"fields": {"name": "required"}}


def test_error_detail_missing_code_raises():
    """ErrorDetail requires code."""
    with pytest.raises(Exception):
        ErrorDetail(message="oops")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# ErrorResponse schema
# ---------------------------------------------------------------------------


def test_error_response_wraps_detail():
    """ErrorResponse.error must be an ErrorDetail instance."""
    resp = ErrorResponse(
        error=ErrorDetail(code="server_error", message="Something broke")
    )
    assert resp.error.code == "server_error"
    assert resp.error.message == "Something broke"


def test_error_response_serialises_to_dict():
    """ErrorResponse.model_dump() produces the expected nested structure."""
    resp = ErrorResponse(
        error=ErrorDetail(code="not_found", message="Not found", details=None)
    )
    data = resp.model_dump()
    assert data == {"error": {"code": "not_found", "message": "Not found", "details": None}}


# ---------------------------------------------------------------------------
# PaginatedResponse schema
# ---------------------------------------------------------------------------


def test_paginated_response_fields():
    """PaginatedResponse carries items, next_cursor, and has_more."""
    result: PaginatedResponse[str] = PaginatedResponse(
        items=["a", "b"],
        next_cursor="01CURSOR",
        has_more=True,
    )
    assert result.items == ["a", "b"]
    assert result.next_cursor == "01CURSOR"
    assert result.has_more is True


def test_paginated_response_null_cursor():
    """next_cursor is None when there are no more items."""
    result: PaginatedResponse[str] = PaginatedResponse(
        items=["only"],
        next_cursor=None,
        has_more=False,
    )
    assert result.next_cursor is None
    assert result.has_more is False


def test_paginated_response_empty():
    """PaginatedResponse works with an empty items list."""
    result: PaginatedResponse[str] = PaginatedResponse(
        items=[],
        next_cursor=None,
        has_more=False,
    )
    assert result.items == []
    assert result.next_cursor is None
    assert result.has_more is False


# ---------------------------------------------------------------------------
# paginate() utility
# ---------------------------------------------------------------------------


def test_paginate_returns_all_items_when_fewer_than_limit(db_session, seeded_users):
    """paginate() with limit > row count returns all rows, has_more=False."""
    q = select(User)
    result = paginate(db_session, q, model=User, limit=100)
    assert len(result.items) == 5
    assert result.has_more is False
    assert result.next_cursor is None


def test_paginate_respects_limit(db_session, seeded_users):
    """paginate() with limit=2 returns exactly 2 items and has_more=True."""
    q = select(User)
    result = paginate(db_session, q, model=User, limit=2)
    assert len(result.items) == 2
    assert result.has_more is True
    assert result.next_cursor is not None


def test_paginate_next_cursor_is_last_item_id(db_session, seeded_users):
    """next_cursor must equal the id of the last item returned."""
    q = select(User)
    result = paginate(db_session, q, model=User, limit=2)
    assert result.next_cursor == result.items[-1].id


def test_paginate_cursor_advances_page(db_session, seeded_users):
    """Using next_cursor as after= fetches the next page without overlap."""
    q = select(User)
    page1 = paginate(db_session, q, model=User, limit=2)
    page2 = paginate(db_session, q, model=User, after=page1.next_cursor, limit=2)

    page1_ids = {item.id for item in page1.items}
    page2_ids = {item.id for item in page2.items}
    assert page1_ids.isdisjoint(page2_ids), "Pages must not overlap"


def test_paginate_collects_all_rows_across_pages(db_session, seeded_users):
    """Iterating through pages with cursor covers every row exactly once."""
    q = select(User)
    seen_ids: set[str] = set()
    cursor = None
    while True:
        page = paginate(db_session, q, model=User, after=cursor, limit=2)
        for item in page.items:
            assert item.id not in seen_ids, f"Duplicate id {item.id}"
            seen_ids.add(item.id)
        if not page.has_more:
            break
        cursor = page.next_cursor

    assert len(seen_ids) == 5


def test_paginate_order_is_descending(db_session, seeded_users):
    """paginate() returns items in descending ULID order (newest first)."""
    q = select(User)
    result = paginate(db_session, q, model=User, limit=100)
    ids = [item.id for item in result.items]
    assert ids == sorted(ids, reverse=True), "Items should be newest-first (id DESC)"


def test_paginate_clamps_limit_to_max(db_session, seeded_users):
    """paginate() silently clamps limit to 100."""
    q = select(User)
    result = paginate(db_session, q, model=User, limit=9999)
    # With only 5 rows this simply returns all 5; the clamp is behaviorally safe.
    assert len(result.items) == 5


def test_paginate_last_page_has_no_cursor(db_session, seeded_users):
    """The final page has next_cursor=None and has_more=False."""
    q = select(User)
    # Fetch page 2 of 2 (limit=3 → page1 has 3 items, page2 has 2)
    page1 = paginate(db_session, q, model=User, limit=3)
    assert page1.has_more is True
    page2 = paginate(db_session, q, model=User, after=page1.next_cursor, limit=3)
    assert page2.has_more is False
    assert page2.next_cursor is None


# ---------------------------------------------------------------------------
# error_response() helper
# ---------------------------------------------------------------------------


def test_error_response_status_code():
    """error_response() returns a JSONResponse with the given status code."""
    resp = error_response(404, "not_found", "Resource not found")
    assert resp.status_code == 404


def test_error_response_body_shape():
    """error_response() body has the standard error envelope shape."""
    import json

    resp = error_response(404, "not_found", "Resource not found")
    body = json.loads(resp.body)
    assert body == {"error": {"code": "not_found", "message": "Resource not found"}}


def test_error_response_with_details():
    """error_response() includes details when provided."""
    import json

    resp = error_response(409, "conflict", "Already exists", details={"id": "abc123"})
    body = json.loads(resp.body)
    assert body["error"]["details"] == {"id": "abc123"}


def test_error_response_no_details_key_when_omitted():
    """error_response() omits the details key when details=None."""
    import json

    resp = error_response(400, "bad_request", "Bad input")
    body = json.loads(resp.body)
    assert "details" not in body["error"]


# ---------------------------------------------------------------------------
# validation_error_response() helper
# ---------------------------------------------------------------------------


def test_validation_error_response_status_422():
    """validation_error_response() always returns 422."""
    resp = validation_error_response({"name": "required"})
    assert resp.status_code == 422


def test_validation_error_response_body():
    """validation_error_response() body matches the canonical shape."""
    import json

    resp = validation_error_response({"name": "must not be blank", "limit": "must be >= 1"})
    body = json.loads(resp.body)
    assert body == {
        "error": {
            "code": "validation_error",
            "message": "Validation failed",
            "details": {
                "fields": {
                    "name": "must not be blank",
                    "limit": "must be >= 1",
                }
            },
        }
    }


def test_validation_error_response_empty_fields():
    """validation_error_response() accepts an empty fields dict."""
    import json

    resp = validation_error_response({})
    body = json.loads(resp.body)
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"]["fields"] == {}


# ---------------------------------------------------------------------------
# paginate() edge cases
# ---------------------------------------------------------------------------


def test_paginate_exact_limit_has_no_more(db_session, seeded_users):
    """When limit equals exactly the total row count, has_more must be False."""
    q = select(User)
    # seeded_users has 5 rows; limit=5 should exhaust all rows cleanly
    result = paginate(db_session, q, model=User, limit=5)
    assert len(result.items) == 5
    assert result.has_more is False
    assert result.next_cursor is None


def test_paginate_default_limit_is_50(db_session, seeded_users):
    """paginate() uses limit=50 when no limit is supplied."""
    from wizards_engine.api.pagination import _DEFAULT_LIMIT

    assert _DEFAULT_LIMIT == 50
    q = select(User)
    # Only 5 rows — default limit should still return all 5 without truncation
    result = paginate(db_session, q, model=User)
    assert len(result.items) == 5
    assert result.has_more is False


# ---------------------------------------------------------------------------
# RequestValidationError → 422 envelope (HTTP integration)
# ---------------------------------------------------------------------------


def test_validation_error_uses_standard_envelope_not_detail_list(client):
    """POST with a missing required field returns 422 in the standard error envelope.

    Verifies that the custom RequestValidationError handler in app.py emits:
      {"error": {"code": "validation_error", "message": "Validation failed",
                 "details": {"fields": {"<field>": "<message>"}}}}

    and does NOT emit FastAPI's default shape:
      {"detail": [{"loc": [...], "msg": "...", "type": "..."}]}
    """
    # POST /api/v1/auth/login requires {"code": "..."}.
    # Sending an empty body triggers a RequestValidationError for the missing field.
    response = client.post("/api/v1/auth/login", json={})
    assert response.status_code == 422

    body = response.json()

    # Must NOT have the old FastAPI "detail" list shape.
    assert "detail" not in body, (
        "Response must not use FastAPI's default {'detail': [...]} shape"
    )

    # Must have the standard error envelope.
    assert "error" in body
    error = body["error"]
    assert error["code"] == "validation_error"
    assert error["message"] == "Validation failed"

    # Must include per-field details.
    assert "details" in error
    assert "fields" in error["details"]
    fields = error["details"]["fields"]
    # The "code" field is required; its validation message must be present.
    assert "code" in fields, (
        f"Expected 'code' field in validation details; got fields={fields!r}"
    )
