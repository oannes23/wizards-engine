"""Route handlers for feed endpoints (Stories 4.4.1 and 4.4.2).

Provides visibility-filtered, paginated chronological streams of Events
and Story entries.

Endpoints
---------
GET /characters/{id}/feed  — Character feed (Story 4.4.1)
GET /groups/{id}/feed      — Group feed (Story 4.4.1)
GET /locations/{id}/feed   — Location feed (Story 4.4.1)
GET /me/feed               — Personal feed (Story 4.4.2)
GET /me/feed/starred       — Starred feed (Story 4.4.2)
GET /me/feed/silent        — GM-only silent feed (Story 4.4.2)

All feed endpoints:
- Require authentication (any role, except /me/feed/silent which is GM-only).
- Return a merged stream of Events and Story entries visibility-filtered for
  the requesting user.
- Apply the unified 7-level visibility model per the requesting user.
- Support ULID cursor pagination (``?after=<ulid>&limit=N``).
- Support the full feed filter set (``?type=``, ``?target_type=``,
  ``?target_id=``, ``?actor_type=``, ``?session_id=``, ``?since=``,
  ``?until=``).
- Event-only filters (``type``, ``actor_type``) exclude story entries.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from wizards_engine.api.deps import get_current_user, require_gm
from wizards_engine.api.responses import raise_not_found
from wizards_engine.db import get_db
from wizards_engine.models.character import Character
from wizards_engine.models.group import Group
from wizards_engine.models.location import Location
from wizards_engine.models.user import User
from wizards_engine.schemas.feed import FeedResponse
from wizards_engine.services.feed import (
    build_game_object_feed,
    build_personal_feed,
    build_silent_feed,
    build_starred_feed,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Shared parameter documentation
# ---------------------------------------------------------------------------

_FEED_DESCRIPTION = (
    "Returns a merged chronological stream of Events and Story entries "
    "targeting or involving this {object_type}, visibility-filtered for the "
    "authenticated user.  Items are sorted newest-first by ULID.  "
    "Excludes ``silent`` events.  "
    "Supports ULID cursor pagination (``?after=<ulid>&limit=N``) and "
    "filters: ``type`` (event type prefix, e.g. ``character.*``), "
    "``target_type``, ``target_id``, ``actor_type``, ``session_id``, "
    "``since`` (inclusive datetime), ``until`` (inclusive datetime).  "
    "Event-only filters (``type``, ``actor_type``) exclude story entries."
)


def _feed_params(
    type: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    actor_type: str | None = None,
    session_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    after: str | None = None,
    limit: int = 50,
):
    """Shared query parameter factory (used via FastAPI Depends)."""
    return {
        "type": type,
        "target_type": target_type,
        "target_id": target_id,
        "actor_type": actor_type,
        "session_id": session_id,
        "since": since,
        "until": until,
        "after": after,
        "limit": limit,
    }


# ---------------------------------------------------------------------------
# GET /characters/{id}/feed
# ---------------------------------------------------------------------------


@router.get(
    "/characters/{character_id}/feed",
    response_model=FeedResponse,
    status_code=200,
    summary="Character feed",
    description=_FEED_DESCRIPTION.format(object_type="Character"),
)
def character_feed(
    character_id: str,
    params: dict = Depends(_feed_params),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FeedResponse:
    """Return the visibility-filtered feed for a Character.

    Args:
        character_id: ULID of the Character.
        params: Parsed feed query parameters (from ``_feed_params``).
        current_user: Authenticated user (any role).
        db: Injected SQLAlchemy session.

    Returns:
        :class:`~wizards_engine.schemas.feed.FeedResponse` with the
        merged, paginated feed items.

    Raises:
        HTTPException(404): If the Character does not exist.
    """
    character = db.get(Character, character_id)
    if character is None:
        raise_not_found("Character", character_id)

    return build_game_object_feed(
        db,
        current_user,
        "character",
        character_id,
        after=params["after"],
        limit=params["limit"],
        event_type=params["type"],
        target_type=params["target_type"],
        target_id=params["target_id"],
        actor_type=params["actor_type"],
        session_id=params["session_id"],
        since=params["since"],
        until=params["until"],
    )


# ---------------------------------------------------------------------------
# GET /groups/{id}/feed
# ---------------------------------------------------------------------------


@router.get(
    "/groups/{group_id}/feed",
    response_model=FeedResponse,
    status_code=200,
    summary="Group feed",
    description=_FEED_DESCRIPTION.format(object_type="Group"),
)
def group_feed(
    group_id: str,
    params: dict = Depends(_feed_params),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FeedResponse:
    """Return the visibility-filtered feed for a Group.

    Args:
        group_id: ULID of the Group.
        params: Parsed feed query parameters (from ``_feed_params``).
        current_user: Authenticated user (any role).
        db: Injected SQLAlchemy session.

    Returns:
        :class:`~wizards_engine.schemas.feed.FeedResponse` with the
        merged, paginated feed items.

    Raises:
        HTTPException(404): If the Group does not exist.
    """
    group = db.get(Group, group_id)
    if group is None:
        raise_not_found("Group", group_id)

    return build_game_object_feed(
        db,
        current_user,
        "group",
        group_id,
        after=params["after"],
        limit=params["limit"],
        event_type=params["type"],
        target_type=params["target_type"],
        target_id=params["target_id"],
        actor_type=params["actor_type"],
        session_id=params["session_id"],
        since=params["since"],
        until=params["until"],
    )


# ---------------------------------------------------------------------------
# GET /locations/{id}/feed
# ---------------------------------------------------------------------------


@router.get(
    "/locations/{location_id}/feed",
    response_model=FeedResponse,
    status_code=200,
    summary="Location feed",
    description=_FEED_DESCRIPTION.format(object_type="Location"),
)
def location_feed(
    location_id: str,
    params: dict = Depends(_feed_params),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FeedResponse:
    """Return the visibility-filtered feed for a Location.

    Args:
        location_id: ULID of the Location.
        params: Parsed feed query parameters (from ``_feed_params``).
        current_user: Authenticated user (any role).
        db: Injected SQLAlchemy session.

    Returns:
        :class:`~wizards_engine.schemas.feed.FeedResponse` with the
        merged, paginated feed items.

    Raises:
        HTTPException(404): If the Location does not exist.
    """
    location = db.get(Location, location_id)
    if location is None:
        raise_not_found("Location", location_id)

    return build_game_object_feed(
        db,
        current_user,
        "location",
        location_id,
        after=params["after"],
        limit=params["limit"],
        event_type=params["type"],
        target_type=params["target_type"],
        target_id=params["target_id"],
        actor_type=params["actor_type"],
        session_id=params["session_id"],
        since=params["since"],
        until=params["until"],
    )


# ---------------------------------------------------------------------------
# GET /me/feed  (Story 4.4.2)
# ---------------------------------------------------------------------------


@router.get(
    "/me/feed",
    response_model=FeedResponse,
    status_code=200,
    summary="Personal feed",
    description=(
        "Returns all feed items visible to the authenticated user across all "
        "Game Objects.  Merges Events and Story entries visibility-filtered per "
        "the requesting user.  The authenticated player's own actions are "
        "flagged with ``is_own: true``.  ``silent`` events are always excluded "
        "(use ``/me/feed/silent`` for those).  "
        "For GM: all non-silent events and story entries.  "
        "Supports ULID cursor pagination (``?after=<ulid>&limit=N``) and "
        "filters: ``type``, ``target_type``, ``target_id``, ``actor_type``, "
        "``session_id``, ``since``, ``until``.  "
        "Event-only filters (``type``, ``actor_type``) exclude story entries."
    ),
)
def personal_feed(
    params: dict = Depends(_feed_params),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FeedResponse:
    """Return the complete personal feed for the authenticated user.

    Queries all non-silent events visible to the user and all story entries
    visible to the user, merges them newest-first, and paginates.

    Args:
        params: Parsed feed query parameters (from ``_feed_params``).
        current_user: Authenticated user (any role).
        db: Injected SQLAlchemy session.

    Returns:
        :class:`~wizards_engine.schemas.feed.FeedResponse` with the
        merged, paginated feed items.
    """
    return build_personal_feed(
        db,
        current_user,
        after=params["after"],
        limit=params["limit"],
        event_type=params["type"],
        target_type=params["target_type"],
        target_id=params["target_id"],
        actor_type=params["actor_type"],
        session_id=params["session_id"],
        since=params["since"],
        until=params["until"],
    )


# ---------------------------------------------------------------------------
# GET /me/feed/starred  (Story 4.4.2)
# ---------------------------------------------------------------------------


@router.get(
    "/me/feed/starred",
    response_model=FeedResponse,
    status_code=200,
    summary="Starred feed",
    description=(
        "Returns feed items visible to the authenticated user, filtered to "
        "only Game Objects the user has starred.  Same visibility rules as "
        "the personal feed.  ``silent`` events are excluded.  "
        "Supports ULID cursor pagination (``?after=<ulid>&limit=N``) and "
        "filters: ``type``, ``target_type``, ``target_id``, ``actor_type``, "
        "``session_id``, ``since``, ``until``.  "
        "Event-only filters (``type``, ``actor_type``) exclude story entries."
    ),
)
def starred_feed(
    params: dict = Depends(_feed_params),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FeedResponse:
    """Return the starred feed for the authenticated user.

    Restricts the personal feed to Game Objects the user has starred via
    ``POST /me/starred``.  Uses the ``starred_objects`` table to determine
    which objects are in scope.

    Args:
        params: Parsed feed query parameters (from ``_feed_params``).
        current_user: Authenticated user (any role).
        db: Injected SQLAlchemy session.

    Returns:
        :class:`~wizards_engine.schemas.feed.FeedResponse` with the
        merged, paginated feed items for starred objects only.
    """
    return build_starred_feed(
        db,
        current_user,
        after=params["after"],
        limit=params["limit"],
        event_type=params["type"],
        target_type=params["target_type"],
        target_id=params["target_id"],
        actor_type=params["actor_type"],
        session_id=params["session_id"],
        since=params["since"],
        until=params["until"],
    )


# ---------------------------------------------------------------------------
# GET /me/feed/silent  (Story 4.4.2)
# ---------------------------------------------------------------------------


@router.get(
    "/me/feed/silent",
    response_model=FeedResponse,
    status_code=200,
    summary="Silent feed (GM only)",
    description=(
        "Returns all ``silent``-visibility Events.  GM only — non-GM users "
        "receive 403.  Story entries are excluded (they have no ``silent`` "
        "visibility level).  "
        "Supports ULID cursor pagination (``?after=<ulid>&limit=N``) and "
        "filters: ``type``, ``target_type``, ``target_id``, ``actor_type``, "
        "``session_id``, ``since``, ``until``."
    ),
)
def silent_feed(
    params: dict = Depends(_feed_params),
    current_user: User = Depends(require_gm),
    db: Session = Depends(get_db),
) -> FeedResponse:
    """Return all silent-visibility events (GM only).

    The silent feed is the GM's audit log for bookkeeping changes that
    should not surface in any player feed.

    Args:
        params: Parsed feed query parameters (from ``_feed_params``).
        current_user: Authenticated GM (non-GM callers receive 403).
        db: Injected SQLAlchemy session.

    Returns:
        :class:`~wizards_engine.schemas.feed.FeedResponse` with silent
        events only, newest-first.
    """
    return build_silent_feed(
        db,
        current_user,
        after=params["after"],
        limit=params["limit"],
        event_type=params["type"],
        target_type=params["target_type"],
        target_id=params["target_id"],
        actor_type=params["actor_type"],
        session_id=params["session_id"],
        since=params["since"],
        until=params["until"],
    )
