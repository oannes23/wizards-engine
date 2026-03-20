"""Route handler for POST /api/v1/characters/{id}/recharge-trait.

Player direct action that spends 1 Free Time to restore a trait's charges to 5.

Endpoint
--------
POST /characters/{id}/recharge-trait  — Owner or GM.  Spend 1 FT to fully
recharge one active Core or Role trait slot.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from wizards_engine.api.deps import get_current_user
from wizards_engine.api.responses import raise_forbidden, raise_not_found
from wizards_engine.db import get_db
from wizards_engine.models.character import Character
from wizards_engine.models.user import User
from wizards_engine.schemas.character import CharacterResponse
from wizards_engine.services.player_actions import execute_recharge_trait

router = APIRouter()


# ---------------------------------------------------------------------------
# Request schema
# ---------------------------------------------------------------------------


class RechargeTraitRequest(BaseModel):
    """Request body for the recharge-trait action.

    Attributes
    ----------
    trait_instance_id:
        ULID of the Slot record representing the trait to recharge.
    narrative:
        Player-written description of how the trait is recharged.  Must be
        a non-empty string.
    """

    model_config = ConfigDict(from_attributes=True)

    trait_instance_id: str
    narrative: str


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.post(
    "/characters/{character_id}/recharge-trait",
    response_model=CharacterResponse,
    status_code=200,
    summary="Recharge Trait — spend 1 Free Time to restore a trait to full charges",
    description=(
        "Player direct action.  Spends 1 Free Time to set a Core or Role trait's "
        "charges back to 5 (full).  "
        "Only full (PC-level) characters may use this action.  "
        "The owning player may call this endpoint; the GM may call it on behalf of "
        "any character.  "
        "Returns 409 if the trait is already at 5 charges (trait_already_full) or "
        "Free Time is 0 (insufficient_free_time).  "
        "Returns 404 if the character or trait is not found.  "
        "Returns 422 if the target slot does not belong to the character, is "
        "inactive, or is not a core_trait or role_trait."
    ),
)
def recharge_trait(
    character_id: str,
    body: RechargeTraitRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CharacterResponse:
    """Recharge a Core or Role trait to full (5 charges) for a full (PC) character.

    Args:
        character_id: ULID of the target character.
        body: Request body containing ``trait_instance_id`` and ``narrative``.
        current_user: Authenticated user.  Must be the character's owning player
            or the GM.
        db: Injected SQLAlchemy session.

    Returns:
        ``CharacterResponse`` with the character's current state after the action.

    Raises:
        HTTPException(404): If the character does not exist or is deleted.
        HTTPException(403): If the caller is neither the GM nor the
            character's owning player.
        HTTPException(422): If the character is not a full (PC-level) character
            (``not_a_pc``), the narrative is empty (``narrative_required``), the
            trait slot is not found (``trait_not_found``), the slot does not
            belong to the character (``trait_not_owned``), the slot is inactive
            (``trait_not_active``), or the slot type is not ``core_trait`` or
            ``role_trait`` (``not_a_trait``).
        HTTPException(409): If the trait is already at 5 charges
            (``trait_already_full``) or Free Time is 0
            (``insufficient_free_time``).
    """
    # Authorisation — owner or GM (checked before calling the service).
    character: Character | None = db.get(Character, character_id)
    if character is None or character.is_deleted:
        raise_not_found("Character", character_id)

    if current_user.role != "gm" and current_user.character_id != character_id:
        raise_forbidden("You do not have permission to perform this action for this character.")

    return execute_recharge_trait(
        db,
        character_id=character_id,
        slot_id=body.trait_instance_id,
        narrative=body.narrative,
        actor_user=current_user,
    )
