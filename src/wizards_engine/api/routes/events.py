"""Route handlers for /api/v1/events — Events read API.

Provides read-only access to the append-only event log, plus a GM-only
visibility override endpoint.  Events are never created via the API —
they are produced as side-effects of state-changing operations.

Endpoints
---------
GET    /events          — Authenticated.  List events with filters + pagination.
GET    /events/{id}     — Authenticated.  Single event detail.
PATCH  /events/{id}/visibility  — GM only.  Override visibility level.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from wizards_engine.api.deps import get_current_user, require_gm
from wizards_engine.api.pagination import paginate
from wizards_engine.db import get_db
from wizards_engine.models.event import Event, EventTarget
from wizards_engine.models.user import User
from wizards_engine.schemas.common import PaginatedResponse
from wizards_engine.schemas.event import EventResponse, UpdateEventVisibilityRequest
from wizards_engine.services.visibility import (
    can_user_see_event,
    filter_events_for_user,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# GET /events — paginated list with filters
# ---------------------------------------------------------------------------


@router.get(
    "/events",
    response_model=PaginatedResponse[EventResponse],
    status_code=200,
    summary="List events",
    description=(
        "Returns a paginated, visibility-filtered list of events.  "
        "``silent`` events are excluded from this feed (even for the GM — "
        "those are accessed via a separate silent feed).  "
        "Supports optional filters: ``type`` (prefix wildcard via ``*``), "
        "``target_type``, ``target_id``, ``session_id``, ``actor_type``, "
        "``proposal_id``, ``since`` (inclusive), ``until`` (inclusive).  "
        "ULID cursor pagination via ``?after=<ulid>&limit=N``."
    ),
)
def list_events(
    type: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    session_id: str | None = None,
    actor_type: str | None = None,
    proposal_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    after: str | None = None,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedResponse[EventResponse]:
    """Return a paginated, filtered, visibility-filtered list of events.

    Results exclude ``silent`` events regardless of caller role.  The GM's
    silent feed is a separate concern.  All other filters narrow results
    further; filters are combined with AND.

    Args:
        type: Optional event type filter.  Supports glob-style prefix
            matching: ``character.*`` becomes ``LIKE 'character.%'``.
            Exact strings match exactly.
        target_type: Optional filter by target Game Object type.
        target_id: Optional filter by specific target ULID.
        session_id: Optional filter by session ULID.
        actor_type: Optional filter by actor type (``player``, ``gm``,
            ``system``).
        proposal_id: Optional filter by proposal ULID.
        since: Optional lower bound on ``created_at`` (inclusive).
        until: Optional upper bound on ``created_at`` (inclusive).
        after: ULID cursor for pagination (return items older than this ID).
        limit: Page size (default 50, max 100).
        current_user: Authenticated user (any role).
        db: Injected SQLAlchemy session.

    Returns:
        ``PaginatedResponse`` wrapping a list of ``EventResponse`` objects.
    """
    q = select(Event)

    # Exclude silent events from normal feed.
    q = q.where(Event.visibility != "silent")

    # --- Type filter (supports prefix wildcard) ---
    if type is not None:
        if type.endswith("*"):
            # Convert glob-style "character.*" → SQL LIKE "character.%"
            prefix = type[:-1] + "%"
            q = q.where(Event.type.like(prefix))
        else:
            q = q.where(Event.type == type)

    # --- Direct column filters ---
    if session_id is not None:
        q = q.where(Event.session_id == session_id)

    if actor_type is not None:
        q = q.where(Event.actor_type == actor_type)

    if proposal_id is not None:
        q = q.where(Event.proposal_id == proposal_id)

    if since is not None:
        q = q.where(Event.created_at >= since)

    if until is not None:
        q = q.where(Event.created_at <= until)

    # --- Target filters (require a JOIN) ---
    if target_type is not None or target_id is not None:
        target_conditions = []
        if target_type is not None:
            target_conditions.append(EventTarget.target_type == target_type)
        if target_id is not None:
            target_conditions.append(EventTarget.target_id == target_id)

        q = q.join(
            EventTarget,
            and_(EventTarget.event_id == Event.id, *target_conditions),
        ).distinct()

    # Paginate (applies ORDER BY id DESC and cursor filter internally).
    page = paginate(db, q, model=Event, after=after, limit=limit)

    # Visibility filter — applied after DB fetch since it requires bond-graph
    # traversal that cannot be expressed as SQL.  For small groups (4–6 players)
    # this is acceptably performant.
    visible_items = filter_events_for_user(db, current_user, list(page.items))

    # Recompute pagination metadata based on the visibility-filtered slice.
    # next_cursor and has_more from the DB page may be stale after filtering,
    # but we preserve the DB-level cursor semantics: next_cursor is the last
    # DB-fetched item's id (not the last visible item's id).  This ensures that
    # subsequent pages skip past already-seen rows regardless of visibility.
    return PaginatedResponse[EventResponse](
        items=[EventResponse.model_validate(e) for e in visible_items],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


# ---------------------------------------------------------------------------
# GET /events/{id} — single event detail
# ---------------------------------------------------------------------------


@router.get(
    "/events/{event_id}",
    response_model=EventResponse,
    status_code=200,
    summary="Get event detail",
    description=(
        "Returns the full event record including its targets list.  "
        "Returns 404 if the event does not exist, if the calling user cannot "
        "see it under the visibility model, or if the event is ``silent`` "
        "and the caller is not the GM."
    ),
)
def get_event(
    event_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EventResponse:
    """Return a single event by ID, subject to visibility rules.

    Args:
        event_id: ULID of the event to retrieve.
        current_user: Authenticated user (any role).
        db: Injected SQLAlchemy session.

    Returns:
        ``EventResponse`` for the requested event.

    Raises:
        HTTPException(404): If the event does not exist, is not visible to
            the caller, or is ``silent`` and the caller is not the GM.
    """
    event = db.get(Event, event_id)

    if event is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "not_found",
                    "message": f"Event '{event_id}' not found.",
                }
            },
        )

    # Silent events are excluded from the normal read path for all users
    # (including the GM — the GM uses a separate silent feed endpoint).
    if event.visibility == "silent":
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "not_found",
                    "message": f"Event '{event_id}' not found.",
                }
            },
        )

    # Apply visibility check — 404 (not 403) per API conventions.
    if not can_user_see_event(db, current_user, event):
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "not_found",
                    "message": f"Event '{event_id}' not found.",
                }
            },
        )

    return EventResponse.model_validate(event)


# ---------------------------------------------------------------------------
# PATCH /events/{id}/visibility — GM override
# ---------------------------------------------------------------------------


@router.patch(
    "/events/{event_id}/visibility",
    response_model=EventResponse,
    status_code=200,
    summary="Update event visibility",
    description=(
        "GM only.  Changes the visibility level of an event.  "
        "This is the only mutable field on an event — all other fields "
        "are immutable after creation.  "
        "Returns 404 if the event does not exist."
    ),
)
def update_event_visibility(
    event_id: str,
    body: UpdateEventVisibilityRequest,
    _gm: User = Depends(require_gm),
    db: Session = Depends(get_db),
) -> EventResponse:
    """Override the visibility level on a single event.

    Args:
        event_id: ULID of the event to update.
        body: Validated request body with the new ``visibility`` value.
        _gm: The authenticated GM (injected; ensures GM-only access).
        db: Injected SQLAlchemy session.

    Returns:
        ``EventResponse`` with the updated visibility (200).

    Raises:
        HTTPException(404): If no event exists with ``event_id``.
    """
    event = db.get(Event, event_id)

    if event is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "not_found",
                    "message": f"Event '{event_id}' not found.",
                }
            },
        )

    event.visibility = body.visibility
    db.flush()
    db.refresh(event)

    return EventResponse.model_validate(event)
