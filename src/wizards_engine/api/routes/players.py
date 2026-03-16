"""Route handlers for /api/v1/players — Player Roster endpoints.

Provides a listing of all users in the campaign and GM-only player management
actions.  The GET response shape differs based on the caller's role:

- Authenticated non-GM callers receive display_name, role, character_id,
  and is_active for each user.
- GM callers additionally receive login_url per user (the magic link URL),
  enabling the GM to view and share player links without regenerating them.

Endpoints
---------
GET  /players                        — Any authenticated user.  Returns all users.
POST /players/{id}/regenerate-token  — GM only.  Regenerates login code for the
                                       target player; old link stops working
                                       immediately.
"""

import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from wizards_engine.api.deps import get_current_user, require_gm
from wizards_engine.db import get_db
from wizards_engine.models.user import User
from wizards_engine.schemas.player import PlayerGMResponse, PlayerResponse

router = APIRouter()


@router.get(
    "/players",
    status_code=200,
    summary="Player roster",
    description=(
        "Returns all users in the campaign (GM + players), not paginated.  "
        "All authenticated users may call this endpoint.  "
        "For GM callers, each entry includes ``login_url`` — the magic link URL "
        "for that player.  For non-GM callers, ``login_url`` is omitted."
    ),
)
def list_players(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PlayerGMResponse] | list[PlayerResponse]:
    """Return all users in the campaign.

    The response shape differs by caller role.  GM callers receive the full
    ``PlayerGMResponse`` (including ``login_url``); all other callers receive
    ``PlayerResponse`` (without ``login_url``).

    Args:
        current_user: The authenticated user (any role).
        db: Injected SQLAlchemy session.

    Returns:
        A flat list of player records.  GM callers receive ``login_url`` per
        entry; non-GM callers do not.
    """
    users: list[User] = db.query(User).order_by(User.id).all()

    if current_user.role == "gm":
        return [
            PlayerGMResponse(
                id=u.id,
                display_name=u.display_name,
                role=u.role,
                character_id=u.character_id,
                is_active=u.is_active,
                login_url=f"/login/{u.login_code}",
            )
            for u in users
        ]

    return [PlayerResponse.model_validate(u) for u in users]


@router.post(
    "/players/{id}/regenerate-token",
    status_code=200,
    summary="Regenerate a player's login code",
    description=(
        "GM only.  Generates a new ``secrets.token_urlsafe(32)`` login code "
        "for the target player.  The old magic link stops working immediately.  "
        "Returns the new magic link URL for the GM to share with the player."
    ),
)
def regenerate_player_token(
    id: str,
    gm: User = Depends(require_gm),
    db: Session = Depends(get_db),
) -> dict:
    """Rotate a player's login code and return the new magic link URL.

    Looks up the target user by primary key.  Returns 404 if the user does
    not exist.  The new code is **not** set as a cookie — the GM receives the
    URL to share with the player out-of-band.

    Args:
        id: ULID primary key of the target user.
        gm: The authenticated GM user (enforced via ``require_gm``).
        db: Injected SQLAlchemy session.

    Returns:
        A dict with a single ``login_url`` key containing the new magic link
        path (``/login/<new_code>``).

    Raises:
        HTTPException(404): if no user with the given ``id`` exists
            (``player_not_found``).
    """
    target = db.get(User, id)
    if target is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "player_not_found", "message": "Player not found."}},
        )

    new_code = secrets.token_urlsafe(32)
    target.login_code = new_code
    db.flush()

    return {"login_url": f"/login/{new_code}"}
