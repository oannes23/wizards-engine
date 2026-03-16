"""Route handlers for /me endpoints — identity, profile, character, and link refresh.

All endpoints require authentication via the ``get_current_user`` dependency.
The GM and player accounts both use the same endpoints; the ``character_id``
field in the response will be ``None`` for users not yet linked to a character.

Endpoints
---------
GET   /me                — Any authenticated user. Returns identity.
PATCH /me                — Any authenticated user. Updates display_name.
POST  /me/character      — GM only. Creates a full Character and links to GM.
POST  /me/refresh-link   — Any authenticated user. Rotates own login code.
"""

import secrets

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from wizards_engine.api.auth import set_auth_cookie
from wizards_engine.api.deps import get_current_user, require_gm
from wizards_engine.db import get_db
from wizards_engine.models.character import Character
from wizards_engine.models.user import User
from wizards_engine.schemas.auth import MeResponse, UpdateMeRequest
from wizards_engine.schemas.character import CharacterResponse, CreateCharacterRequest
from wizards_engine.services.onboarding import _FULL_MAGIC_STATS, _FULL_SKILLS

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


@router.post(
    "/me/character",
    response_model=CharacterResponse,
    status_code=201,
    summary="Create GM character",
    description=(
        "GM only.  Creates a full (PC-level) Character with all mechanical "
        "fields defaulting to 0 and links it to the GM account.  If the GM "
        "already has a linked character, the old character is left as an "
        "ownerless full Character in the database — it is not deleted."
    ),
)
def create_gm_character(
    body: CreateCharacterRequest,
    gm: User = Depends(require_gm),
    db: Session = Depends(get_db),
) -> CharacterResponse:
    """Create a full Character and link it to the GM account.

    Validates ``name`` (1–200 characters after stripping via
    ``CreateCharacterRequest``).  If the GM already owns a character, the FK
    is simply overwritten — the old character record remains intact but
    unowned.

    Args:
        body: Validated request body containing the character ``name``.
        gm: The authenticated GM user (enforced via ``require_gm``).
        db: Injected SQLAlchemy session.

    Returns:
        ``CharacterResponse`` for the newly created Character (HTTP 201).
    """
    character = Character(
        name=body.name,
        detail_level="full",
        stress=0,
        free_time=0,
        plot=0,
        gnosis=0,
        skills=dict(_FULL_SKILLS),
        magic_stats={k: dict(v) for k, v in _FULL_MAGIC_STATS.items()},
        last_session_time_now=0,
        is_deleted=False,
    )
    db.add(character)
    db.flush()  # populate character.id before setting the FK

    gm.character_id = character.id
    db.flush()
    db.refresh(character)

    return CharacterResponse.model_validate(character)


@router.post(
    "/me/refresh-link",
    status_code=200,
    summary="Refresh own magic link",
    description=(
        "Any authenticated user.  Generates a new ``secrets.token_urlsafe(32)`` "
        "login code, invalidates the old link immediately, updates the auth "
        "cookie, and returns the new magic link URL."
    ),
)
def refresh_link(
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Rotate the caller's login code and update the auth cookie.

    The old login code is overwritten in-place so that any session still using
    it will receive a 401 on the next request.  The new code is written to the
    ``Set-Cookie`` header so the current browser session remains authenticated.

    Args:
        response: FastAPI Response object used to set the updated cookie.
        current_user: The authenticated user (any role).
        db: Injected SQLAlchemy session.

    Returns:
        A dict with a single ``login_url`` key containing the new magic link
        path (``/login/<new_code>``).
    """
    new_code = secrets.token_urlsafe(32)
    current_user.login_code = new_code
    db.flush()

    set_auth_cookie(response, new_code)

    return {"login_url": f"/login/{new_code}"}
