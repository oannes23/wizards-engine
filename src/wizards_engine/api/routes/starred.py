"""Route handlers for /api/v1/me/starred — Game Object starring endpoints.

Players can star Game Objects (characters, groups, locations) so that the
starred feed (GET /api/v1/me/feed/starred) only shows activity for those
objects.

Endpoints
---------
GET    /me/starred             — Authenticated.  List all starred objects.
POST   /me/starred             — Authenticated.  Star a Game Object.
DELETE /me/starred/{type}/{id} — Authenticated.  Unstar a Game Object.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from wizards_engine.api.deps import get_current_user
from wizards_engine.api.responses import raise_not_found
from wizards_engine.db import get_db
from wizards_engine.models.character import Character
from wizards_engine.models.group import Group
from wizards_engine.models.location import Location
from wizards_engine.models.starred import StarredObject
from wizards_engine.models.user import User
from wizards_engine.schemas.starred import VALID_OBJECT_TYPES, StarredObjectResponse, StarRequest

router = APIRouter()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_name(db: Session, object_type: str, object_id: str) -> str | None:
    """Look up the name of a Game Object from the appropriate table.

    Returns ``None`` if the object does not exist or has been soft-deleted.

    Args:
        db: SQLAlchemy session.
        object_type: One of ``character``, ``group``, or ``location``.
        object_id: ULID of the Game Object.

    Returns:
        The object's display name, or ``None`` if not found / deleted.
    """
    if object_type == "character":
        obj = db.scalars(
            select(Character).where(
                Character.id == object_id,
                Character.is_deleted == False,  # noqa: E712
            )
        ).first()
    elif object_type == "group":
        obj = db.scalars(
            select(Group).where(
                Group.id == object_id,
                Group.is_deleted == False,  # noqa: E712
            )
        ).first()
    elif object_type == "location":
        obj = db.scalars(
            select(Location).where(
                Location.id == object_id,
                Location.is_deleted == False,  # noqa: E712
            )
        ).first()
    else:
        return None

    return obj.name if obj is not None else None


# ---------------------------------------------------------------------------
# GET /me/starred
# ---------------------------------------------------------------------------


@router.get(
    "/me/starred",
    response_model=list[StarredObjectResponse],
    status_code=200,
    summary="List starred Game Objects",
    description=(
        "Returns all Game Objects starred by the authenticated user.  Each item "
        "includes the object type, ULID, and resolved display name.  Starred "
        "entries whose target object has since been soft-deleted are included "
        "with an empty string for name."
    ),
)
def list_starred(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[StarredObjectResponse]:
    """Return the authenticated user's list of starred Game Objects.

    Queries ``starred_objects`` for all rows belonging to the current user,
    then resolves the display name of each from the appropriate model table.

    Args:
        current_user: The authenticated user (injected via ``get_current_user``).
        db: Injected SQLAlchemy session.

    Returns:
        A list of ``StarredObjectResponse`` items, one per starred entry.
        Order matches database insertion order.
    """
    rows = db.scalars(
        select(StarredObject).where(StarredObject.user_id == current_user.id)
    ).all()

    items: list[StarredObjectResponse] = []
    for row in rows:
        name = _resolve_name(db, row.object_type, row.object_id) or ""
        items.append(
            StarredObjectResponse(type=row.object_type, id=row.object_id, name=name)
        )

    return items


# ---------------------------------------------------------------------------
# POST /me/starred
# ---------------------------------------------------------------------------


@router.post(
    "/me/starred",
    response_model=StarredObjectResponse,
    status_code=201,
    summary="Star a Game Object",
    description=(
        "Stars a Game Object for the authenticated user.  The object must "
        "exist and must not be soft-deleted.  If the object is already "
        "starred, returns 200 instead of 201 (idempotent).  "
        "``type`` must be one of: ``character``, ``group``, ``location``."
    ),
)
def star_object(
    body: StarRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StarredObjectResponse:
    """Star a Game Object for the authenticated user.

    Validates that the target Game Object exists and is not soft-deleted,
    then creates or returns the existing ``StarredObject`` row.

    Args:
        body: Validated request body with ``type`` and ``id``.
        current_user: The authenticated user (injected via ``get_current_user``).
        db: Injected SQLAlchemy session.

    Returns:
        ``StarredObjectResponse`` with type, id, and resolved name.

    Raises:
        HTTPException(404): If the Game Object does not exist or is deleted.
    """
    name = _resolve_name(db, body.type, body.id)
    if name is None:
        raise_not_found(body.type.capitalize(), body.id)

    # Check for existing star (idempotent: return 200 if already starred).
    existing = db.get(
        StarredObject,
        {"user_id": current_user.id, "object_type": body.type, "object_id": body.id},
    )
    if existing is not None:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=200,
            content={"type": body.type, "id": body.id, "name": name},
        )

    row = StarredObject(
        user_id=current_user.id,
        object_type=body.type,
        object_id=body.id,
    )
    db.add(row)
    db.flush()

    return StarredObjectResponse(type=body.type, id=body.id, name=name)


# ---------------------------------------------------------------------------
# DELETE /me/starred/{type}/{id}
# ---------------------------------------------------------------------------


@router.delete(
    "/me/starred/{object_type}/{object_id}",
    status_code=204,
    summary="Unstar a Game Object",
    description=(
        "Removes the starred entry for the given Game Object.  "
        "If the object is not currently starred, still returns 204 (idempotent).  "
        "``object_type`` must be one of: ``character``, ``group``, ``location``."
    ),
)
def unstar_object(
    object_type: str,
    object_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Remove the starred entry for a Game Object.

    If the ``object_type`` is invalid or the entry does not exist, returns 204
    without error (idempotent by design).

    Args:
        object_type: The Game Object type path parameter.
        object_id: The ULID of the Game Object path parameter.
        current_user: The authenticated user (injected via ``get_current_user``).
        db: Injected SQLAlchemy session.

    Returns:
        ``None`` — FastAPI sends 204 No Content.
    """
    if object_type not in VALID_OBJECT_TYPES:
        # Invalid type — nothing to unstar, still idempotent.
        return None

    existing = db.get(
        StarredObject,
        {"user_id": current_user.id, "object_type": object_type, "object_id": object_id},
    )
    if existing is not None:
        db.delete(existing)
        db.flush()

    return None
