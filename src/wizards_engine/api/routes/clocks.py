"""Route handlers for Clock endpoints.

Provides CRUD for the Clock resource via two access routes:

  - Standalone: ``/api/v1/clocks``
  - Group sub-resource sugar: ``/api/v1/groups/{group_id}/clocks``

Endpoints
---------
POST   /clocks                     — GM only.  Create a clock (optional association).
GET    /clocks                     — Authenticated.  List with filters + pagination.
GET    /clocks/{id}                — Authenticated.  Clock detail (incl. soft-deleted).
PATCH  /clocks/{id}                — GM only.  Update name, notes, segments.
DELETE /clocks/{id}                — GM only.  Soft delete.
POST   /groups/{group_id}/clocks   — GM only.  Create clock auto-associated with group.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from wizards_engine.api.deps import get_current_user, require_gm
from wizards_engine.api.pagination import paginate
from wizards_engine.api.responses import raise_not_found, validation_error_response
from wizards_engine.db import get_db
from wizards_engine.models.clock import Clock
from wizards_engine.models.group import Group
from wizards_engine.models.user import User
from wizards_engine.schemas.clock import (
    ClockResponse,
    CreateClockRequest,
    CreateGroupClockRequest,
    UpdateClockRequest,
)
from wizards_engine.schemas.common import PaginatedResponse
from wizards_engine.services import clock as clock_svc
from wizards_engine.services.shared import get_game_object

router = APIRouter()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_ASSOCIATED_TYPES = {"character", "group", "location"}


def _clock_response(clock: Clock, db: Session) -> ClockResponse:
    """Build a ClockResponse with associated_name resolved."""
    resp = ClockResponse.from_orm_model(clock)
    if clock.associated_id and clock.associated_type:
        obj = get_game_object(db, clock.associated_type, clock.associated_id)
        resp.associated_name = obj.name if obj else None
    return resp


def _get_clock_or_404(db: Session, clock_id: str) -> Clock:
    """Return the Clock for *clock_id* or raise 404.

    Args:
        db: Active SQLAlchemy session.
        clock_id: ULID of the clock.

    Returns:
        The :class:`~wizards_engine.models.clock.Clock` ORM instance.

    Raises:
        HTTPException(404): If no clock exists with ``clock_id``.
    """
    clock = clock_svc.get_clock(db, clock_id)
    if clock is None:
        raise_not_found("Clock", clock_id)
    return clock


# ---------------------------------------------------------------------------
# POST /clocks — create a clock (standalone, optional association)
# ---------------------------------------------------------------------------


@router.post(
    "/clocks",
    response_model=ClockResponse,
    status_code=201,
    summary="Create a clock",
    description=(
        "GM only.  Creates a new Clock.  ``segments`` defaults to 5 and must "
        "be a positive integer.  ``associated_type`` and ``associated_id`` are "
        "optional but must be provided together.  Association is fixed at "
        "creation and cannot be changed via PATCH."
    ),
)
def create_clock(
    body: CreateClockRequest,
    _gm: User = Depends(require_gm),
    db: Session = Depends(get_db),
) -> ClockResponse:
    """Create a new Clock.

    Args:
        body: Validated request body.
        _gm: Authenticated GM (injected; ensures GM-only access).
        db: Injected SQLAlchemy session.

    Returns:
        ``ClockResponse`` for the newly created clock (201).

    Raises:
        HTTPException(422): If the referenced Game Object does not exist.
    """
    # Validate the associated object exists (if provided).
    if body.associated_type is not None and body.associated_id is not None:
        if not clock_svc.resolve_associated_object(
            db, body.associated_type, body.associated_id
        ):
            return validation_error_response(
                {
                    "associated_id": (
                        f"{body.associated_type} '{body.associated_id}' not found."
                    )
                }
            )

    clock = clock_svc.create_clock(
        db,
        name=body.name,
        segments=body.segments,
        associated_type=body.associated_type,
        associated_id=body.associated_id,
        notes=body.notes,
    )
    return _clock_response(clock, db)


# ---------------------------------------------------------------------------
# POST /groups/{group_id}/clocks — sugar route: create clock for a group
# ---------------------------------------------------------------------------


@router.post(
    "/groups/{group_id}/clocks",
    response_model=ClockResponse,
    status_code=201,
    summary="Create a clock for a group",
    description=(
        "GM only.  Sugar for ``POST /clocks`` that auto-sets "
        "``associated_type = 'group'`` and ``associated_id`` to the group ID.  "
        "The group must exist and not be soft-deleted.  The body must not "
        "include association fields."
    ),
)
def create_group_clock(
    group_id: str,
    body: CreateGroupClockRequest,
    _gm: User = Depends(require_gm),
    db: Session = Depends(get_db),
) -> ClockResponse:
    """Create a Clock auto-associated with the given Group.

    Args:
        group_id: ULID of the Group to associate the clock with.
        body: Validated request body (no association fields).
        _gm: Authenticated GM (injected; ensures GM-only access).
        db: Injected SQLAlchemy session.

    Returns:
        ``ClockResponse`` for the newly created clock (201).

    Raises:
        HTTPException(404): If the Group does not exist or is soft-deleted.
    """
    group = db.get(Group, group_id)
    if group is None or group.is_deleted:
        raise_not_found("Group", group_id)

    clock = clock_svc.create_clock(
        db,
        name=body.name,
        segments=body.segments,
        associated_type="group",
        associated_id=group_id,
        notes=body.notes,
    )
    return _clock_response(clock, db)


# ---------------------------------------------------------------------------
# GET /clocks — list clocks
# ---------------------------------------------------------------------------


@router.get(
    "/clocks",
    response_model=PaginatedResponse[ClockResponse],
    status_code=200,
    summary="List clocks",
    description=(
        "Returns a paginated list of clocks.  Soft-deleted clocks are excluded "
        "by default.  Supports filtering by ``associated_type``, "
        "``associated_id``, and ``include_deleted``.  "
        "ULID cursor pagination via ``?after=<ulid>&limit=N``."
    ),
)
def list_clocks(
    associated_type: str | None = None,
    associated_id: str | None = None,
    include_deleted: bool = False,
    after: str | None = None,
    limit: int = 50,
    _current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedResponse[ClockResponse]:
    """Return a paginated, filtered list of clocks.

    Args:
        associated_type: Optional filter — ``"character"``, ``"group"``,
            or ``"location"``.
        associated_id: Optional filter — ULID of the associated Game Object.
        include_deleted: When ``true``, include soft-deleted clocks.
        after: ULID cursor for pagination.
        limit: Page size (default 50, max 100).
        _current_user: Authenticated user (any role).
        db: Injected SQLAlchemy session.

    Returns:
        ``PaginatedResponse`` wrapping a list of ``ClockResponse`` objects.
    """
    if associated_type is not None and associated_type not in _VALID_ASSOCIATED_TYPES:
        return validation_error_response(
            {"associated_type": "must be 'character', 'group', or 'location'"}
        )

    q = clock_svc.list_clocks_query(
        db,
        associated_type=associated_type,
        associated_id=associated_id,
        include_deleted=include_deleted,
    )

    page = paginate(db, q, model=Clock, after=after, limit=limit)

    return PaginatedResponse[ClockResponse](
        items=[_clock_response(c, db) for c in page.items],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


# ---------------------------------------------------------------------------
# GET /clocks/{id} — clock detail
# ---------------------------------------------------------------------------


@router.get(
    "/clocks/{clock_id}",
    response_model=ClockResponse,
    status_code=200,
    summary="Get clock detail",
    description=(
        "Returns the full clock record, including soft-deleted clocks "
        "(``is_deleted`` will be ``true`` in those cases).  Returns 404 if no "
        "clock exists with that ID.  ``is_completed`` is computed on read as "
        "``progress >= segments``."
    ),
)
def get_clock(
    clock_id: str,
    _current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ClockResponse:
    """Return a single clock by ID.

    Args:
        clock_id: ULID of the clock to retrieve.
        _current_user: Authenticated user (any role).
        db: Injected SQLAlchemy session.

    Returns:
        ``ClockResponse`` for the requested clock.

    Raises:
        HTTPException(404): If no clock exists with ``clock_id``.
    """
    clock = _get_clock_or_404(db, clock_id)
    return _clock_response(clock, db)


# ---------------------------------------------------------------------------
# PATCH /clocks/{id} — update clock
# ---------------------------------------------------------------------------


@router.patch(
    "/clocks/{clock_id}",
    response_model=ClockResponse,
    status_code=200,
    summary="Update a clock",
    description=(
        "GM only.  Partial update for ``name``, ``notes``, and ``segments``.  "
        "Omitted fields are unchanged; sending ``null`` clears a nullable field.  "
        "The fields ``associated_type``, ``associated_id``, and ``progress`` "
        "are rejected — association is fixed at creation; progress is changed "
        "via GM actions."
    ),
)
def update_clock(
    clock_id: str,
    body: UpdateClockRequest,
    _gm: User = Depends(require_gm),
    db: Session = Depends(get_db),
) -> ClockResponse:
    """Apply a partial update to a clock.

    Args:
        clock_id: ULID of the clock to update.
        body: Validated partial update.  Only explicitly provided fields are
            applied (``model_fields_set`` semantics).
        _gm: Authenticated GM (injected; ensures GM-only access).
        db: Injected SQLAlchemy session.

    Returns:
        ``ClockResponse`` with updated fields.

    Raises:
        HTTPException(404): If the clock does not exist.
        HTTPException(422): If the request body includes forbidden fields.
    """
    clock = _get_clock_or_404(db, clock_id)

    raw = body.model_dump(exclude_unset=True)

    clock = clock_svc.update_clock(db, clock, raw)
    return _clock_response(clock, db)


# ---------------------------------------------------------------------------
# DELETE /clocks/{id} — soft delete
# ---------------------------------------------------------------------------


@router.delete(
    "/clocks/{clock_id}",
    status_code=204,
    summary="Soft-delete a clock",
    description=(
        "GM only.  Sets ``is_deleted = true`` on the clock.  "
        "The clock remains accessible via direct GET but is hidden from list "
        "results.  Returns 204 with no body."
    ),
)
def delete_clock(
    clock_id: str,
    _gm: User = Depends(require_gm),
    db: Session = Depends(get_db),
) -> None:
    """Soft-delete a clock.

    Args:
        clock_id: ULID of the clock to delete.
        _gm: Authenticated GM (injected; ensures GM-only access).
        db: Injected SQLAlchemy session.

    Returns:
        ``None`` — FastAPI sends 204 No Content.

    Raises:
        HTTPException(404): If no clock exists with ``clock_id``.
    """
    clock = _get_clock_or_404(db, clock_id)
    clock_svc.delete_clock(db, clock)
