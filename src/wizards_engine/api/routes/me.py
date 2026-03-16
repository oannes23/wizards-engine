"""Route handlers for GET /me and PATCH /me — identity and profile endpoints.

Both endpoints require authentication via the ``get_current_user`` dependency.
The GM and player accounts both use the same endpoints; the ``character_id``
field in the response will be ``None`` for users not yet linked to a character.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from wizards_engine.api.deps import get_current_user
from wizards_engine.db import get_db
from wizards_engine.models.user import User
from wizards_engine.schemas.auth import MeResponse, UpdateMeRequest

router = APIRouter()


@router.get(
    "/me",
    response_model=MeResponse,
    status_code=200,
    summary="Get current user identity",
    description=(
        "Returns the identity of the authenticated caller: id, display_name, "
        "role, and character_id (null if not linked to a character).  Requires "
        "a valid login_code cookie."
    ),
)
def get_me(
    current_user: User = Depends(get_current_user),
) -> MeResponse:
    """Return the authenticated user's identity.

    Args:
        current_user: The authenticated user (injected via ``get_current_user``).

    Returns:
        MeResponse containing the user's id, display_name, role, and
        character_id.
    """
    return MeResponse(
        id=current_user.id,
        display_name=current_user.display_name,
        role=current_user.role,
        character_id=current_user.character_id,
    )


@router.patch(
    "/me",
    response_model=MeResponse,
    status_code=200,
    summary="Update current user profile",
    description=(
        "Updates the authenticated user's profile.  Currently only "
        "``display_name`` can be changed.  The name is stripped of surrounding "
        "whitespace and must be 1–50 characters long after trimming."
    ),
)
def patch_me(
    body: UpdateMeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MeResponse:
    """Update the authenticated user's display name.

    Only fields present in the request body are applied (``exclude_unset``
    behaviour is handled implicitly here since ``UpdateMeRequest`` only exposes
    ``display_name`` — the pattern remains consistent with richer future PATCH
    endpoints).

    Args:
        body: Validated request body with the new display_name.
        current_user: The authenticated user (injected via ``get_current_user``).
        db: Injected SQLAlchemy session.

    Returns:
        MeResponse with the updated user data on success.
    """
    current_user.display_name = body.display_name
    db.flush()

    return MeResponse(
        id=current_user.id,
        display_name=current_user.display_name,
        role=current_user.role,
        character_id=current_user.character_id,
    )
