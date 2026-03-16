"""Route handler for game-level unauthenticated endpoints.

Currently provides:

- ``POST /game/join``: Redeem an invite code to create a new player account
  and full Character in a single atomic transaction.
"""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from wizards_engine.api.auth import set_auth_cookie
from wizards_engine.db import get_db
from wizards_engine.schemas.auth import JoinRequest, JoinResponse
from wizards_engine.services.onboarding import InviteNotFoundError, join_game

router = APIRouter()


@router.post(
    "/game/join",
    response_model=JoinResponse,
    status_code=201,
    summary="Redeem an invite code and create a player account",
    description=(
        "Atomically redeems an invite code: marks the invite as consumed, "
        "creates a full Character (all mechanical fields defaulting to 0), "
        "and creates a User account (login_code = the invite code).  Sets an "
        "httpOnly auth cookie.  Returns 201 with the new user's info.  "
        "Returns 404 with invite_not_found for all invalid invite cases."
    ),
)
def join(
    body: JoinRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> JoinResponse:
    """Redeem an invite code and create a player account + full Character.

    This endpoint is intentionally unauthenticated — it is the entry point
    for a new player joining the game.

    Args:
        body: Validated request body containing code, character_name,
            and display_name.
        response: FastAPI Response object used to set the auth cookie.
        db: Injected SQLAlchemy session.

    Returns:
        JoinResponse with the new user's id, display_name, role, and
        character_id.

    Raises:
        HTTPException(404): If the invite code is invalid, already consumed,
            or does not exist (``invite_not_found`` error code).  The same
            error is returned for all invalid cases to prevent code enumeration.
    """
    try:
        user = join_game(
            db,
            code=body.code,
            character_name=body.character_name,
            display_name=body.display_name,
        )
    except InviteNotFoundError:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "invite_not_found",
                    "message": "The provided invite code is invalid or has already been used.",
                }
            },
        )

    set_auth_cookie(response, body.code)

    return JoinResponse(
        id=user.id,
        display_name=user.display_name,
        role=user.role,
        character_id=user.character_id,
    )
