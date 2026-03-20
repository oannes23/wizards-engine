"""Route handlers for /api/v1/game/invites — Invite management endpoints.

All endpoints are GM-only.  Invite IDs are ULIDs and serve as the
shareable magic link codes — there is no separate code column.

Endpoints
---------
POST   /game/invites        — GM only.  Generate a bare invite.  Returns 201 with
                              invite info including the magic link URL (/login/<id>).
GET    /game/invites        — GM only.  List all invites (consumed + unconsumed).
                              ULID cursor pagination.
DELETE /game/invites/{id}  — GM only.  Hard-delete an unconsumed invite.
                              Returns 204.  Returns 409 if already consumed.
                              Returns 404 if not found.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from wizards_engine.api.deps import require_gm
from wizards_engine.api.pagination import paginate
from wizards_engine.api.responses import raise_not_found
from wizards_engine.db import get_db
from wizards_engine.models.user import Invite, User
from wizards_engine.schemas.common import PaginatedResponse
from wizards_engine.schemas.invite import InviteResponse
from wizards_engine.services import invite as invite_svc

router = APIRouter()


@router.post(
    "/game/invites",
    response_model=InviteResponse,
    status_code=201,
    summary="Create an invite",
    description=(
        "GM only.  Generates a bare invite with a ULID as the shareable code.  "
        "The invite ID IS the code — no separate code column exists.  "
        "Returns 201 with invite info including the magic link URL (``/login/<id>``)."
    ),
)
def create_invite(
    _gm: User = Depends(require_gm),
    db: Session = Depends(get_db),
) -> InviteResponse:
    """Generate a new bare invite code.

    Args:
        _gm: The authenticated GM (injected; ensures GM-only access).
        db: Injected SQLAlchemy session.

    Returns:
        ``InviteResponse`` for the newly created invite (201), including
        the computed ``login_url`` magic link.
    """
    invite = invite_svc.create_invite(db)
    return InviteResponse.model_validate(invite)


@router.get(
    "/game/invites",
    response_model=PaginatedResponse[InviteResponse],
    status_code=200,
    summary="List invites",
    description=(
        "GM only.  Returns a paginated list of all invite codes (consumed and "
        "unconsumed).  ULID cursor pagination via ``?after=<ulid>&limit=N``."
    ),
)
def list_invites(
    after: str | None = None,
    limit: int = 50,
    _gm: User = Depends(require_gm),
    db: Session = Depends(get_db),
) -> PaginatedResponse[InviteResponse]:
    """Return a paginated list of all invites.

    Args:
        after: ULID cursor for pagination (return items older than this ID).
        limit: Page size (default 50, max 100).
        _gm: The authenticated GM (injected; ensures GM-only access).
        db: Injected SQLAlchemy session.

    Returns:
        ``PaginatedResponse`` wrapping a list of ``InviteResponse`` objects.
    """
    q = invite_svc.list_invites_query(db)
    page = paginate(db, q, model=Invite, after=after, limit=limit)

    return PaginatedResponse[InviteResponse](
        items=[InviteResponse.model_validate(inv) for inv in page.items],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


@router.delete(
    "/game/invites/{invite_id}",
    status_code=204,
    summary="Delete an invite",
    description=(
        "GM only.  Hard-deletes an unconsumed invite code.  "
        "Returns 204 with no body on success.  "
        "Returns 409 if the invite has already been consumed.  "
        "Returns 404 if no invite exists with that ID."
    ),
)
def delete_invite(
    invite_id: str,
    _gm: User = Depends(require_gm),
    db: Session = Depends(get_db),
) -> None:
    """Hard-delete an unconsumed invite.

    Args:
        invite_id: ULID of the invite to delete.
        _gm: The authenticated GM (injected; ensures GM-only access).
        db: Injected SQLAlchemy session.

    Returns:
        ``None`` — FastAPI sends 204 No Content.

    Raises:
        HTTPException(404): If no invite exists with ``invite_id``.
        HTTPException(409): If the invite has already been consumed.
    """
    invite = invite_svc.get_invite(db, invite_id)
    if invite is None:
        raise_not_found("Invite", invite_id)

    if invite.is_consumed:
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "invite_consumed",
                    "message": (
                        "This invite has already been consumed and cannot be deleted."
                    ),
                }
            },
        )

    invite_svc.delete_invite(db, invite)
