"""Route handler for POST /api/v1/characters/{id}/find-time.

Player direct action that converts 3 Plot → 1 Free Time.

Endpoint
--------
POST /characters/{id}/find-time  — Owner or GM.  Spend 3 Plot to gain 1 FT.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from wizards_engine.api.deps import get_current_user
from wizards_engine.db import get_db
from wizards_engine.models.character import Character
from wizards_engine.models.user import User
from wizards_engine.services.event import create_event

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
    # ------------------------------------------------------------------
    # 1. Fetch character — must exist and not be deleted
    # ------------------------------------------------------------------
    character: Character | None = db.get(Character, character_id)
    if character is None or character.is_deleted:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "not_found",
                    "message": f"Character '{character_id}' not found.",
                }
            },
        )

    # ------------------------------------------------------------------
    # 2. Authorisation — owner or GM
    # ------------------------------------------------------------------
    if current_user.role != "gm" and current_user.character_id != character_id:
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "forbidden",
                    "message": "You do not have permission to perform this action for this character.",
                }
            },
        )

    # ------------------------------------------------------------------
    # 3. Must be a full (PC-level) character
    # ------------------------------------------------------------------
    if character.detail_level != "full":
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "not_a_pc",
                    "message": "Only full (PC-level) characters can use find-time.",
                }
            },
        )

    # ------------------------------------------------------------------
    # 4. Validate Plot >= 3
    # ------------------------------------------------------------------
    plot_before: int = character.plot or 0
    if plot_before < 3:
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "insufficient_plot",
                    "message": "Character does not have enough Plot (requires 3).",
                }
            },
        )

    # ------------------------------------------------------------------
    # 5. Validate Free Time < 20
    # ------------------------------------------------------------------
    ft_before: int = character.free_time or 0
    if ft_before >= 20:
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "free_time_at_cap",
                    "message": "Character's Free Time is already at the cap of 20.",
                }
            },
        )

    # ------------------------------------------------------------------
    # 6. Apply changes
    # ------------------------------------------------------------------
    plot_after = plot_before - 3
    ft_after = ft_before + 1

    character.plot = plot_after
    character.free_time = ft_after
    db.flush()

    # ------------------------------------------------------------------
    # 7. Create event
    # ------------------------------------------------------------------
    create_event(
        db,
        type="player.find_time",
        actor_type="gm" if current_user.role == "gm" else "player",
        actor_id=current_user.id,
        visibility="private",
        changes={
            f"character.{character_id}.plot": {
                "op": "meter.delta",
                "before": plot_before,
                "after": plot_after,
            },
            f"character.{character_id}.free_time": {
                "op": "meter.delta",
                "before": ft_before,
                "after": ft_after,
            },
        },
        targets=[
            {
                "target_type": "character",
                "target_id": character_id,
                "is_primary": True,
            }
        ],
    )

    # ------------------------------------------------------------------
    # 8. Return updated meters
    # ------------------------------------------------------------------
    db.refresh(character)
    return FindTimeResponse(
        id=character.id,
        plot=character.plot,
        free_time=character.free_time,
    )
