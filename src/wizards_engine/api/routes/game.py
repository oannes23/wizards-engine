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
    summary="Redeem an invite code and create an account",
    description=(
        "Atomically redeems an invite code: marks the invite as consumed "
        "and creates a User account (login_code = the invite code).  For "
        "player invites a full Character (all mechanical fields defaulting "
        "to 0) is also created.  For viewer invites no character is created.  "
        "Sets an httpOnly auth cookie.  Returns 201 with the new user's info.  "
        "Returns 404 with invite_not_found for all invalid invite cases.  "
        "Returns 422 if a player invite is redeemed without a character_name."
    ),
)
def join(
    body: JoinRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> JoinResponse:
    """Redeem an invite code and create a user account.

    This endpoint is intentionally unauthenticated — it is the entry point
    for a new participant (player or viewer) joining the game.

    For player invites ``character_name`` is required; the service raises
    ``ValueError`` if it is missing, which the route surfaces as 422.

    Args:
        body: Validated request body containing code, optional character_name,
            and display_name.
        response: FastAPI Response object used to set the auth cookie.
        db: Injected SQLAlchemy session.

    Returns:
        JoinResponse with the new user's id, display_name, role, and
        character_id (non-null for players, null for viewers).

    Raises:
        HTTPException(404): If the invite code is invalid, already consumed,
            or does not exist (``invite_not_found`` error code).  The same
            error is returned for all invalid cases to prevent code enumeration.
        HTTPException(422): If the invite is a player invite and
            ``character_name`` was not provided.
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
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "missing_character_name",
                    "message": str(exc),
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
