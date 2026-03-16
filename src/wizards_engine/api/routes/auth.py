"""Route handler for POST /auth/login — code-based login.

Accepts a raw code string and resolves it against two tables in priority order:

1. Users — if the code matches a User's ``login_code`` AND the user is active,
   set the auth cookie and return user info with ``type="user"``.
2. Invites — if the code matches an unconsumed Invite's ``id``, return
   ``{"type": "invite"}`` (no cookie set; frontend redirects to the join form).
3. Otherwise — return 404 with ``{"error": {"code": "code_not_found"}}``.

Inactive users with a matching ``login_code`` fall through to case 3 to avoid
leaking account-state information through the login endpoint.

Consumed invites with a matching ``id`` also fall through to case 3 to avoid
leaking whether a code was once a valid invite.
"""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from wizards_engine.api.auth import set_auth_cookie
from wizards_engine.db import get_db
from wizards_engine.models.user import Invite, User
from wizards_engine.schemas.auth import LoginInviteResponse, LoginRequest, LoginUserResponse

router = APIRouter()


@router.post(
    "/auth/login",
    status_code=200,
    summary="Log in with a code",
    description=(
        "Accepts a raw code string and resolves it against active users and "
        "unconsumed invites.  On a user match the auth cookie is set and user "
        "info is returned.  On an invite match no cookie is set and the response "
        "signals the frontend to redirect to the join form.  All unresolved codes "
        "return 404 regardless of whether the code was once a valid invite."
    ),
)
def login(
    body: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> LoginUserResponse | LoginInviteResponse:
    """Resolve a login code and return the appropriate response.

    Args:
        body: Validated request body containing the ``code`` string.
        response: FastAPI Response object used to set the auth cookie on success.
        db: Injected SQLAlchemy session.

    Returns:
        ``LoginUserResponse`` (with auth cookie set) when the code matches an
        active user, or ``LoginInviteResponse`` when it matches an unconsumed
        invite.

    Raises:
        JSONResponse(404): When the code does not resolve to an active user or
            an unconsumed invite (``code_not_found`` error code).
    """
    # --- 1. Check active users first ---
    user = (
        db.query(User)
        .filter(User.login_code == body.code, User.is_active.is_(True))
        .first()
    )
    if user is not None:
        set_auth_cookie(response, user.login_code)
        return LoginUserResponse(
            id=user.id,
            display_name=user.display_name,
            role=user.role,
            character_id=user.character_id,
        )

    # --- 2. Check unconsumed invites ---
    invite = (
        db.query(Invite)
        .filter(Invite.id == body.code, Invite.is_consumed.is_(False))
        .first()
    )
    if invite is not None:
        return LoginInviteResponse()

    # --- 3. No match — same 404 for all remaining cases (consumed invites,
    #         inactive users, unknown codes) to avoid leaking state.
    raise HTTPException(
        status_code=404,
        detail={"error": {"code": "code_not_found", "message": "No active user or unconsumed invite matches the provided code."}},
    )
