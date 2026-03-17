"""Route handler for POST /setup — initial GM account creation.

This is an unauthenticated endpoint that must be called exactly once to
bootstrap the system.  It creates the GM user record, issues a login code,
sets the httpOnly auth cookie, and returns the magic link URL.

Subsequent calls return 409 Conflict because only one GM may exist.
"""

import secrets

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from wizards_engine.api.auth import set_auth_cookie
from wizards_engine.db import get_db
from wizards_engine.models.user import User
from wizards_engine.schemas.auth import SetupRequest, SetupResponse

router = APIRouter()


@router.post(
    "/setup",
    response_model=SetupResponse,
    status_code=201,
    summary="Bootstrap the GM account",
    description=(
        "Creates the initial GM user.  May only be called once — returns 409 "
        "if a GM already exists.  Sets an httpOnly login_code cookie and returns "
        "the magic link URL for the GM."
    ),
)
def setup(
    body: SetupRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> SetupResponse:
    """Create the GM user and issue an auth cookie.

    This endpoint is intentionally unauthenticated — it is the entry point
    that bootstraps a fresh system before any users exist.

    Args:
        body: Validated request body containing the GM's display name.
        response: FastAPI Response object used to set the auth cookie.
        db: Injected SQLAlchemy session.

    Returns:
        SetupResponse with the new GM's id, display_name, role, and login_url.

    Raises:
        JSONResponse(409): If a user with ``role = 'gm'`` already exists
            (``already_setup`` error code).
    """
    existing_gm = db.scalars(select(User).where(User.role == "gm")).first()
    if existing_gm is not None:
        raise HTTPException(
            status_code=409,
            detail={"error": {"code": "already_setup", "message": "A GM account already exists. Setup can only be run once."}},
        )

    login_code = secrets.token_urlsafe(32)

    gm = User(
        display_name=body.display_name,
        role="gm",
        login_code=login_code,
        is_active=True,
    )
    db.add(gm)
    db.flush()

    set_auth_cookie(response, login_code)

    return SetupResponse(
        id=gm.id,
        display_name=gm.display_name,
        role=gm.role,
        login_url=f"/login/{login_code}",
    )
