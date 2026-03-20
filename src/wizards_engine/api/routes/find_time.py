"""Route handler for POST /api/v1/characters/{id}/find-time.

Player direct action that converts 3 Plot → 1 Free Time.

Endpoint
--------
POST /characters/{id}/find-time  — Owner or GM.  Spend 3 Plot to gain 1 FT.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from wizards_engine.api.deps import get_current_user
from wizards_engine.api.responses import raise_forbidden, raise_not_found
from wizards_engine.db import get_db
from wizards_engine.models.user import User
from wizards_engine.models.character import Character
from wizards_engine.services.player_actions import execute_find_time

router = APIRouter()

# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------


class FindTimeResponse(BaseModel):
    """Response body for the find-time action.

    Returns the character's updated meter values after the conversion.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    plot: int
    free_time: int


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.post(
    "/characters/{character_id}/find-time",
    response_model=FindTimeResponse,
    status_code=200,
    summary="Find Time — convert 3 Plot to 1 Free Time",
    description=(
        "Player direct action.  Spends 3 Plot to gain 1 Free Time.  "
        "Only full (PC-level) characters may use this action.  "
        "The owning player may call this endpoint; the GM may call it on behalf of any character.  "
        "Returns 409 if Plot < 3 (insufficient_plot) or Free Time is already at cap of 20 "
        "(free_time_at_cap)."
    ),
)
def find_time(
    character_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FindTimeResponse:
    """Convert 3 Plot into 1 Free Time for a full (PC) character.

    Args:
        character_id: ULID of the target character.
        current_user: Authenticated user.  Must be the character's owning player
            or the GM.
        db: Injected SQLAlchemy session.

    Returns:
        ``FindTimeResponse`` with the character's updated ``plot`` and
        ``free_time`` values.

    Raises:
        HTTPException(404): If the character does not exist or is deleted.
        HTTPException(403): If the caller is neither the GM nor the
            character's owning player.
        HTTPException(409): If the character has fewer than 3 Plot
            (``insufficient_plot``) or Free Time is already at 20
            (``free_time_at_cap``).
    """
    # Authorisation — owner or GM (checked before calling the service).
    character: Character | None = db.get(Character, character_id)
    if character is None or character.is_deleted:
        raise_not_found("Character", character_id)

    if current_user.role != "gm" and current_user.character_id != character_id:
        raise_forbidden("You do not have permission to perform this action for this character.")

    result = execute_find_time(db, character_id, actor_user=current_user)
    return FindTimeResponse(
        id=result.id,
        plot=result.plot,
        free_time=result.free_time,
    )
