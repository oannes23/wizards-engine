"""Route handlers for /api/v1/stories — Story CRUD and owners sub-resource.

Provides standard CRUD for the Story resource plus owners sub-resource management.
Stories are GM-created; all authenticated users can read them.

Endpoints
---------
POST   /stories                       — GM only.  Create a story.
GET    /stories                       — Authenticated.  List with filters + pagination.
GET    /stories/{id}                  — Authenticated.  Story detail with owners + entries.
GET    /stories/{id}/entries          — Authenticated.  Paginated entries for a story.
PATCH  /stories/{id}                  — GM only.  Update story fields.
DELETE /stories/{id}                  — GM only.  Soft delete.
POST   /stories/{id}/owners           — GM only.  Add a Game Object as owner.
DELETE /stories/{id}/owners/{type}/{owner_id}  — GM only.  Remove an owner.
"""

from sqlalchemy.exc import IntegrityError
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from wizards_engine.api.deps import get_current_user, require_gm
from wizards_engine.roles import Role
from wizards_engine.api.pagination import paginate
from wizards_engine.api.responses import raise_forbidden, raise_not_found
from wizards_engine.db import get_db
from wizards_engine.models.story import Story, StoryEntry
from wizards_engine.models.user import User
from wizards_engine.schemas.common import PaginatedResponse
from wizards_engine.schemas.story import (
    AddOwnerRequest,
    CreateStoryEntryRequest,
    CreateStoryRequest,
    StoryDetailResponse,
    StoryEntryResponse,
    StoryOwnerResponse,
    StoryResponse,
    UpdateStoryEntryRequest,
    UpdateStoryRequest,
)
from wizards_engine.services import story as story_svc
from wizards_engine.services.visibility import can_user_see_story, filter_stories_for_user

router = APIRouter()

_VALID_STATUSES = {"active", "completed", "abandoned"}
_VALID_OWNER_TYPES = {"character", "group", "location"}
_VALID_SORT_BY = frozenset({"name", "created_at", "updated_at"})
_VALID_SORT_DIR = frozenset({"asc", "desc"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _story_not_found(story_id: str) -> None:
    """Raise a 404 HTTPException for a missing Story."""
    raise_not_found("Story", story_id)


def _entry_not_found(entry_id: str) -> None:
    """Raise a 404 HTTPException for a missing StoryEntry."""
    raise_not_found("Story entry", entry_id)


_INLINE_ENTRY_CAP = 20


def _build_detail_response(db: Session, story: Story) -> StoryDetailResponse:
    """Construct a StoryDetailResponse including owners and capped entries.

    Inline entries are limited to the 20 most recent (by ``created_at``).
    If the story has more entries, ``has_more_entries`` is ``True`` and
    the client should use ``GET /stories/{id}/entries`` to paginate.

    Args:
        db: Active SQLAlchemy session.
        story: The Story ORM instance.

    Returns:
        Fully populated :class:`~wizards_engine.schemas.story.StoryDetailResponse`.
    """
    owners = [
        StoryOwnerResponse(type=o.owner_type, id=o.owner_id) for o in story.owners
    ]
    all_entries_orm = story_svc.get_story_entries(db, story.id)
    total = len(all_entries_orm)
    has_more = total > _INLINE_ENTRY_CAP

    capped = all_entries_orm[-_INLINE_ENTRY_CAP:] if has_more else all_entries_orm
    entries = [StoryEntryResponse.model_validate(e) for e in capped]

    base = StoryResponse.model_validate(story)
    return StoryDetailResponse(
        **base.model_dump(),
        owners=owners,
        entries=entries,
        has_more_entries=has_more,
        entries_cursor=None,
    )


# ---------------------------------------------------------------------------
# POST /stories
# ---------------------------------------------------------------------------


@router.post(
    "/stories",
    response_model=StoryResponse,
    status_code=201,
    summary="Create a story",
    description=(
        "GM only.  Creates a new narrative thread (Story).  "
        "Status defaults to ``active`` if not provided.  "
        "``parent_id`` must reference an existing Story if provided."
    ),
)
def create_story(
    body: CreateStoryRequest,
    _gm: User = Depends(require_gm),
    db: Session = Depends(get_db),
) -> StoryResponse:
    """Create a new Story.

    Args:
        body: Validated request body.
        _gm: The authenticated GM (injected; ensures GM-only access).
        db: Injected SQLAlchemy session.

    Returns:
        ``StoryResponse`` for the newly created story (201).

    Raises:
        HTTPException(404): If ``parent_id`` references a non-existent story.
    """
    if body.parent_id is not None:
        parent = story_svc.get_story(db, body.parent_id)
        if parent is None:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": {
                        "code": "validation_error",
                        "message": "Validation failed",
                        "details": {
                            "fields": {
                                "parent_id": f"Parent story '{body.parent_id}' not found."
                            }
                        },
                    }
                },
            )

    story = story_svc.create_story(
        db,
        name=body.name,
        summary=body.summary,
        status=body.status,
        parent_id=body.parent_id,
        tags=body.tags,
    )
    return StoryResponse.model_validate(story)


# ---------------------------------------------------------------------------
# GET /stories
# ---------------------------------------------------------------------------


@router.get(
    "/stories",
    response_model=PaginatedResponse[StoryResponse],
    status_code=200,
    summary="List stories",
    description=(
        "Returns a paginated list of stories.  Soft-deleted stories are excluded by default.  "
        "Supports filtering by ``?status=``, ``?tag=``, ``?owner=<type>:<id>``, "
        "and ``?include_deleted=true``.  "
        "Supports sorting via ``?sort_by=name|created_at|updated_at`` and "
        "``?sort_dir=asc|desc``.  "
        "ULID cursor pagination via ``?after=<ulid>&limit=N``."
    ),
)
def list_stories(
    status: str | None = None,
    tag: str | None = None,
    owner: str | None = None,
    include_deleted: bool = False,
    sort_by: str = "name",
    sort_dir: str = "asc",
    after: str | None = None,
    limit: int = 50,
    _current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedResponse[StoryResponse]:
    """Return a paginated, filtered list of stories.

    Args:
        status: Optional filter — ``"active"``, ``"completed"``, or ``"abandoned"``.
        tag: Optional exact tag string filter.
        owner: Optional owner filter in ``<type>:<id>`` format, e.g. ``character:01H...``.
        include_deleted: When ``true``, include soft-deleted stories.
        sort_by: Column to sort by — ``"name"``, ``"created_at"``, or ``"updated_at"``.
            Defaults to ``"name"``.
        sort_dir: Sort direction — ``"asc"`` or ``"desc"``.  Defaults to ``"asc"``.
        after: ULID cursor for pagination (return items older than this ID).
        limit: Page size (default 50, max 100).
        _current_user: Authenticated user (any role).
        db: Injected SQLAlchemy session.

    Returns:
        ``PaginatedResponse`` wrapping a list of ``StoryResponse`` objects.

    Raises:
        HTTPException(422): If ``status`` is not a valid enum value.
        HTTPException(422): If ``owner`` format is invalid.
        HTTPException(422): If ``sort_by`` or ``sort_dir`` are invalid.
    """
    if status is not None and status not in _VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "validation_error",
                    "message": "Validation failed",
                    "details": {
                        "fields": {
                            "status": "must be 'active', 'completed', or 'abandoned'"
                        }
                    },
                }
            },
        )

    if sort_by not in _VALID_SORT_BY:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "validation_error",
                    "message": "Validation failed",
                    "details": {
                        "fields": {
                            "sort_by": "must be 'name', 'created_at', or 'updated_at'"
                        }
                    },
                }
            },
        )

    if sort_dir not in _VALID_SORT_DIR:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "validation_error",
                    "message": "Validation failed",
                    "details": {
                        "fields": {"sort_dir": "must be 'asc' or 'desc'"}
                    },
                }
            },
        )

    owner_type: str | None = None
    owner_id: str | None = None
    if owner is not None:
        parts = owner.split(":", 1)
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": {
                        "code": "validation_error",
                        "message": "Validation failed",
                        "details": {
                            "fields": {
                                "owner": "must be in format '<type>:<id>' e.g. 'character:01H...'"
                            }
                        },
                    }
                },
            )
        owner_type, owner_id = parts[0], parts[1]
        if owner_type not in _VALID_OWNER_TYPES:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": {
                        "code": "validation_error",
                        "message": "Validation failed",
                        "details": {
                            "fields": {
                                "owner": "type must be 'character', 'group', or 'location'"
                            }
                        },
                    }
                },
            )

    q, sort_col, resolved_sort_dir = story_svc.list_stories_query(
        db,
        status=status,
        tag=tag,
        owner_type=owner_type,
        owner_id=owner_id,
        include_deleted=include_deleted,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )

    page = paginate(
        db, q, model=Story, after=after, limit=limit,
        sort_col=sort_col, sort_dir=resolved_sort_dir,
    )

    # Apply visibility filtering for non-GM users.
    visible_items = filter_stories_for_user(db, _current_user, page.items)

    return PaginatedResponse[StoryResponse](
        items=[StoryResponse.model_validate(s) for s in visible_items],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


# ---------------------------------------------------------------------------
# GET /stories/{id}
# ---------------------------------------------------------------------------


@router.get(
    "/stories/{story_id}",
    response_model=StoryDetailResponse,
    status_code=200,
    summary="Get story detail",
    description=(
        "Returns the full story record including owners list and narrative entries.  "
        "Entries are sorted by creation time (oldest first).  "
        "Soft-deleted entries are excluded.  "
        "Returns 404 if no story exists with that ID."
    ),
)
def get_story(
    story_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StoryDetailResponse:
    """Return a single story by ID with owners and entries.

    Args:
        story_id: ULID of the story to retrieve.
        current_user: Authenticated user (any role).
        db: Injected SQLAlchemy session.

    Returns:
        ``StoryDetailResponse`` for the requested story.

    Raises:
        HTTPException(404): If no story exists with ``story_id``, or if the
            authenticated player does not have visibility of this story.
    """
    story = story_svc.get_story(db, story_id)
    if story is None:
        raise _story_not_found(story_id)
    if not can_user_see_story(db, current_user, story):
        raise _story_not_found(story_id)
    return _build_detail_response(db, story)


# ---------------------------------------------------------------------------
# GET /stories/{id}/entries — paginated entries
# ---------------------------------------------------------------------------


@router.get(
    "/stories/{story_id}/entries",
    response_model=PaginatedResponse[StoryEntryResponse],
    status_code=200,
    summary="List story entries (paginated)",
    description=(
        "Returns a paginated list of non-deleted narrative entries for a story, "
        "sorted by ``created_at`` ascending (oldest first).  "
        "Cursor pagination via ``?after=<cursor>&limit=N``.  "
        "Returns 404 if the story does not exist or is not visible to the caller."
    ),
)
def list_story_entries(
    story_id: str,
    after: str | None = None,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedResponse[StoryEntryResponse]:
    """Return a paginated list of entries for a story.

    Args:
        story_id: ULID of the story.
        after: Cursor for pagination continuation.
        limit: Page size (default 50, max 100).
        current_user: Authenticated user (any role).
        db: Injected SQLAlchemy session.

    Returns:
        ``PaginatedResponse`` of ``StoryEntryResponse`` objects.

    Raises:
        HTTPException(404): If the story does not exist or is not visible.
    """
    story = story_svc.get_story(db, story_id)
    if story is None:
        raise _story_not_found(story_id)
    if not can_user_see_story(db, current_user, story):
        raise _story_not_found(story_id)

    q = story_svc.list_story_entries_query(story.id)
    page = paginate(
        db, q, model=StoryEntry,
        after=after, limit=limit,
        sort_col=StoryEntry.created_at, sort_dir="asc",
    )

    return PaginatedResponse[StoryEntryResponse](
        items=[StoryEntryResponse.model_validate(e) for e in page.items],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


# ---------------------------------------------------------------------------
# PATCH /stories/{id}
# ---------------------------------------------------------------------------


@router.patch(
    "/stories/{story_id}",
    response_model=StoryResponse,
    status_code=200,
    summary="Update a story",
    description=(
        "GM only.  Partial update for name, summary, status, tags, "
        "visibility_level, and visibility_overrides.  "
        "Omitted fields are unchanged; sending ``null`` clears a nullable field.  "
        "Status can be set to any valid value freely."
    ),
)
def update_story(
    story_id: str,
    body: UpdateStoryRequest,
    _gm: User = Depends(require_gm),
    db: Session = Depends(get_db),
) -> StoryResponse:
    """Apply a partial update to a story.

    Args:
        story_id: ULID of the story to update.
        body: Validated partial update.  Only explicitly provided fields are applied.
        _gm: The authenticated GM (injected; ensures GM-only access).
        db: Injected SQLAlchemy session.

    Returns:
        ``StoryResponse`` with updated fields.

    Raises:
        HTTPException(404): If the story does not exist.
    """
    story = story_svc.get_story(db, story_id)
    if story is None:
        raise _story_not_found(story_id)

    updates = body.model_dump(exclude_unset=True)
    story = story_svc.update_story(db, story, updates)
    return StoryResponse.model_validate(story)


# ---------------------------------------------------------------------------
# DELETE /stories/{id}
# ---------------------------------------------------------------------------


@router.delete(
    "/stories/{story_id}",
    status_code=204,
    summary="Soft-delete a story",
    description=(
        "GM only.  Sets ``is_deleted = true`` on the story.  "
        "The story remains accessible via direct GET but is hidden from list results.  "
        "Returns 204 with no body."
    ),
)
def delete_story(
    story_id: str,
    _gm: User = Depends(require_gm),
    db: Session = Depends(get_db),
) -> None:
    """Soft-delete a story.

    Args:
        story_id: ULID of the story to delete.
        _gm: The authenticated GM (injected; ensures GM-only access).
        db: Injected SQLAlchemy session.

    Returns:
        ``None`` — FastAPI sends 204 No Content.

    Raises:
        HTTPException(404): If no story exists with ``story_id``.
    """
    story = story_svc.get_story(db, story_id)
    if story is None:
        raise _story_not_found(story_id)

    story_svc.delete_story(db, story)


# ---------------------------------------------------------------------------
# POST /stories/{id}/owners
# ---------------------------------------------------------------------------


@router.post(
    "/stories/{story_id}/owners",
    response_model=StoryOwnerResponse,
    status_code=201,
    summary="Add a story owner",
    description=(
        "GM only.  Adds a Game Object (Character, Group, or Location) as an owner "
        "of this story.  Mixed owner types are allowed.  "
        "Validates that the referenced Game Object exists.  "
        "Returns 404 if the story or game object does not exist.  "
        "Returns 409 if this owner is already on the story."
    ),
)
def add_owner(
    story_id: str,
    body: AddOwnerRequest,
    _gm: User = Depends(require_gm),
    db: Session = Depends(get_db),
) -> StoryOwnerResponse:
    """Add a Game Object owner to a story.

    Args:
        story_id: ULID of the story.
        body: Validated add-owner request with ``type`` and ``id``.
        _gm: The authenticated GM (injected; ensures GM-only access).
        db: Injected SQLAlchemy session.

    Returns:
        ``StoryOwnerResponse`` for the newly added owner (201).

    Raises:
        HTTPException(404): If the story or referenced game object does not exist.
        HTTPException(409): If this owner already exists on the story.
    """
    story = story_svc.get_story(db, story_id)
    if story is None:
        raise _story_not_found(story_id)

    game_object = story_svc.get_game_object(db, body.type, body.id)
    if game_object is None:
        raise_not_found(body.type.capitalize(), body.id)

    try:
        owner_record = story_svc.add_owner(db, story, owner_type=body.type, owner_id=body.id)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "conflict",
                    "message": (
                        f"{body.type.capitalize()} '{body.id}' is already an owner of this story."
                    ),
                }
            },
        )

    return StoryOwnerResponse(type=owner_record.owner_type, id=owner_record.owner_id)


# ---------------------------------------------------------------------------
# DELETE /stories/{id}/owners/{type}/{owner_id}
# ---------------------------------------------------------------------------


@router.delete(
    "/stories/{story_id}/owners/{owner_type}/{owner_id}",
    status_code=204,
    summary="Remove a story owner",
    description=(
        "GM only.  Removes a Game Object from the story's owners list.  "
        "Returns 204 with no body.  "
        "Returns 404 if the story does not exist or the owner is not on this story."
    ),
)
def remove_owner(
    story_id: str,
    owner_type: str,
    owner_id: str,
    _gm: User = Depends(require_gm),
    db: Session = Depends(get_db),
) -> None:
    """Remove a Game Object owner from a story.

    Args:
        story_id: ULID of the story.
        owner_type: Owner type — ``character``, ``group``, or ``location``.
        owner_id: ULID of the owning Game Object.
        _gm: The authenticated GM (injected; ensures GM-only access).
        db: Injected SQLAlchemy session.

    Returns:
        ``None`` — FastAPI sends 204 No Content.

    Raises:
        HTTPException(404): If the story does not exist.
        HTTPException(404): If this owner is not on the story.
        HTTPException(422): If ``owner_type`` is not a valid type.
    """
    if owner_type not in _VALID_OWNER_TYPES:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "validation_error",
                    "message": "Validation failed",
                    "details": {
                        "fields": {
                            "owner_type": "must be 'character', 'group', or 'location'"
                        }
                    },
                }
            },
        )

    story = story_svc.get_story(db, story_id)
    if story is None:
        raise _story_not_found(story_id)

    owner_record = story_svc.get_owner(db, story_id, owner_type, owner_id)
    if owner_record is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "not_found",
                    "message": (
                        f"{owner_type.capitalize()} '{owner_id}' is not an owner of story '{story_id}'."
                    ),
                }
            },
        )

    story_svc.remove_owner(db, owner_record)


# ---------------------------------------------------------------------------
# POST /stories/{id}/entries
# ---------------------------------------------------------------------------


@router.post(
    "/stories/{story_id}/entries",
    response_model=StoryEntryResponse,
    status_code=201,
    summary="Add a narrative entry to a story",
    description=(
        "Any authenticated user may add a narrative entry to a story.  "
        "``author_id`` is set from the authenticated user — not from the request body.  "
        "``session_id`` is auto-captured from the currently active session, if any.  "
        "Returns 404 if the story does not exist."
    ),
)
def create_entry(
    story_id: str,
    body: CreateStoryEntryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StoryEntryResponse:
    """Add a narrative entry to a story.

    Args:
        story_id: ULID of the story to add an entry to.
        body: Validated request body containing ``text``, optional ``character_id``,
            and optional ``game_object_refs``.
        current_user: Authenticated user (any role).
        db: Injected SQLAlchemy session.

    Returns:
        ``StoryEntryResponse`` for the newly created entry (201).

    Raises:
        HTTPException(404): If the story does not exist.
    """
    if current_user.role == Role.VIEWER:
        raise_forbidden("Viewers have read-only access.")

    story = story_svc.get_story(db, story_id)
    if story is None:
        raise _story_not_found(story_id)
    if not can_user_see_story(db, current_user, story):
        raise _story_not_found(story_id)

    session_id = story_svc.get_active_session_id(db)

    entry = story_svc.create_story_entry(
        db,
        story_id=story_id,
        text=body.text,
        author_id=current_user.id,
        character_id=body.character_id,
        game_object_refs=body.game_object_refs,
        session_id=session_id,
    )
    return StoryEntryResponse.model_validate(entry)


# ---------------------------------------------------------------------------
# PATCH /stories/{id}/entries/{entry_id}
# ---------------------------------------------------------------------------


@router.patch(
    "/stories/{story_id}/entries/{entry_id}",
    response_model=StoryEntryResponse,
    status_code=200,
    summary="Edit a story entry",
    description=(
        "Update the text of a narrative entry.  "
        "Players may only edit their own entries (``author_id`` matches the authenticated user).  "
        "The GM may edit any entry.  "
        "Sets ``updated_by`` to the current user's ID.  "
        "Returns 404 if the story or entry does not exist, or if the entry does not belong to "
        "the specified story.  "
        "Returns 403 if a player attempts to edit another player's entry."
    ),
)
def update_entry(
    story_id: str,
    entry_id: str,
    body: UpdateStoryEntryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StoryEntryResponse:
    """Update the text of a story entry.

    Args:
        story_id: ULID of the containing story.
        entry_id: ULID of the entry to update.
        body: Validated request body with ``text``.
        current_user: Authenticated user.
        db: Injected SQLAlchemy session.

    Returns:
        ``StoryEntryResponse`` with updated fields (200).

    Raises:
        HTTPException(404): If the story or entry does not exist, or the entry
            does not belong to this story.
        HTTPException(403): If a non-GM player attempts to edit another user's entry.
    """
    if current_user.role == Role.VIEWER:
        raise_forbidden("Viewers have read-only access.")

    story = story_svc.get_story(db, story_id)
    if story is None:
        raise _story_not_found(story_id)

    entry = story_svc.get_story_entry(db, entry_id)
    if entry is None or entry.story_id != story_id:
        raise _entry_not_found(entry_id)

    if current_user.role != Role.GM and entry.author_id != current_user.id:
        raise_forbidden("You can only edit your own story entries.")

    entry = story_svc.update_story_entry(
        db,
        entry,
        text=body.text,
        updated_by=current_user.id,
    )
    return StoryEntryResponse.model_validate(entry)


# ---------------------------------------------------------------------------
# DELETE /stories/{id}/entries/{entry_id}
# ---------------------------------------------------------------------------


@router.delete(
    "/stories/{story_id}/entries/{entry_id}",
    status_code=204,
    summary="Soft-delete a story entry",
    description=(
        "Soft-delete a narrative entry by setting ``is_deleted = true``.  "
        "Sets ``deleted_by`` to the current user's ID.  "
        "Players may only delete their own entries.  GM may delete any entry.  "
        "Returns 404 if the story or entry does not exist, or if the entry does not belong to "
        "the specified story.  "
        "Returns 403 if a player attempts to delete another player's entry.  "
        "Returns 204 with no body on success."
    ),
)
def delete_entry(
    story_id: str,
    entry_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Soft-delete a story entry.

    Args:
        story_id: ULID of the containing story.
        entry_id: ULID of the entry to soft-delete.
        current_user: Authenticated user.
        db: Injected SQLAlchemy session.

    Returns:
        ``None`` — FastAPI sends 204 No Content.

    Raises:
        HTTPException(404): If the story or entry does not exist, or the entry
            does not belong to this story.
        HTTPException(403): If a non-GM player attempts to delete another user's entry.
    """
    if current_user.role == Role.VIEWER:
        raise_forbidden("Viewers have read-only access.")

    story = story_svc.get_story(db, story_id)
    if story is None:
        raise _story_not_found(story_id)

    entry = story_svc.get_story_entry(db, entry_id)
    if entry is None or entry.story_id != story_id:
        raise _entry_not_found(entry_id)

    if current_user.role != Role.GM and entry.author_id != current_user.id:
        raise_forbidden("You can only delete your own story entries.")

    story_svc.delete_story_entry(db, entry, deleted_by=current_user.id)
