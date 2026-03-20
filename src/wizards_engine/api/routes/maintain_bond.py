"""Route handler for POST /api/v1/characters/{id}/maintain-bond.

Player direct action that spends 1 Free Time to restore a bond's charges to
its effective maximum (5 - degradations).

Endpoint
--------
POST /characters/{id}/maintain-bond  — Owner or GM.  Spend 1 FT to restore
one active PC bond slot to full charges.
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
from wizards_engine.services.player_actions import execute_maintain_bond

router = APIRouter()


# ---------------------------------------------------------------------------
# Request schema
# ---------------------------------------------------------------------------


class MaintainBondRequest(BaseModel):
    """Request body for the maintain-bond action.

    Attributes
    ----------
    bond_instance_id:
        ULID of the Slot record representing the bond to maintain.
    narrative:
        Player-written description of how the bond is maintained.  Must be
        a non-empty string.
    """

    model_config = ConfigDict(from_attributes=True)

    bond_instance_id: str
    narrative: str


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.post(
    "/characters/{character_id}/maintain-bond",
    response_model=CharacterResponse,
    status_code=200,
    summary="Maintain Bond — spend 1 Free Time to restore a bond to its effective maximum charges",
    description=(
        "Player direct action.  Spends 1 Free Time to set a PC bond's charges "
        "back to its effective maximum (5 - degradations).  "
        "Only full (PC-level) characters may use this action.  "
        "The owning player may call this endpoint; the GM may call it on behalf of "
        "any character.  "
        "Returns 409 if the bond is already at effective max charges "
        "(bond_already_maintained) or Free Time is 0 (insufficient_free_time).  "
        "Returns 404 if the character or bond is not found.  "
        "Returns 422 if the target slot does not belong to the character, is "
        "inactive, is not a pc_bond, or is a trauma bond."
    ),
)
def maintain_bond(
    character_id: str,
    body: MaintainBondRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CharacterResponse:
    """Restore a PC bond to its effective maximum charges for a full (PC) character.

    Args:
        character_id: ULID of the target character.
        body: Request body containing ``bond_instance_id`` and ``narrative``.
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
            bond slot is not found (``bond_not_found``), the slot does not
            belong to the character (``bond_not_owned``), the slot is inactive
            (``bond_not_active``), the slot type is not ``pc_bond``
            (``not_a_pc_bond``), or the bond is a trauma bond
            (``cannot_maintain_trauma``).
        HTTPException(409): If the bond is already at effective max charges
            (``bond_already_maintained``) or Free Time is 0
            (``insufficient_free_time``).
    """
    # Authorisation — owner or GM (checked before calling the service).
    character: Character | None = db.get(Character, character_id)
    if character is None or character.is_deleted:
        raise_not_found("Character", character_id)

    if current_user.role != "gm" and current_user.character_id != character_id:
        raise_forbidden("You do not have permission to perform this action for this character.")

    return execute_maintain_bond(
        db,
        character_id=character_id,
        slot_id=body.bond_instance_id,
        narrative=body.narrative,
        actor_user=current_user,
    )
